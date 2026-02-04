# LR-001 Evidence: Enforce CI Required Checks (no bypass)

**Issue:** #776
**Status:** ✅ PASS
**Date:** 2026-02-03
**Implemented by:** Claude Code (Governance Agent)

## Ziel

Stelle sicher, dass CI Required Checks nicht umgangen werden können (no --no-verify, keine Admin-Bypasses). GitHub Branch Protection Rules müssen erzwungen werden.

## Implementation

### Required Status Checks Configured

**Branch:** `main`
**Protection Endpoint:** `https://api.github.com/repos/jannekbuengener/Claire_de_Binare/branches/main/protection/required_status_checks`

**Settings:**
```json
{
  "strict": true,
  "contexts": [
    "ci (Unit/Integration + Lint gesammelt)",
    "validate-branch-name",
    "gitleaks (Secrets-Alarm)",
    "trivy (kritische CVEs/Supply-Chain)",
    "Check Core Duplicates",
    "Check Delivery Gate",
    "guard",
    "E2E Happy Path"
  ]
}
```

**Rationale:**
- **strict: true** → Branch must be up-to-date with main before merge
- **8 Required Checks** → All critical guards enforced
- **No conditional checks** → Only checks that produce SUCCESS/FAILURE (never SKIPPED)
- **No redundant checks** → One check per protection category

### Excluded Checks

**Intentionally NOT made required:**

| Check Name | Reason |
|------------|--------|
| `claude`, `claude-review` | AI optional, produces SKIPPED |
| `enforce-pr-template` | Conditional, sometimes SKIPPED |
| `validate-feature-workflow` | Conditional, sometimes SKIPPED |
| `Full Repository Scan` | Only runs on specific triggers |
| `🚫 Block PR Merge` | Returns SKIPPED instead of FAILURE |
| `Core Duplicates Guard` | Redundant to `Check Core Duplicates` |
| Individual CI steps | Covered by aggregate `ci (Unit/Integration + Lint gesammelt)` |

## Evidence

### 1. Branch Protection API Response

**Verification Command:**
```bash
gh api repos/jannekbuengener/Claire_de_Binare/branches/main/protection/required_status_checks
```

**Result:** 8 checks configured with `strict: true`
**File:** `/tmp/required_checks.json`

### 2. Proof Test (Negative Test)

**Test Branch:** `test-INVALID-Branch-NAME`
**PR:** #791 (closed)
**Purpose:** Prove that a failing required check blocks merge

**Test Setup:**
1. Created branch with invalid name (uppercase letters)
2. Branch violates naming policy: `^(feature|fix|...)/(description)$`
3. Expected: `validate-branch-name` check FAILURE

**Results:**
- Check status: **FAILURE** ✅
- PR merge state: **BLOCKED** ✅
- Admin bypass attempt: **REJECTED** ✅

**Admin Bypass Test:**
```bash
$ gh pr merge 791 --admin --squash
GraphQL: Repository rule violations found

5 of 8 required status checks have not succeeded: 1 expected and 1 failing.

 (mergePullRequest)
```

**Conclusion:** Admin bypass is prevented by GitHub GraphQL API. `enforce_admins: true` works correctly.

### 3. Positive Test (PR #790)

**Test Branch:** `feature/live-readiness-gate`
**PR:** #790
**Purpose:** Verify that valid PR with all checks passing can merge

**Required Checks Status (fresh run after 2026-02-03T19:46:00Z):**
- ✅ `ci (Unit/Integration + Lint gesammelt)` - SUCCESS
- ✅ `validate-branch-name` - SUCCESS
- ✅ `gitleaks (Secrets-Alarm)` - SUCCESS
- ✅ `trivy (kritische CVEs/Supply-Chain)` - SUCCESS
- ✅ `Check Core Duplicates` - SUCCESS
- ✅ `Check Delivery Gate` - SUCCESS
- ✅ `guard` - SUCCESS
- ✅ `E2E Happy Path` - SUCCESS

**CI Run URL:** https://github.com/jannekbuengener/Claire_de_Binare/pull/790

### 4. Historical Bypass Example (Before LR-001)

**Branch:** `feat/live-readiness-gate` (old PR #789)
**Issue:** Branch name violated policy (`feat/` vs `feature/`)
**Check:** `validate-branch-name` - FAILURE
**Outcome:** PR was created and **could have been merged** (no required checks at that time)

**This demonstrates the exact bypass that LR-001 prevents.**

After LR-001 implementation: Same scenario (PR #791) is **hard blocked** with no merge option.

## Pass Criteria

- [x] Branch Protection Rules are activated for main/production
- [x] Required Checks are defined and cannot be skipped (8 checks)
- [x] Admin-Bypass is documented and controlled (`enforce_admins: true`)
- [x] CI Workflow validates Branch Protection Status (proof test PR #791)
- [x] Documentation in docs/live-readiness/ updated (this file)

## Admin Bypass Controls

**Current Setting:** `enforce_admins: true`

**Verification:**
```bash
gh api repos/jannekbuengener/Claire_de_Binare/branches/main/protection/enforce_admins
# Result: {"enabled": true}
```

**Control Mechanism:**
- Admins **cannot** bypass required status checks
- Admins **cannot** bypass branch protection rules
- Admins **cannot** force merge failing PRs
- GitHub GraphQL API enforces this at server level

**Emergency Override:** Not available without disabling `enforce_admins` (requires separate action + audit log)

## Continuous Validation

**Monitor for drift:**
```bash
# Verify Required Checks are still configured
gh api repos/jannekbuengener/Claire_de_Binare/branches/main/protection/required_status_checks \
  | jq '{strict, check_count: (.contexts | length)}'

# Expected: {"strict": true, "check_count": 8}
```

**Alert if:**
- `strict` becomes `false`
- `contexts` array is empty or reduced
- `enforce_admins.enabled` becomes `false`

## Go/No-Go Relevanz

**BLOCKER** (P0 Phase)

This issue was a precondition for all other live-readiness phases. Without enforced CI checks:
- LR-002 (Contract Tests) could be skipped
- LR-003 (Kill-Switch Tests) could be skipped
- All P1-P4 validations could be bypassed

**Status:** ✅ GO - All pass criteria met, evidence documented
