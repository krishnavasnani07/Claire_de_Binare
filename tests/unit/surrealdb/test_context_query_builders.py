"""Unit tests for Context Query query builders (#2088)."""

from __future__ import annotations

import pytest

from tools.surrealdb.context_query import (
    ConfigValidationError,
    TOMBSTONE_FILTER_SCHEMA_SUPPORTED,
    _tombstone_meta,
    build_artifact_query,
    build_doc_query,
    build_symbol_query,
    build_import_query,
    build_trace_query,
    build_explain_source_query,
    build_snapshot_query,
    build_drift_query,
    build_audit_query,
)

EXAMPLE_CONFIG = "infrastructure/config/surrealdb/context_query.local.example.yaml"


@pytest.mark.unit
def test_build_artifact_query_with_filters() -> None:
    query = build_artifact_query(
        source_path="src/",
        file_type="python",
        hash_value="abc123",
        limit=50,
        include_tombstoned=False,
    )
    assert "FROM repo_artifact" in query
    assert 'source_path CONTAINS "src/"' in query
    assert 'file_type = "python"' in query
    assert 'normalized_sha256 = "abc123"' in query
    assert "LIMIT 50" in query
    assert "tombstoned" not in query


@pytest.mark.unit
def test_build_artifact_query_no_filters() -> None:
    query = build_artifact_query(limit=10, include_tombstoned=True)
    assert "FROM repo_artifact" in query
    assert "LIMIT 10" in query
    assert "tombstoned" not in query


@pytest.mark.unit
def test_build_doc_query_with_filters() -> None:
    query = build_doc_query(
        query_text="test",
        source_path="docs/",
        heading="intro",
        limit=20,
        include_tombstoned=False,
    )
    assert "FROM doc_chunk" in query
    assert 'content CONTAINS "test"' in query
    assert 'source_path CONTAINS "docs/"' in query
    assert 'heading_path CONTAINS "intro"' in query
    assert "LIMIT 20" in query
    assert "tombstoned" not in query


@pytest.mark.unit
def test_build_doc_query_no_filters() -> None:
    query = build_doc_query(limit=5, include_tombstoned=True)
    assert "FROM doc_chunk" in query
    assert "LIMIT 5" in query
    assert "tombstoned" not in query


@pytest.mark.unit
def test_build_symbol_query_with_filters() -> None:
    query = build_symbol_query(
        name="MyClass",
        qualified_name="module.submodule.MyClass",
        source_path="src/",
        symbol_type="class",
        limit=25,
        include_tombstoned=False,
    )
    assert "FROM code_symbol" in query
    assert 'name CONTAINS "MyClass"' in query
    assert 'qualified_name CONTAINS "module.submodule.MyClass"' in query
    assert 'source_path CONTAINS "src/"' in query
    assert 'symbol_type = "class"' in query
    assert "LIMIT 25" in query
    assert "tombstoned" not in query


@pytest.mark.unit
def test_build_symbol_query_no_filters() -> None:
    query = build_symbol_query(limit=10, include_tombstoned=True)
    assert "FROM code_symbol" in query
    assert "LIMIT 10" in query


@pytest.mark.unit
def test_build_import_query_with_filters() -> None:
    query = build_import_query(
        module="json",
        source_path="src/",
        source_hash="abc123",
        import_id="import-1",
        limit=30,
        include_tombstoned=False,
    )
    assert "FROM import_reference" in query
    assert 'module CONTAINS "json"' in query
    assert 'source_path CONTAINS "src/"' in query
    assert 'source_hash = "abc123"' in query
    assert 'import_id = "import-1"' in query
    assert "LIMIT 30" in query
    assert "tombstoned" not in query


@pytest.mark.unit
def test_build_import_query_no_filters() -> None:
    query = build_import_query(limit=10, include_tombstoned=True)
    assert "FROM import_reference" in query
    assert "LIMIT 10" in query


