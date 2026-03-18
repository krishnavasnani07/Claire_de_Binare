#!/usr/bin/env python3
"""Read-only compare + Evidence Gate for market_price (live) vs market_price_v3 (shadow).

Reads both Redis keys, records N samples over a configurable observation window,
computes price/timestamp delta metrics, evaluates explicit gate criteria, and writes
a JSON evidence artefact.

Usage (standalone):
    python -m services.market.tools.v3_compare \\
        --symbol BTCUSDT --samples 20 --interval 5 \\
        --out reports/v3_compare_BTCUSDT.json

Gate thresholds (all have explicit defaults; override via CLI flags):
    --min-comparable-samples      INT    default: 20
    --max-missing-shadow-pct      FLOAT  default: 0.05   (5 %)
    --max-stale-shadow-pct        FLOAT  default: 0.05   (5 %)
    --max-price-delta-rel-p95-pct FLOAT  default: 0.05   (0.05 %)
    --max-price-delta-rel-max-pct FLOAT  default: 0.10   (0.10 %)
    --max-ts-delta-ms-p95         INT    default: 10000  (10 s)

Environment variables (Redis connection):
    REDIS_HOST      hostname   (default: localhost)
    REDIS_PORT      port       (default: 6379)
    REDIS_PASSWORD  password   (default: empty)

Exit codes:
    0 — gate PASS
    1 — gate FAIL, INCONCLUSIVE, or runtime error

Design:
- Pure functions (compare_snapshot, summarize, evaluate_gate, build_report) — no I/O
- collect_samples() accepts an injected redis client → fully mockable in tests
- No writes to any Redis key; live-path is never touched
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ─── Constants ────────────────────────────────────────────────────────────────

SCHEMA_VERSION = "1.1"
LIVE_KEY_PREFIX = "market_price"
SHADOW_KEY_PREFIX = "market_price_v3"

# Keys are stale when their age exceeds the 30 s TTL used by service.py.
STALE_THRESHOLD_MS: int = 30_000  # 30 seconds


# ─── Gate thresholds ──────────────────────────────────────────────────────────


@dataclasses.dataclass
class GateThresholds:
    """Explicit, named gate criteria for V3 shadow promotion readiness.

    All defaults are intentionally conservative and documented below.
    Override via CLI flags or direct instantiation.

    Rationale for defaults (derived from first evidence run 2026-03-18):
      max_missing_shadow_pct       5 % — tolerate brief Redis key eviction / restart lag
      max_stale_shadow_pct         5 % — tolerate at most 1 stale entry per 20 samples
      max_price_delta_rel_p95_pct  0.05 % — first run p95 was ~0 %; 0.05 % ≈ 16x headroom
      max_price_delta_rel_max_pct  0.10 % — first run max was 0.003 %; 0.10 % ≈ 30x headroom
      max_ts_delta_ms_p95          10 000 ms — first run max was 2976 ms; 10 s ≈ 3x headroom
    """

    # Minimum number of comparable samples before a PASS/FAIL decision is made.
    # Below this the gate is INCONCLUSIVE — not enough data to trust the stats.
    min_comparable_samples: int = 20

    # Maximum fraction (0–1) of total samples where the shadow key is absent.
    # Exceeding this is a hard FAIL regardless of sample count.
    max_missing_shadow_pct: float = 0.05

    # Maximum fraction (0–1) of *comparable* samples where shadow entry is stale
    # (age > STALE_THRESHOLD_MS = 30 s).
    max_stale_shadow_pct: float = 0.05

    # Maximum p95 of relative price delta (percent).
    max_price_delta_rel_p95_pct: float = 0.05

    # Hard maximum of relative price delta (percent).
    # A single outlier above this causes an immediate FAIL.
    max_price_delta_rel_max_pct: float = 0.10

    # Maximum p95 of ts_delta_ms (milliseconds).
    max_ts_delta_ms_p95: int = 10_000

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


# ─── Pure computation layer ───────────────────────────────────────────────────


def compare_snapshot(
    live: dict[str, Any] | None,
    shadow: dict[str, Any] | None,
    now_ms: int,
) -> dict[str, Any]:
    """Compare one snapshot of live vs V3 shadow Redis entries.

    Both *live* and *shadow* are already-decoded dicts (or None when the key
    is absent from Redis).  *now_ms* is the epoch-millisecond timestamp of
    the sample, used to compute freshness.

    Returns a flat dict with:
      comparable          — True only when both entries are present and parseable
      live_missing        — True when the live key was absent
      shadow_missing      — True when the shadow key was absent
      price_delta_abs     — |live_price - shadow_price|  (float)
      price_delta_rel_pct — delta / live_price * 100     (float, None when live=0)
      ts_delta_ms         — |live_ts_ms - shadow_ts_ms|  (int)
      live_age_ms         — now_ms - live_ts_ms           (int)
      shadow_age_ms       — now_ms - shadow_ts_ms         (int)
      live_stale          — live_age_ms > STALE_THRESHOLD_MS
      shadow_stale        — shadow_age_ms > STALE_THRESHOLD_MS
    """
    result: dict[str, Any] = {
        "ts_sample_ms": now_ms,
        "live_missing": live is None,
        "shadow_missing": shadow is None,
    }

    if live is None or shadow is None:
        result["comparable"] = False
        return result

    try:
        live_price = float(live["price"])
        shadow_price = float(shadow["price"])
    except (KeyError, ValueError, TypeError) as exc:
        result["comparable"] = False
        result["error"] = f"price parse error: {exc}"
        return result

    price_delta_abs = abs(live_price - shadow_price)
    price_delta_rel_pct: float | None = (
        round(price_delta_abs / live_price * 100, 8) if live_price != 0.0 else None
    )

    live_ts: int | None = live.get("ts_ms")
    shadow_ts: int | None = shadow.get("ts_ms")

    ts_delta_ms: int | None = (
        abs(int(shadow_ts) - int(live_ts))
        if live_ts is not None and shadow_ts is not None
        else None
    )
    live_age_ms: int | None = now_ms - int(live_ts) if live_ts is not None else None
    shadow_age_ms: int | None = (
        now_ms - int(shadow_ts) if shadow_ts is not None else None
    )

    result.update(
        {
            "comparable": True,
            "live_price": live["price"],
            "shadow_price": shadow["price"],
            "price_delta_abs": price_delta_abs,
            "price_delta_rel_pct": price_delta_rel_pct,
            "live_ts_ms": live_ts,
            "shadow_ts_ms": shadow_ts,
            "ts_delta_ms": ts_delta_ms,
            "live_age_ms": live_age_ms,
            "shadow_age_ms": shadow_age_ms,
            "live_stale": (
                live_age_ms > STALE_THRESHOLD_MS if live_age_ms is not None else None
            ),
            "shadow_stale": (
                shadow_age_ms > STALE_THRESHOLD_MS
                if shadow_age_ms is not None
                else None
            ),
        }
    )
    return result


def _numeric_stats(values: list[float]) -> dict[str, float | None]:
    """Return min/max/mean/p95 for a list of floats. Returns None for all when empty."""
    if not values:
        return {"min": None, "max": None, "mean": None, "p95": None}
    sorted_v = sorted(values)
    p95_idx = max(0, int(len(sorted_v) * 0.95) - 1)
    return {
        "min": sorted_v[0],
        "max": sorted_v[-1],
        "mean": sum(values) / len(values),
        "p95": sorted_v[p95_idx],
    }


def summarize(samples: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate sample metrics into a summary dict.

    Counts missing/stale occurrences and computes distribution stats for
    price delta, relative price delta, and ts_ms delta across all
    *comparable* samples.
    """
    comparable = [s for s in samples if s.get("comparable") is True]

    price_deltas = [s["price_delta_abs"] for s in comparable]
    rel_deltas = [
        s["price_delta_rel_pct"]
        for s in comparable
        if s.get("price_delta_rel_pct") is not None
    ]
    ts_deltas = [
        s["ts_delta_ms"] for s in comparable if s.get("ts_delta_ms") is not None
    ]
    live_ages = [
        s["live_age_ms"] for s in comparable if s.get("live_age_ms") is not None
    ]
    shadow_ages = [
        s["shadow_age_ms"] for s in comparable if s.get("shadow_age_ms") is not None
    ]

    return {
        "total_samples": len(samples),
        "comparable_samples": len(comparable),
        "missing_live_count": sum(1 for s in samples if s.get("live_missing")),
        "missing_shadow_count": sum(1 for s in samples if s.get("shadow_missing")),
        "stale_live_count": sum(1 for s in comparable if s.get("live_stale") is True),
        "stale_shadow_count": sum(
            1 for s in comparable if s.get("shadow_stale") is True
        ),
        "price_delta_abs": _numeric_stats(price_deltas),
        "price_delta_rel_pct": _numeric_stats(rel_deltas),
        "ts_delta_ms": _numeric_stats(ts_deltas),
        "live_age_ms": _numeric_stats(live_ages),
        "shadow_age_ms": _numeric_stats(shadow_ages),
    }


