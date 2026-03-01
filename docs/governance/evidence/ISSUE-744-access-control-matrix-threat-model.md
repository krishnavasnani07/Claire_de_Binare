# Evidence Spec for Issue #744 — P1 — Access Control Matrix & Threat Model (DB Layer)
Purpose:
- Create the governance anchor for DB-layer access control across Postgres and SurrealDB.
- Capture the current permission surface, explicit gaps, and the child-issue trace needed to harden the DB layer without changing runtime behavior.

Pass criteria:
- [x] INDEX metadata is present and aligned to Issue #744.
- [x] Evidence links are concrete where available and explicit where gaps remain.
- [x] Parent, child, and related issue links are traceable from this document.
- [x] Child issue mapping explicitly covers #741, #750, #751, #752, and #753.

Evidence plan:
- This anchor stays open until child DB-hardening issues close the current UNKNOWN/GAP entries with implementation evidence.
- Live privilege evidence is expected from grant dumps, migration verification, and integrity-guard changes tracked in child issues.

Current status:
- Matrix: Open
- GitHub: OPEN
- Date: 2026-03-01

---

## INDEX (Governance Anchor)

- Title: `P1 — Access Control Matrix & Threat Model (DB Layer)`
- Category: `Security Governance (ACM/Threat Model)`
- Gate-Level: `P1 / should`
- Status snapshot:
  - Matrix: `Open`
  - GitHub: `OPEN`
  - updatedAt: `2026-03-01T03:55:25Z`
