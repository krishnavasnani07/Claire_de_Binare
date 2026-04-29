# Context Intelligence — Ingestion Scope and Classification Rules (#1986)

**Status**: Draft
**Authority**: Issue #1986 / Parent #1985 / Epic #1976

---

## 1. Zweck
Dieses Dokument definiert den autorisierten Ingest-Scope und die Klassifikationsregeln für das Context Intelligence System.
Es dient der Absicherung gegen den Index-Import von sensitiven, irrelevanten oder gefährlichen Daten.

---

## 2. Scope-Klassen
Daten werden in folgende Klassen eingeteilt:

| Klasse | Beschreibung |
| :--- | :--- |
| `source_code` | Repo-eigener Source Code |
| `documentation` | Markdown/Dokumentations-Artefakte |
| `configuration` | YAML/TOML/JSON Konfigurationen |
| `tests` | Unit-/Integrationstests |
| `governance` | Governance-Richtlinien und Audits |
| `generated_artifacts` | Vom System erzeugte Reports (nach Prüfung) |
| `archives` | Historische Artefakte (nur Read-only) |
| `temporary_files` | (Ausgeschlossen) |
| `secrets_or_sensitive` | (Ausgeschlossen) |
| `runtime_state` | (Ausgeschlossen) |
| `trading_state` | (Ausgeschlossen) |

---

## 3. Include-Regeln (Inclusions)
Grundsätzlich ingestierbar sind folgende Pfade:
- `docs/`
- `knowledge/`
- `agents/`
- `infrastructure/surrealdb/`
- `infrastructure/config/surrealdb/`
- `tools/surrealdb/`
- `README.md` (root & submodule-level)

Bedingt ingestierbar (nach expliziter Prüfung):
- `core/`
- `services/`
- `tests/`
- `infrastructure/compose/`

---

## 4. Exclude-Regeln (Exclusions)
Folgende Pfade und Muster sind zwingend ausgeschlossen:
- `.git/`
- `.venv/`
- `.worktrees/`
- `logs/`
- `artifacts/`
- `tmp/`
- Secrets/Passwörter (via `.secretsignore`)
- Trading/Runtime-State (Orders, positions, fills, risk/execution state)
- Lock-files mit sensiblen Daten
- Binär-Archive (außer explizit zugelassen)

---

## 5. Sicherheitsregeln
1. **Maskierung**: Sensitive Treffer müssen maskiert werden.
2. **Fail-Closed**: Bei unklaren Inhalten ist der Ingest zu stoppen.
3. **No Secrets**: Secrets dürfen unter keinen Umständen im Context Index landen.
4. **Path Sanitization**: Keine absoluten Paths verwenden, nur repo-relative.

---

## 6. Klassifikationsmatrix

| Muster | Klasse | Ingest | Risiko |
| :--- | :--- | :--- | :--- |
| `docs/**/*.md` | `documentation` | Ja | Niedrig |
| `infrastructure/surrealdb/*` | `configuration` | Ja | Mittel |
| `core/trading/*` | `trading_state` | **Nein** | Hoch |
| `**/.env*` | `secrets` | **Nein** | Kritisch |

---

## 7. Determinismus
- Ingest muss stabil sortiert sein.
- Pfade müssen immer repo-relativ angegeben werden.
- Identität einer Datei darf nicht von dynamischen Timestamps abhängen.

---

## 8. Abhängigkeiten
- #1987 (Hashing-Regeln): In Arbeit.
- #1988 (Chunking-Modell): In Arbeit.
- #1989 (CLI-Vertrag): Siehe PR #2215 (Pending Review).

---

## 9. Ausblick
- #2045: Automatisierte Klassifizierung (Implementierungs-Slice erforderlich).

---
