"""Unit tests for CandleService._lookup_regime_id - regime string to ID mapping."""

import os
import time
import pytest
from unittest.mock import MagicMock

# Set required env var before importing service
os.environ.setdefault("CANDLE_INTERVAL_SECONDS", "60")

from services.candles.service import CandleService


def _make_service_with_mock_redis(xrevrange_return):
    """Create CandleService with mocked Redis returning given xrevrange data."""
    service = CandleService()
    service.redis_client = MagicMock()
    service.redis_client.xrevrange.return_value = xrevrange_return
    return service


@pytest.mark.unit
def test_regime_mapping_trend():
    """TREND → regime_id=0"""
    now_s = int(time.time())
    entries = [("1-0", {"symbol": "BTCUSDT", "regime": "TREND", "ts": str(now_s - 10)})]
    service = _make_service_with_mock_redis(entries)
    assert service._lookup_regime_id("BTCUSDT") == 0


@pytest.mark.unit
def test_regime_mapping_range():
    """RANGE → regime_id=1"""
    now_s = int(time.time())
    entries = [("1-0", {"symbol": "BTCUSDT", "regime": "RANGE", "ts": str(now_s - 10)})]
    service = _make_service_with_mock_redis(entries)
    assert service._lookup_regime_id("BTCUSDT") == 1


@pytest.mark.unit
def test_regime_mapping_high_vol_chaotic():
    """HIGH_VOL_CHAOTIC → regime_id=2"""
    now_s = int(time.time())
    entries = [("1-0", {"symbol": "BTCUSDT", "regime": "HIGH_VOL_CHAOTIC", "ts": str(now_s - 10)})]
    service = _make_service_with_mock_redis(entries)
    assert service._lookup_regime_id("BTCUSDT") == 2


@pytest.mark.unit
def test_regime_mapping_high_vol_any_suffix():
    """HIGH_VOL_* (any suffix via startswith) → regime_id=2"""
    now_s = int(time.time())
    entries = [("1-0", {"symbol": "BTCUSDT", "regime": "HIGH_VOL_WHATEVER", "ts": str(now_s - 10)})]
    service = _make_service_with_mock_redis(entries)
    assert service._lookup_regime_id("BTCUSDT") == 2


@pytest.mark.unit
def test_regime_mapping_crisis():
    """CRISIS → regime_id=3"""
    now_s = int(time.time())
    entries = [("1-0", {"symbol": "BTCUSDT", "regime": "CRISIS", "ts": str(now_s - 10)})]
    service = _make_service_with_mock_redis(entries)
    assert service._lookup_regime_id("BTCUSDT") == 3


@pytest.mark.unit
def test_regime_unknown_returns_none():
    """UNKNOWN regime string → None (fail-closed)"""
    now_s = int(time.time())
    entries = [("1-0", {"symbol": "BTCUSDT", "regime": "UNKNOWN", "ts": str(now_s - 10)})]
    service = _make_service_with_mock_redis(entries)
    assert service._lookup_regime_id("BTCUSDT") is None


@pytest.mark.unit
def test_regime_empty_string_returns_none():
    """Empty regime string → None (fail-closed)"""
    now_s = int(time.time())
    entries = [("1-0", {"symbol": "BTCUSDT", "regime": "", "ts": str(now_s - 10)})]
    service = _make_service_with_mock_redis(entries)
    assert service._lookup_regime_id("BTCUSDT") is None


@pytest.mark.unit
def test_regime_not_found_returns_none():
    """No regime signal for symbol → None (fail-closed)"""
    now_s = int(time.time())
    entries = [("1-0", {"symbol": "ETHUSDT", "regime": "TREND", "ts": str(now_s - 10)})]
    service = _make_service_with_mock_redis(entries)
    assert service._lookup_regime_id("BTCUSDT") is None


