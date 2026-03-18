"""Unit tests for mexc_v3_client.normalize_deal and its contract with sanitize_market_data.

Goal (Issue #1206 Delta 1):
  Prove that normalize_deal() output is compatible with sanitize_market_data()
  before any runtime integration between mexc_v3_client.py and service.py.

Import strategy:
  mexc_v3_client.py imports websockets and protobuf stubs at module level.
  Neither is installed in the standard test environment.
  We inject sys.modules mocks before the import — this is the standard Python
  technique for testing modules with unavailable dependencies.
  No production code is modified.
"""

import sys
import types
from unittest.mock import MagicMock

import pytest

# ── Inject stubs before importing mexc_v3_client ──────────────────────────────
# Must happen before the first import of the module in this process.
# setdefault() is safe: no-op if the module was already installed/mocked.
sys.modules.setdefault("websockets", MagicMock())
sys.modules.setdefault("websockets.exceptions", MagicMock())
sys.modules.setdefault("PushDataV3ApiWrapper_pb2", MagicMock())
sys.modules.setdefault("PublicAggreDealsV3Api_pb2", MagicMock())

from services.market.mexc_v3_client import normalize_deal  # noqa: E402
from core.utils.redis_payload import sanitize_market_data  # noqa: E402

# ── Required fields by sanitize_market_data ────────────────────────────────────
_REQUIRED = ["source", "symbol", "ts_ms", "price", "trade_qty", "side"]


def _deal(
    price="50000.00",
    quantity="1.5",
    tradetype=1,
    time=1700000000000,
    tradeId="trade-001",
):
    """Build a duck-typed deal object matching the MEXC protobuf field names."""
    return types.SimpleNamespace(
        price=price,
        quantity=quantity,
        tradetype=tradetype,
        time=time,
        tradeId=tradeId,
    )


# ── normalize_deal: side mapping ───────────────────────────────────────────────


@pytest.mark.unit
def test_normalize_deal_tradetype_1_maps_to_buy():
    result = normalize_deal("BTCUSDT", _deal(tradetype=1))
    assert result["side"] == "buy"


@pytest.mark.unit
def test_normalize_deal_tradetype_2_maps_to_sell():
    result = normalize_deal("BTCUSDT", _deal(tradetype=2))
    assert result["side"] == "sell"


@pytest.mark.unit
def test_normalize_deal_tradetype_0_maps_to_unknown():
    result = normalize_deal("BTCUSDT", _deal(tradetype=0))
    assert result["side"] == "unknown"


@pytest.mark.unit
def test_normalize_deal_tradetype_99_maps_to_unknown():
    result = normalize_deal("BTCUSDT", _deal(tradetype=99))
    assert result["side"] == "unknown"


@pytest.mark.unit
def test_normalize_deal_camelcase_tradeType_fallback():
    """normalize_deal reads tradeType (camelCase) if tradetype is absent/zero."""
    deal = types.SimpleNamespace(
        price="50000.00",
        quantity="1.0",
        tradetype=0,
        tradeType=1,  # camelCase fallback
        time=1700000000000,
    )
    result = normalize_deal("BTCUSDT", deal)
    # tradetype=0 OR tradeType=1 → int() of (0 or 1) = 1 → buy
    assert result["side"] == "buy"


# ── normalize_deal: schema fields ─────────────────────────────────────────────


@pytest.mark.unit
def test_normalize_deal_always_sets_schema_version():
    result = normalize_deal("BTCUSDT", _deal())
    assert result["schema_version"] == "v1.0"


@pytest.mark.unit
def test_normalize_deal_always_sets_source_mexc():
    result = normalize_deal("BTCUSDT", _deal())
    assert result["source"] == "mexc"


@pytest.mark.unit
def test_normalize_deal_uses_symbol_parameter():
    result = normalize_deal("ETHUSDT", _deal())
    assert result["symbol"] == "ETHUSDT"


@pytest.mark.unit
def test_normalize_deal_price_is_string():
    result = normalize_deal("BTCUSDT", _deal(price="12345.67"))
    assert isinstance(result["price"], str)
    assert result["price"] == "12345.67"


@pytest.mark.unit
def test_normalize_deal_trade_qty_is_string():
    result = normalize_deal("BTCUSDT", _deal(quantity="2.5"))
    assert isinstance(result["trade_qty"], str)
    assert result["trade_qty"] == "2.5"


@pytest.mark.unit
def test_normalize_deal_ts_ms_from_time_field():
    result = normalize_deal("BTCUSDT", _deal(time=1700000000000))
    assert result["ts_ms"] == 1700000000000
    assert isinstance(result["ts_ms"], int)


# ── normalize_deal: field fallbacks ───────────────────────────────────────────


@pytest.mark.unit
def test_normalize_deal_qty_fallback_when_quantity_empty():
    """When quantity is empty, normalize_deal falls back to qty attribute."""
    deal = types.SimpleNamespace(
        price="100.00",
        quantity="",
        qty="3.0",
        tradetype=1,
        time=1700000000000,
    )
    result = normalize_deal("BTCUSDT", deal)
    assert result["trade_qty"] == "3.0"


