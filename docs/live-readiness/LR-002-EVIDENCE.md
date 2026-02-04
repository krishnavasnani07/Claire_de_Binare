# LR-002 Evidence: Contract Tests as First-Class Gate

**Date:** 2026-02-04
**Baseline:** main@81955684a2ef038cb478b2280c4d2eb0ad4b7c5e
**Implementation:** LR-002 (P0 - Contract Tests)

---

## What Changed

### 1. Reason Codes Centralized (Refactor-Only)
**New File:** `services/risk/reason_codes.py`
- Extracted 8 reason codes from `services/risk/service.py`
- RC_001, RC_002, RC_003, RC_004, RC_010, RC_020, RC_021, RC_022
- No logic changes, only extract-to-constant refactor

**Updated:** `services/risk/service.py`
- Imported reason codes from new module
- Replaced all hardcoded strings (`"RC_001"` → `RC_001`)
- No changes to decision thresholds or conditions

**Evidence:**
```bash
git diff services/risk/
pytest -q tests/unit/risk/test_decision_contract.py
# Result: 16/16 PASS (no behavior change)
```

### 2. Decision Contract Tests Promoted
**Moved:** `tests/unit/risk/test_decision_contract.py` → `tests/contract/test_decision_contract.py`
- All 16 tests moved from unit/ to contract/ directory
- Marker changed: `@pytest.mark.unit` → `@pytest.mark.contract`
- pytest.ini: Registered new marker `contract`

**Evidence:**
```bash
pytest -m contract -q
# Result: 16 passed, 1 skipped, 344 deselected

pytest -m "not contract" -q tests/unit/risk/
# Result: 31 passed (other risk tests unaffected)
```

### 3. CI Job: Explicit Contract Tests Gate
**Updated:** `.github/workflows/ci.yaml`
- New job: `contract-tests` (name: "Contract Tests")
- Command: `pytest -m contract -v --tb=short --maxfail=1`
- Python: 3.11 (baseline)
- Triggers: All pull_request events
- Added to `build-summary` dependencies
- Visible in CI summary output

**Evidence:**
```bash
grep -n "Contract Tests" .github/workflows/ci.yaml
# Line 287: name: Contract Tests
# Line 458: echo "- Contract Tests: ..."
```

---

## Commands + Outputs

### Baseline Safety Check
```bash
$ git rev-parse HEAD
81955684a2ef038cb478b2280c4d2eb0ad4b7c5e

$ pytest tests/unit/risk/test_decision_contract.py -q --disable-warnings
============================= test session starts =============================
collected 16 items

tests\unit\risk\test_decision_contract.py ................               [100%]
============================= 16 passed in 0.18s ==============================
```

### Post-Refactor Validation
```bash
$ pytest -m contract -q --disable-warnings
============================= test session starts =============================
collected 360 items / 344 deselected / 1 skipped / 16 selected

tests\contract\test_decision_contract.py ................                [100%]
========== 16 passed, 1 skipped, 344 deselected in 0.96s ==========
```

### Other Risk Tests Unaffected
```bash
$ pytest -m "not contract" -q tests/unit/risk/ --disable-warnings
============================= test session starts =============================
collected 31 items

tests\unit\risk\test_circuit_breakers.py ..................              [ 58%]
tests\unit\risk\test_service.py ........                                 [ 83%]
tests\unit\risk\test_signal_serialization.py .....                       [100%]
============================= 31 passed in 0.25s ==============================
```

---

## CI Run Evidence

**PR:** https://github.com/jannekbuengener/Claire_de_Binare/pull/793
**CI Run:** https://github.com/jannekbuengener/Claire_de_Binare/actions/runs/21672987067
**Status:** ✅ ALL PASS

### Key Jobs
- **Contract Tests:** ✅ PASS (24s)
  - URL: https://github.com/jannekbuengener/Claire_de_Binare/actions/runs/21672987067/job/62485473262
  - Command: `pytest -m contract -v --tb=short --maxfail=1`
  - Result: 16 contract tests passed

- **Unit Tests (Python 3.11):** ✅ PASS (36s)
  - URL: https://github.com/jannekbuengener/Claire_de_Binare/actions/runs/21672987067/job/62485473149

- **Unit Tests (Python 3.12):** ✅ PASS (34s)
  - URL: https://github.com/jannekbuengener/Claire_de_Binare/actions/runs/21672987067/job/62485473196

- **Format Check (Black):** ✅ PASS (16s)
  - URL: https://github.com/jannekbuengener/Claire_de_Binare/actions/runs/21672987067/job/62485473163

- **E2E Happy Path:** ✅ PASS (28s)
  - URL: https://github.com/jannekbuengener/Claire_de_Binare/actions/runs/21672987067/job/62485542055

**Contract Tests Job:** Explicitly visible in CI as first-class check ✅

---

## Known External Test Failures (Out of Scope)

### MCP Runtime Test Failure
**Test:** `tests/smoke/test_mcp_runtime.py::test_mcp_time_server_runtime`
**Error:** "async def functions are not natively supported" (pytest-asyncio issue)
**Status:** Out of LR-002 scope
**Reason:** Infrastructure/test-harness issue, not a contract regression
**Action:** Deferred (not blocking LR-002 by design)

---

## Runtime Behavior Guarantee

**No runtime behavior changes:**
- Reason code values unchanged (still strings: "RC_001", etc.)
- Decision thresholds unchanged
- Test assertions unchanged
- All 16 contract tests pass identically before/after refactor

**Contract surface preserved:**
- `decide_trade()` signature unchanged
- Evidence structure unchanged
- Reason code semantics unchanged

---

## Definition of Done (LR-002)

- ✅ Reason Codes centralized (refactor-only)
- ✅ Decision Contract Tests under tests/contract/
- ✅ pytest marker `contract` registered
- ✅ CI Job "Contract Tests" visible & required
- ✅ Evidence File created (this file)
- ✅ No runtime behavior changed (validated via tests)

---

**Evidence Status:** Complete (pending CI run URL in STOP F)
**Next:** STOP F - PR creation + CI validation
