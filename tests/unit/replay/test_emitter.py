"""Tests for core.replay.emitter — toggle-gated envelope emission.

Governance: LR-021 Slice 2 Evidence (docs/live-readiness/LR-021-EVIDENCE-SLICE2.md)
"""

import json
import logging

from core.replay.emitter import (
    _build_envelope,
    _compute_event_hash,
    emit_decision_envelope,
    emit_envelope,
    emit_fill_envelope,
    emit_order_envelope,
    envelope_emit_enabled,
)


class TestEnvelopeEmitEnabled:
    def test_default_off(self, monkeypatch):
        monkeypatch.delenv("LR021_ENVELOPE_EMIT_ENABLED", raising=False)
        assert envelope_emit_enabled() is False

    def test_explicit_zero_off(self, monkeypatch):
        monkeypatch.setenv("LR021_ENVELOPE_EMIT_ENABLED", "0")
        assert envelope_emit_enabled() is False

    def test_one_on(self, monkeypatch):
        monkeypatch.setenv("LR021_ENVELOPE_EMIT_ENABLED", "1")
        assert envelope_emit_enabled() is True

    def test_garbage_value_off(self, monkeypatch):
        monkeypatch.setenv("LR021_ENVELOPE_EMIT_ENABLED", "yes")
        assert envelope_emit_enabled() is False


class TestBuildEnvelope:
    def test_required_fields_only(self):
        env = _build_envelope(
            event_type="DECISION",
            event_id="ev-001",
            ts_ms=1700000000000,
            payload={"decision": "ALLOW"},
        )
        assert env["schema_version"] == "envelope.v1"
        assert env["event_type"] == "DECISION"
        assert env["event_id"] == "ev-001"
        assert env["ts_ms"] == 1700000000000
        assert env["payload"] == {"decision": "ALLOW"}
        assert "policy_id" not in env
        assert "policy_hash" not in env
        assert "input_hash" not in env
        assert "output_hash" not in env

    def test_optional_fields_included(self):
        env = _build_envelope(
            event_type="ORDER",
            event_id="ord-001",
            ts_ms=1700000000000,
            payload={"symbol": "BTCUSDT"},
            policy_id="risk_v1",
            policy_hash="abc",
            input_hash="inp",
            output_hash="out",
        )
        assert env["policy_id"] == "risk_v1"
        assert env["policy_hash"] == "abc"
        assert env["input_hash"] == "inp"
        assert env["output_hash"] == "out"


class TestComputeEventHash:
    def test_deterministic(self):
        env = {"event_type": "DECISION", "event_id": "ev-001", "ts_ms": 1000, "payload": {}}
        h1 = _compute_event_hash(env)
        h2 = _compute_event_hash(env)
        assert h1 == h2
        assert len(h1) == 64

    def test_different_data_different_hash(self):
        env1 = {"event_type": "DECISION", "event_id": "ev-001", "ts_ms": 1000, "payload": {}}
        env2 = {"event_type": "DECISION", "event_id": "ev-002", "ts_ms": 1000, "payload": {}}
        assert _compute_event_hash(env1) != _compute_event_hash(env2)


class TestEmitEnvelope:
    def test_noop_when_off(self, monkeypatch, caplog):
        monkeypatch.delenv("LR021_ENVELOPE_EMIT_ENABLED", raising=False)
        env = _build_envelope(
            event_type="DECISION", event_id="ev-001", ts_ms=1000, payload={}
        )
        with caplog.at_level(logging.INFO, logger="lr021.emitter"):
            emit_envelope(env)
        assert len(caplog.records) == 0

    def test_emits_jsonl_when_on(self, monkeypatch, caplog):
        monkeypatch.setenv("LR021_ENVELOPE_EMIT_ENABLED", "1")
        env = _build_envelope(
            event_type="DECISION", event_id="ev-001", ts_ms=1000, payload={"k": "v"}
        )
        with caplog.at_level(logging.INFO, logger="lr021.emitter"):
            emit_envelope(env)
        assert len(caplog.records) == 1
        line = caplog.records[0].message
        parsed = json.loads(line)
        assert parsed["event_type"] == "DECISION"
        assert parsed["event_id"] == "ev-001"
        assert "event_hash" in parsed
        assert len(parsed["event_hash"]) == 64

    def test_event_hash_is_correct(self, monkeypatch, caplog):
        monkeypatch.setenv("LR021_ENVELOPE_EMIT_ENABLED", "1")
        env = _build_envelope(
            event_type="ORDER", event_id="ord-001", ts_ms=2000, payload={"x": 1}
        )
        expected_hash = _compute_event_hash(env)
        with caplog.at_level(logging.INFO, logger="lr021.emitter"):
            emit_envelope(env)
        parsed = json.loads(caplog.records[0].message)
        assert parsed["event_hash"] == expected_hash


