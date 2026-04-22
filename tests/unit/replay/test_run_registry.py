"""Unit tests for core/replay/run_registry.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.replay.run_registry import (
    ReplayRunRecord,
    ReplayRunRegistry,
    RunRegistryError,
    build_operator_summary,
    build_replay_provenance_fingerprint,
    build_replay_run_id,
)


def _make_record(**overrides) -> ReplayRunRecord:
    defaults = {
        "run_id": "replay-0123456789ab-0001",
        "status": "completed",
        "mode": "baseline",
        "strategy_id": "primary_breakout_v1",
        "symbol": "BTCUSDT",
        "dataset_fingerprint": "a" * 64,
        "scheduler_profile": "2x",
        "execution_provenance_id": "bt-0123456789abcdef",
        "artifact_root": "artifacts/replay_reports/replay-0123456789ab-0001",
        "gate_status": "PASS",
        "deterministic_replay_ok": True,
        "failure_reason": None,
        "started_at_utc": "2026-04-22T14:00:00+00:00",
        "finished_at_utc": "2026-04-22T14:00:05+00:00",
    }
    defaults.update(overrides)
    return ReplayRunRecord(**defaults)


@pytest.mark.unit
class TestReplayRunRecord:
    def test_invalid_status_fails_closed(self) -> None:
        with pytest.raises(RunRegistryError, match="Invalid status"):
            _make_record(status="unknown")

    def test_failed_record_requires_reason(self) -> None:
        with pytest.raises(RunRegistryError, match="require failure_reason"):
            _make_record(status="failed", failure_reason=None)

    def test_to_dict_is_deterministic(self) -> None:
        result = _make_record().to_dict()
        assert list(result.keys()) == [
            "run_id",
            "status",
            "mode",
            "strategy_id",
            "symbol",
            "dataset_fingerprint",
            "scheduler_profile",
            "execution_provenance_id",
            "artifact_root",
            "deterministic_replay_ok",
            "started_at_utc",
            "gate_status",
            "finished_at_utc",
        ]


@pytest.mark.unit
class TestProvenanceHelpers:
    def test_provenance_fingerprint_is_deterministic(self) -> None:
        p1 = build_replay_provenance_fingerprint(
            strategy_id="primary_breakout_v1",
            symbol="BTCUSDT",
            adapter_id="primary_breakout_runner_v1",
            dataset_fingerprint="a" * 64,
            scheduler_profile="5x",
            execution_provenance_id="bt-0123456789abcdef",
            code_commit="abc1234",
            config_snapshot={"entry_lookback_minutes": 240},
        )
        p2 = build_replay_provenance_fingerprint(
            strategy_id="primary_breakout_v1",
            symbol="BTCUSDT",
            adapter_id="primary_breakout_runner_v1",
            dataset_fingerprint="a" * 64,
            scheduler_profile="5x",
            execution_provenance_id="bt-0123456789abcdef",
            code_commit="abc1234",
            config_snapshot={"entry_lookback_minutes": 240},
        )
        assert p1 == p2
        assert len(p1) == 64

    def test_run_ids_are_distinct_for_attempts(self) -> None:
        provenance = "f" * 64
        assert build_replay_run_id(provenance, 1) == "replay-ffffffffffff-0001"
        assert build_replay_run_id(provenance, 2) == "replay-ffffffffffff-0002"


@pytest.mark.unit
class TestReplayRunRegistry:
    def test_append_and_load_cycle(self, tmp_path: Path) -> None:
        registry = ReplayRunRegistry(tmp_path / "run_registry.jsonl")
        record = _make_record()

        registry.append(record)
        loaded = registry.load_all()

        assert loaded == [record]

    def test_malformed_registry_line_fails_closed(self, tmp_path: Path) -> None:
        path = tmp_path / "run_registry.jsonl"
        path.write_text("not-json\n", encoding="utf-8")
        registry = ReplayRunRegistry(path)

        with pytest.raises(RunRegistryError, match="Malformed JSON"):
            registry.load_all()

    def test_invalid_lifecycle_status_in_registry_fails_closed(self, tmp_path: Path) -> None:
        path = tmp_path / "run_registry.jsonl"
        path.write_text(
            (
                '{"run_id":"replay-0123456789ab-0001","status":"broken","mode":"baseline",'
                '"strategy_id":"primary_breakout_v1","symbol":"BTCUSDT",'
                '"dataset_fingerprint":"' + ("a" * 64) + '","scheduler_profile":"instant",'
                '"execution_provenance_id":"bt-0123456789abcdef",'
                '"artifact_root":"artifacts/replay_reports/replay-0123456789ab-0001",'
                '"deterministic_replay_ok":false,"started_at_utc":"2026-04-22T14:00:00+00:00"}\n'
            ),
            encoding="utf-8",
        )
        registry = ReplayRunRegistry(path)

        with pytest.raises(RunRegistryError, match="Invalid run registry record"):
            registry.load_all()

    def test_next_attempt_uses_existing_run_ids(self, tmp_path: Path) -> None:
        registry = ReplayRunRegistry(tmp_path / "run_registry.jsonl")
        provenance = "f" * 64
        run_id = build_replay_run_id(provenance, 1)
        registry.append(_make_record(run_id=run_id))
        registry.append(_make_record(run_id=run_id, status="failed", failure_reason="boom"))

        assert registry.next_attempt(provenance) == 2


@pytest.mark.unit
class TestOperatorSummary:
    def test_summary_contains_required_fields(self) -> None:
        summary = build_operator_summary(_make_record(status="failed", failure_reason="boom"))

        assert summary["run_id"] == "replay-0123456789ab-0001"
        assert summary["status"] == "failed"
        assert summary["mode"] == "baseline"
        assert summary["dataset_fingerprint"] == "a" * 64
        assert summary["scheduler_profile"] == "2x"
        assert summary["execution_provenance_id"] == "bt-0123456789abcdef"
        assert summary["artifact_root"].endswith("replay-0123456789ab-0001")
        assert summary["failure_reason"] == "boom"