# ─── Gate evaluation ──────────────────────────────────────────────────────────


def _chk(
    criterion: str,
    threshold: Any,
    measured: Any,
    result: str,
    note: str = "",
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "criterion": criterion,
        "threshold": threshold,
        "measured": measured,
        "result": result,
    }
    if note:
        entry["note"] = note
    return entry


def evaluate_gate(
    summary: dict[str, Any],
    thresholds: GateThresholds,
) -> dict[str, Any]:
    """Evaluate gate criteria against a completed summary.

    Evaluation order (determines overall status priority):
      1. max_missing_shadow_pct  — FAIL even when comparable count is low
      2. min_comparable_samples  — INCONCLUSIVE when not met (and no FAIL above)
      3. max_stale_shadow_pct    — FAIL  (only when enough comparable data)
      4. max_price_delta_rel_p95_pct  — FAIL
      5. max_price_delta_rel_max_pct  — FAIL
      6. max_ts_delta_ms_p95     — FAIL

    Returns a dict with:
      gate_status   — PASS / FAIL / INCONCLUSIVE
      gate_reason   — human-readable summary
      thresholds    — copy of the applied thresholds (for full transparency)
      checks        — list of individual check records (criterion/threshold/measured/result)
    """
    total = summary["total_samples"]
    comparable = summary["comparable_samples"]
    checks: list[dict[str, Any]] = []

    # ── C1: Missing shadow fraction ───────────────────────────────────────────
    # Evaluated first and unconditionally; a systematically absent shadow key
    # is always a hard FAIL regardless of how many samples we have.
    msf = summary["missing_shadow_count"] / total if total > 0 else 0.0
    c1_pass = msf <= thresholds.max_missing_shadow_pct
    checks.append(
        _chk(
            "max_missing_shadow_pct",
            thresholds.max_missing_shadow_pct,
            round(msf, 6),
            "PASS" if c1_pass else "FAIL",
        )
    )

    # ── C2: Minimum comparable samples ───────────────────────────────────────
    # INCONCLUSIVE (not FAIL) — insufficient data is a data-collection problem,
    # not a correctness problem.
    enough_data = comparable >= thresholds.min_comparable_samples
    checks.append(
        _chk(
            "min_comparable_samples",
            thresholds.min_comparable_samples,
            comparable,
            "PASS" if enough_data else "INCONCLUSIVE",
            note="" if enough_data else "below minimum — stats not reliable",
        )
    )

    if not enough_data:
        # Skip stats-based checks; they're not meaningful with too few samples.
        for crit in (
            "max_stale_shadow_pct",
            "max_price_delta_rel_p95_pct",
            "max_price_delta_rel_max_pct",
            "max_ts_delta_ms_p95",
        ):
            checks.append(
                _chk(crit, None, None, "SKIP", note="insufficient comparable samples")
            )
    else:
        # ── C3: Stale shadow fraction ─────────────────────────────────────────
        ssf = summary["stale_shadow_count"] / comparable
        checks.append(
            _chk(
                "max_stale_shadow_pct",
                thresholds.max_stale_shadow_pct,
                round(ssf, 6),
                "PASS" if ssf <= thresholds.max_stale_shadow_pct else "FAIL",
            )
        )

        # ── C4: Price delta rel p95 ───────────────────────────────────────────
        rel_p95 = summary["price_delta_rel_pct"]["p95"]
        if rel_p95 is None:
            checks.append(
                _chk(
                    "max_price_delta_rel_p95_pct",
                    thresholds.max_price_delta_rel_p95_pct,
                    None,
                    "FAIL",
                    note="p95 unavailable (all live prices zero?)",
                )
            )
        else:
            checks.append(
                _chk(
                    "max_price_delta_rel_p95_pct",
                    thresholds.max_price_delta_rel_p95_pct,
                    round(rel_p95, 8),
                    (
                        "PASS"
                        if rel_p95 <= thresholds.max_price_delta_rel_p95_pct
                        else "FAIL"
                    ),
                )
            )

        # ── C5: Price delta rel max ───────────────────────────────────────────
        rel_max = summary["price_delta_rel_pct"]["max"]
        if rel_max is None:
            checks.append(
                _chk(
                    "max_price_delta_rel_max_pct",
                    thresholds.max_price_delta_rel_max_pct,
                    None,
                    "FAIL",
                    note="max unavailable",
                )
            )
        else:
            checks.append(
                _chk(
                    "max_price_delta_rel_max_pct",
                    thresholds.max_price_delta_rel_max_pct,
                    round(rel_max, 8),
                    (
                        "PASS"
                        if rel_max <= thresholds.max_price_delta_rel_max_pct
                        else "FAIL"
                    ),
                )
            )

        # ── C6: ts_delta p95 ─────────────────────────────────────────────────
        ts_p95 = summary["ts_delta_ms"]["p95"]
        if ts_p95 is None:
            checks.append(
                _chk(
                    "max_ts_delta_ms_p95",
                    thresholds.max_ts_delta_ms_p95,
                    None,
                    "FAIL",
                    note="p95 unavailable",
                )
            )
        else:
            checks.append(
                _chk(
                    "max_ts_delta_ms_p95",
                    thresholds.max_ts_delta_ms_p95,
                    round(ts_p95, 1),
                    "PASS" if ts_p95 <= thresholds.max_ts_delta_ms_p95 else "FAIL",
                )
            )

    # ── Determine overall gate status ─────────────────────────────────────────
    results = {c["result"] for c in checks}
    if "FAIL" in results:
        failed_criteria = [c["criterion"] for c in checks if c["result"] == "FAIL"]
        gate_status = "FAIL"
        gate_reason = f"{len(failed_criteria)} criterion failed: {failed_criteria}"
    elif "INCONCLUSIVE" in results:
        gate_status = "INCONCLUSIVE"
        gate_reason = (
            f"insufficient data: "
            f"{comparable}/{thresholds.min_comparable_samples} comparable samples"
        )
    else:
        passed = sum(1 for c in checks if c["result"] == "PASS")
        gate_status = "PASS"
        gate_reason = f"all {passed} criteria satisfied"

    return {
        "gate_status": gate_status,
        "gate_reason": gate_reason,
        "thresholds": thresholds.to_dict(),
        "checks": checks,
    }