@pytest.mark.unit
def test_normalize_deal_ts_fallback_to_ts_attribute():
    """When time is 0 (falsy), normalize_deal falls back to ts attribute."""
    deal = types.SimpleNamespace(
        price="100.00",
        quantity="1.0",
        tradetype=1,
        time=0,
        ts=9999999,
    )
    result = normalize_deal("BTCUSDT", deal)
    assert result["ts_ms"] == 9999999


@pytest.mark.unit
def test_normalize_deal_trade_id_included_when_present():
    result = normalize_deal("BTCUSDT", _deal(tradeId="abc-123"))
    assert result.get("trade_id") == "abc-123"


@pytest.mark.unit
def test_normalize_deal_trade_id_absent_when_not_set():
    deal = types.SimpleNamespace(
        price="100.00",
        quantity="1.0",
        tradetype=1,
        time=1700000000000,
    )
    result = normalize_deal("BTCUSDT", deal)
    assert "trade_id" not in result


# ── normalize_deal: missing / zero fields ─────────────────────────────────────


@pytest.mark.unit
def test_normalize_deal_missing_all_optional_fields_produces_defaults():
    """A deal with no attributes at all yields safe string/int defaults."""
    deal = types.SimpleNamespace()
    result = normalize_deal("BTCUSDT", deal)
    assert result["source"] == "mexc"
    assert result["symbol"] == "BTCUSDT"
    assert isinstance(result["ts_ms"], int)
    assert isinstance(result["price"], str)
    assert isinstance(result["trade_qty"], str)
    assert result["side"] == "unknown"


@pytest.mark.unit
def test_normalize_deal_ts_zero_when_all_time_fields_absent():
    deal = types.SimpleNamespace(price="100.00", quantity="1.0", tradetype=1)
    result = normalize_deal("BTCUSDT", deal)
    assert result["ts_ms"] == 0


# ── Contract: normalize_deal → sanitize_market_data ───────────────────────────


@pytest.mark.unit
def test_contract_valid_deal_passes_sanitize():
    """Full happy-path: normalize_deal output clears sanitize_market_data."""
    event = normalize_deal("BTCUSDT", _deal())
    sanitized = sanitize_market_data(event)
    for field in _REQUIRED:
        assert field in sanitized
    assert sanitized["schema_version"] == "v1.0"
    assert sanitized["source"] == "mexc"
    assert sanitized["symbol"] == "BTCUSDT"


@pytest.mark.unit
def test_contract_sanitize_result_has_correct_types():
    event = normalize_deal("BTCUSDT", _deal())
    sanitized = sanitize_market_data(event)
    assert isinstance(sanitized["ts_ms"], int)
    assert isinstance(sanitized["price"], str)
    assert isinstance(sanitized["trade_qty"], str)


@pytest.mark.unit
def test_contract_ts_zero_passes_sanitize_type_check():
    """ts_ms=0 is semantically stale but structurally valid (int).
    sanitize_market_data only enforces type, not range.
    This test documents the gap explicitly: callers must guard against ts=0."""
    deal = types.SimpleNamespace(price="100.00", quantity="1.0", tradetype=1, time=0)
    event = normalize_deal("BTCUSDT", deal)
    assert event["ts_ms"] == 0
    # Must not raise — type check passes
    sanitized = sanitize_market_data(event)
    assert sanitized["ts_ms"] == 0


@pytest.mark.unit
def test_contract_empty_price_passes_sanitize_type_check():
    """price='' is a str and passes the type check in sanitize_market_data.
    This test documents the gap: callers must guard against empty price strings."""
    deal = types.SimpleNamespace(
        price="", quantity="1.0", tradetype=1, time=1700000000000
    )
    event = normalize_deal("BTCUSDT", deal)
    assert event["price"] == ""
    # Must not raise — "" is a str
    sanitize_market_data(event)


@pytest.mark.unit
def test_contract_missing_required_field_raises_value_error():
    """If a required field is removed after normalization, sanitize raises."""
    event = normalize_deal("BTCUSDT", _deal())
    del event["price"]
    with pytest.raises(ValueError, match="Missing required fields"):
        sanitize_market_data(event)


@pytest.mark.unit
def test_contract_wrong_ts_ms_type_raises_value_error():
    """If ts_ms is a str (not int), sanitize raises."""
    event = normalize_deal("BTCUSDT", _deal())
    event["ts_ms"] = "not-an-int"
    with pytest.raises(ValueError, match="ts_ms must be int"):
        sanitize_market_data(event)


@pytest.mark.unit
def test_contract_multiple_symbols_each_pass():
    for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
        event = normalize_deal(symbol, _deal())
        sanitized = sanitize_market_data(event)
        assert sanitized["symbol"] == symbol
