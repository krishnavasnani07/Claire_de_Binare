#!/usr/bin/env python3
"""Read-only compare tool: market_price:{symbol} (live) vs market_price_v3:{symbol} (V3 shadow).

Reads both Redis keys, records N samples over a configurable observation window,
computes price/timestamp delta metrics, and writes a JSON evidence artefact.

Usage (standalone):
    python -m services.market.tools.v3_compare \\
        --symbol BTCUSDT --samples 10 --interval 5 \\
        --out reports/v3_compare_BTCUSDT.json

Environment variables (same as service.py):
    REDIS_HOST      Redis hostname (default: localhost)
    REDIS_PORT      Redis port    (default: 6379)
    REDIS_PASSWORD  Redis password (default: empty)

Design:
- Pure functions (compare_snapshot, summarize, build_report) — fully testable without Redis
- collect_samples() accepts an injected redis client → mockable in tests
- No writes to any key, no changes to live path
- Fail-closed on missing keys (flagged, not skipped silently)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ─── Constants ────────────────────────────────────────────────────────────────

SCHEMA_VERSION = "1.0"
LIVE_KEY_PREFIX = "market_price"
SHADOW_KEY_PREFIX = "market_price_v3"

# A key is stale when its age exceeds the TTL used by service.py (30 s).
# Freshness threshold is intentionally set to the same TTL value so that
# any entry approaching expiry is flagged in the report.
STALE_THRESHOLD_MS: int = 30_000  # 30 seconds


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
      comparable       — True only when both entries are present and numeric-parseable
      live_missing     — True when the live key was absent
      shadow_missing   — True when the shadow key was absent
      price_delta_abs  — |live_price - shadow_price|  (float)
      price_delta_rel_pct — delta / live_price * 100   (float, None when live=0)
      ts_delta_ms      — |live_ts_ms - shadow_ts_ms|   (int)
      live_age_ms      — now_ms - live_ts_ms            (int)
      shadow_age_ms    — now_ms - shadow_ts_ms          (int)
      live_stale       — live_age_ms > STALE_THRESHOLD_MS
      shadow_stale     — shadow_age_ms > STALE_THRESHOLD_MS
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


def build_report(
    symbol: str,
    samples: list[dict[str, Any]],
    summary: dict[str, Any],
    generated_at: str,
) -> dict[str, Any]:
    """Wrap samples + summary into the canonical JSON evidence structure."""
    overall = "PASS"
    if summary["missing_shadow_count"] == summary["total_samples"]:
        overall = "FAIL"
        overall_reason = "shadow key absent for all samples"
    elif summary["missing_live_count"] == summary["total_samples"]:
        overall = "FAIL"
        overall_reason = "live key absent for all samples"
    elif summary["comparable_samples"] == 0:
        overall = "INCONCLUSIVE"
        overall_reason = "no comparable samples"
    else:
        overall_reason = f"{summary['comparable_samples']}/{summary['total_samples']} samples comparable"

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "symbol": symbol,
        "live_key_prefix": LIVE_KEY_PREFIX,
        "shadow_key_prefix": SHADOW_KEY_PREFIX,
        "stale_threshold_ms": STALE_THRESHOLD_MS,
        "overall": overall,
        "overall_reason": overall_reason,
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only compare: market_price vs market_price_v3"
    )
    parser.add_argument("--symbol", default="BTCUSDT", help="Symbol to compare")
    parser.add_argument(
        "--samples", type=int, default=10, help="Number of snapshots to collect"
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=5.0,
        help="Seconds between snapshots",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=None,
        help="Output JSON file path (default: stdout only)",
    )
    args = parser.parse_args()

    try:
        r = _connect_redis()
    except Exception as exc:  # noqa: BLE001
        print(f"[v3_compare] Redis connection failed: {exc}", file=sys.stderr)
        sys.exit(1)

    print(
        f"[v3_compare] Collecting {args.samples} samples for {args.symbol} "
        f"(interval={args.interval}s) …"
    )
    samples = collect_samples(r, args.symbol, args.samples, args.interval)

    now_iso = datetime.now(tz=timezone.utc).isoformat()
    summary = summarize(samples)
    report = build_report(args.symbol, samples, summary, now_iso)

    report_json = json.dumps(report, indent=2)
    print(report_json)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report_json, encoding="utf-8")
        print(f"[v3_compare] Report written to {out_path}", file=sys.stderr)

    # Exit 1 when no comparable samples (e.g. shadow key never appeared)
    if summary["comparable_samples"] == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
