"""Unit tests for ARVP DatasetSpec and DatasetProvider.

Tests validate:
- DatasetSpec invariants (all fail-closed rules)
- DatasetSpec fingerprint determinism and serialization
- FileBackedDatasetProvider: JSON array and JSONL loading, all error paths
- DBBackedDatasetProvider: raises NotImplementedError with schema gap message

Part of ARVP §4.2 — Historical Data Access layer.
Tracked in GitHub Issue #1841.
"""

from __future__ import annotations

import json

import pytest

from core.replay.dataset_provider import (
    DBBackedDatasetProvider,
    DatasetLoadError,
    DatasetResult,
    FileBackedDatasetProvider,
)
from core.replay.dataset_spec import DatasetSpec, DatasetSpecError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_START_MS = 1_700_000_000_000


def _make_spec(
    *,
    symbol: str = "BTCUSDT",
    timeframe: str = "1m",
    start_ts_ms: int = _BASE_START_MS,
    end_ts_ms: int = _BASE_START_MS + 600_000,
    warmup_candles: int = 3,
    source: str = "file",
    file_path: str | None = "/tmp/data.json",
    db_dataset_id: str | None = None,
) -> DatasetSpec:
    return DatasetSpec(
        symbol=symbol,
        timeframe=timeframe,
        start_ts_ms=start_ts_ms,
        end_ts_ms=end_ts_ms,
        warmup_candles=warmup_candles,
        source=source,
        file_path=file_path,
        db_dataset_id=db_dataset_id,
    )


def _make_candles(count: int, start_ts_ms: int = _BASE_START_MS) -> list[dict]:
    return [
        {
            "ts_ms": start_ts_ms + i * 60_000,
            "high": 50_000.0 + i,
            "low": 49_000.0 + i,
            "close": 49_500.0 + i,
        }
        for i in range(count)
    ]


# ---------------------------------------------------------------------------
# DatasetSpec — validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_valid_file_spec_validates_without_error() -> None:
    spec = _make_spec()
    spec.validate()


@pytest.mark.unit
def test_valid_db_spec_validates_without_error() -> None:
    spec = _make_spec(source="db", file_path=None, db_dataset_id="ds-001")
    spec.validate()


@pytest.mark.unit
def test_invalid_symbol_rejected() -> None:
    spec = _make_spec(symbol="ETHUSDT")
    with pytest.raises(DatasetSpecError, match="Invalid symbol"):
        spec.validate()


@pytest.mark.unit
def test_invalid_timeframe_rejected() -> None:
    spec = _make_spec(timeframe="5m")
    with pytest.raises(DatasetSpecError, match="Invalid timeframe"):
        spec.validate()


@pytest.mark.unit
def test_start_greater_than_end_rejected() -> None:
    spec = _make_spec(start_ts_ms=_BASE_START_MS + 120_000, end_ts_ms=_BASE_START_MS)
    with pytest.raises(DatasetSpecError, match="start_ts_ms"):
        spec.validate()


@pytest.mark.unit
def test_start_equals_end_accepted() -> None:
    spec = _make_spec(start_ts_ms=_BASE_START_MS, end_ts_ms=_BASE_START_MS, warmup_candles=0)
    spec.validate()


@pytest.mark.unit
def test_negative_warmup_rejected() -> None:
    spec = _make_spec(warmup_candles=-1)
    with pytest.raises(DatasetSpecError, match="warmup_candles"):
        spec.validate()


@pytest.mark.unit
def test_zero_warmup_accepted() -> None:
    spec = _make_spec(warmup_candles=0)
    spec.validate()


@pytest.mark.unit
def test_file_source_missing_file_path_rejected() -> None:
    spec = _make_spec(source="file", file_path=None)
    with pytest.raises(DatasetSpecError, match="file_path"):
        spec.validate()


@pytest.mark.unit
def test_file_source_with_db_dataset_id_rejected() -> None:
    spec = _make_spec(source="file", file_path="/tmp/f.json", db_dataset_id="ds-001")
    with pytest.raises(DatasetSpecError, match="mutually exclusive"):
        spec.validate()


@pytest.mark.unit
def test_db_source_missing_db_dataset_id_rejected() -> None:
    spec = _make_spec(source="db", file_path=None, db_dataset_id=None)
    with pytest.raises(DatasetSpecError, match="db_dataset_id"):
        spec.validate()


@pytest.mark.unit
def test_db_source_with_file_path_rejected() -> None:
    spec = _make_spec(source="db", file_path="/tmp/f.json", db_dataset_id="ds-001")
    with pytest.raises(DatasetSpecError, match="mutually exclusive"):
        spec.validate()


