# Evidence Spec for Issue #753 — Access Integrity Guard

Purpose:
- Prove deterministic integrity detection for `system_config` and `security_policies` mirror records.
- Keep the evidence contract stable until PR and CI links are filled in.

Pass criteria:
- [ ] At least one implementation PR is linked.
- [ ] At least one CI/test run is linked.
- [ ] At least one doc/spec reference explains hash scope, ENV requirements, and fail-closed behavior.

---

## Implementation

- PR: TODO
- CI/Test run: TODO
- Doc/ADR: `docs/surrealdb/access-integrity-guard.md`

### What Changed

- Added `system_config` mirror storage with integrity metadata.
- Added `integrity_algo` and `integrity_version` to the repo storage for `security_policies` (`security_policy_refs`).
- Added a deterministic validator/report CLI using canonical JSON + `HMAC-SHA256`.

### ENV Requirement

- `CDB_ACCESS_INTEGRITY_KEY`

### Status Codes

- `0`: all records verified
- `2`: integrity mismatch, unsupported metadata, or missing key
- `1`: parser/runtime failure

### Tests

- Unit: OK case
- Unit: tampered field -> `ACCESS_INTEGRITY_HASH_MISMATCH`
- Unit: missing `CDB_ACCESS_INTEGRITY_KEY` -> fail-closed