- Owner metadata from issue body: `scope:core + prio:should + agent:gemini`
- Scope: `Role x Resource x Action (CRUD)` for Postgres and SurrealDB, plus bypass paths and control gaps.
- GitHub labels observed on Issue #744: `documentation`, `security`, `type:docs`, `type:security`, `type:research`, `scope:core`, `scope:docs`, `scope:monitoring`, `stage:proof`, `prio:must`, `agent:gemini`, `agent:copilot`
- Parent: [#749](https://github.com/jannekbuengener/Claire_de_Binare/issues/749) `Governance Core Gap — Strategy & Nexus Overview`
- Child issues:
  - [#741](https://github.com/jannekbuengener/Claire_de_Binare/issues/741) `Postgres Least-Privilege + RLS Hardening (Writer/Reader Split)`
  - [#750](https://github.com/jannekbuengener/Claire_de_Binare/issues/750) `Core Secrets Domain: Integrity Guards for core_secrets`
  - [#751](https://github.com/jannekbuengener/Claire_de_Binare/issues/751) `Governance Domain: Integrity Guards for audit_trail and governance_events`
  - [#752](https://github.com/jannekbuengener/Claire_de_Binare/issues/752) `Deployment Domain: Integrity Guards for deployment_approvals`
  - [#753](https://github.com/jannekbuengener/Claire_de_Binare/issues/753) `Access Domain: Integrity Guards for system_config and security_policies`
- Related:
  - [#641](https://github.com/jannekbuengener/Claire_de_Binare/issues/641) `Access Rules / RLS hardening`
  - [#663](https://github.com/jannekbuengener/Claire_de_Binare/issues/663) `Six-Eyes enforcement`

## Goal

Define a stable DB-layer governance anchor that records:

- the current Postgres and SurrealDB access model that is actually visible in-repo,
- the intended protection boundaries for audit, governance, access, and secret-adjacent domains,
- the bypass vectors that still exist, and
- the child issues that must close the remaining gaps.

## Scope

- Postgres roles and grants for runtime, governance, and security-adjacent tables.
- SurrealDB governance-mirror table permissions and documented access expectations.
- Comparison of visible `IST` permissions versus intended `SOLL` controls where those differ.
- Explicit documentation of forbidden or risky write paths such as shared credentials, migration/admin bypass, owner bypass, and manual SQL.

## Out of Scope

- Changing grants, migrations, RLS, triggers, or application behavior.
- Live database privilege dumps or environment-specific credential inspection.
- GitHub policy, workflow, or deployment changes.

## Access Control Matrix

### Postgres

| Role / principal | Resources | Create | Read | Update | Delete | Current state / notes |
|---|---|---|---|---|---|---|
| `claire_user` (runtime login before hardening) | `public` schema tables and sequences | CONDITIONAL | CONDITIONAL | CONDITIONAL | CONDITIONAL | `schema.sql` grants broad `ALL PRIVILEGES` to `claire_user`; `enforce_least_privilege.sql` is the compensating script that revokes and rebinds the runtime login to `cdb_writer`. Effective least privilege is therefore deployment-dependent, not guaranteed by schema alone. |
| `cdb_reader` | `signals`, `orders`, `trades`, `positions`, `portfolio_snapshots`, `risk_events`, `correlation_ledger`, `blocked_decisions`, `core_secrets_metadata`, `audit_trail`, `governance_events`, `deployment_approvals_mirror`, `system_config`, `security_policy_refs`, `schema_version` | DENY | ALLOW | DENY | DENY | Explicit `SELECT`-only allowlist in `roles_and_grants.sql`. No write path documented. |
| `cdb_writer` | `signals`, `orders`, `trades`, `portfolio_snapshots`, `risk_events`, `correlation_ledger`, `blocked_decisions` | ALLOW | ALLOW | DENY | DENY | Explicit `SELECT` + `INSERT`; no `UPDATE`, no `DELETE`. Intended for append-style runtime writes. |
| `cdb_writer` | `positions` | ALLOW | ALLOW | ALLOW | DENY | The only table with explicit `UPDATE` for the writer role. |
| `cdb_writer` | `schema_version` | DENY | ALLOW | DENY | DENY | Explicit read-only visibility for schema version checks. |
| `cdb_writer` | `core_secrets_metadata`, `audit_trail`, `governance_events`, `deployment_approvals_mirror`, `system_config`, `security_policy_refs` | DENY | DENY | DENY | DENY | No explicit grants found for the writer role in `roles_and_grants.sql`. This is good for least privilege if the hardening script has actually been enforced. |
| `cdb_admin` (deploy / migration role) | All tables and sequences in `public` | ALLOW | ALLOW | ALLOW | ALLOW | Full-power role intended for deployment and migration tasks. This role remains the main privilege-escalation and ownership-bypass surface. |

Postgres notes:

- `core_secrets` is referenced by child issue #750, but the inspected Postgres schema in-repo exposes `core_secrets_metadata`, not a `core_secrets` table.
- `system_config` exists in the Postgres grant file, but `security_policies` does not; the visible table is `security_policy_refs`.
- No active RLS policies were found in the inspected DB-layer artifacts. The runbook explicitly frames the current work as grant hardening first, not completed RLS enforcement.

### SurrealDB

| Role / scope | Resources | Create | Read | Update | Delete | Current state / notes |
|---|---|---|---|---|---|---|
| Implicit application principal (auth object not defined) | `audit_trail`, `deployment_approvals_mirror`, `system_config`, `security_policy_refs`, `access_matrix` | ALLOW | ALLOW | UNKNOWN (GAP) | UNKNOWN (GAP) | `setup.surql` explicitly spells `CREATE` and `SELECT` but does not declare named principals or explicit `UPDATE NONE` / `DELETE NONE` for these tables. The README describes them as append-only or read-oriented, but the auth boundary is undocumented. |
| Implicit application principal (auth object not defined) | `governance_events` | ALLOW | ALLOW | UNKNOWN (GAP) | UNKNOWN (GAP) | The permission clause in `setup.surql` appears syntactically malformed around `CREATE` / `SELECT`, so the effective permission surface should be treated as unverified until validated. |
| Implicit application principal (auth object not defined) | `ledger_event` | ALLOW | ALLOW | DENY | DENY | `setup.surql` explicitly sets `SELECT FULL`, `CREATE FULL`, `UPDATE NONE`, `DELETE NONE`. This is the clearest append-only control in the SurrealDB snapshot. |
| Namespace / database owner or admin (not defined in repo) | All tables in `governance.governance_mirror` | UNKNOWN (GAP) | UNKNOWN (GAP) | UNKNOWN (GAP) | UNKNOWN (GAP) | No `DEFINE USER`, `DEFINE ACCESS`, `DEFINE SCOPE`, or token configuration is present in the inspected SurrealDB artifacts, so the privileged-actor boundary is not documented here. |

SurrealDB notes:

- The inspected SurrealDB model documents table-level permissions, not authenticated actors. The actor dimension therefore remains partially unresolved by design and must be treated as a governance gap.
- `system_config` is present in SurrealDB, but `security_policies` is not; the visible table is `security_policy_refs`.
- The SurrealDB mirror is documented as governance-oriented and out-of-scope for secrets values, production balances, and live order routing.

## Threat Model (DB Layer)

| Threat / bypass vector | Current exposure | Current or planned control | Tracking |
|---|---|---|---|
| Shared or direct DB credentials (`claire_user`, PAT-backed ops, manual SQL clients) | A single runtime login can be over-privileged if `enforce_least_privilege.sql` has not been applied in the target environment. | Revoke broad grants, bind runtime access to reader/writer split, and verify effective grants from live DB. | [#741](https://github.com/jannekbuengener/Claire_de_Binare/issues/741), [#641](https://github.com/jannekbuengener/Claire_de_Binare/issues/641) |
| Privilege escalation via migration / deploy role | `cdb_admin` has full schema, table, and sequence power; manual ownership transfer is an explicit step in the runbook. | Keep admin role deploy-only, separate credentials from runtime, and add verifiable least-privilege evidence. | [#741](https://github.com/jannekbuengener/Claire_de_Binare/issues/741) |
| RLS bypass via owner/admin or absent RLS | No active RLS policies were found in the inspected repo artifacts, and table ownership can bypass grant intent. | Add actual RLS and least-privilege proof rather than relying on grant scripts alone. | [#741](https://github.com/jannekbuengener/Claire_de_Binare/issues/741), [#641](https://github.com/jannekbuengener/Claire_de_Binare/issues/641) |
| Append-only violations on `audit_trail`, `governance_events`, and deployment mirrors | Writer grants already avoid these Postgres tables, but admin/manual SQL can still mutate them; several SurrealDB tables do not explicitly declare `UPDATE NONE` / `DELETE NONE`. | Add integrity guards and append-only enforcement in the governance and deployment domains. | [#751](https://github.com/jannekbuengener/Claire_de_Binare/issues/751), [#752](https://github.com/jannekbuengener/Claire_de_Binare/issues/752) |
| Out-of-band writes through scripts or manual SQL | Scripts and operator commands can write outside the normal application control path, especially during setup or recovery. | Narrow allowed write principals, document approved operational paths, and verify them with audits. | [#749](https://github.com/jannekbuengener/Claire_de_Binare/issues/749), [#741](https://github.com/jannekbuengener/Claire_de_Binare/issues/741) |
| Schema drift or missing grant enforcement | `schema.sql`, `roles_and_grants.sql`, `enforce_least_privilege.sql`, and verification comments can diverge across environments. | Treat live grant dump plus migration verification as the source of truth and attach that evidence to the hardening issues. | [#741](https://github.com/jannekbuengener/Claire_de_Binare/issues/741), [#749](https://github.com/jannekbuengener/Claire_de_Binare/issues/749) |
| Secrets exposure in `system_config`, `security_policy_refs`, and `core_secrets_metadata` adjacency | The inspected schema exposes metadata and policy-reference surfaces, but not a clearly hardened secrets/access domain end state. | Add integrity guards and explicit domain boundaries for secrets and access-policy records. | [#750](https://github.com/jannekbuengener/Claire_de_Binare/issues/750), [#753](https://github.com/jannekbuengener/Claire_de_Binare/issues/753) |
| SurrealDB auth ambiguity | Table permissions exist, but named SurrealDB users/scopes/access methods do not appear in-repo, so actor accountability is incomplete. | Document or implement the auth boundary explicitly, or treat the mirror as internal-only with enforced operational controls. | [#753](https://github.com/jannekbuengener/Claire_de_Binare/issues/753), [#749](https://github.com/jannekbuengener/Claire_de_Binare/issues/749) |

## Crosslinks and Child Mapping

### Parent / meta anchor

| Issue | Status | Relation | What it delivers |
|---|---|---|---|
| [#749](https://github.com/jannekbuengener/Claire_de_Binare/issues/749) | OPEN | Parent / meta | Program-level governance gap overview that links the DB-hardening slices into one roadmap. |

### Child issues

| Issue | Status | What it delivers |
|---|---|---|
| [#741](https://github.com/jannekbuengener/Claire_de_Binare/issues/741) | CLOSED | Establishes the Postgres least-privilege baseline and the writer/reader split; this anchor depends on its grant model but still needs live-environment proof. |
| [#750](https://github.com/jannekbuengener/Claire_de_Binare/issues/750) | OPEN | Hardens the `core_secrets` domain and should resolve the remaining integrity boundary around `core_secrets_metadata` and secret-adjacent flows. |
| [#751](https://github.com/jannekbuengener/Claire_de_Binare/issues/751) | CLOSED | Adds integrity guard intent for `audit_trail` and `governance_events`; this closes part of the append-only threat model but not the full DB-layer matrix. |
| [#752](https://github.com/jannekbuengener/Claire_de_Binare/issues/752) | OPEN | Hardens the deployment-approval domain, especially append-only and anti-bypass expectations for `deployment_approvals`. |
| [#753](https://github.com/jannekbuengener/Claire_de_Binare/issues/753) | OPEN | Hardens the access domain around `system_config` and `security_policies`; this anchor notes that the inspected schema currently exposes `system_config` and `security_policy_refs`, not a `security_policies` table. |

### Related issues

| Issue | Status | Why it matters here |
|---|---|---|
| [#641](https://github.com/jannekbuengener/Claire_de_Binare/issues/641) | CLOSED | Earlier least-privilege / append-only / RLS hardening track that informs the intended control model for this anchor. |
| [#663](https://github.com/jannekbuengener/Claire_de_Binare/issues/663) | CLOSED | Six-eyes governance control relevant to who is allowed to approve high-impact changes, even though this anchor stays focused on DB access paths. |

## Evidence

### Issue-linked evidence from #744

- Issue: [#744](https://github.com/jannekbuengener/Claire_de_Binare/issues/744)
- PR: [#911](https://github.com/jannekbuengener/Claire_de_Binare/pull/911) `deps(actions): bump actions/upload-artifact from 4.6.2 to 6.0.0`
- Run: [22291780927](https://github.com/jannekbuengener/Claire_de_Binare/actions/runs/22291780927) `Claude Code Review`
- Run: [22291780930](https://github.com/jannekbuengener/Claire_de_Binare/actions/runs/22291780930) `ci`
- Run: [22291780252](https://github.com/jannekbuengener/Claire_de_Binare/actions/runs/22291780252) `Automatic Dependency Submission`

### Repo artifacts used for the current-state matrix

- `infrastructure/database/roles_and_grants.sql`
- `infrastructure/database/schema.sql`
- `infrastructure/database/enforce_least_privilege.sql`
- `docs/runbooks/postgres_least_privilege_rls.md`
- `infrastructure/surrealdb/setup.surql`
- `infrastructure/surrealdb/README.md`
- `docs/surrealdb/data-ownership-matrix.md`

### Explicit gaps

- No live Postgres grant dump or `\du` / `information_schema` evidence is attached here, so effective runtime privileges in deployed environments remain partially unverified. This is the main gap for [#741](https://github.com/jannekbuengener/Claire_de_Binare/issues/741).
- No active Postgres RLS policy definitions were found in the inspected repo snapshot. Any "RLS" expectation must therefore be treated as planned or historical unless child evidence proves otherwise.
- No explicit SurrealDB users, scopes, or access tokens are defined in the inspected repo artifacts, so actor attribution in the SurrealDB matrix remains `UNKNOWN (GAP)`.
- The SurrealDB `governance_events` permission line appears malformed in `setup.surql`, so its effective append-only semantics are not yet provable from the checked-in file alone.
- The inspected DB layer exposes `core_secrets_metadata` and `security_policy_refs`; it does not expose `core_secrets` or `security_policies` tables directly. The child issues still define the intended target domains and remain the correct implementation trace.