@pytest.mark.unit
def test_build_trace_query_with_filters() -> None:
    query = build_trace_query(
        target_ref="module",
        source_path="src/",
        symbol_name="func",
        direction="upstream",
        edge_type="depends_on",
        confidence="high",
        limit=15,
        include_tombstoned=False,
    )
    assert "FROM dependency_edge" in query
    assert 'source_ref CONTAINS "module"' in query
    assert 'source_path CONTAINS "src/"' in query
    assert 'symbol_name CONTAINS "func"' in query
    assert "edge_type = 'depends_on'" in query
    assert 'confidence = "high"' in query
    assert "LIMIT 15" in query
    assert "tombstoned" not in query


@pytest.mark.unit
def test_build_trace_query_direction_downstream() -> None:
    query = build_trace_query(target_ref="test", direction="downstream")
    assert "FROM dependency_edge" in query
    assert "edge_type = 'used_by'" in query


@pytest.mark.unit
def test_build_trace_query_no_filters() -> None:
    query = build_trace_query(limit=10, include_tombstoned=True)
    assert "FROM dependency_edge" in query
    assert "LIMIT 10" in query


@pytest.mark.unit
def test_build_explain_source_query_with_artifact_id() -> None:
    query = build_explain_source_query(
        artifact_id="artifact-1",
        source_path="src/",
        limit=10,
        include_tombstoned=False,
    )
    assert "FROM repo_artifact" in query
    assert 'artifact_id = "artifact-1"' in query
    assert 'source_path CONTAINS "src/"' in query
    assert "LIMIT 10" in query
    assert "tombstoned = false" not in query


@pytest.mark.unit
def test_build_explain_source_query_with_chunk_id() -> None:
    query = build_explain_source_query(chunk_id="chunk-1")
    assert "FROM repo_artifact" in query
    assert 'chunk_id = "chunk-1"' in query


@pytest.mark.unit
def test_build_explain_source_query_multiple_ids_raises() -> None:
    with pytest.raises(ConfigValidationError):
        build_explain_source_query(artifact_id="a", chunk_id="b")


@pytest.mark.unit
def test_build_snapshot_query_with_filters() -> None:
    query = build_snapshot_query(
        snapshot_id="snap-1",
        run_id="run-123",
        source_path="src/",
        limit=10,
        include_tombstoned=False,
    )
    assert "FROM repo_artifact" in query
    assert 'snapshot_id = "snap-1"' in query
    assert 'run_id = "run-123"' in query
    assert 'source_path CONTAINS "src/"' in query
    assert "LIMIT 10" in query
    assert "tombstoned" not in query


@pytest.mark.unit
def test_build_snapshot_query_no_filters() -> None:
    query = build_snapshot_query(limit=5, include_tombstoned=True)
    assert "FROM repo_artifact" in query
    assert "LIMIT 5" in query


@pytest.mark.unit
def test_build_drift_query_with_filters() -> None:
    query = build_drift_query(
        artifact_id="artifact-1",
        source_path="src/",
        status="blocking",
        kind="depends_on",
        limit=20,
        include_tombstoned=False,
    )
    assert "FROM dependency_edge" in query
    assert 'source_ref CONTAINS "artifact-1"' in query
    assert 'source_path CONTAINS "src/"' in query
    assert 'status = "blocking"' in query
    assert 'edge_type = "depends_on"' in query
    assert "LIMIT 20" in query
    assert "tombstoned" not in query


@pytest.mark.unit
def test_build_drift_query_no_filters() -> None:
    query = build_drift_query(limit=5, include_tombstoned=True)
    assert "FROM dependency_edge" in query
    assert "LIMIT 5" in query


@pytest.mark.unit
def test_build_audit_query_with_filters() -> None:
    query = build_audit_query(
        audit_id="audit-1",
        run_id="run-123",
        source_path="src/",
        limit=10,
        include_tombstoned=False,
    )
    assert "FROM import_reference" in query
    assert 'import_id = "audit-1"' in query
    assert 'run_id = "run-123"' in query
    assert 'source_path CONTAINS "src/"' in query
    assert "LIMIT 10" in query
    assert "tombstoned" not in query


@pytest.mark.unit
def test_build_audit_query_no_filters() -> None:
    query = build_audit_query(limit=5, include_tombstoned=True)
    assert "FROM import_reference" in query
    assert "LIMIT 5" in query


