"""Tests for scripts/replay/lr021_replay.py — offline replay runner.

Governance: LR-021 Slice 1 (Deterministic Replay Framework)
"""

import io
import json
import sys
from pathlib import Path

import pytest

# scripts/ is not a Python package (no __init__.py), so add it to sys.path
# to allow importing lr021_replay. Same pattern as tests/unit/test_lr_reporter.py.
repo_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo_root / "scripts"))

from replay.lr021_replay import replay, validate_envelope  # noqa: E402

from core.replay.canonical_json import canonical_json_dumps, sha256_hex  # noqa: E402

FIXTURES = repo_root / "tests" / "fixtures" / "replay"
SAMPLE_FILE = FIXTURES / "lr021_sample_envelopes.jsonl"
GOLDEN_FILE = FIXTURES / "lr021_expected_hashes.jsonl"


class TestGoldenFileReplay:
    def test_replay_matches_golden_hashes(self):
        """Replay over fixture produces exactly expected hashes."""
        output_buf = io.StringIO()
        with open(SAMPLE_FILE, "r") as f_in:
            summary = replay(f_in, output_buf, strict=True, chain=True)

        assert summary["processed"] == 5
        assert summary["skipped"] == 0

        output_buf.seek(0)
        actual_lines = [json.loads(line) for line in output_buf if line.strip()]

        with open(GOLDEN_FILE, "r") as f_exp:
            expected_lines = [json.loads(line) for line in f_exp if line.strip()]

        assert len(actual_lines) == len(expected_lines)
        for i, (actual, expected) in enumerate(zip(actual_lines, expected_lines)):
            assert actual["event_hash"] == expected["event_hash"], (
                f"event_hash mismatch at line {i + 1}"
            )
            assert actual["chain_hash"] == expected["chain_hash"], (
                f"chain_hash mismatch at line {i + 1}"
            )

    def test_golden_canonical_bytes_stability(self):
        """Assert canonical JSON bytes per event, not just hash.

        If a hash ever breaks, this test shows exactly which bytes changed.
        """
        with open(SAMPLE_FILE, "r") as f_in:
            input_envelopes = [json.loads(line) for line in f_in if line.strip()]

        with open(GOLDEN_FILE, "r") as f_exp:
            expected_lines = [json.loads(line) for line in f_exp if line.strip()]

        for i, (inp, exp) in enumerate(zip(input_envelopes, expected_lines)):
            canonical_bytes = canonical_json_dumps(inp)
            computed_hash = sha256_hex(canonical_bytes.encode("utf-8"))
            assert computed_hash == exp["event_hash"], (
                f"line {i + 1}: canonical bytes changed.\n"
                f"  canonical: {canonical_bytes!r}\n"
                f"  computed hash:  {computed_hash}\n"
                f"  expected hash:  {exp['event_hash']}"
            )


class TestValidation:
    def test_missing_fields_strict(self):
        bad_input = '{"event_type":"DECISION"}\n'
        with pytest.raises(ValueError, match="missing fields"):
            replay(io.StringIO(bad_input), io.StringIO(), strict=True)

    def test_invalid_event_type_strict(self):
        bad_input = json.dumps(
            {
                "schema_version": "envelope.v1",
                "event_type": "BOGUS",
                "event_id": "ev-001",
                "ts_ms": 1000,
                "payload": {},
            }
        ) + "\n"
        with pytest.raises(ValueError, match="invalid event_type"):
            replay(io.StringIO(bad_input), io.StringIO(), strict=True)

    def test_ts_ms_not_int_strict(self):
        bad_input = json.dumps(
            {
                "schema_version": "envelope.v1",
                "event_type": "DECISION",
                "event_id": "ev-001",
                "ts_ms": "not-an-int",
                "payload": {},
            }
        ) + "\n"
        with pytest.raises(ValueError, match="ts_ms must be int"):
            replay(io.StringIO(bad_input), io.StringIO(), strict=True)

    def test_payload_not_dict_strict(self):
        bad_input = json.dumps(
            {
                "schema_version": "envelope.v1",
                "event_type": "DECISION",
                "event_id": "ev-001",
                "ts_ms": 1000,
                "payload": "not-a-dict",
            }
        ) + "\n"
        with pytest.raises(ValueError, match="payload must be dict"):
            replay(io.StringIO(bad_input), io.StringIO(), strict=True)

    def test_invalid_json_strict(self):
        with pytest.raises(ValueError, match="invalid JSON"):
            replay(io.StringIO("NOT JSON\n"), io.StringIO(), strict=True)

    def test_validate_envelope_valid(self):
        obj = {
            "schema_version": "envelope.v1",
            "event_type": "DECISION",
            "event_id": "ev-1",
            "ts_ms": 1000,
            "payload": {},
        }
        assert validate_envelope(obj, 1) == []


