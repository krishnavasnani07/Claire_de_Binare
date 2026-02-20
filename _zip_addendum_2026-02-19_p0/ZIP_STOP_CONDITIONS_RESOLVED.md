# Stop Conditions — Auflösung

## SC-1: timestamp_ms / staleness_s / data_silence_s in DECISION_HASH_FIELDS

**Problem:** 3 von 14 Feldern in `DECISION_HASH_FIELDS` (`core/utils/uuid_gen.py:71`) sind
direkt oder indirekt wall-clock-getrieben:
- `timestamp_ms` → direkt `time.time() * 1000`
- `staleness_s` → `now_ms - max(signal/market/account timestamps)`
- `data_silence_s` → `now_ms - last_tick_ts_ms`

Damit ist `compute_input_snapshot_hash()` und folglich `decision_pk` nicht replay-deterministisch.

**Entscheidung:** Alle 3 Felder aus `DECISION_HASH_FIELDS` entfernen.

**Begründung:**
1. `DECISION_HASH_FIELDS` wird ausschließlich in `compute_input_snapshot_hash()` verwendet
   (Usage-Audit: `rg -n "DECISION_HASH_FIELDS"` — nur 2 Treffer in Code, Rest Doku).
2. Kein Legacy-Code außerhalb Phase-9/Trace nutzt diese Konstante.
3. Toggle ist OFF (Default "0"), es existieren keine produktiven Hashes mit diesen Feldern.
4. Die 3 Felder bleiben in der Evidence für Observability/Debug erhalten.
5. Kollisionsrisiko: 11 verbleibende Felder + deterministisches `signal_ts_ms` als `ts_ms`-Parameter
   in `generate_decision_pk()` bieten ausreichende Einzigartigkeit. Identische Werte in allen
   11 Feldern + gleiches `signal_ts_ms` = de facto gleiche Entscheidung → Idempotenz korrekt.

**Compat-safe:** Ja. Kein bestehender Code außerhalb Trace verwendet `DECISION_HASH_FIELDS`.