@pytest.mark.unit
def test_regime_empty_stream_returns_none():
    """Empty stream → None (fail-closed)"""
    service = _make_service_with_mock_redis([])
    assert service._lookup_regime_id("BTCUSDT") is None


@pytest.mark.unit
def test_regime_stale_returns_none():
    """Regime signal older than staleness threshold → None (fail-closed)"""
    now_s = int(time.time())
    entries = [("1-0", {"symbol": "BTCUSDT", "regime": "TREND", "ts": str(now_s - 10)})]
    service = _make_service_with_mock_redis(entries)
    original_staleness = service.config.regime_staleness_seconds
    try:
        service.config.regime_staleness_seconds = 5  # 10s old > 5s threshold
        assert service._lookup_regime_id("BTCUSDT") is None
    finally:
        service.config.regime_staleness_seconds = original_staleness


@pytest.mark.unit
def test_regime_ts_missing_returns_none():
    """Missing ts field → None (fail-closed)"""
    entries = [("1-0", {"symbol": "BTCUSDT", "regime": "TREND"})]
    service = _make_service_with_mock_redis(entries)
    assert service._lookup_regime_id("BTCUSDT") is None


@pytest.mark.unit
def test_regime_ts_invalid_returns_none():
    """Non-numeric ts field → None (fail-closed)"""
    entries = [("1-0", {"symbol": "BTCUSDT", "regime": "TREND", "ts": "invalid"})]
    service = _make_service_with_mock_redis(entries)
    assert service._lookup_regime_id("BTCUSDT") is None


@pytest.mark.unit
def test_regime_ts_milliseconds_returns_none():
    """ts in milliseconds (too large) → None (fail-closed)"""
    now_ms = int(time.time() * 1000)
    entries = [("1-0", {"symbol": "BTCUSDT", "regime": "TREND", "ts": str(now_ms)})]
    service = _make_service_with_mock_redis(entries)
    assert service._lookup_regime_id("BTCUSDT") is None


@pytest.mark.unit
def test_regime_ts_in_future_returns_none():
    """ts in future → None (fail-closed)"""
    future_s = int(time.time()) + 100
    entries = [("1-0", {"symbol": "BTCUSDT", "regime": "TREND", "ts": str(future_s)})]
    service = _make_service_with_mock_redis(entries)
    assert service._lookup_regime_id("BTCUSDT") is None


@pytest.mark.unit
def test_regime_case_insensitive():
    """Regime mapping should be case-insensitive"""
    now_s = int(time.time())
    entries = [("1-0", {"symbol": "BTCUSDT", "regime": "trend", "ts": str(now_s - 10)})]
    service = _make_service_with_mock_redis(entries)
    assert service._lookup_regime_id("BTCUSDT") == 0


@pytest.mark.unit
def test_regime_selects_correct_symbol_btc():
    """Should return regime for BTCUSDT from multiple entries"""
    now_s = int(time.time())
    entries = [
        ("3-0", {"symbol": "ETHUSDT", "regime": "CRISIS", "ts": str(now_s - 5)}),
        ("2-0", {"symbol": "BTCUSDT", "regime": "TREND", "ts": str(now_s - 10)}),
        ("1-0", {"symbol": "BTCUSDT", "regime": "RANGE", "ts": str(now_s - 20)}),
    ]
    service = _make_service_with_mock_redis(entries)
    # Should find first BTCUSDT entry (TREND)
    assert service._lookup_regime_id("BTCUSDT") == 0


@pytest.mark.unit
def test_regime_selects_correct_symbol_eth():
    """Should return regime for ETHUSDT from multiple entries"""
    now_s = int(time.time())
    entries = [
        ("3-0", {"symbol": "ETHUSDT", "regime": "CRISIS", "ts": str(now_s - 5)}),
        ("2-0", {"symbol": "BTCUSDT", "regime": "TREND", "ts": str(now_s - 10)}),
    ]
    service = _make_service_with_mock_redis(entries)
    assert service._lookup_regime_id("ETHUSDT") == 3
