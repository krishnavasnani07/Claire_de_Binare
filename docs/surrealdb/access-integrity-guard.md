# Access Integrity Guard

Dieses Guard prüft Access-Domain-Mirror-Records deterministisch, ohne Hashes zu reparieren oder Trading-Logik zu berühren.

## Betroffene Storage-Ziele

- `system_config`
- `security_policy_refs` als tatsächlicher Repo-Storage für `security_policies`

## Hash-Scope

Der erwartete Hash wird als `HMAC-SHA256` über canonical JSON aller persistierten Record-Felder berechnet, ausgenommen:

- `integrity_hash`
- `integrity_algo`
- `integrity_version`
- optionale Chain-Felder wie `integrity_prev_hash` oder `integrity_chain_hash`
- reine Transportfelder wie `table` oder `record_type`

Für `system_config` umfasst der Payload aktuell:

- `config_key`
- `config_scope`
- `value_ref`
- `value_hash`
- `source_path`
- `observed_at`

Für `security_policies` / `security_policy_refs` umfasst der Payload aktuell:

- `policy_id`
- `version_hash`
- `docs_path`
- `observed_at`

## ENV

- `CDB_ACCESS_INTEGRITY_KEY`: verpflichtender HMAC-Key für Validierung und Report

Fehlt die Variable, läuft der Guard fail-closed und markiert jeden Record mit `ACCESS_INTEGRITY_KEY_MISSING`.

## Verhalten bei Mismatch

- Kein Fix-up, kein Rewrite, keine DB-Mutation
- Report pro Record mit `OK` oder `FAIL`
- Exit-Code `0`: alle Records validiert
- Exit-Code `2`: mindestens ein Integrity-Fail oder fehlender Key
- Exit-Code `1`: Parser-/Runtime-Fehler

CLI:

```bash
python -m tools.surrealdb.access_integrity_guard --input snapshot.json --output reports/access-integrity-report.md
```