# ---------------------------------------------------------------------------
# DatasetSpec — to_dict and fingerprint
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_to_dict_omits_none_optional_fields() -> None:
    spec = _make_spec(source="file", file_path="/tmp/f.json", db_dataset_id=None)
    d = spec.to_dict()
    assert "db_dataset_id" not in d
    assert d["file_path"] == "/tmp/f.json"


@pytest.mark.unit
def test_to_dict_includes_db_dataset_id_when_set() -> None:
    spec = _make_spec(source="db", file_path=None, db_dataset_id="ds-abc")
    d = spec.to_dict()
    assert "file_path" not in d
    assert d["db_dataset_id"] == "ds-abc"


@pytest.mark.unit
def test_fingerprint_is_deterministic() -> None:
    spec_a = _make_spec()
    spec_b = _make_spec()
    assert spec_a.fingerprint() == spec_b.fingerprint()


@pytest.mark.unit
def test_different_specs_produce_different_fingerprints() -> None:
    spec_a = _make_spec(start_ts_ms=_BASE_START_MS)
    spec_b = _make_spec(start_ts_ms=_BASE_START_MS + 60_000)
    assert spec_a.fingerprint() != spec_b.fingerprint()


@pytest.mark.unit
def test_fingerprint_is_64_char_lowercase_hex() -> None:
    fp = _make_spec().fingerprint()
    assert len(fp) == 64
    assert all(c in "0123456789abcdef" for c in fp)


# ---------------------------------------------------------------------------
# FileBackedDatasetProvider — happy paths
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_file_backed_loads_json_array(tmp_path: object) -> None:
    candles = _make_candles(10)
    f = tmp_path / "data.json"
    f.write_text(json.dumps(candles), encoding="utf-8")

    spec = _make_spec(file_path=str(f), warmup_candles=3)
    result = FileBackedDatasetProvider().load(spec)

    assert isinstance(result, DatasetResult)
    assert len(result.candles) == 10
    assert result.warmup_count == 3
    assert result.effective_candle_count == 7
    assert result.fingerprint == spec.fingerprint()
    assert result.spec is spec


@pytest.mark.unit
def test_file_backed_loads_jsonl(tmp_path: object) -> None:
    candles = _make_candles(5)
    f = tmp_path / "data.jsonl"
    f.write_text("\n".join(json.dumps(c) for c in candles), encoding="utf-8")

    spec = _make_spec(file_path=str(f), warmup_candles=2)
    result = FileBackedDatasetProvider().load(spec)

    assert len(result.candles) == 5
    assert result.effective_candle_count == 3


@pytest.mark.unit
def test_file_backed_jsonl_with_blank_lines_ignored(tmp_path: object) -> None:
    candles = _make_candles(4)
    lines = [json.dumps(c) for c in candles]
    content = "\n\n".join(lines) + "\n"
    f = tmp_path / "data.jsonl"
    f.write_text(content, encoding="utf-8")

    spec = _make_spec(file_path=str(f), warmup_candles=1)
    result = FileBackedDatasetProvider().load(spec)
    assert len(result.candles) == 4


@pytest.mark.unit
def test_file_backed_result_is_deterministic(tmp_path: object) -> None:
    candles = _make_candles(5)
    f = tmp_path / "data.json"
    f.write_text(json.dumps(candles), encoding="utf-8")
    spec = _make_spec(file_path=str(f), warmup_candles=1)

    provider = FileBackedDatasetProvider()
    r1 = provider.load(spec)
    r2 = provider.load(spec)
    assert r1.candles == r2.candles
    assert r1.fingerprint == r2.fingerprint
    assert r1.effective_candle_count == r2.effective_candle_count


@pytest.mark.unit
def test_file_backed_zero_warmup_accepted(tmp_path: object) -> None:
    candles = _make_candles(3)
    f = tmp_path / "data.json"
    f.write_text(json.dumps(candles), encoding="utf-8")
    spec = _make_spec(file_path=str(f), warmup_candles=0)
    result = FileBackedDatasetProvider().load(spec)
    assert result.warmup_count == 0
    assert result.effective_candle_count == 3


# ---------------------------------------------------------------------------
# FileBackedDatasetProvider — error paths
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_file_backed_missing_file_raises(tmp_path: object) -> None:
    spec = _make_spec(file_path=str(tmp_path / "missing.json"))
    with pytest.raises(DatasetLoadError, match="not found"):
        FileBackedDatasetProvider().load(spec)


@pytest.mark.unit
def test_file_backed_empty_file_raises(tmp_path: object) -> None:
    f = tmp_path / "empty.json"
    f.write_text("", encoding="utf-8")
    spec = _make_spec(file_path=str(f), warmup_candles=0)
    with pytest.raises(DatasetLoadError):
        FileBackedDatasetProvider().load(spec)


@pytest.mark.unit
def test_file_backed_malformed_json_array_raises(tmp_path: object) -> None:
    f = tmp_path / "bad.json"
    f.write_text("[{not valid", encoding="utf-8")
    spec = _make_spec(file_path=str(f))
    with pytest.raises(DatasetLoadError, match="JSON"):
        FileBackedDatasetProvider().load(spec)


