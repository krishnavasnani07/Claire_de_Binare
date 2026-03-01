"""Validate access-domain integrity metadata for mirror records."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from core.replay.canonical_json import canonical_json_dumps

SUPPORTED_INTEGRITY_ALGO = "HMAC-SHA256"
SUPPORTED_INTEGRITY_VERSION = 1
DEFAULT_ENV_VAR = "CDB_ACCESS_INTEGRITY_KEY"

ACCESS_INTEGRITY_KEY_MISSING = "ACCESS_INTEGRITY_KEY_MISSING"
ACCESS_INTEGRITY_HASH_MISMATCH = "ACCESS_INTEGRITY_HASH_MISMATCH"
ACCESS_INTEGRITY_METADATA_MISSING = "ACCESS_INTEGRITY_METADATA_MISSING"
ACCESS_INTEGRITY_RECORD_TYPE_UNSUPPORTED = "ACCESS_INTEGRITY_RECORD_TYPE_UNSUPPORTED"
ACCESS_INTEGRITY_IDENTIFIER_MISSING = "ACCESS_INTEGRITY_IDENTIFIER_MISSING"
ACCESS_INTEGRITY_UNSUPPORTED_ALGO = "ACCESS_INTEGRITY_UNSUPPORTED_ALGO"
ACCESS_INTEGRITY_UNSUPPORTED_VERSION = "ACCESS_INTEGRITY_UNSUPPORTED_VERSION"

_TABLE_ALIASES = {
    "global_settings": "system_config",
    "security_policies": "security_policy_refs",
    "security_policy_refs": "security_policy_refs",
    "system_config": "system_config",
}

_DISPLAY_NAMES = {
    "security_policy_refs": "security_policies",
    "system_config": "system_config",
}

_IDENTIFIER_FIELDS = {
    "security_policy_refs": ("policy_id",),
    "system_config": ("config_key",),
}

_HASH_EXCLUDED_FIELDS = frozenset(
    {
        "_table",
        "integrity_algo",
        "integrity_chain_hash",
        "integrity_hash",
        "integrity_prev_hash",
        "integrity_version",
        "record_type",
        "table",
    }
)


@dataclass(frozen=True)
class SnapshotRecord:
    table: str
    record: dict[str, Any]


@dataclass(frozen=True)
class ValidationResult:
    table: str
    identifier: str
    status: str
    reason: str
    stored_hash: str | None
    expected_hash: str | None


def _normalize_table_name(raw_table: str) -> str | None:
    return _TABLE_ALIASES.get(str(raw_table).strip())


def _display_table_name(table: str) -> str:
    return _DISPLAY_NAMES.get(table, table)


def _record_identifier(table: str, record: dict[str, Any]) -> str | None:
    fields = _IDENTIFIER_FIELDS.get(table)
    if fields is None:
        return None
    values: list[str] = []
    for field in fields:
        value = record.get(field)
        if value is None or str(value).strip() == "":
            return None
        values.append(str(value))
    return ":".join(values)


def _payload_for_hash(record: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value for key, value in record.items() if key not in _HASH_EXCLUDED_FIELDS
    }


def compute_integrity_hash(record: dict[str, Any], key: str) -> str:
    payload = canonical_json_dumps(_payload_for_hash(record)).encode("utf-8")
    digest = hmac.new(key.encode("utf-8"), payload, hashlib.sha256)
    return digest.hexdigest()


def validate_record(
    snapshot_record: SnapshotRecord,
    *,
    key: str | None,
) -> ValidationResult:
    table = snapshot_record.table
    record = snapshot_record.record
    identifier = _record_identifier(table, record) or "<missing>"
    stored_hash = record.get("integrity_hash")

    if table not in _IDENTIFIER_FIELDS:
        return ValidationResult(
            table=table,
            identifier=identifier,
            status="FAIL",
            reason=ACCESS_INTEGRITY_RECORD_TYPE_UNSUPPORTED,
            stored_hash=str(stored_hash) if stored_hash is not None else None,
            expected_hash=None,
        )

    if not key:
        return ValidationResult(
            table=table,
            identifier=identifier,
            status="FAIL",
            reason=ACCESS_INTEGRITY_KEY_MISSING,
            stored_hash=str(stored_hash) if stored_hash is not None else None,
            expected_hash=None,
        )

    if identifier == "<missing>":
        return ValidationResult(
            table=table,
            identifier=identifier,
            status="FAIL",
            reason=ACCESS_INTEGRITY_IDENTIFIER_MISSING,
            stored_hash=str(stored_hash) if stored_hash is not None else None,
            expected_hash=None,
        )

    if not isinstance(stored_hash, str) or not stored_hash.strip():
        return ValidationResult(
            table=table,
            identifier=identifier,
            status="FAIL",
            reason=ACCESS_INTEGRITY_METADATA_MISSING,
            stored_hash=None,
            expected_hash=None,
        )

    integrity_algo = record.get("integrity_algo")
    if integrity_algo != SUPPORTED_INTEGRITY_ALGO:
        return ValidationResult(
            table=table,
            identifier=identifier,
            status="FAIL",
            reason=ACCESS_INTEGRITY_UNSUPPORTED_ALGO,
            stored_hash=stored_hash,
            expected_hash=None,
        )

    integrity_version = record.get("integrity_version")
    if integrity_version != SUPPORTED_INTEGRITY_VERSION:
        return ValidationResult(
            table=table,
            identifier=identifier,
            status="FAIL",
            reason=ACCESS_INTEGRITY_UNSUPPORTED_VERSION,
            stored_hash=stored_hash,
            expected_hash=None,
        )

    expected_hash = compute_integrity_hash(record, key)
    status = "OK" if hmac.compare_digest(stored_hash, expected_hash) else "FAIL"
    reason = "OK" if status == "OK" else ACCESS_INTEGRITY_HASH_MISMATCH
    return ValidationResult(
        table=table,
        identifier=identifier,
        status=status,
        reason=reason,
        stored_hash=stored_hash,
        expected_hash=expected_hash,
    )


def validate_records(
    snapshot_records: Sequence[SnapshotRecord],
    *,
    key: str | None,
) -> list[ValidationResult]:
    ordered = sorted(
        snapshot_records,
        key=lambda item: (
            _display_table_name(item.table),
            _record_identifier(item.table, item.record) or "",
        ),
    )
    return [validate_record(record, key=key) for record in ordered]


def _coerce_records(table: str, value: Any) -> list[SnapshotRecord]:
    if not isinstance(value, list):
        raise ValueError(f"table '{table}' must map to a list of objects")
    normalized = _normalize_table_name(table)
    if normalized is None:
        raise ValueError(f"unsupported table '{table}'")

    records: list[SnapshotRecord] = []
    for record in value:
        if not isinstance(record, dict):
            raise ValueError(f"table '{table}' contains a non-object record")
        records.append(SnapshotRecord(table=normalized, record=dict(record)))
    return records


def load_snapshot_records(path: Path) -> list[SnapshotRecord]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        records: list[SnapshotRecord] = []
        for table in sorted(payload):
            records.extend(_coerce_records(table, payload[table]))
        return records

    if isinstance(payload, list):
        records = []
        for entry in payload:
            if not isinstance(entry, dict):
                raise ValueError("flat snapshot entries must be objects")
            raw_table = (
                entry.get("table") or entry.get("record_type") or entry.get("_table")
            )
            normalized = _normalize_table_name(str(raw_table))
            if normalized is None:
                raise ValueError(f"unsupported table '{raw_table}'")
            record = {
                key: value
                for key, value in entry.items()
                if key not in {"table", "record_type", "_table"}
            }
            records.append(SnapshotRecord(table=normalized, record=record))
        return records

    raise ValueError("snapshot must be a JSON object or array")


def render_report(results: Sequence[ValidationResult], *, env_var: str) -> str:
    ok_count = sum(1 for result in results if result.status == "OK")
    fail_count = len(results) - ok_count
    lines = [
        "# Access Integrity Report",
        "",
        f"Records: {len(results)}",
        f"OK: {ok_count}",
        f"FAIL: {fail_count}",
        "",
        "## Notes",
        "- Canonical payload excludes `integrity_hash`, `integrity_algo`, `integrity_version`.",
        f"- Missing `{env_var}` is fail-closed for every record.",
        "- `security_policies` input is normalized to storage table `security_policy_refs`.",
    ]

    grouped_tables = sorted({_display_table_name(result.table) for result in results})
    for display_table in grouped_tables:
        lines.extend(["", f"## {display_table}"])
        if display_table == "security_policies":
            lines.append("Storage table: `security_policy_refs`")
        matching = [
            result
            for result in results
            if _display_table_name(result.table) == display_table
        ]
        for result in matching:
            stored_hash = result.stored_hash or "-"
            expected_hash = result.expected_hash or "-"
            lines.append(
                f"- `{result.identifier}` status=`{result.status}` reason=`{result.reason}` "
                f"stored=`{stored_hash}` expected=`{expected_hash}`"
            )

    if not results:
        lines.extend(["", "## Records", "- None"])

    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate access-domain mirror integrity hashes."
    )
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="JSON snapshot of system_config/security_policies records",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/access-integrity-report.md"),
        help="Markdown report output path",
    )
    parser.add_argument(
        "--env-var",
        default=DEFAULT_ENV_VAR,
        help="Environment variable containing the HMAC key",
    )
    args = parser.parse_args(argv)

    snapshot_records = load_snapshot_records(args.input)
    key = os.getenv(args.env_var)
    results = validate_records(snapshot_records, key=key)
    report = render_report(results, env_var=args.env_var)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    return 0 if all(result.status == "OK" for result in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
