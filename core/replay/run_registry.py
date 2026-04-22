"""ARVP replay run registry: runner identity, lifecycle, and small summaries.

Scope (#1843): file-backed run registry, runner-owned run ids, lifecycle status,
and concise operator-facing per-run summaries.

Non-goals:
  - scenario orchestration
  - database-backed registries
  - multi-process locking
  - scheduler logic
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from core.replay.canonical_json import canonical_hash, canonical_json_dumps
from core.replay.scheduler import SchedulerConfig, SchedulerError

_DEFAULT_REGISTRY_PATH = Path("artifacts") / "replay_reports" / "run_registry.jsonl"
_VALID_STATUSES: frozenset[str] = frozenset({"running", "completed", "failed"})
_VALID_MODES: frozenset[str] = frozenset({"baseline"})
_HEX_64_RE = re.compile(r"^[a-f0-9]{64}$")
_RUN_ID_RE = re.compile(r"^replay-[a-f0-9]{12}-\d{4}$")
_EXECUTION_PROVENANCE_ID_RE = re.compile(r"^bt-[a-f0-9]{16}$")


class RunRegistryError(ValueError):
    """Raised when replay run registry data fails validation."""


def _require_non_empty_string(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise RunRegistryError(f"{field_name} must be a non-empty string")


def _parse_utc_iso(value: str, field_name: str) -> datetime:
    _require_non_empty_string(value, field_name)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise RunRegistryError(f"{field_name} must be a valid ISO-8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RunRegistryError(f"{field_name} must include an explicit UTC offset")
    if parsed.utcoffset() != timedelta(0):
        raise RunRegistryError(f"{field_name} must be a UTC timestamp")
    return parsed


@dataclass(frozen=True, slots=True)
class ReplayRunRecord:
    run_id: str
    status: str
    mode: str
    strategy_id: str
    symbol: str
    dataset_fingerprint: str
    scheduler_profile: str
    execution_provenance_id: str
    artifact_root: str
    gate_status: str | None = None
    deterministic_replay_ok: bool = False
    failure_reason: str | None = None
    started_at_utc: str = ""
    finished_at_utc: str | None = None

    def __post_init__(self) -> None:
        if not _RUN_ID_RE.match(self.run_id):
            raise RunRegistryError(
                "run_id must match 'replay-<12 hex>-<4 digit attempt>'"
            )
        if self.status not in _VALID_STATUSES:
            raise RunRegistryError(
                f"Invalid status {self.status!r}. Valid: {sorted(_VALID_STATUSES)}"
            )
        if self.mode not in _VALID_MODES:
            raise RunRegistryError(
                f"Invalid mode {self.mode!r}. Valid: {sorted(_VALID_MODES)}"
            )
        _require_non_empty_string(self.strategy_id, "strategy_id")
        _require_non_empty_string(self.symbol, "symbol")
        if not _HEX_64_RE.match(self.dataset_fingerprint):
            raise RunRegistryError("dataset_fingerprint must be a 64-char lowercase hex hash")
        try:
            SchedulerConfig(profile=self.scheduler_profile).validate()
        except SchedulerError as exc:
            raise RunRegistryError(str(exc)) from exc
        if not _EXECUTION_PROVENANCE_ID_RE.match(self.execution_provenance_id):
            raise RunRegistryError(
                "execution_provenance_id must match 'bt-<16 hex>'"
            )
        _require_non_empty_string(self.artifact_root, "artifact_root")
        if not isinstance(self.deterministic_replay_ok, bool):
            raise RunRegistryError("deterministic_replay_ok must be bool")
        started = _parse_utc_iso(self.started_at_utc, "started_at_utc")
        finished: datetime | None = None
        if self.finished_at_utc is not None:
            finished = _parse_utc_iso(self.finished_at_utc, "finished_at_utc")
            if finished < started:
                raise RunRegistryError("finished_at_utc must be >= started_at_utc")

        if self.gate_status is not None:
            _require_non_empty_string(self.gate_status, "gate_status")
        if self.failure_reason is not None:
            _require_non_empty_string(self.failure_reason, "failure_reason")

        if self.status == "running":
            if self.finished_at_utc is not None:
                raise RunRegistryError("running records must not set finished_at_utc")
            if self.failure_reason is not None:
                raise RunRegistryError("running records must not set failure_reason")
        elif self.status == "completed":
            if self.finished_at_utc is None:
                raise RunRegistryError("completed records require finished_at_utc")
            if self.failure_reason is not None:
                raise RunRegistryError("completed records must not set failure_reason")
        elif self.status == "failed":
            if self.finished_at_utc is None:
                raise RunRegistryError("failed records require finished_at_utc")
            if self.failure_reason is None:
                raise RunRegistryError("failed records require failure_reason")

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "run_id": self.run_id,
            "status": self.status,
            "mode": self.mode,
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "dataset_fingerprint": self.dataset_fingerprint,
            "scheduler_profile": self.scheduler_profile,
            "execution_provenance_id": self.execution_provenance_id,
            "artifact_root": self.artifact_root,
            "deterministic_replay_ok": self.deterministic_replay_ok,
            "started_at_utc": self.started_at_utc,
        }
        if self.gate_status is not None:
            result["gate_status"] = self.gate_status
        if self.failure_reason is not None:
            result["failure_reason"] = self.failure_reason
        if self.finished_at_utc is not None:
            result["finished_at_utc"] = self.finished_at_utc
        return result


def build_replay_provenance_fingerprint(
    *,
    strategy_id: str,
    symbol: str,
    adapter_id: str,
    dataset_fingerprint: str,
    scheduler_profile: str,
    execution_provenance_id: str,
    code_commit: str,
    mode: str = "baseline",
    config_snapshot: dict[str, Any] | None = None,
) -> str:
    if mode not in _VALID_MODES:
        raise RunRegistryError(f"Invalid mode {mode!r}. Valid: {sorted(_VALID_MODES)}")
    if not _HEX_64_RE.match(dataset_fingerprint):
        raise RunRegistryError("dataset_fingerprint must be a 64-char lowercase hex hash")
    try:
        SchedulerConfig(profile=scheduler_profile).validate()
    except SchedulerError as exc:
        raise RunRegistryError(str(exc)) from exc
    if not _EXECUTION_PROVENANCE_ID_RE.match(execution_provenance_id):
        raise RunRegistryError(
            "execution_provenance_id must match 'bt-<16 hex>'"
        )
    payload: dict[str, Any] = {
        "mode": mode,
        "strategy_id": strategy_id,
        "symbol": symbol,
        "adapter_id": adapter_id,
        "dataset_fingerprint": dataset_fingerprint,
        "scheduler_profile": scheduler_profile,
        "execution_provenance_id": execution_provenance_id,
        "code_commit": code_commit,
    }
    if config_snapshot is not None:
        payload["config_snapshot"] = config_snapshot
    return canonical_hash(payload)


def build_replay_run_id(provenance_fingerprint: str, attempt: int) -> str:
    if not _HEX_64_RE.match(provenance_fingerprint):
        raise RunRegistryError(
            "provenance_fingerprint must be a 64-char lowercase hex hash"
        )
    if attempt <= 0:
        raise RunRegistryError("attempt must be >= 1")
    return f"replay-{provenance_fingerprint[:12]}-{attempt:04d}"


def build_operator_summary(record: ReplayRunRecord) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "run_id": record.run_id,
        "status": record.status,
        "mode": record.mode,
        "strategy_id": record.strategy_id,
        "symbol": record.symbol,
        "dataset_fingerprint": record.dataset_fingerprint,
        "scheduler_profile": record.scheduler_profile,
        "execution_provenance_id": record.execution_provenance_id,
        "artifact_root": record.artifact_root,
        "deterministic_replay_ok": record.deterministic_replay_ok,
        "started_at_utc": record.started_at_utc,
    }
    if record.gate_status is not None:
        summary["gate_status"] = record.gate_status
    if record.failure_reason is not None:
        summary["failure_reason"] = record.failure_reason
    if record.finished_at_utc is not None:
        summary["finished_at_utc"] = record.finished_at_utc
    return summary


class ReplayRunRegistry:
    """Append-only JSONL registry for ARVP replay runs."""

    def __init__(self, registry_path: str | Path = _DEFAULT_REGISTRY_PATH) -> None:
        self._registry_path = Path(registry_path)

    @property
    def path(self) -> Path:
        return self._registry_path

    def append(self, record: ReplayRunRecord) -> None:
        if not isinstance(record, ReplayRunRecord):
            raise RunRegistryError(
                f"Expected ReplayRunRecord, got {type(record).__name__}"
            )
        try:
            self._registry_path.parent.mkdir(parents=True, exist_ok=True)
            with self._registry_path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(canonical_json_dumps(record.to_dict()))
                handle.write("\n")
        except OSError as exc:
            raise RunRegistryError(
                f"Failed to append run registry entry to {self._registry_path}: {exc}"
            ) from exc

    def load_all(self) -> list[ReplayRunRecord]:
        if not self._registry_path.exists():
            return []
        try:
            raw = self._registry_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise RunRegistryError(
                f"Failed to read run registry {self._registry_path}: {exc}"
            ) from exc
        if not raw:
            return []

        records: list[ReplayRunRecord] = []
        for lineno, line in enumerate(raw.splitlines(), start=1):
            if not line.strip():
                raise RunRegistryError(
                    f"Malformed run registry {self._registry_path}: empty line at {lineno}"
                )
            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RunRegistryError(
                    f"Malformed JSON in run registry {self._registry_path} line {lineno}: {exc}"
                ) from exc
            if not isinstance(data, dict):
                raise RunRegistryError(
                    f"Malformed run registry {self._registry_path} line {lineno}: JSON root must be an object"
                )
            try:
                records.append(ReplayRunRecord(**data))
            except (TypeError, RunRegistryError) as exc:
                raise RunRegistryError(
                    f"Invalid run registry record in {self._registry_path} line {lineno}: {exc}"
                ) from exc
        return records

    def next_attempt(self, provenance_fingerprint: str) -> int:
        run_id_prefix = build_replay_run_id(provenance_fingerprint, 1)[:-4]
        attempts: set[int] = set()
        for record in self.load_all():
            if record.run_id.startswith(run_id_prefix):
                suffix = record.run_id.rsplit("-", maxsplit=1)[-1]
                if not suffix.isdigit():
                    raise RunRegistryError(
                        f"Existing run_id has invalid attempt suffix: {record.run_id}"
                    )
                attempts.add(int(suffix))
        return max(attempts, default=0) + 1
