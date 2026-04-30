# Context Intelligence — Ingestion Scope and Classification Rules

**Issue**: #1986
**Parent**: #1985
**Epic**: #1976
**Depends on**: #1978, #1981
**Status**: Canonical — implementation target for #2045 (separate implementation GO required)

---

> **DISCLAIMER — NO LIVE DB AUTHORIZATION**
>
> Reading, indexing, or ingesting repository context as defined in this document does **NOT** authorize,
> imply, or constitute a connection to any live SurrealDB instance. Any future connection to a live or
> production SurrealDB instance requires a separate, explicit implementation GO issued through the
> canonical Live-Readiness process (`docs/live-readiness/`). Live-Readiness verdict as of
> 2026-03-05 remains **NO-GO**. Board stage `trade-capable` does not override this verdict.

---

## 1. Purpose

This document defines the authoritative ingestion scope and classification rules for the CDB Context
Intelligence system. It governs which repository paths and file types may be ingested into a context
index, how content is classified by sensitivity, and what guardrails apply at ingest time.

This document is the single source of truth for scope decisions. All tooling, agents, and pipelines
that perform context ingestion MUST derive their scope configuration from this document.

Exclude rules always take precedence over include rules. When a path matches both, it is excluded.

---

## 2. Scope Roots

### 2.1 Allowed Roots (always eligible for ingestion)

| Root | Rationale |
|:-----|:----------|
| `docs/` | Project documentation, runbooks, architecture, and governance docs |
| `knowledge/` | Canonical knowledge hub, governance policies, and shared decisions |
| `agents/` | Agent registry, roles, and operating conventions |
| `infrastructure/surrealdb/` | SurrealDB-specific infrastructure definitions |
| `infrastructure/config/surrealdb/` | SurrealDB configuration files |
| `tools/surrealdb/` | SurrealDB tooling and utility scripts |
| `README.md` (root README.md and README.md files under allowed roots) | Entry-point orientation documents |

### 2.2 Conditional Roots (eligible only with explicit scope-config approval)

These roots contain mixed content. Ingestion requires explicit opt-in in the scope configuration and
per-file sensitivity classification at ingest time.

| Root | Rationale | Condition |
|:-----|:----------|:----------|
| `core/` | Core trading and system logic; may contain sensitive constructs | Explicit approval per module |
| `services/` | Service implementations; may contain execution or risk logic | Explicit approval per service |
| `tests/` | Unit and integration tests; generally safe but may reference fixtures | Explicit approval per suite |
| `infrastructure/compose/` | Docker Compose definitions; may contain port/secret references | Explicit approval, secret-scrubbed only |

### 2.3 Excluded Roots (never eligible — exclusions override all include rules)

| Path Pattern | Reason |
|:-------------|:-------|
| `.git/` | Version control internals |
| `.venv/` | Python virtual environment; third-party binaries |
| `.worktrees/` | Git worktree state |
| `logs/` | Runtime log output; may contain sensitive runtime state |
| `artifacts/**` (automatic discovery) | Generated artifacts are excluded by default. No automatic ingestion from `artifacts/`; only explicitly reviewed, allow-listed report artifacts may be referenced or ingested |
| `artifacts/context-indexer/` | Self-ingestion prevention |
| `tmp/` | Temporary files |
| `temp/` | Temporary files |
| `tmp/context-indexer/` | Self-ingestion prevention |
| `temp/context-indexer/` | Self-ingestion prevention |
| `docs/archive/` | Historical snapshots; no longer canonical |
| `knowledge/archive/` | Historical snapshots; no longer canonical |
| `**/archive/` | Any archive subdirectory unless explicitly referenced and reviewed |
| `**/.env*` | Environment and secrets files |
| `**/*.key`, `**/*.pem`, `**/*.p12` | Cryptographic key material |
| Runtime order / position / fill state paths | Live trading state only; excludes runtime state, not approved static source code |
| Runtime risk-state snapshots / ledgers / caches / exports | Runtime risk state only; approved `core/` / `services/` source code is not excluded by directory name alone |
| Execution-state snapshots / ledgers / queues / exports | Execution state only; approved `core/` / `services/` source code is not excluded by directory name alone |
| `**/secrets/**` | Secrets directories |
| Binary archives (`.zip`, `.tar`, `.gz`, etc.) | Not human-readable; ingest only if explicitly referenced and manually reviewed |

---

## 3. File Type Classifications

Only the following file types are eligible for ingestion. Any file type not listed here is excluded
by default.