def build_report(
    symbol: str,
    samples: list[dict[str, Any]],
    summary: dict[str, Any],
    generated_at: str,
    thresholds: GateThresholds | None = None,
) -> dict[str, Any]:
    """Wrap samples + summary + gate result into the canonical JSON evidence structure.

    *thresholds* defaults to GateThresholds() (all conservative defaults) when None.
    The gate result is the authoritative source of the ``overall`` status.
    """
    t = thresholds if thresholds is not None else GateThresholds()
    gate = evaluate_gate(summary, t)

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "symbol": symbol,
        "live_key_prefix": LIVE_KEY_PREFIX,
        "shadow_key_prefix": SHADOW_KEY_PREFIX,
        "stale_threshold_ms": STALE_THRESHOLD_MS,
        "overall": gate["gate_status"],
        "overall_reason": gate["gate_reason"],
        "gate": gate,
        "summary": summary,
        "samples": samples,
    }


# ─── Redis-dependent collection layer ─────────────────────────────────────────


def collect_samples(
    redis_client: Any,
    symbol: str,
    n: int,
    interval_s: float,
) -> list[dict[str, Any]]:
    """Collect *n* comparison snapshots at *interval_s* second intervals.

    *redis_client* must expose a `.get(key) -> bytes | None` interface.
    Never writes to Redis.
    """
    live_key = f"{LIVE_KEY_PREFIX}:{symbol}"
    shadow_key = f"{SHADOW_KEY_PREFIX}:{symbol}"
    samples: list[dict[str, Any]] = []

    for i in range(n):
        now_ms = int(time.time() * 1000)
        live_raw = redis_client.get(live_key)
        shadow_raw = redis_client.get(shadow_key)

        try:
            live = json.loads(live_raw) if live_raw is not None else None
        except (json.JSONDecodeError, TypeError):
            live = None

        try:
            shadow = json.loads(shadow_raw) if shadow_raw is not None else None
        except (json.JSONDecodeError, TypeError):
            shadow = None

        samples.append(compare_snapshot(live, shadow, now_ms))

        if i < n - 1:
            time.sleep(interval_s)

    return samples


