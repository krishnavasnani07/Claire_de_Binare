# Go / No-Go Entscheidung

**Canonical State Source:** `LR-TASKS.yaml` (manifest) + `LR-*-STATE.yaml` (per-task state)
**Validation:** `python scripts/lr004_completion_guard.py --check` (CI-enforced)
**Spec:** `LR-004-SPEC.md`

| Phase | Bereich | Status | Blocker | Evidence | Owner |
|-------|---------|--------|---------|----------|-------|
| P0 | CI Required Checks | | YES | | |
| P0 | Contract Tests | | YES | | |
| P0 | Kill-Switch + Limits | | YES | | |
| P1 | Risk Engine Tests | | NO | | |
| P1 | State Machine Tests | | NO | | |
| P1 | Negative Payload | | NO | | |
| P2 | E2E Paper Trading | | NO | | |
| P2 | Replay Framework | | NO | | |
| P3 | Shadow Mode | | NO | | |
| P3 | Metrics Comparison | | NO | | |
| P4 | 72h Soak | | NO | | |
| P4 | Chaos: DB Failure | | NO | | |
| P4 | Chaos: Network | | NO | | |
| P5 | Canary Checklist | | YES | | |

**Rules:**
- Blocker = YES: Must PASS before go-live
- Blocker = NO: Should PASS, but not hard blocker
- Ohne vollständige PASS-Zeile für alle Blocker = YES: **NO GO**