@pytest.mark.unit
def test_file_backed_malformed_jsonl_line_raises(tmp_path: object) -> None:
    candles = _make_candles(3)
    lines = [json.dumps(c) for c in candles]
    lines[1] = "{bad json"
    f = tmp_path / "data.jsonl"
    f.write_text("\n".join(lines), encoding="utf-8")
    spec = _make_spec(file_path=str(f))
    with pytest.raises(DatasetLoadError, match="JSON"):
        FileBackedDatasetProvider().load(spec)


@pytest.mark.unit
def test_file_backed_missing_close_field_raises(tmp_path: object) -> None:
    candles = _make_candles(5)
    del candles[2]["close"]
    f = tmp_path / "data.json"
    f.write_text(json.dumps(candles), encoding="utf-8")
    spec = _make_spec(file_path=str(f))
    with pytest.raises(DatasetLoadError, match="close"):
        FileBackedDatasetProvider().load(spec)


@pytest.mark.unit
def test_file_backed_missing_ts_ms_field_raises(tmp_path: object) -> None:
    candles = _make_candles(3)
    del candles[0]["ts_ms"]
    f = tmp_path / "data.json"
    f.write_text(json.dumps(candles), encoding="utf-8")
    spec = _make_spec(file_path=str(f))
    with pytest.raises(DatasetLoadError, match="ts_ms"):
        FileBackedDatasetProvider().load(spec)


@pytest.mark.unit
def test_file_backed_duplicate_ts_ms_raises(tmp_path: object) -> None:
    """Duplicate ts_ms values violate strictly-increasing invariant."""
    candles = _make_candles(5)
    candles[3]["ts_ms"] = candles[2]["ts_ms"]  # make [3] == [2], not strictly increasing
    f = tmp_path / "data.json"
    f.write_text(json.dumps(candles), encoding="utf-8")
    spec = _make_spec(file_path=str(f))
    with pytest.raises(DatasetLoadError, match="strictly increasing"):
        FileBackedDatasetProvider().load(spec)


@pytest.mark.unit
def test_file_backed_non_1m_cadence_raises(tmp_path: object) -> None:
    candles = _make_candles(5)
    candles[1]["ts_ms"] += 30_000  # 90 000 ms gap from candle[0] → 1m cadence violation
    f = tmp_path / "data.json"
    f.write_text(json.dumps(candles), encoding="utf-8")
    spec = _make_spec(file_path=str(f))
    with pytest.raises(DatasetLoadError, match="1m cadence"):
        FileBackedDatasetProvider().load(spec)


@pytest.mark.unit
def test_file_backed_warmup_equals_candle_count_raises(tmp_path: object) -> None:
    """len(candles) must be strictly greater than warmup_candles."""
    candles = _make_candles(3)
    f = tmp_path / "data.json"
    f.write_text(json.dumps(candles), encoding="utf-8")
    spec = _make_spec(file_path=str(f), warmup_candles=3)  # equal, not strictly greater
    with pytest.raises(DatasetLoadError, match="Insufficient candles"):
        FileBackedDatasetProvider().load(spec)


@pytest.mark.unit
def test_file_backed_warmup_exceeds_candle_count_raises(tmp_path: object) -> None:
    candles = _make_candles(2)
    f = tmp_path / "data.json"
    f.write_text(json.dumps(candles), encoding="utf-8")
    spec = _make_spec(file_path=str(f), warmup_candles=5)
    with pytest.raises(DatasetLoadError, match="Insufficient candles"):
        FileBackedDatasetProvider().load(spec)


@pytest.mark.unit
def test_file_backed_source_mismatch_raises() -> None:
    """FileBackedDatasetProvider refuses a db-source spec."""
    spec = _make_spec(source="db", file_path=None, db_dataset_id="ds-001")
    with pytest.raises(DatasetLoadError, match="source='file'"):
        FileBackedDatasetProvider().load(spec)


# ---------------------------------------------------------------------------
# DBBackedDatasetProvider
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_db_backed_raises_not_implemented_with_schema_gap_message() -> None:
    spec = _make_spec(source="db", file_path=None, db_dataset_id="ds-001")
    with pytest.raises(NotImplementedError, match="candles table"):
        DBBackedDatasetProvider().load(spec)


@pytest.mark.unit
def test_db_backed_validates_spec_before_raising() -> None:
    """A bad db spec should raise DatasetSpecError, not NotImplementedError."""
    spec = _make_spec(source="db", file_path=None, db_dataset_id=None)  # missing db_dataset_id
    with pytest.raises(DatasetSpecError, match="db_dataset_id"):
        DBBackedDatasetProvider().load(spec)