# ─── CLI entry point ──────────────────────────────────────────────────────────


def _connect_redis() -> Any:
    import redis as redis_lib  # noqa: F401 — only imported when running as CLI

    host = os.getenv("REDIS_HOST", "localhost")
    port = int(os.getenv("REDIS_PORT", "6379"))
    password = os.getenv("REDIS_PASSWORD") or None
    client = redis_lib.Redis(
        host=host, port=port, password=password, decode_responses=True
    )
    client.ping()
    return client


def _print_gate_summary(gate: dict[str, Any]) -> None:
    """Print a human-readable gate summary to stderr."""
    status = gate["gate_status"]
    print(f"\n[v3_compare] Gate verdict: {status}", file=sys.stderr)
    print(f"             Reason     : {gate['gate_reason']}", file=sys.stderr)
    print("[v3_compare] Checks:", file=sys.stderr)
    for c in gate["checks"]:
        result = c["result"]
        crit = c["criterion"]
        thresh = c.get("threshold")
        measured = c.get("measured")
        note = c.get("note", "")
        suffix = f"  ({note})" if note else ""
        print(
            f"  {'✓' if result == 'PASS' else '✗' if result == 'FAIL' else '~'}"
            f"  {crit:<35} threshold={thresh}  measured={measured}  → {result}{suffix}",
            file=sys.stderr,
        )