class TestLenientMode:
    def test_skips_invalid_lines(self):
        bad_line = "NOT JSON\n"
        good_line = json.dumps(
            {
                "schema_version": "envelope.v1",
                "event_type": "DECISION",
                "event_id": "ev-001",
                "ts_ms": 1000,
                "payload": {},
            }
        ) + "\n"
        output = io.StringIO()
        summary = replay(
            io.StringIO(bad_line + good_line), output, strict=False, chain=True
        )
        assert summary["processed"] == 1
        assert summary["skipped"] == 1
        assert len(summary["errors"]) == 1


class TestChainHash:
    def test_swapped_order_changes_chain_hash(self):
        """Swapping event order produces different chain_hash (sequence integrity)."""
        events = [
            {
                "schema_version": "envelope.v1",
                "event_type": "DECISION",
                "event_id": "ev-1",
                "ts_ms": 1000,
                "payload": {"d": "ALLOW"},
            },
            {
                "schema_version": "envelope.v1",
                "event_type": "ORDER",
                "event_id": "ev-2",
                "ts_ms": 2000,
                "payload": {"symbol": "BTC"},
            },
        ]
        # Order A->B
        buf_ab = io.StringIO()
        input_ab = "\n".join(json.dumps(e) for e in events) + "\n"
        replay(io.StringIO(input_ab), buf_ab, chain=True)
        buf_ab.seek(0)
        lines_ab = [json.loads(line) for line in buf_ab if line.strip()]

        # Order B->A
        buf_ba = io.StringIO()
        input_ba = "\n".join(json.dumps(e) for e in reversed(events)) + "\n"
        replay(io.StringIO(input_ba), buf_ba, chain=True)
        buf_ba.seek(0)
        lines_ba = [json.loads(line) for line in buf_ba if line.strip()]

        assert lines_ab[-1]["chain_hash"] != lines_ba[-1]["chain_hash"]

    def test_no_chain_mode(self):
        """With chain=False, output has no chain_hash field."""
        event = json.dumps(
            {
                "schema_version": "envelope.v1",
                "event_type": "DECISION",
                "event_id": "ev-1",
                "ts_ms": 1000,
                "payload": {},
            }
        ) + "\n"
        output = io.StringIO()
        summary = replay(io.StringIO(event), output, chain=False)
        output.seek(0)
        result = json.loads(output.readline())
        assert "chain_hash" not in result
        assert "event_hash" in result
        assert summary["final_chain_hash"] is None


class TestEdgeCases:
    def test_empty_input(self):
        output = io.StringIO()
        summary = replay(io.StringIO(""), output, strict=True, chain=True)
        assert summary["processed"] == 0
        assert summary["skipped"] == 0

    def test_blank_lines_skipped(self):
        event = json.dumps(
            {
                "schema_version": "envelope.v1",
                "event_type": "FILL",
                "event_id": "ev-1",
                "ts_ms": 1000,
                "payload": {},
            }
        )
        input_text = f"\n\n{event}\n\n"
        output = io.StringIO()
        summary = replay(io.StringIO(input_text), output, strict=True)
        assert summary["processed"] == 1
