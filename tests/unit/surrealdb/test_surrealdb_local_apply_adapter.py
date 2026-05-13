"""Unit tests for SurrealDBLocalContextApplyAdapter (#2458).

All tests use mocked urllib; no real SurrealDB container is needed.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
import urllib.error

import pytest

from tools.surrealdb.context_importer import (
    ADAPTER_KIND_IN_MEMORY,
    ADAPTER_KIND_SURREALDB_LOCAL,
    ALLOWED_CONTEXT_IMPORT_TABLES,
    ApplyAdapterError,
    ApplyGateError,
    InMemoryContextApplyAdapter,
    REAL_SURREALDB_ADAPTER_AVAILABLE,
    SurrealDBLocalContextApplyAdapter,
    TOMBSTONE_FIELD_AT,
    TOMBSTONE_FIELD_FLAG,
    TOMBSTONE_FIELD_LAST_SEEN_RUN_ID,
    TOMBSTONE_FIELD_REASON,
    TOMBSTONE_FIELD_SUPERSEDED_BY,
    main,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LOCAL_URL = "http://127.0.0.1:8010"
_NS = "cdb_context_local"
_DB = "cdb_context_intel"


def _ok_body(result: Any = None) -> bytes:
    return json.dumps([{"status": "OK", "result": result}]).encode()


def _make_adapter(
    url: str = _LOCAL_URL,
    user: str | None = None,
    password: str | None = None,
    timeout: int = 5,
) -> SurrealDBLocalContextApplyAdapter:
    return SurrealDBLocalContextApplyAdapter(
        surreal_url=url,
        namespace=_NS,
        database=_DB,
        user=user,
        password=password,
        timeout=timeout,
    )


def _tombstone_payload() -> dict[str, Any]:
    return {
        TOMBSTONE_FIELD_FLAG: True,
        TOMBSTONE_FIELD_AT: "2026-05-13T12:00:00Z",
        TOMBSTONE_FIELD_REASON: "record_removed_from_snapshot",
        TOMBSTONE_FIELD_LAST_SEEN_RUN_ID: "run-1",
        TOMBSTONE_FIELD_SUPERSEDED_BY: None,
    }


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_real_surrealdb_adapter_available_is_true() -> None:
    """#2458: REAL_SURREALDB_ADAPTER_AVAILABLE must be True after implementation."""
    assert REAL_SURREALDB_ADAPTER_AVAILABLE is True


@pytest.mark.unit
def test_adapter_kind_constant() -> None:
    assert ADAPTER_KIND_SURREALDB_LOCAL == "surrealdb-local"


@pytest.mark.unit
def test_adapter_kind_attribute() -> None:
    adapter = _make_adapter()
    assert adapter.kind == ADAPTER_KIND_SURREALDB_LOCAL


# ---------------------------------------------------------------------------
# URL guard (fail-closed for non-local targets)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_adapter_rejects_remote_ip() -> None:
    with pytest.raises(ApplyGateError):
        _make_adapter(url="http://10.0.0.1:8010")


@pytest.mark.unit
def test_adapter_rejects_production_url() -> None:
    with pytest.raises(ApplyGateError):
        _make_adapter(url="https://surrealdb.prod.example.com/")


@pytest.mark.unit
def test_adapter_accepts_127_0_0_1() -> None:
    _make_adapter(url="http://127.0.0.1:8010")  # must not raise


@pytest.mark.unit
def test_adapter_accepts_localhost() -> None:
    _make_adapter(url="http://localhost:8010")  # must not raise


