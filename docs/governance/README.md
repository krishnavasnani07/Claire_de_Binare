# Governance Documentation

This directory contains governance artifacts for the Claire de Binare (CDB) trading system.

## System Invariants (Canonical)

**Location**: [DocsHub → knowledge/governance/SYSTEM_INVARIANTS.md](https://github.com/jannekbuengener/Claire_de_Binare_Docs/blob/main/knowledge/governance/SYSTEM_INVARIANTS.md)

**Purpose**: Defines the 20 non-negotiable system contracts that govern CDB's behavior. All service logic, tests, schemas, and CI enforcement must conform to these invariants.

**Key Invariants Include**:
- Fail-closed trade decisions (INV-001)
- Deterministic decision logic (INV-002)
- Risk-first hierarchy (INV-003)
- Schema strictness (INV-008)
- Decision traceability (INV-012)
- Live trading authorization gates (INV-006)
- Contract drift protection (INV-007)

**Change Policy**:
- Any change to system invariants requires:
  1. Update to canonical document in DocsHub
  2. Updated references and enforcement mechanisms
  3. Passing all contract tests and drift guards
  4. Human approval via PR review

**Cross-Repo Reference Rule**:
- SYSTEM_INVARIANTS.md lives in DocsHub (documentation repo)
- Enforcement mechanisms live in Working Repo (tests, schemas, CI, guards)
- All Working Repo references in invariants are prefixed with "Working Repo:"

---

## Local Governance Files

### risk_events.schema.yaml
Schema specification for risk events stored in PostgreSQL. Enforced by:
- `scripts/governance/check_risk_events_schema_contract.py`
- `.github/workflows/governance-drift-guard.yml`

See INV-019 in SYSTEM_INVARIANTS.md for canonical statement.
