# Branch Protection Drift Report (main)

Timestamp (Europe/Berlin): `2026-02-19T20:37:26+01:00`  
Timestamp (UTC): `2026-02-19T19:37:26Z`  
Repo: `jannekbuengener/Claire_de_Binare`  
Branch: `main`  
State: **NO DRIFT**

## Inputs

- Baseline file: `reports/BRANCH_PROTECTION_BASELINE_main.json`
- Current source: `live gh api`
- Normalization: sorted keys; unordered-list normalization for known set-like arrays; volatile-field stripping: none

## Hashes (SHA256)

- Baseline snapshot hash: `fdaeb7004820356e6a8bcdb9978d6dc3a66bae52e3edf14e7ed52cffbd027ae0`
- Current snapshot hash: `fdaeb7004820356e6a8bcdb9978d6dc3a66bae52e3edf14e7ed52cffbd027ae0`

## Drift Summary

- none

## Unified Diff (normalized JSON)

```diff
(no diff)
```

## Manual Apply Commands (maintainer only, never auto-executed)

```bash
gh api repos/jannekbuengener/Claire_de_Binare/branches/main/protection > reports/BRANCH_PROTECTION_CURRENT_main.json
gh api --method PUT repos/jannekbuengener/Claire_de_Binare/branches/main/protection --input reports/BRANCH_PROTECTION_APPLY_PAYLOAD_main.json
gh api --method DELETE repos/jannekbuengener/Claire_de_Binare/branches/main/protection/required_signatures
```

Safety note: this checker is read-only and does not run apply commands.