class TestEmitDecisionEnvelope:
    def test_noop_when_off(self, monkeypatch, caplog):
        monkeypatch.delenv("LR021_ENVELOPE_EMIT_ENABLED", raising=False)
        with caplog.at_level(logging.INFO, logger="lr021.emitter"):
            emit_decision_envelope(
                event_id="dec-001",
                ts_ms=1000,
                decision="ALLOW",
                reason_code=None,
                symbol="BTCUSDT",
                evidence={"key1": "val1"},
            )
        assert len(caplog.records) == 0

    def test_emits_with_evidence_keys(self, monkeypatch, caplog):
        monkeypatch.setenv("LR021_ENVELOPE_EMIT_ENABLED", "1")
        with caplog.at_level(logging.INFO, logger="lr021.emitter"):
            emit_decision_envelope(
                event_id="dec-001",
                ts_ms=1000,
                decision="BLOCK",
                reason_code="MAX_EXPOSURE",
                symbol="ETHUSDT",
                evidence={"z_key": 1, "a_key": 2},
            )
        assert len(caplog.records) == 1
        parsed = json.loads(caplog.records[0].message)
        assert parsed["event_type"] == "DECISION"
        payload = parsed["payload"]
        assert payload["decision"] == "BLOCK"
        assert payload["reason_code"] == "MAX_EXPOSURE"
        assert payload["symbol"] == "ETHUSDT"
        assert payload["evidence_keys"] == ["a_key", "z_key"]

    def test_reason_code_none_omitted(self, monkeypatch, caplog):
        monkeypatch.setenv("LR021_ENVELOPE_EMIT_ENABLED", "1")
        with caplog.at_level(logging.INFO, logger="lr021.emitter"):
            emit_decision_envelope(
                event_id="dec-002",
                ts_ms=1000,
                decision="ALLOW",
                reason_code=None,
                symbol="BTCUSDT",
                evidence={},
            )
        parsed = json.loads(caplog.records[0].message)
        assert "reason_code" not in parsed["payload"]
        assert "evidence_keys" not in parsed["payload"]

    def test_empty_evidence_no_keys(self, monkeypatch, caplog):
        monkeypatch.setenv("LR021_ENVELOPE_EMIT_ENABLED", "1")
        with caplog.at_level(logging.INFO, logger="lr021.emitter"):
            emit_decision_envelope(
                event_id="dec-003",
                ts_ms=1000,
                decision="ALLOW",
                reason_code=None,
                symbol="BTCUSDT",
                evidence={},
            )
        parsed = json.loads(caplog.records[0].message)
        assert "evidence_keys" not in parsed["payload"]


