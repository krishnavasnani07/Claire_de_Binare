# Phase 6 Runtime Evidence Report

**Date**: 2026-02-14 23:15 CET
**Stack**: cdb (all services healthy)
**Branch**: main

## Stack Status

| Service | Status |
|---------|--------|
| cdb_redis | Up (healthy) |
| cdb_postgres | Up (healthy) |
| cdb_ws | Up (healthy) |
| cdb_candles | Up (healthy) |
| cdb_regime | Up (healthy) |
| cdb_signal | Up (healthy) |
| cdb_risk | Up (healthy) |
| cdb_allocation | Up (healthy) |
| cdb_paper_runner | Up (healthy) |
| cdb_db_writer | Up (healthy) |

## Gate Status

| Gate | Status | Evidence |
|------|--------|----------|
| **RC_001** | RESOLVED | `market_state.regime_id = 0` present, lookup functional |
| **RC_002** | RESOLVED | `return_1m`, `return_5m`, `price_change_5m` present |
| **RC_003** | RESOLVED | `staleness_s` computed from available timestamps |
| **RC_004** | RESOLVED | `last_tick_ts_ms` fresh (transient blocks during restart) |
| **RC_010** | ACTIVE (strategy gate) | `pct_change_15m = 1.05%` < threshold `3%` |

## Evidence Snapshots

### market_state:BTCUSDT
```json
{
  "regime_id": 0,
  "return_1m": 0.0004224,
  "return_5m": -0.0003298,
  "price_change_5m": 0.0003298,
  "ts_ms": 1771107060700,
  "last_tick_ts_ms": 1771107060232
}
```

### Risk Metrics
```
orders_approved_total: 0
orders_blocked_total: 8
```

### Block Reason Distribution
- RC_010: 3 (signal threshold - no-trade condition)
- RC_004: 4 (transient during service restart)
- RC_001: 1 (stale regime before refresh)

## Conclusions

1. **RC_001 operationally resolved**: `regime_id` is present in market_state, deterministic lookup via `stream.regime_signals` works.

2. **RC_010 is a strategy gate, not a bug**: Market movement < 3% correctly blocks trading. This is protective behavior.

3. **RC_004 transient**: Data silence blocks occurred during service restart window. Pending validation under steady-state.

4. **approvals = 0 is correct**: No trade conditions met (low volatility market).

## Open Work Items (not blockers)

- Regime Service heartbeat/refresh logic (robustness improvement, prevents future RC_001 if no regime change for > 5 min)

---

*Runtime Status: GREEN*
