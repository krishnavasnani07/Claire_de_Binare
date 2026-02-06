# LR-004 Evidence: Deterministic Completion Mechanism

**Status:** 🔄 IN PROGRESS
**Date:** 2026-02-05
**Baseline:** feature/lr-003b-contract-drift-guard-clean

---

## Ziel

Establish fail-closed, deterministic completion tracking for LR tasks through:
- Canonical task manifest (`LR-TASKS.yaml`)
- Per-task state files (`LR-NNN-STATE.yaml`)
- Validator enforcing rules V000-V015
- CI integration with fail-closed enforcement

---

## Implementation

### Components

| Component | Location | Purpose |
|-----------|----------|---------|
| Specification | `docs/live-readiness/LR-004-SPEC.md` | Full schema, rules V000-V015, reason codes |
| Manifest | `docs/live-readiness/LR-TASKS.yaml` | Canonical list of LR tasks (append-only) |
| Validator | `scripts/lr004_completion_guard.py` | Python 3.11 validator (--check, --report modes) |
| Template | `docs/live-readiness/LR-STATE-TEMPLATE.yaml` | Template for new STATE files |
| CI Job | `.github/workflows/ci.yaml` | `lr-004-completion-guard` job |

### Validation Rules Implemented

- **V000-V002:** Manifest validation (existence, schema, no duplicates, format, ordering)
- **V003-V005:** Cross-validation (missing STATE, orphan STATE, duplicate STATE)
- **V006-V009:** Basic STATE validation (schema version, task ID/title consistency, status enum)
- **V010-V011:** State completeness (DONE vs BLOCKED field requirements)
- **V012:** Timestamp format (ISO 8601 UTC)
- **V013:** Reason code taxonomy
- **V014:** Evidence file existence + path safety (no absolute, no ..)
- **V015:** Evidence commit format (7-40 hex chars)

---

## Evidence: Test Cases

### Test Case 1: Positive - All Tasks Valid (DONE + BLOCKED)

**Setup:**
- LR-001: DONE
- LR-002: DONE
- LR-003: DONE
- LR-004: BLOCKED (RC_B400)

**Command:**
```bash
python scripts/lr004_completion_guard.py --check
```

**Expected Output:**
```
[LR-004] Completion Guard: Validating LR-Task States...
[LR-004] Loading manifest: docs/live-readiness/LR-TASKS.yaml
[LR-004] Found 4 tasks in manifest
[OK] LR-001: DONE (completed 2026-01-28)
[OK] LR-002: DONE (completed 2026-01-30)
[OK] LR-003: DONE (completed 2026-02-04)
[BLOCKED] LR-004: RC_B400 - Implementation in progress

[LR-004] Summary:
  Total Tasks: 4
  DONE: 3
  BLOCKED: 1
  Missing: 0
  Orphaned: 0

[LR-004] BLOCKED Tasks:
  - LR-004: RC_B400 - Implementation in progress - awaiting CI integration

[LR-004] ✓ PASS: All LR-Task states valid
```

**Expected Exit Code:** 0 (PASS)

**Rationale:** BLOCKED is a valid terminal state; validator reports it but does not fail.

**Commit:** TBD
**CI Job:** TBD

---

### Test Case 2: Negative - Missing STATE File

**Setup:**
- Remove LR-003-STATE.yaml temporarily

**Command:**
```bash
mv docs/live-readiness/LR-003-STATE.yaml docs/live-readiness/LR-003-STATE.yaml.bak
python scripts/lr004_completion_guard.py --check
```

**Expected Output:**
```
[LR-004] Completion Guard: Validating LR-Task States...
[LR-004] Loading manifest: docs/live-readiness/LR-TASKS.yaml
[LR-004] Found 4 tasks in manifest
[OK] LR-001: DONE (completed 2026-01-28)
[OK] LR-002: DONE (completed 2026-01-30)
[BLOCKED] LR-004: RC_B400 - Implementation in progress

[LR-004] Summary:
  Total Tasks: 4
  DONE: 2
  BLOCKED: 1
  Missing: 1
  Orphaned: 0

[LR-004] VALIDATION FAILURES (1):
  ✗ LR-003: Rule V003 violation - Missing STATE file (expected: docs/live-readiness/LR-003-STATE.yaml)

[LR-004] ❌ FAIL: Validation failed (fail-closed)
```

**Expected Exit Code:** 1 (FAIL)

**Cleanup:**
```bash
mv docs/live-readiness/LR-003-STATE.yaml.bak docs/live-readiness/LR-003-STATE.yaml
```

**Commit:** TBD
**CI Job:** TBD (should block merge)

---

### Test Case 3: Negative - Invalid Reason Code

**Setup:**
- Temporarily modify LR-004-STATE.yaml with invalid reason code

**Command:**
```bash
sed -i 's/RC_B400/RC_INVALID/' docs/live-readiness/LR-004-STATE.yaml
python scripts/lr004_completion_guard.py --check
```

**Expected Output:**
```
[LR-004] Completion Guard: Validating LR-Task States...
[LR-004] Loading manifest: docs/live-readiness/LR-TASKS.yaml
[LR-004] Found 4 tasks in manifest
[OK] LR-001: DONE (completed 2026-01-28)
[OK] LR-002: DONE (completed 2026-01-30)
[OK] LR-003: DONE (completed 2026-02-04)
[BLOCKED] LR-004: RC_INVALID - Implementation in progress

[LR-004] Summary:
  Total Tasks: 4
  DONE: 3
  BLOCKED: 1
  Missing: 0
  Orphaned: 0

[LR-004] BLOCKED Tasks:
  - LR-004: RC_INVALID - Implementation in progress - awaiting CI integration (has validation errors)

[LR-004] VALIDATION FAILURES (1):
  ✗ LR-004: Rule V013 violation - Invalid blocked_reason_code: RC_INVALID (not in taxonomy)

[LR-004] ❌ FAIL: Validation failed (fail-closed)
```

