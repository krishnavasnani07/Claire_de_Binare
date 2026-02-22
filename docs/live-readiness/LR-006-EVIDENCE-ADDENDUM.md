# LR-006 Evidence Addendum: Evidence Dict Key Inventory

**Task ID:** LR-006
**Task Title:** P0 Deterministic Decision Traceability Contract
**Addendum Date:** 2026-02-22
**Author:** Claude Code (Repo Analyst)
**Type:** Append-only addendum. Does not modify `LR-006-STATE.yaml` or `LR-006-EVIDENCE.md`.

---

## 1. Purpose and Scope

This addendum documents the current structure of the evidence dictionary returned by `decide_trade()` at `services/risk/service.py:193`, observed at HEAD `1d08c7c` (2026-02-22).

The original `LR-006-EVIDENCE.md` (2026-02-07) attested 3 example trace records and acceptance criteria AC8/AC9/AC13/AC14. This addendum records the current evidence dict key inventory as returned by the public `decide_trade()` API, under both toggle states of `TRACE_CONTRACT_V1_ENABLED`.

This document is append-only. It does not rewrite or invalidate the original LR-006 evidence. No claims are made about traceability quality or compliance — only the observable key set is inventoried.

---

## 2. Evidence Dict Keys — Toggle OFF (Default)

**Environment:** `TRACE_CONTRACT_V1_ENABLED` not set (default `"0"`)
**Command:**

```bash
python -c "
from services.risk import service as rs
now_ms = 1_700_000_000_000
sig = {'signal_id':'sig-test','symbol':'BTCUSDT','pct_change_15m':3.5,'volume_15m':200000.0,'ts_ms':now_ms-1000}
ms  = {'regime_id':0,'return_1m':-1.0,'return_5m':-1.0,'price_change_5m':5.0,'last_tick_ts_ms':now_ms-500,'ts_ms':now_ms-900}
acc = {'daily_drawdown_pct':1.0,'total_exposure_pct':10.0,'ts_ms':now_ms-800}
mh  = {'slippage_pct':0.5,'ts_ms':now_ms-700}
d, rc, ev = rs.decide_trade(sig, ms, acc, mh, now_ms)
print('decision:', d, 'reason_code:', rc)
print('key_count:', len(ev))
print('evidence_keys:', sorted(ev.keys()))
"
```

**Output:**

```
decision: ALLOW reason_code: None
key_count: 20
evidence_keys: ['contract_version', 'daily_drawdown_pct', 'data_silence_s', 'decision_id', 'pct_change_15m', 'price_change_5m', 'regime_id', 'return_1m', 'return_5m', 'signal_id', 'slippage_pct', 'staleness_s', 'staleness_sources', 'symbol', 'thresholds', 'timestamp_ms', 'timestamps_ms', 'total_exposure_pct', 'trace_id', 'volume_15m']
```

**Key count:** 20

**Correlation IDs present:** `decision_id`, `trace_id`, `signal_id`
**Contract marker present:** `contract_version`

---

## 3. Evidence Dict Keys — Toggle ON (`TRACE_CONTRACT_V1_ENABLED=1`)

**Environment:** `TRACE_CONTRACT_V1_ENABLED=1`
**Command:**

```bash
TRACE_CONTRACT_V1_ENABLED=1 python -c "
from services.risk import service as rs
now_ms = 1_700_000_000_000
sig = {'signal_id':'sig-test','symbol':'BTCUSDT','pct_change_15m':3.5,'volume_15m':200000.0,'ts_ms':now_ms-1000}
ms  = {'regime_id':0,'return_1m':-1.0,'return_5m':-1.0,'price_change_5m':5.0,'last_tick_ts_ms':now_ms-500,'ts_ms':now_ms-900}
acc = {'daily_drawdown_pct':1.0,'total_exposure_pct':10.0,'ts_ms':now_ms-800}
mh  = {'slippage_pct':0.5,'ts_ms':now_ms-700}
d, rc, ev = rs.decide_trade(sig, ms, acc, mh, now_ms)
print('decision:', d, 'reason_code:', rc)
print('key_count:', len(ev))
print('evidence_keys:', sorted(ev.keys()))
"
```