| File Type | Extensions | Scope Class | Notes |
|:----------|:-----------|:------------|:------|
| Markdown | `.md`, `.mdx` | `documentation` | Primary documentation format |
| YAML | `.yml`, `.yaml` | `configuration` | Config, CI/CD, compose; apply secret scrub |
| JSON | `.json` | `configuration` | Config and schema files |
| Python | `.py` | `source_code` | Conditional roots only; apply sensitivity check |
| TOML | `.toml` | `configuration` | Project config (`pyproject.toml`, etc.) |
| Shell / PowerShell | `.sh`, `.ps1`, `.bash` | `source_code` | Utility scripts; verify no embedded secrets |
| Docker Compose YAML | `compose*.yml`, `compose*.yaml` | `configuration` | Apply secret scrub; port references OK |
| Plain text | `.txt` | `documentation` | Only in `docs/` and `knowledge/` roots |
| reStructuredText | `.rst` | `documentation` | Documentation only |

File types explicitly excluded regardless of root:

- `.env`, `.env.*` — secrets
- `*.key`, `*.pem`, `*.p12`, `*.pfx` — cryptographic material
- `*.pyc`, `*.pyo`, `__pycache__/` — compiled Python
- `*.log` — runtime logs
- `*.sqlite`, `*.db` — database files
- `*.zip`, `*.tar`, `*.gz`, `*.tgz` — binary archives (unless explicitly reviewed)
- `*.pkl`, `*.pickle` — serialized Python objects

---

## 4. Sensitivity Classification

Content is classified on two independent axes: **Scope Class** (what it is) and **Sensitivity Class**
(how sensitive it is). Both must be evaluated at ingest time.

### 4.1 Scope Classes

| Class | Description |
|:------|:------------|
| `documentation` | Markdown and text documentation artifacts |
| `configuration` | YAML, JSON, TOML configuration files |
| `source_code` | Python and shell source code |
| `governance` | Governance policies, constitutions, and audit records |
| `generated_artifacts` | System-generated reports and evidence artifacts — excluded by default; eligible only after explicit review and allow-listing |
| `archives` | Historical artifacts — excluded by default |
| `secrets` | Secret or credential material — always excluded |
| `runtime_state` | Runtime operational state — always excluded |
| `trading_state` | Orders, positions, fills, runtime risk state, and execution state — always excluded |

### 4.2 Sensitivity Classes

| Class | Description | Typical Paths | Ingest | Guardrail |
|:------|:------------|:--------------|:-------|:----------|
| `public_context` | Non-sensitive project context safe for broad sharing | `docs/`, `knowledge/`, `agents/`, root README.md and README.md files under allowed roots | Yes | None beyond file-type check |
| `internal_context` | Internal but non-sensitive; suitable for agent and tooling use | `infrastructure/surrealdb/`, `tools/surrealdb/`, `tests/` | Yes | Per-file sensitivity check required |
| `sensitive_metadata` | Metadata touching architecture, ops, or infrastructure | `infrastructure/compose/`, `core/`, `services/` | Conditional | Secret scrub mandatory; explicit approval |
| `forbidden` | High-sensitivity or trading-critical content | `**/.env*`, `**/orders/**`, `**/secrets/**` | **Never** | Fail-closed; block and alert |

> Note: Scope Class and Sensitivity Class are orthogonal. A `configuration` file can be `forbidden`
> (e.g., a `.env` YAML). Evaluate both axes independently.

---

## 5. Guardrails

The following rules are non-negotiable and must be enforced at every ingest boundary:

1. **Fail-Closed**: Any content that cannot be unambiguously classified must be excluded. When in doubt, exclude.
2. **No Secrets**: Secrets, credentials, API keys, and cryptographic material must never appear in the context index. Detect via pattern matching (gitleaks-compatible rules) before indexing.
3. **No Trading State**: Orders, positions, fills, runtime risk state, and execution state are permanently excluded. Static source code under approved conditional roots is not excluded by directory name alone. This is not configurable.
4. **No Runtime State**: Live system metrics, log files, and runtime snapshots are permanently excluded.
5. **Path Sanitization**: All paths in the index must be repository-relative. Absolute paths are forbidden.
6. **Deterministic Classification**: Given the same commit SHA and scope configuration, classification results must be identical across runs.
7. **Exclusions Override Inclusions**: If a path matches both an include rule and an exclude rule, it is excluded. No exception.
8. **Self-Ingestion Prevention**: The context indexer must not ingest its own output artifacts (`artifacts/context-indexer/`, `tmp/context-indexer/`, `temp/context-indexer/`).
9. **Generated Artifacts Default-Deny**: Generated artifacts are excluded by default. Only explicitly reviewed and allow-listed report artifacts may be referenced or ingested, never via automatic discovery of `artifacts/`.
10. **Secret Scrub on Conditional Roots**: Any file from a conditional root (`core/`, `services/`, `infrastructure/compose/`) must pass a secret-scrub check before indexing.
11. **No Live DB Authorization**: Defining or consuming this scope document does not authorize connection to any live SurrealDB instance. See Disclaimer at top of this document.

