"""Unit tests for the access-domain integrity guard."""

import json
from pathlib import Path

import pytest

from tools.surrealdb.access_integrity_guard import (
    ACCESS_INTEGRITY_HASH_MISMATCH,
    ACCESS_INTEGRITY_KEY_MISSING,
    SnapshotRecord,
    SUPPORTED_INTEGRITY_ALGO,
    SUPPORTED_INTEGRITY_VERSION,
    compute_integrity_hash,
    main,
    validate_record,
    validate_records,
)


def _system_config_record(key: str) -> dict:
    record = {
        "config_key": "risk_limits",
        "config_scope": "global",
        "value_ref": "docs/governance/config/risk_limits.yaml",
        "value_hash": "sha256:risk-limits-v1",
        "source_path": "infrastructure/config/surrealdb/feature-flags.yaml",
        "integrity_algo": SUPPORTED_INTEGRITY_ALGO,
        "integrity_version": SUPPORTED_INTEGRITY_VERSION,
        "observed_at": "2026-02-24T00:00:00Z",
    }
    record["integrity_hash"] = compute_integrity_hash(record, key)
    return record


def _security_policy_record(key: str) -> dict:
    record = {
        "policy_id": "policy-access-001",
        "version_hash": "sha256:policy-v1",
        "docs_path": "docs/security/policies/access-policy.md",
        "integrity_algo": SUPPORTED_INTEGRITY_ALGO,
        "integrity_version": SUPPORTED_INTEGRITY_VERSION,
        "observed_at": "2026-02-24T00:00:00Z",
    }
    record["integrity_hash"] = compute_integrity_hash(record, key)
    return record


@pytest.mark.unit
def test_validate_record_ok() -> None:
    key = "test-access-key"
    result = validate_record(
        SnapshotRecord(table="system_config", record=_system_config_record(key)),
        key=key,
    )

    assert result.status == "OK"
    assert result.reason == "OK"
    assert result.expected_hash == result.stored_hash


@pytest.mark.unit
def test_validate_record_tampered_field_fails() -> None:
    key = "test-access-key"
    record = _system_config_record(key)
    record["value_hash"] = "sha256:risk-limits-v2"

    result = validate_record(
        SnapshotRecord(table="system_config", record=record),
        key=key,
    )

    assert result.status == "FAIL"
    assert result.reason == ACCESS_INTEGRITY_HASH_MISMATCH
    assert result.expected_hash != result.stored_hash


@pytest.mark.unit
def test_validate_records_missing_key_is_fail_closed() -> None:
    results = validate_records(
        [
            SnapshotRecord(
                table="system_config", record=_system_config_record("seed-key")
            )
        ],
        key=None,
    )

    assert len(results) == 1
    assert results[0].status == "FAIL"
    assert results[0].reason == ACCESS_INTEGRITY_KEY_MISSING
    assert results[0].expected_hash is None


@pytest.mark.unit
def test_main_writes_report_with_security_policies_alias(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = "test-access-key"
    system_config = _system_config_record(key)
    security_policy = _security_policy_record(key)
    security_policy["docs_path"] = "docs/security/policies/access-policy-v2.md"

    input_path = tmp_path / "snapshot.json"
    output_path = tmp_path / "report.md"
    input_path.write_text(
        json.dumps(
            {
                "system_config": [system_config],
                "security_policies": [security_policy],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CDB_ACCESS_INTEGRITY_KEY", key)

    exit_code = main(["--input", str(input_path), "--output", str(output_path)])
    report = output_path.read_text(encoding="utf-8")

    assert exit_code == 2
    assert "Storage table: `security_policy_refs`" in report
    assert "`risk_limits` status=`OK` reason=`OK`" in report
    assert ACCESS_INTEGRITY_HASH_MISMATCH in report
