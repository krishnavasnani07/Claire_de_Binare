"""Unit tests for services/market/tools/v3_compare.py (Issue #1206 shadow compare)."""

import json
from unittest.mock import MagicMock, patch

import pytest

from services.market.tools.v3_compare import (
    STALE_THRESHOLD_MS,
    build_report,
    collect_samples,
    compare_snapshot,
    summarize,
)

# ─── Fixtures ─────────────────────────────────────────────────────────────────

_NOW_MS = 1_700_000_030_000  # arbitrary reference epoch-ms


def _live(price: str = "50000.00", ts_ms: int = 1_700_000_000_000) -> dict:
    return {
        "symbol": "BTCUSDT",
        "price": price,
        "ts_ms": ts_ms,
        "source": "mexc",
        "trade_qty": "0.001",
        "side": "BUY",
        "cached_at_ms": ts_ms + 1,
    }


def _shadow(price: str = "50000.00", ts_ms: int = 1_700_000_001_000) -> dict:
    return {
        "symbol": "BTCUSDT",
        "price": price,
        "ts_ms": ts_ms,
        "source": "mexc",
        "trade_qty": "0.001",
        "side": "buy",
        "cached_at_ms": ts_ms + 2,
    }


# ─── compare_snapshot: happy path ─────────────────────────────────────────────


@pytest.mark.unit
def test_compare_snapshot_comparable_true_when_both_present():
    snap = compare_snapshot(_live(), _shadow(), _NOW_MS)
    assert snap["comparable"] is True


@pytest.mark.unit
def test_compare_snapshot_price_delta_abs_identical_prices():
    snap = compare_snapshot(_live("50000.00"), _shadow("50000.00"), _NOW_MS)
    assert snap["price_delta_abs"] == pytest.approx(0.0)


@pytest.mark.unit
def test_compare_snapshot_price_delta_abs_different_prices():
    snap = compare_snapshot(_live("50000.00"), _shadow("50010.00"), _NOW_MS)
    assert snap["price_delta_abs"] == pytest.approx(10.0)


@pytest.mark.unit
def test_compare_snapshot_price_delta_rel_pct_correct():
    # 10 / 50000 * 100 = 0.02 %
    snap = compare_snapshot(_live("50000.00"), _shadow("50010.00"), _NOW_MS)
    assert snap["price_delta_rel_pct"] == pytest.approx(0.02, rel=1e-4)


@pytest.mark.unit
def test_compare_snapshot_ts_delta_ms_correct():
    snap = compare_snapshot(
        _live(ts_ms=1_700_000_000_000),
        _shadow(ts_ms=1_700_000_001_500),
        _NOW_MS,
    )
    assert snap["ts_delta_ms"] == 1500


@pytest.mark.unit
def test_compare_snapshot_live_age_ms_correct():
    snap = compare_snapshot(
        _live(ts_ms=_NOW_MS - 5_000),
        _shadow(ts_ms=_NOW_MS - 3_000),
        _NOW_MS,
    )
    assert snap["live_age_ms"] == 5_000
    assert snap["shadow_age_ms"] == 3_000


@pytest.mark.unit
def test_compare_snapshot_prices_are_preserved_as_strings():
    snap = compare_snapshot(_live("49999.99"), _shadow("50000.01"), _NOW_MS)
    assert snap["live_price"] == "49999.99"
    assert snap["shadow_price"] == "50000.01"


@pytest.mark.unit
def test_compare_snapshot_ts_sample_ms_set_correctly():
    snap = compare_snapshot(_live(), _shadow(), _NOW_MS)
    assert snap["ts_sample_ms"] == _NOW_MS


# ─── compare_snapshot: missing keys ───────────────────────────────────────────


@pytest.mark.unit
def test_compare_snapshot_live_missing_sets_flag():
    snap = compare_snapshot(None, _shadow(), _NOW_MS)
    assert snap["live_missing"] is True
    assert snap["comparable"] is False


@pytest.mark.unit
def test_compare_snapshot_shadow_missing_sets_flag():
    snap = compare_snapshot(_live(), None, _NOW_MS)
    assert snap["shadow_missing"] is True
    assert snap["comparable"] is False


@pytest.mark.unit
def test_compare_snapshot_both_missing():
    snap = compare_snapshot(None, None, _NOW_MS)
    assert snap["live_missing"] is True
    assert snap["shadow_missing"] is True
    assert snap["comparable"] is False


# ─── compare_snapshot: stale detection ────────────────────────────────────────


@pytest.mark.unit
def test_compare_snapshot_live_stale_when_age_exceeds_threshold():
    old_ts = _NOW_MS - STALE_THRESHOLD_MS - 1
    snap = compare_snapshot(
        _live(ts_ms=old_ts), _shadow(ts_ms=_NOW_MS - 1_000), _NOW_MS
    )
    assert snap["live_stale"] is True
    assert snap["shadow_stale"] is False