**Expected Exit Code:** 1 (FAIL)

**Cleanup:**
```bash
git checkout docs/live-readiness/LR-004-STATE.yaml
```

**Commit:** TBD
**CI Job:** TBD (should block merge)

---

### Test Case 4: Negative - DONE State Missing Required Field

**Setup:**
- Temporarily modify LR-001-STATE.yaml (remove completion_timestamp)

**Command:**
```bash
sed -i '/completion_timestamp:/d' docs/live-readiness/LR-001-STATE.yaml
python scripts/lr004_completion_guard.py --check
```

**Expected Output:**
```
[LR-004] Completion Guard: Validating LR-Task States...
[LR-004] Loading manifest: docs/live-readiness/LR-TASKS.yaml
[LR-004] Found 4 tasks in manifest
[OK] LR-001: DONE (completed unknown)
[OK] LR-002: DONE (completed 2026-01-30)
[OK] LR-003: DONE (completed 2026-02-04)
[BLOCKED] LR-004: RC_B400 - Implementation in progress

[LR-004] Summary:
  Total Tasks: 4
  DONE: 3
  BLOCKED: 1
  Missing: 0
  Orphaned: 0

[LR-004] VALIDATION FAILURES (1):
  ✗ LR-001: Rule V010 violation - DONE state missing required field: completion_timestamp

[LR-004] ❌ FAIL: Validation failed (fail-closed)
```

**Expected Exit Code:** 1 (FAIL)

**Cleanup:**
```bash
git checkout docs/live-readiness/LR-001-STATE.yaml
```

**Commit:** TBD
**CI Job:** TBD (should block merge)

---

### Test Case 5: Negative - Orphan STATE File

**Setup:**
- Create STATE file for non-existent task

**Command:**
```bash
cat > docs/live-readiness/LR-999-STATE.yaml <<EOF
spec_version: "1.0"
task_id: "LR-999"
task_title: "Orphan Task"
status: "DONE"
completion_timestamp: "2026-02-05T13:00:00Z"
completion_author: "testuser"
evidence_file: "docs/live-readiness/LR-999-EVIDENCE.md"
evidence_commit: "abc1234"
blocked_reason_code: null
blocked_reason_text: null
blocked_since: null
EOF
python scripts/lr004_completion_guard.py --check
```

**Expected Output:**
```
[LR-004] Completion Guard: Validating LR-Task States...
[LR-004] Loading manifest: docs/live-readiness/LR-TASKS.yaml
[LR-004] Found 4 tasks in manifest
[OK] LR-001: DONE (completed 2026-01-28)
[OK] LR-002: DONE (completed 2026-01-30)
[OK] LR-003: DONE (completed 2026-02-04)
[BLOCKED] LR-004: RC_B400 - Implementation in progress

[LR-004] Summary:
  Total Tasks: 4
  DONE: 3
  BLOCKED: 1
  Missing: 0
  Orphaned: 1

[LR-004] VALIDATION FAILURES (1):
  ✗ LR-999: Rule V004 violation - Orphan STATE file (LR-999-STATE.yaml not in manifest)

[LR-004] ❌ FAIL: Validation failed (fail-closed)
```

**Expected Exit Code:** 1 (FAIL)

**Cleanup:**
```bash
rm docs/live-readiness/LR-999-STATE.yaml
```

**Commit:** TBD
**CI Job:** TBD (should block merge)

---

## Design Rationale

### Why Manifest-Driven?

**Problem:** Glob-based discovery (`LR-*-STATE.yaml`) cannot detect missing files.

**Solution:** Canonical manifest (`LR-TASKS.yaml`) lists all expected tasks. Validator cross-validates:
- Manifest → STATE (missing detection)
- STATE → Manifest (orphan detection)

### Why Binary Terminal States?

**Problem:** Intermediate states (IN_PROGRESS, PENDING) create ambiguity.

**Solution:** Only DONE or BLOCKED:
- DONE: Work complete, evidence present
- BLOCKED: Explicit blocker with reason code

### Why Fail-Closed?

**Problem:** Silent failures or missing validation allow incomplete work to slip through.

**Solution:** Any validation failure → CI blocks merge. BLOCKED tasks are valid but reported.

### Why No GitHub API?

**Problem:** GitHub API has eventual consistency issues, rate limits, authentication requirements.

**Solution:** Validator reads only local filesystem (manifest + STATE files). Deterministic, offline-capable, fast.

---

## Acceptance Criteria

LR-004 is DONE when:

- [x] Specification complete (`LR-004-SPEC.md`)
- [x] Manifest created (`LR-TASKS.yaml`)
- [x] Validator implements V000-V015 (`lr004_completion_guard.py`)
- [x] Template available (`LR-STATE-TEMPLATE.yaml`)
- [x] Example STATE files (LR-001, LR-002, LR-003, LR-004)
- [ ] CI job integrated (`.github/workflows/ci.yaml`)
- [ ] Build summary updated
- [x] Evidence demonstrates 5 test cases (this file)
- [ ] CI passes with LR-004 checks green
- [ ] GO_NO_GO.md updated with reference

---

## Next Steps

1. ✅ Validator patched (manifest rules, BLOCKED tracking, evidence path safety)
2. ✅ Template created
3. ✅ Example STATE files + Evidence stubs created
4. 🔄 CI integration (pending)
5. 🔄 Build summary integration (pending)
6. 🔄 GO_NO_GO.md update (pending)

---

**End of Evidence (In Progress)**