# ---------------------------------------------------------------------------
# apply_create — SQL sent to /sql
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_apply_create_sends_upsert_content_sql(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _make_adapter()
    sent: list[str] = []

    def fake_urlopen(req, timeout=None):
        sent.append(req.data.decode("utf-8"))
        resp = MagicMock()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        resp.status = 200
        resp.read.return_value = _ok_body()
        return resp

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    adapter.apply_create("repo_artifact", "abc-123", {"path": "README.md"})

    assert len(sent) == 1
    sql = sent[0]
    assert "UPSERT repo_artifact:" in sql
    assert "CONTENT" in sql
    assert "README.md" in sql


@pytest.mark.unit
def test_apply_create_no_auth_header_when_no_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _make_adapter(user=None, password=None)
    captured_req: list[Any] = []

    def fake_urlopen(req, timeout=None):
        captured_req.append(req)
        resp = MagicMock()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        resp.status = 200
        resp.read.return_value = _ok_body()
        return resp

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    adapter.apply_create("repo_artifact", "abc", {"k": "v"})

    req = captured_req[0]
    assert req.get_header("Authorization") is None


@pytest.mark.unit
def test_apply_create_includes_basic_auth_header(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _make_adapter(user="root", password="s3cr3t")
    captured_req: list[Any] = []

    def fake_urlopen(req, timeout=None):
        captured_req.append(req)
        resp = MagicMock()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        resp.status = 200
        resp.read.return_value = _ok_body()
        return resp

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    adapter.apply_create("repo_artifact", "abc", {"k": "v"})

    req = captured_req[0]
    expected_token = base64.b64encode(b"root:s3cr3t").decode()
    assert req.get_header("Authorization") == f"Basic {expected_token}"


# ---------------------------------------------------------------------------
# apply_update — same SQL pattern as create (UPSERT CONTENT)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_apply_update_sends_upsert_content_sql(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _make_adapter()
    sent: list[str] = []

    def fake_urlopen(req, timeout=None):
        sent.append(req.data.decode("utf-8"))
        resp = MagicMock()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        resp.status = 200
        resp.read.return_value = _ok_body()
        return resp

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    adapter.apply_update("doc_page", "page-1", {"title": "updated"})

    assert len(sent) == 1
    sql = sent[0]
    assert "UPSERT doc_page:" in sql
    assert "CONTENT" in sql
    assert "updated" in sql


# ---------------------------------------------------------------------------
# apply_tombstone
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_apply_tombstone_sends_upsert_sql(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _make_adapter()
    sent: list[str] = []

    def fake_urlopen(req, timeout=None):
        sent.append(req.data.decode("utf-8"))
        resp = MagicMock()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        resp.status = 200
        resp.read.return_value = _ok_body()
        return resp

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    payload = _tombstone_payload()
    adapter.apply_tombstone("doc_chunk", "chunk-1", payload)

    assert len(sent) == 1
    sql = sent[0]
    assert "UPSERT doc_chunk:" in sql
    assert "CONTENT" in sql
    assert "record_removed_from_snapshot" in sql


@pytest.mark.unit
def test_apply_tombstone_missing_fields_raises() -> None:
    adapter = _make_adapter()
    with pytest.raises(ApplyAdapterError, match="missing required fields"):
        adapter.apply_tombstone("doc_chunk", "chunk-1", {})


@pytest.mark.unit
def test_apply_tombstone_flag_must_be_true_raises() -> None:
    adapter = _make_adapter()
    payload = _tombstone_payload()
    payload[TOMBSTONE_FIELD_FLAG] = False
    with pytest.raises(ApplyAdapterError, match=TOMBSTONE_FIELD_FLAG):
        adapter.apply_tombstone("doc_chunk", "chunk-1", payload)


# ---------------------------------------------------------------------------
# HTTP error handling (fail-closed)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_http_500_raises_apply_adapter_error(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _make_adapter()

    class FakeHTTPError(urllib.error.HTTPError):
        def read(self) -> bytes:
            return b""

    http_err = FakeHTTPError(
        url=f"{_LOCAL_URL}/sql",
        code=500,
        msg="Internal Server Error",
        hdrs=None,  # type: ignore[arg-type]
        fp=None,  # type: ignore[arg-type]
    )
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *a, **kw: (_ for _ in ()).throw(http_err),
    )

    with pytest.raises(ApplyAdapterError):
        adapter.apply_create("repo_artifact", "abc", {"k": "v"})


@pytest.mark.unit
def test_connection_refused_raises_apply_adapter_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _make_adapter()
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *a, **kw: (_ for _ in ()).throw(
            urllib.error.URLError("Connection refused")
        ),
    )

    with pytest.raises(ApplyAdapterError, match="connection failed"):
        adapter.apply_create("repo_artifact", "abc", {"k": "v"})


@pytest.mark.unit
def test_surrealdb_err_response_raises_apply_adapter_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _make_adapter()
    err_body = json.dumps([{"status": "ERR", "result": "Parse error"}]).encode()

    def fake_urlopen(req, timeout=None):
        resp = MagicMock()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        resp.status = 200
        resp.read.return_value = err_body
        return resp

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    with pytest.raises(ApplyAdapterError, match="statement error"):
        adapter.apply_create("repo_artifact", "abc", {"k": "v"})


# ---------------------------------------------------------------------------
# Credential security — secrets must never appear in error messages or logs
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_password_not_in_adapter_error_message(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _make_adapter(user="myuser", password="supersecret123")
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *a, **kw: (_ for _ in ()).throw(
            urllib.error.URLError("Connection refused")
        ),
    )

    with pytest.raises(ApplyAdapterError) as exc_info:
        adapter.apply_create("repo_artifact", "abc", {"k": "v"})

    assert "supersecret123" not in str(exc_info.value)
    assert "myuser" not in str(exc_info.value)


@pytest.mark.unit
def test_password_not_in_log_output(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    import logging

    adapter = _make_adapter(user="root", password="hunter2")
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *a, **kw: (_ for _ in ()).throw(
            urllib.error.URLError("Connection refused")
        ),
    )

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(ApplyAdapterError):
            adapter.apply_create("repo_artifact", "abc", {"k": "v"})

    for record in caplog.records:
        assert "hunter2" not in record.getMessage()
        assert "hunter2" not in (record.exc_text or "")


# ---------------------------------------------------------------------------
# CLI adapter selection
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_cli_help_advertises_adapter_flag(capsys: pytest.CaptureFixture) -> None:
    """CLI --help shows --adapter flag with both choices."""
    with pytest.raises(SystemExit) as exc_info:
        main(["apply", "--help"])
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "--adapter" in out
    assert "in-memory" in out
    assert "surrealdb-local" in out


@pytest.mark.unit
def test_cli_default_adapter_choice_is_in_memory(capsys: pytest.CaptureFixture) -> None:
    """Without --adapter flag, help shows in-memory as the default."""
    with pytest.raises(SystemExit) as exc_info:
        main(["apply", "--help"])
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "in-memory" in out


# ---------------------------------------------------------------------------
# Makefile / config integration checks
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_makefile_context_import_local_uses_surrealdb_local_adapter() -> None:
    """Makefile context-import-local must pass --adapter surrealdb-local (#2458)."""
    makefile = Path(__file__).parents[3] / "Makefile"
    assert makefile.exists(), "Makefile not found"
    content = makefile.read_text(encoding="utf-8")
    in_target = False
    for line in content.splitlines():
        if line.startswith("context-import-local:"):
            in_target = True
        elif in_target and line.startswith("\t"):
            if "--adapter surrealdb-local" in line:
                return
        elif in_target and not line.startswith("\t") and line.strip():
            break
    pytest.fail(
        "context-import-local target in Makefile does not contain '--adapter surrealdb-local'"
    )


@pytest.mark.unit
def test_config_example_allowed_tables_match_allowed_context_import_tables() -> None:
    """Config example allowed_tables must exactly match ALLOWED_CONTEXT_IMPORT_TABLES."""
    import yaml as _yaml

    config_path = (
        Path(__file__).parents[3]
        / "infrastructure"
        / "config"
        / "surrealdb"
        / "context_import.local.example.yaml"
    )
    assert config_path.exists(), f"Config example not found at {config_path}"
    data = _yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config_tables = frozenset(data.get("allowed_tables", []))
    assert config_tables == ALLOWED_CONTEXT_IMPORT_TABLES, (
        f"Config allowed_tables {sorted(config_tables)} != "
        f"ALLOWED_CONTEXT_IMPORT_TABLES {sorted(ALLOWED_CONTEXT_IMPORT_TABLES)}"
    )