@pytest.mark.unit
def test_compare_snapshot_shadow_stale_when_age_exceeds_threshold():
    old_ts = _NOW_MS - STALE_THRESHOLD_MS - 1
    snap = compare_snapshot(
        _live(ts_ms=_NOW_MS - 1_000), _shadow(ts_ms=old_ts), _NOW_MS
    )
    assert snap["shadow_stale"] is True
    assert snap["live_stale"] is False


@pytest.mark.unit
def test_compare_snapshot_not_stale_when_fresh():
    fresh_ts = _NOW_MS - 1_000  # 1 second old
    snap = compare_snapshot(_live(ts_ms=fresh_ts), _shadow(ts_ms=fresh_ts), _NOW_MS)
    assert snap["live_stale"] is False
    assert snap["shadow_stale"] is False


# ─── compare_snapshot: invalid payloads ───────────────────────────────────────


@pytest.mark.unit
def test_compare_snapshot_non_numeric_price_sets_comparable_false():
    bad_live = _live()
    bad_live["price"] = "not-a-number"
    snap = compare_snapshot(bad_live, _shadow(), _NOW_MS)
    assert snap["comparable"] is False
    assert "error" in snap


@pytest.mark.unit
def test_compare_snapshot_missing_price_key_sets_comparable_false():
    bad = _live()
    del bad["price"]
    snap = compare_snapshot(bad, _shadow(), _NOW_MS)
    assert snap["comparable"] is False


@pytest.mark.unit
def test_compare_snapshot_live_price_zero_sets_rel_pct_none():
    snap = compare_snapshot(_live("0.00"), _shadow("0.01"), _NOW_MS)
    # live_price=0 → can't compute relative delta
    assert snap["price_delta_rel_pct"] is None


# ─── summarize ────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_summarize_empty_samples_returns_none_stats():
    s = summarize([])
    assert s["total_samples"] == 0
    assert s["comparable_samples"] == 0
    assert s["price_delta_abs"]["min"] is None
    assert s["price_delta_abs"]["mean"] is None


@pytest.mark.unit
def test_summarize_counts_missing_live_and_shadow():
    samples = [
        compare_snapshot(None, _shadow(), _NOW_MS),
        compare_snapshot(_live(), None, _NOW_MS),
        compare_snapshot(None, None, _NOW_MS),
    ]
    s = summarize(samples)
    assert s["missing_live_count"] == 2  # sample 0 and 2
    assert s["missing_shadow_count"] == 2  # sample 1 and 2
    assert s["comparable_samples"] == 0


@pytest.mark.unit
def test_summarize_correct_stats_for_comparable_samples():
    deltas = [10.0, 20.0, 30.0]
    samples = [
        compare_snapshot(_live("50000.00"), _shadow(str(50000.0 + d)), _NOW_MS)
        for d in deltas
    ]
    s = summarize(samples)
    assert s["comparable_samples"] == 3
    assert s["price_delta_abs"]["min"] == pytest.approx(10.0)
    assert s["price_delta_abs"]["max"] == pytest.approx(30.0)
    assert s["price_delta_abs"]["mean"] == pytest.approx(20.0)


@pytest.mark.unit
def test_summarize_counts_stale_correctly():
    old_ts = _NOW_MS - STALE_THRESHOLD_MS - 1
    fresh_ts = _NOW_MS - 1_000
    samples = [
        compare_snapshot(_live(ts_ms=old_ts), _shadow(ts_ms=fresh_ts), _NOW_MS),
        compare_snapshot(_live(ts_ms=fresh_ts), _shadow(ts_ms=old_ts), _NOW_MS),
        compare_snapshot(_live(ts_ms=fresh_ts), _shadow(ts_ms=fresh_ts), _NOW_MS),
    ]
    s = summarize(samples)
    assert s["stale_live_count"] == 1
    assert s["stale_shadow_count"] == 1


@pytest.mark.unit
def test_summarize_p95_is_highest_when_single_sample():
    samples = [compare_snapshot(_live("50000.00"), _shadow("50010.00"), _NOW_MS)]
    s = summarize(samples)
    # single value: p95 == that value
    assert s["price_delta_abs"]["p95"] == pytest.approx(10.0)


# ─── build_report ─────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_build_report_schema_version_and_symbol():
    samples = [compare_snapshot(_live(), _shadow(), _NOW_MS)]
    summary = summarize(samples)
    report = build_report("BTCUSDT", samples, summary, "2026-03-18T00:00:00+00:00")
    assert report["schema_version"] == "1.0"
    assert report["symbol"] == "BTCUSDT"