# ---------------------------------------------------------------------------
# Literal escaping tests (#2459 Thread 3 – SQL-literal injection fix)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_build_doc_query_apostrophe_escaped() -> None:
    """Apostrophe in query_text must produce a valid double-quoted JSON literal."""
    query = build_doc_query(query_text="don't")
    # json.dumps produces "don't" (double-quoted, apostrophe needs no escaping)
    assert 'content CONTAINS "don\'t"' in query
    # Must NOT produce a broken single-quoted literal
    assert "content CONTAINS 'don't'" not in query


@pytest.mark.unit
def test_build_artifact_query_backslash_escaped() -> None:
    """Backslash in source_path must be JSON-escaped to \\\\."""
    query = build_artifact_query(source_path="path\\name")
    # json.dumps escapes backslash → "path\\name"
    assert '"path\\\\name"' in query
    # Must NOT produce a raw unescaped backslash literal
    assert "source_path CONTAINS 'path\\name'" not in query


@pytest.mark.unit
def test_build_doc_query_apostrophe_and_backslash_escaped() -> None:
    """Combined apostrophe + backslash must both be handled."""
    query = build_doc_query(query_text="a'b\\c")
    # json.dumps: apostrophe unchanged in double-quotes, backslash → \\
    assert '"a\'b\\\\c"' in query
    assert "content CONTAINS 'a'b" not in query


@pytest.mark.unit
def test_build_symbol_query_apostrophe_in_name() -> None:
    """Apostrophe in symbol name must be escaped."""
    query = build_symbol_query(name="O'Brien")
    assert 'name CONTAINS "O\'Brien"' in query
    assert "name CONTAINS 'O'Brien'" not in query


@pytest.mark.unit
def test_build_drift_query_apostrophe_in_source_path() -> None:
    """Apostrophe in source_path for drift query must be safe."""
    query = build_drift_query(source_path="src/can't")
    assert 'source_path CONTAINS "src/can\'t"' in query
    assert "source_path CONTAINS 'src/can't'" not in query


@pytest.mark.unit
def test_hardcoded_direction_literals_stay_single_quoted() -> None:
    """Hardcoded direction literals ('depends_on', 'used_by') must remain single-quoted.

    These are not user-supplied values so they are not run through _surrealql_string.
    """
    upstream = build_trace_query(direction="upstream")
    assert "edge_type = 'depends_on'" in upstream

    downstream = build_trace_query(direction="downstream")
    assert "edge_type = 'used_by'" in downstream


# ---------------------------------------------------------------------------
# Tombstone-filter transparency tests (#2459 / PR #2465 Thread 4)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_tombstone_filter_schema_supported_is_false() -> None:
    """TOMBSTONE_FILTER_SCHEMA_SUPPORTED must be False until schema declares the field."""
    assert TOMBSTONE_FILTER_SCHEMA_SUPPORTED is False


@pytest.mark.unit
def test_tombstone_meta_default() -> None:
    """_tombstone_meta(False): tombstone_filter_applied=False, reason=schema-field-not-defined."""
    meta = _tombstone_meta(False)
    assert meta["tombstone_filter_applied"] is False
    assert meta["tombstone_filter_reason"] == "schema-field-not-defined"
    assert "include_tombstoned" not in meta


@pytest.mark.unit
def test_tombstone_meta_include_true() -> None:
    """_tombstone_meta(True): tombstone_filter_applied=False, include_tombstoned=True."""
    meta = _tombstone_meta(True)
    assert meta["tombstone_filter_applied"] is False
    assert meta["include_tombstoned"] is True
    assert meta["tombstone_filter_reason"] == "include-tombstoned-requested"


@pytest.mark.unit
def test_build_artifact_query_include_tombstoned_true_no_predicate() -> None:
    """include_tombstoned=True must not inject a tombstone WHERE predicate (schema-disabled)."""
    query = build_artifact_query(include_tombstoned=True)
    assert "tombstoned" not in query


@pytest.mark.unit
def test_build_doc_query_include_tombstoned_false_no_predicate() -> None:
    """include_tombstoned=False (default) must not inject a tombstone WHERE predicate."""
    query = build_doc_query(include_tombstoned=False)
    assert "tombstoned" not in query
