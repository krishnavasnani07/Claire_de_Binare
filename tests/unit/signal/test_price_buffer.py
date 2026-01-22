"""
Unit-Tests für PriceBuffer (Issue #345)

Tests stateful pct_change calculation for raw trade data from cdb_ws.
"""

import pytest
import sys
from pathlib import Path

# Add services to path for imports
services_path = Path(__file__).parent.parent.parent.parent / "services" / "signal"
if str(services_path) not in sys.path:
    sys.path.insert(0, str(services_path))

from price_buffer import PriceBuffer


@pytest.mark.unit
def test_price_buffer_initialization():
    """Test: PriceBuffer can be initialized with default settings."""
    buffer = PriceBuffer()
    assert buffer is not None
    assert len(buffer) == 0
    assert buffer.get_tracked_symbols() == []


@pytest.mark.unit
def test_cold_start_first_price():
    """Test: First price for symbol returns pct_change = 0.0 (cold start)."""
    buffer = PriceBuffer()

    pct_change = buffer.calculate_pct_change("BTCUSDT", 50000.0)

    assert pct_change == 0.0
    assert buffer.get_last_price("BTCUSDT") == 50000.0
    assert len(buffer) == 1
    assert "BTCUSDT" in buffer.get_tracked_symbols()


@pytest.mark.unit
def test_pct_change_calculation_positive():
    """Test: Positive price movement calculates correct pct_change."""
    buffer = PriceBuffer()

    # First price: cold start
    pct_change_1 = buffer.calculate_pct_change("BTCUSDT", 50000.0)
    assert pct_change_1 == 0.0

    # Second price: +2% increase
    # Formula: (51000 - 50000) / 50000 * 100 = 2.0%
    pct_change_2 = buffer.calculate_pct_change("BTCUSDT", 51000.0)
    assert pct_change_2 == pytest.approx(2.0, rel=1e-9)
    assert buffer.get_last_price("BTCUSDT") == 51000.0


@pytest.mark.unit
def test_pct_change_calculation_negative():
    """Test: Negative price movement calculates correct pct_change."""
    buffer = PriceBuffer()

    # First price
    buffer.calculate_pct_change("ETHUSDT", 3000.0)

    # Second price: -5% decrease
    # Formula: (2850 - 3000) / 3000 * 100 = -5.0%
    pct_change = buffer.calculate_pct_change("ETHUSDT", 2850.0)
    assert pct_change == pytest.approx(-5.0, rel=1e-9)


@pytest.mark.unit
def test_multiple_symbols_independent():
    """Test: Multiple symbols track price changes independently."""
    buffer = PriceBuffer()

    # BTC: 50k → 51k (+2%)
    buffer.calculate_pct_change("BTCUSDT", 50000.0)
    btc_pct = buffer.calculate_pct_change("BTCUSDT", 51000.0)

    # ETH: 3k → 2.9k (-3.33%)
    buffer.calculate_pct_change("ETHUSDT", 3000.0)
    eth_pct = buffer.calculate_pct_change("ETHUSDT", 2900.0)

    assert btc_pct == pytest.approx(2.0, rel=1e-9)
    assert eth_pct == pytest.approx(-3.333333, rel=1e-5)
    assert len(buffer) == 2
    assert set(buffer.get_tracked_symbols()) == {"BTCUSDT", "ETHUSDT"}


@pytest.mark.unit
def test_price_sequence_chaining():
    """Test: Price changes chain correctly over multiple updates."""
    buffer = PriceBuffer()

    # Sequence: 100 → 110 (+10%) → 121 (+10%) → 109 (-9.917%)
    pct_1 = buffer.calculate_pct_change("TESTSYM", 100.0)
    pct_2 = buffer.calculate_pct_change("TESTSYM", 110.0)
    pct_3 = buffer.calculate_pct_change("TESTSYM", 121.0)
    pct_4 = buffer.calculate_pct_change("TESTSYM", 109.0)

    assert pct_1 == 0.0
    assert pct_2 == pytest.approx(10.0, rel=1e-9)
    assert pct_3 == pytest.approx(10.0, rel=1e-9)
    assert pct_4 == pytest.approx(-9.917355, rel=1e-5)


@pytest.mark.unit
def test_reset_single_symbol():
    """Test: Reset clears price history for specific symbol."""
    buffer = PriceBuffer()

    buffer.calculate_pct_change("BTCUSDT", 50000.0)
    buffer.calculate_pct_change("ETHUSDT", 3000.0)

    assert len(buffer) == 2

    buffer.reset("BTCUSDT")

    assert len(buffer) == 1
    assert buffer.get_last_price("BTCUSDT") is None
    assert buffer.get_last_price("ETHUSDT") == 3000.0


@pytest.mark.unit
def test_reset_all_symbols():
    """Test: Reset without symbol clears all price history."""
    buffer = PriceBuffer()

    buffer.calculate_pct_change("BTCUSDT", 50000.0)
    buffer.calculate_pct_change("ETHUSDT", 3000.0)
    buffer.calculate_pct_change("ADAUSDT", 1.0)

    assert len(buffer) == 3

    buffer.reset()

    assert len(buffer) == 0
    assert buffer.get_tracked_symbols() == []


@pytest.mark.unit
def test_get_last_price_unknown_symbol():
    """Test: get_last_price returns None for unknown symbol."""
    buffer = PriceBuffer()

    assert buffer.get_last_price("UNKNOWN") is None


@pytest.mark.unit
def test_small_price_movement():
    """Test: Small price changes are calculated with precision."""
    buffer = PriceBuffer()

    # 0.01% movement (1 cent on $100)
    buffer.calculate_pct_change("TESTSYM", 100.00)
    pct_change = buffer.calculate_pct_change("TESTSYM", 100.01)

    assert pct_change == pytest.approx(0.01, rel=1e-9)


@pytest.mark.unit
def test_large_price_movement():
    """Test: Large price changes are calculated correctly."""
    buffer = PriceBuffer()

    # 50% movement
    buffer.calculate_pct_change("VOLATILE", 100.0)
    pct_change = buffer.calculate_pct_change("VOLATILE", 150.0)

    assert pct_change == pytest.approx(50.0, rel=1e-9)


@pytest.mark.unit
def test_replay_determinism():
    """Test: Same sequence of prices produces same pct_change results (deterministic)."""
    # First run
    buffer1 = PriceBuffer()
    sequence1 = [
        buffer1.calculate_pct_change("BTCUSDT", 50000.0),
        buffer1.calculate_pct_change("BTCUSDT", 51000.0),
        buffer1.calculate_pct_change("BTCUSDT", 50500.0),
    ]

    # Second run (replay)
    buffer2 = PriceBuffer()
    sequence2 = [
        buffer2.calculate_pct_change("BTCUSDT", 50000.0),
        buffer2.calculate_pct_change("BTCUSDT", 51000.0),
        buffer2.calculate_pct_change("BTCUSDT", 50500.0),
    ]

    assert sequence1 == sequence2
    assert sequence1 == [0.0, pytest.approx(2.0), pytest.approx(-0.9803921, rel=1e-5)]