@pytest.mark.unit
def test_build_report_overall_pass_when_comparable():
    samples = [compare_snapshot(_live(), _shadow(), _NOW_MS)]
    summary = summarize(samples)
    report = build_report("BTCUSDT", samples, summary, "2026-03-18T00:00:00+00:00")
    assert report["overall"] == "PASS"


@pytest.mark.unit
def test_build_report_overall_fail_when_all_shadow_missing():
    samples = [compare_snapshot(_live(), None, _NOW_MS)] * 3
    summary = summarize(samples)
    report = build_report("BTCUSDT", samples, summary, "2026-03-18T00:00:00+00:00")
    assert report["overall"] == "FAIL"
    assert "shadow key absent" in report["overall_reason"]


@pytest.mark.unit
def test_build_report_overall_fail_when_all_live_missing():
    samples = [compare_snapshot(None, _shadow(), _NOW_MS)] * 3
    summary = summarize(samples)
    report = build_report("BTCUSDT", samples, summary, "2026-03-18T00:00:00+00:00")
    assert report["overall"] == "FAIL"
    assert "live key absent" in report["overall_reason"]


@pytest.mark.unit
def test_build_report_overall_inconclusive_when_no_comparable():
    # One live missing, one shadow missing → 0 comparable
    samples = [
        compare_snapshot(None, _shadow(), _NOW_MS),
        compare_snapshot(_live(), None, _NOW_MS),
    ]
    summary = summarize(samples)
    report = build_report("BTCUSDT", samples, summary, "2026-03-18T00:00:00+00:00")
    assert report["overall"] == "INCONCLUSIVE"


@pytest.mark.unit
def test_build_report_contains_samples_list():
    samples = [compare_snapshot(_live(), _shadow(), _NOW_MS)]
    summary = summarize(samples)
    report = build_report("BTCUSDT", samples, summary, "2026-03-18T00:00:00+00:00")
    assert len(report["samples"]) == 1
    assert report["samples"][0]["ts_sample_ms"] == _NOW_MS


@pytest.mark.unit
def test_build_report_is_json_serializable():
    samples = [compare_snapshot(_live(), _shadow(), _NOW_MS)]
    summary = summarize(samples)
    report = build_report("BTCUSDT", samples, summary, "2026-03-18T00:00:00+00:00")
    # Must not raise
    json.dumps(report)


# ─── collect_samples ──────────────────────────────────────────────────────────


@pytest.mark.unit
def test_collect_samples_reads_both_keys():
    mock_redis = MagicMock()
    mock_redis.get.side_effect = lambda key: (
        json.dumps(_live()).encode()
        if key.startswith("market_price:")
        else (
            json.dumps(_shadow()).encode()
            if key.startswith("market_price_v3:")
            else None
        )
    )
    with patch("services.market.tools.v3_compare.time.sleep"):
        samples = collect_samples(mock_redis, "BTCUSDT", 3, 1.0)

    assert len(samples) == 3
    assert all(s["comparable"] for s in samples)


@pytest.mark.unit
def test_collect_samples_handles_missing_live_key():
    mock_redis = MagicMock()
    mock_redis.get.side_effect = lambda key: (
        None if key.startswith("market_price:") else json.dumps(_shadow()).encode()
    )
    with patch("services.market.tools.v3_compare.time.sleep"):
        samples = collect_samples(mock_redis, "BTCUSDT", 2, 1.0)

    assert all(s["live_missing"] for s in samples)
    assert all(not s["comparable"] for s in samples)


@pytest.mark.unit
def test_collect_samples_handles_corrupt_json():
    mock_redis = MagicMock()
    mock_redis.get.return_value = b"not-valid-json{"
    with patch("services.market.tools.v3_compare.time.sleep"):
        samples = collect_samples(mock_redis, "BTCUSDT", 1, 1.0)

    # Both keys corrupt → both missing → not comparable
    assert samples[0]["comparable"] is False


@pytest.mark.unit
def test_collect_samples_sleep_called_between_samples():
    mock_redis = MagicMock()
    mock_redis.get.return_value = json.dumps(_live()).encode()
    with patch("services.market.tools.v3_compare.time.sleep") as mock_sleep:
        collect_samples(mock_redis, "BTCUSDT", 3, 2.5)

    # sleep called n-1 times
    assert mock_sleep.call_count == 2
    mock_sleep.assert_called_with(2.5)


@pytest.mark.unit
def test_collect_samples_no_sleep_for_single_sample():
    mock_redis = MagicMock()
    mock_redis.get.return_value = json.dumps(_live()).encode()
    with patch("services.market.tools.v3_compare.time.sleep") as mock_sleep:
        collect_samples(mock_redis, "BTCUSDT", 1, 5.0)

    mock_sleep.assert_not_called()