def main() -> None:
    defaults = GateThresholds()
    parser = argparse.ArgumentParser(
        description="Read-only compare + Evidence Gate: market_price vs market_price_v3"
    )
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--out", type=str, default=None)

    # Gate threshold overrides — all documented with their defaults
    g = parser.add_argument_group(
        "gate thresholds",
        "Override defaults; all values are documented in GateThresholds",
    )
    g.add_argument(
        "--min-comparable-samples",
        type=int,
        default=defaults.min_comparable_samples,
        metavar="N",
    )
    g.add_argument(
        "--max-missing-shadow-pct",
        type=float,
        default=defaults.max_missing_shadow_pct,
        metavar="F",
    )
    g.add_argument(
        "--max-stale-shadow-pct",
        type=float,
        default=defaults.max_stale_shadow_pct,
        metavar="F",
    )
    g.add_argument(
        "--max-price-delta-rel-p95-pct",
        type=float,
        default=defaults.max_price_delta_rel_p95_pct,
        metavar="F",
    )
    g.add_argument(
        "--max-price-delta-rel-max-pct",
        type=float,
        default=defaults.max_price_delta_rel_max_pct,
        metavar="F",
    )
    g.add_argument(
        "--max-ts-delta-ms-p95",
        type=int,
        default=defaults.max_ts_delta_ms_p95,
        metavar="MS",
    )
    args = parser.parse_args()

    thresholds = GateThresholds(
        min_comparable_samples=args.min_comparable_samples,
        max_missing_shadow_pct=args.max_missing_shadow_pct,
        max_stale_shadow_pct=args.max_stale_shadow_pct,
        max_price_delta_rel_p95_pct=args.max_price_delta_rel_p95_pct,
        max_price_delta_rel_max_pct=args.max_price_delta_rel_max_pct,
        max_ts_delta_ms_p95=args.max_ts_delta_ms_p95,
    )

    try:
        r = _connect_redis()
    except Exception as exc:  # noqa: BLE001
        print(f"[v3_compare] Redis connection failed: {exc}", file=sys.stderr)
        sys.exit(1)

    print(
        f"[v3_compare] Collecting {args.samples} samples for {args.symbol} "
        f"(interval={args.interval}s) …",
        file=sys.stderr,
    )
    samples = collect_samples(r, args.symbol, args.samples, args.interval)

    now_iso = datetime.now(tz=timezone.utc).isoformat()
    summary = summarize(samples)
    report = build_report(args.symbol, samples, summary, now_iso, thresholds)

    report_json = json.dumps(report, indent=2)
    print(report_json)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report_json, encoding="utf-8")
        print(f"[v3_compare] Report written to {out_path}", file=sys.stderr)

    _print_gate_summary(report["gate"])

    if report["overall"] != "PASS":
        sys.exit(1)


if __name__ == "__main__":
    main()
