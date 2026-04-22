"""ARVP dataset provider: load historical candle data for replay.

Part of ARVP §4.2 — Historical Data Access layer.
See docs/governance/arvp_platform.md for module boundary definitions.

Providers in this module are responsible for resolving a ``DatasetSpec`` into
an ordered, validated candle series ready for replay injection.

Current implementation status
------------------------------
``FileBackedDatasetProvider`` — **implemented**.
    Loads from a local JSON-array or JSONL file. Validates ordering, 1-minute
    cadence, required fields, and warmup sufficiency.

``DBBackedDatasetProvider`` — **not implemented**.
    Raises ``NotImplementedError``. The Postgres schema
    (``infrastructure/database/schema.sql``) has no candles table.
    ``cdb_db_writer`` does not persist candle data — candles flow through Redis
    ``stream.candles_1m`` and are ephemeral. DB-backed replay input requires a
    candles persistence layer. Tracked in GitHub Issue #1841.

Boundary note
-------------
This provider layer validates *transport and data-shape* concerns only:
ordering, cadence, required field presence. It does NOT enforce bridge-level
semantics such as ``regime_id`` (added by ``historical_bridge.py``) or
window boundary alignment (enforced by the runner layer, #1842/#1843).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from core.replay.dataset_spec import DatasetSpec, DatasetSpecError  # noqa: F401 — re-exported for caller convenience

_REQUIRED_CANDLE_FIELDS: frozenset[str] = frozenset({"ts_ms", "high", "low", "close"})
_ONE_MINUTE_MS: int = 60_000


class DatasetLoadError(ValueError):
    """Raised when a dataset cannot be loaded or fails data-shape validation."""


@dataclass(frozen=True, slots=True)
class DatasetResult:
    """Immutable result of a successful dataset load operation.

    ``candles`` is a tuple of dicts (shallow-immutable at the container level).
    Inner dict values are all numeric primitives (int/float) and are effectively
    immutable. Do not mutate candle dicts after construction.

    ``fingerprint`` is the spec-level request fingerprint (not content hash).
    See ``DatasetSpec.fingerprint()`` for the distinction.
    """

    spec: DatasetSpec
    candles: tuple  # tuple[dict, ...] — full series including warmup rows
    fingerprint: str
    warmup_count: int
    effective_candle_count: int


class DatasetProvider(Protocol):
    """Protocol for all ARVP dataset providers."""

    def load(self, spec: DatasetSpec) -> DatasetResult: ...


class FileBackedDatasetProvider:
    """Load historical candle data from a local JSON-array or JSONL file.

    Accepts:
      - JSON array (``[{...}, ...]``) — all objects in one file
      - JSONL — one JSON object per line; blank lines are skipped

    Validates:
      - Non-empty series after parsing
      - All required fields present in each row: ``ts_ms``, ``high``, ``low``,
        ``close``
      - ``ts_ms`` strictly increasing across consecutive rows
      - Exactly 1-minute (60 000 ms) cadence between consecutive rows
      - ``len(candles) > spec.warmup_candles`` (sufficient data for warmup)

    The file is taken as the authoritative dataset. ``spec.start_ts_ms`` and
    ``spec.end_ts_ms`` are not used to slice the file — window boundary
    enforcement is deferred to the runner/scheduler layer (#1842/#1843).
    """

    def load(self, spec: DatasetSpec) -> DatasetResult:
        spec.validate()

        if spec.source != "file":
            raise DatasetLoadError(
                f"FileBackedDatasetProvider requires source='file', "
                f"got source={spec.source!r}."
            )

        file_path = Path(spec.file_path)  # type: ignore[arg-type]  # validated non-None above

        if not file_path.exists():
            raise DatasetLoadError(f"Dataset file not found: {file_path}")

        try:
            raw = file_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise DatasetLoadError(
                f"Cannot read dataset file {file_path}: {exc}"
            ) from exc

        candles = self._parse(raw, file_path)
        self._validate_series(candles, file_path)

        if len(candles) <= spec.warmup_candles:
            raise DatasetLoadError(
                f"Insufficient candles: {len(candles)} total, "
                f"{spec.warmup_candles} warmup required. "
                f"Need at least {spec.warmup_candles + 1} candles."
            )

        return DatasetResult(
            spec=spec,
            candles=tuple(dict(c) for c in candles),
            fingerprint=spec.fingerprint(),
            warmup_count=spec.warmup_candles,
            effective_candle_count=len(candles) - spec.warmup_candles,
        )

    def _parse(self, raw: str, file_path: Path) -> list[dict]:
        text = raw.strip()
        if not text:
            raise DatasetLoadError(f"Dataset file is empty: {file_path}")

        if text.startswith("["):
            try:
                data = json.loads(text)
            except json.JSONDecodeError as exc:
                raise DatasetLoadError(
                    f"Invalid JSON in dataset file {file_path}: {exc}"
                ) from exc
            if not isinstance(data, list):
                raise DatasetLoadError(
                    f"Expected JSON array in {file_path}, got {type(data).__name__}."
                )
            if not data:
                raise DatasetLoadError(f"Dataset file contains an empty array: {file_path}")
            return data

        # JSONL: one JSON object per line
        rows: list[dict] = []
        for lineno, line in enumerate(text.splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise DatasetLoadError(
                    f"Invalid JSON on line {lineno} of {file_path}: {exc}"
                ) from exc
            if not isinstance(row, dict):
                raise DatasetLoadError(
                    f"Expected JSON object on line {lineno} of {file_path}, "
                    f"got {type(row).__name__}."
                )
            rows.append(row)

        if not rows:
            raise DatasetLoadError(f"Dataset file contains no candle rows: {file_path}")
        return rows

    def _validate_series(self, candles: list[dict], file_path: Path) -> None:
        if not candles:
            raise DatasetLoadError(f"No candles in dataset: {file_path}")

        for idx, candle in enumerate(candles):
            missing = _REQUIRED_CANDLE_FIELDS - candle.keys()
            if missing:
                raise DatasetLoadError(
                    f"Candle at index {idx} is missing required fields "
                    f"{sorted(missing)}: {candle!r}"
                )

        for idx in range(1, len(candles)):
            prev_ts = candles[idx - 1]["ts_ms"]
            curr_ts = candles[idx]["ts_ms"]
            if curr_ts <= prev_ts:
                raise DatasetLoadError(
                    f"ts_ms must be strictly increasing: "
                    f"candle[{idx - 1}]={prev_ts}, candle[{idx}]={curr_ts}. "
                    f"File: {file_path}"
                )
            delta = curr_ts - prev_ts
            if delta != _ONE_MINUTE_MS:
                raise DatasetLoadError(
                    f"1m cadence violation: expected {_ONE_MINUTE_MS}ms gap, "
                    f"got {delta}ms between candle[{idx - 1}] (ts={prev_ts}) "
                    f"and candle[{idx}] (ts={curr_ts}). File: {file_path}"
                )


class DBBackedDatasetProvider:
    """Placeholder for DB-backed historical replay input.

    NOT IMPLEMENTED in this phase.

    Reason: The Postgres schema (``infrastructure/database/schema.sql``) has no
    candles table. The ``cdb_db_writer`` service does not persist candle data —
    candles flow through Redis ``stream.candles_1m`` (ephemeral) and are never
    written to Postgres. Until a candles persistence layer exists, DB-backed
    replay input is not repo-backed implementable.

    This gap is tracked in GitHub Issue #1841.
    """

    def load(self, spec: DatasetSpec) -> DatasetResult:
        spec.validate()
        raise NotImplementedError(
            "DB-backed dataset loading is not implemented. "
            "The Postgres schema has no candles table "
            "(see infrastructure/database/schema.sql). "
            "cdb_db_writer does not persist candle data — "
            "candles are ephemeral in Redis stream.candles_1m. "
            "DB-backed replay input requires a candles persistence layer. "
            "Tracked in GitHub Issue #1841."
        )