---

## 6. Classification Matrix

| Path Pattern | Scope Class | Sensitivity Class | Ingest | Notes |
|:-------------|:------------|:------------------|:-------|:------|
| `docs/**/*.md` | `documentation` | `public_context` | Yes | Always eligible |
| `knowledge/**/*.md` | `governance` | `public_context` | Yes | Always eligible |
| `agents/**/*.md` | `documentation` | `public_context` | Yes | Always eligible |
| `infrastructure/surrealdb/**` | `configuration` | `internal_context` | Yes | Per-file check |
| `infrastructure/config/surrealdb/**` | `configuration` | `internal_context` | Yes | Per-file check |
| `tools/surrealdb/**` | `configuration` | `internal_context` | Yes | Per-file check |
| `README.md` | `documentation` | `public_context` | Yes | Root README.md and README.md files under allowed roots |
| `core/**/*.py` | `source_code` | `sensitive_metadata` | Conditional | Explicit approval; secret scrub; directory names such as `risk` or `execution` do not block approved static source code by themselves |
| `services/**/*.py` | `source_code` | `sensitive_metadata` | Conditional | Explicit approval; secret scrub; directory names such as `risk` or `execution` do not block approved static source code by themselves |
| `tests/**/*.py` | `source_code` | `internal_context` | Conditional | Explicit approval |
| `infrastructure/compose/**/*.yml` | `configuration` | `sensitive_metadata` | Conditional | Secret scrub mandatory |
| `docs/archive/**` | `archives` | `internal_context` | No | Historical; excluded |
| `knowledge/archive/**` | `archives` | `internal_context` | No | Historical; excluded |
| `**/archive/**` | `archives` | `internal_context` | No | Historical; excluded |
| `**/.env*` | `secrets` | `forbidden` | **Never** | Fail-closed |
| `**/*.key`, `**/*.pem` | `secrets` | `forbidden` | **Never** | Fail-closed |
| Runtime order-state paths | `trading_state` | `forbidden` | **Never** | Fail-closed; runtime/live state only |
| Runtime position-state paths | `trading_state` | `forbidden` | **Never** | Fail-closed; runtime/live state only |
| Runtime fill-state paths | `trading_state` | `forbidden` | **Never** | Fail-closed; runtime/live state only |
| Runtime risk-state snapshots / ledgers / caches / exports | `trading_state` | `forbidden` | **Never** | Fail-closed; approved `core/` / `services/` source code remains conditional |
| Execution-state snapshots / ledgers / queues / exports | `trading_state` | `forbidden` | **Never** | Fail-closed; approved `core/` / `services/` source code remains conditional |
| `artifacts/**` (automatic discovery) | `generated_artifacts` | `internal_context` | No | Excluded by default; no automatic ingestion of `artifacts/` |
| Reviewed, allow-listed report artifacts explicitly referenced by scope config | `generated_artifacts` | `internal_context` | Conditional | Explicit review required; never include context-indexer outputs |
| `artifacts/context-indexer/**` | `generated_artifacts` | `internal_context` | No | Self-ingestion prevention; never ingest indexer output |
| `tmp/context-indexer/**` | `generated_artifacts` | `internal_context` | No | Self-ingestion prevention; never ingest indexer output |
| `temp/context-indexer/**` | `generated_artifacts` | `internal_context` | No | Self-ingestion prevention; never ingest indexer output |
| `logs/**` | `runtime_state` | `forbidden` | **Never** | Runtime state |

---

## 7. Determinism Requirements

- Ingestion must produce a stable, sorted file list given the same commit SHA and scope configuration.
- All paths must be repository-relative; no absolute paths permitted.
- File identity must not depend on dynamic timestamps or environment variables.
- Classification must be reproducible: same commit + same scope config → same classification result.
- Exclude rules always override include rules (no exception path).
- Explicit scope-config overrides for conditional roots must themselves be deterministic and committed to the repository.

---

## 8. Dependencies

| Issue | Description | Status |
|:------|:------------|:-------|
| #1978 | SurrealDB schema foundation | Dependency — must be resolved first |
| #1981 | Context Intelligence architecture | Dependency — must be resolved first |
| #1987 | Hashing rules for context chunks | Downstream — prepared, not implemented |
| #1988 | Chunking model | Downstream — prepared, not implemented |
| #1989 | CLI contract for context tooling | Downstream — depends on PR status |
| #2045 | Implementation of context ingestion pipeline | Downstream — requires separate implementation GO |

---

## 9. Change Control

Changes to this document require:

1. A GitHub issue referencing the parent epic (#1976).
2. Human review and approval before merge.
3. Update to `knowledge/CDB_KNOWLEDGE_HUB.md` if the scope change affects downstream agents or tooling.
4. No change to this document authorizes connection to a live SurrealDB instance.
