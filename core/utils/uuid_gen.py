"""
Deterministic UUID Generator for Event-Sourcing Replay.
Governance: CDB_PSM_POLICY.md (Event-Sourcing, Determinismus)

relations:
  role: uuid_generator
  domain: utility
  upstream:
    - governance/CDB_PSM_POLICY.md
  downstream:
    - core/domain/event.py
    - tests/replay/test_deterministic_replay.py
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Optional


DEFAULT_NAMESPACE = uuid.UUID("00000000-0000-0000-0000-000000000000")


class DeterministicUUIDGenerator:
    """Generates deterministic UUIDs for replay scenarios."""

    def __init__(self, seed: int = 0, namespace: uuid.UUID = DEFAULT_NAMESPACE):
        self._seed = seed
        self._counter = 0
        self._namespace = namespace

    def generate(self, name: Optional[str] = None) -> uuid.UUID:
        """Generate a deterministic UUID from a name or seed/counter."""
        if name is None:
            name = f"{self._seed}-{self._counter}"
            self._counter += 1
        return uuid.uuid5(self._namespace, name)

    def reset(self, seed: Optional[int] = None) -> None:
        """Reset the generator counter and optionally update the seed."""
        if seed is not None:
            self._seed = seed
        self._counter = 0


_DEFAULT_GENERATOR = DeterministicUUIDGenerator()


def generate_uuid(name: Optional[str] = None, seed: Optional[int] = None) -> str:
    """Generate a deterministic UUID string."""
    if seed is not None:
        generator = DeterministicUUIDGenerator(seed)
        return str(generator.generate(name))
    return str(_DEFAULT_GENERATOR.generate(name))


def generate_uuid_hex(
    name: Optional[str] = None, seed: Optional[int] = None, length: int = 8
) -> str:
    """Generate a deterministic UUID hex string with a specific length."""
    value = generate_uuid(name=name, seed=seed)
    return uuid.UUID(value).hex[:length]


# Namespace for decision_pk (Phase 8B)
DECISION_PK_NAMESPACE = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

# Fields included in input snapshot hash (deterministic, immutable)
DECISION_HASH_FIELDS = (
    "symbol",
    "timestamp_ms",
    "regime_id",
    "return_1m",
    "return_5m",
    "price_change_5m",
    "pct_change_15m",
    "volume_15m",
    "daily_drawdown_pct",
    "total_exposure_pct",
    "slippage_pct",
    "staleness_s",
    "data_silence_s",
    "thresholds",
)


def _sanitize_float(value: Any) -> Any:
    """Sanitize float values for deterministic JSON serialization."""
    if isinstance(value, float):
        if value != value or value == float("inf") or value == float("-inf"):
            return None
        return round(value, 10)
    if isinstance(value, dict):
        return {k: _sanitize_float(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_float(v) for v in value]
    return value


def compute_input_snapshot_hash(evidence: dict) -> str:
    """Compute SHA256 hash of deterministic evidence fields."""
    snapshot = {}
    for field in DECISION_HASH_FIELDS:
        if field in evidence:
            snapshot[field] = _sanitize_float(evidence[field])
    canonical = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def generate_decision_pk(symbol: str, ts_ms: int, evidence: dict) -> str:
    """Generate deterministic decision_pk (UUIDv5) for idempotent persistence."""
    input_hash = compute_input_snapshot_hash(evidence)
    name = f"{symbol}:{ts_ms}:{input_hash}"
    return str(uuid.uuid5(DECISION_PK_NAMESPACE, name))