class TestEmitOrderEnvelope:
    def test_noop_when_off(self, monkeypatch, caplog):
        monkeypatch.delenv("LR021_ENVELOPE_EMIT_ENABLED", raising=False)
        with caplog.at_level(logging.INFO, logger="lr021.emitter"):
            emit_order_envelope(
                event_id="ord-001",
                ts_ms=1000,
                symbol="BTCUSDT",
                side="BUY",
                quantity=0.01,
                price=50000.0,
            )
        assert len(caplog.records) == 0

    def test_emits_order(self, monkeypatch, caplog):
        monkeypatch.setenv("LR021_ENVELOPE_EMIT_ENABLED", "1")
        with caplog.at_level(logging.INFO, logger="lr021.emitter"):
            emit_order_envelope(
                event_id="ord-001",
                ts_ms=1000,
                symbol="BTCUSDT",
                side="BUY",
                quantity=0.01,
                price=50000.0,
                signal_id="sig-001",
                decision_id="dec-001",
            )
        parsed = json.loads(caplog.records[0].message)
        assert parsed["event_type"] == "ORDER"
        payload = parsed["payload"]
        assert payload["symbol"] == "BTCUSDT"
        assert payload["side"] == "BUY"
        assert payload["quantity"] == 0.01
        assert payload["price"] == 50000.0
        assert payload["signal_id"] == "sig-001"
        assert payload["decision_id"] == "dec-001"

    def test_optional_ids_omitted(self, monkeypatch, caplog):
        monkeypatch.setenv("LR021_ENVELOPE_EMIT_ENABLED", "1")
        with caplog.at_level(logging.INFO, logger="lr021.emitter"):
            emit_order_envelope(
                event_id="ord-002",
                ts_ms=1000,
                symbol="ETHUSDT",
                side="SELL",
                quantity=1.0,
                price=3000.0,
            )
        parsed = json.loads(caplog.records[0].message)
        assert "signal_id" not in parsed["payload"]
        assert "decision_id" not in parsed["payload"]


class TestEmitFillEnvelope:
    def test_noop_when_off(self, monkeypatch, caplog):
        monkeypatch.delenv("LR021_ENVELOPE_EMIT_ENABLED", raising=False)
        with caplog.at_level(logging.INFO, logger="lr021.emitter"):
            emit_fill_envelope(
                event_id="fill-001",
                ts_ms=1000,
                order_id="ord-001",
                fill_id="fill-001",
                symbol="BTCUSDT",
                side="BUY",
                filled_quantity=0.01,
                price=50000.0,
            )
        assert len(caplog.records) == 0

    def test_emits_fill(self, monkeypatch, caplog):
        monkeypatch.setenv("LR021_ENVELOPE_EMIT_ENABLED", "1")
        with caplog.at_level(logging.INFO, logger="lr021.emitter"):
            emit_fill_envelope(
                event_id="fill-001",
                ts_ms=1000,
                order_id="ord-001",
                fill_id="fill-001",
                symbol="BTCUSDT",
                side="BUY",
                filled_quantity=0.01,
                price=50000.0,
            )
        parsed = json.loads(caplog.records[0].message)
        assert parsed["event_type"] == "FILL"
        payload = parsed["payload"]
        assert payload["order_id"] == "ord-001"
        assert payload["fill_id"] == "fill-001"
        assert payload["filled_quantity"] == 0.01
        assert payload["price"] == 50000.0

    def test_price_none_omitted(self, monkeypatch, caplog):
        monkeypatch.setenv("LR021_ENVELOPE_EMIT_ENABLED", "1")
        with caplog.at_level(logging.INFO, logger="lr021.emitter"):
            emit_fill_envelope(
                event_id="fill-002",
                ts_ms=1000,
                order_id="ord-002",
                fill_id="fill-002",
                symbol="ETHUSDT",
                side="SELL",
                filled_quantity=1.0,
                price=None,
            )
        parsed = json.loads(caplog.records[0].message)
        assert "price" not in parsed["payload"]

    def test_policy_fields_included(self, monkeypatch, caplog):
        monkeypatch.setenv("LR021_ENVELOPE_EMIT_ENABLED", "1")
        with caplog.at_level(logging.INFO, logger="lr021.emitter"):
            emit_fill_envelope(
                event_id="fill-003",
                ts_ms=1000,
                order_id="ord-003",
                fill_id="fill-003",
                symbol="BTCUSDT",
                side="BUY",
                filled_quantity=0.5,
                price=49000.0,
                policy_id="risk_v1",
                policy_hash="ph123",
                input_hash="ih456",
                output_hash="oh789",
            )
        parsed = json.loads(caplog.records[0].message)
        assert parsed["policy_id"] == "risk_v1"
        assert parsed["policy_hash"] == "ph123"
        assert parsed["input_hash"] == "ih456"
        assert parsed["output_hash"] == "oh789"