**Output:**

```
decision: ALLOW reason_code: None
key_count: 20
evidence_keys: ['contract_version', 'daily_drawdown_pct', 'data_silence_s', 'decision_id', 'pct_change_15m', 'price_change_5m', 'regime_id', 'return_1m', 'return_5m', 'signal_id', 'slippage_pct', 'staleness_s', 'staleness_sources', 'symbol', 'thresholds', 'timestamp_ms', 'timestamps_ms', 'total_exposure_pct', 'trace_id', 'volume_15m']
```

**Key count:** 20

**Observation:** The evidence dict returned by `decide_trade()` is identical under both toggle states (20 keys, same set). The toggle `TRACE_CONTRACT_V1_ENABLED` does not affect the `decide_trade()` return value itself. Phase 9 enrichment (`_phase9_enrich_evidence`) is invoked downstream in the `RiskManager.process_signal` pipeline, not within `decide_trade()`.

---

## 4. Toggle Reference

| Attribute | Value |
|---|---|
| Toggle file | `core/utils/trace_toggle.py` |
| Toggle function | `trace_contract_v1_enabled()` |
| Environment variable | `TRACE_CONTRACT_V1_ENABLED` |
| Default | `"0"` (OFF) |
| Phase 9 enrichment function | `services/risk/service.py:_phase9_enrich_evidence()` |
| Phase 9 invocation site | Downstream in `RiskManager.process_signal`, not in `decide_trade()` |

Per code path at `services/risk/service.py:337-419`, `_phase9_enrich_evidence()` may add keys (`policy_id`, `policy_hash`, `input_hash`, `output_hash`, `decision_context`) when invoked downstream. These keys are not observable from `decide_trade()` alone.

---

## 5. Reproduction Commands

```bash
# Toggle OFF (default) — evidence keys from decide_trade()
python -c "
from services.risk import service as rs
now_ms = 1_700_000_000_000
sig = {'signal_id':'sig-test','symbol':'BTCUSDT','pct_change_15m':3.5,'volume_15m':200000.0,'ts_ms':now_ms-1000}
ms  = {'regime_id':0,'return_1m':-1.0,'return_5m':-1.0,'price_change_5m':5.0,'last_tick_ts_ms':now_ms-500,'ts_ms':now_ms-900}
acc = {'daily_drawdown_pct':1.0,'total_exposure_pct':10.0,'ts_ms':now_ms-800}
mh  = {'slippage_pct':0.5,'ts_ms':now_ms-700}
d, rc, ev = rs.decide_trade(sig, ms, acc, mh, now_ms)
print('decision:', d, 'reason_code:', rc)
print('key_count:', len(ev))
print('evidence_keys:', sorted(ev.keys()))
"

# Toggle ON — same observation via decide_trade()
TRACE_CONTRACT_V1_ENABLED=1 python -c "
from services.risk import service as rs
now_ms = 1_700_000_000_000
sig = {'signal_id':'sig-test','symbol':'BTCUSDT','pct_change_15m':3.5,'volume_15m':200000.0,'ts_ms':now_ms-1000}
ms  = {'regime_id':0,'return_1m':-1.0,'return_5m':-1.0,'price_change_5m':5.0,'last_tick_ts_ms':now_ms-500,'ts_ms':now_ms-900}
acc = {'daily_drawdown_pct':1.0,'total_exposure_pct':10.0,'ts_ms':now_ms-800}
mh  = {'slippage_pct':0.5,'ts_ms':now_ms-700}
d, rc, ev = rs.decide_trade(sig, ms, acc, mh, now_ms)
print('decision:', d, 'reason_code:', rc)
print('key_count:', len(ev))
print('evidence_keys:', sorted(ev.keys()))
"
```

---

**End of addendum. No files modified beyond this document.**
