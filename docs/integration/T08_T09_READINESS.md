# T08 / T09 Readiness

## Summary

| Task | Readiness | Can begin independent work? | Integration gate |
|---|---|---|---|
| T08 — AIS replay loader, UTC/QC runtime | CONDITIONAL | YES | Agree the selected source timestamp/as-of rule, raw timezone parsing, duplicate behavior, QC fields/status and replay-clock ownership before treating output as shared TrackSnapshot input. |
| T09 — Track buffer, as-of/stale/reset | CONDITIONAL | YES | Agree identity namespace, A/B and pair/encounter IDs, snapshot completeness, age semantics, reset/seek session behavior and API boundary before connecting to Trung's Encounter/Risk adapter. |

These conditions allow implementation behind internal boundaries. They do not state that either task is complete or that replay-to-risk integration is ready.

## T08 — Loader and UTC/QC runtime

**Can start?** Yes, for a source reader and isolated parser/QC components. `evaluation/data/T03_REPLAY_SOURCE_INVENTORY.md` documents a local historical AIS source and recommends cleaned Parquet; `contracts/temporal_contract.json` describes UTC history offsets and an as-of age interval. The source inventory is preparation evidence only, not a production loader contract.

**Dependency on T06–T07?** The source reader, replay time parser, and raw per-vessel QC do not require M5a training. Online feature validation and end-to-end inference adapter do depend on Trung's feature/rule consumption interface. This repository currently has config/design but no model/risk runtime implementation (`src/models/`, `src/risk/`, `src/training/` contain only `__init__.py`).

**Freeze before shared integration:**

1. Whether replay grid is one-minute and anchored at the common evaluation timestamp, and that wall-clock time never advances a historical replay.
2. Raw AIS timestamp parser/timezone policy and rejection behavior for unknown/naive timestamps.
3. Selected `source_timestamp` versus `original_source_timestamp` semantics for real and shifted synthetic AIS; only the selected as-of time may drive freshness/features.
4. As-of interval `0 ≤ grid − source ≤ 60 seconds` inclusive, reuse policy, and which message is chosen on identical/conflicting `(MMSI,timestamp)` duplicates.
5. QC flags/reason and `data_status` mapping; no interpolation or future-message substitution for missing history.
6. Whether a missing/invalid/stale track yields an unavailable snapshot or typed partial history and which statuses prohibit inference/fallback.

**Can implement independently:** source adapters, UTC normalization, deterministic ordering, duplicate detection, QC metrics and read-only test fixtures. Keep output behind a versioned internal boundary until shared semantics are approved.

## T09 — Track buffer, as-of/stale/reset

**Can start?** Yes, for isolated per-vessel buffering and tests using a frozen replay clock. T04 already provides a mock TrackSnapshot shape and a deterministic API, but it does not implement live buffer, session, pair discovery or reset. Schema-level TrackSnapshot alone does not enforce all temporal semantics.

**TrackSnapshot sufficiency:** It carries vessel identity, MMSI, source/simulation type, anchor, current state, history and data status. It does not carry replay-session or pair/encounter identity, EN origin, quality flags, or a reason. Those belong at a separate encounter/session boundary unless both owners approve a versioned extension.

**Freeze before connecting to Trung:**

1. Physical versus simulated `vessel_id` namespace and MMSI rules; no fabricated MMSI.
2. Stable replay A/B ordering and `pair_id` hashing; separate pair ID from anchor-specific encounter ID.
3. Buffer window size/grid and whether current state must equal the last nominal history point.
4. Age calculation against simulation/as-of time (not host wall clock), stale cutoff, inclusive boundary, and behavior for missing or late samples.
5. Pause/resume, reset and seek semantics. Proposed integration prose says reset/seek creates a new replay session and isolated alert state; confirm whether this is the T09 API contract.
6. Track API path, collection envelope/order, session filtering, pagination and error response mapping. T04's mock list envelope `{items,total}` is not documented in shared OpenAPI.

**Can implement independently:** event ordering, per-MMSI buffers, snapshot construction, age computation, reset mechanics and unit tests with mock clock. Do not produce model/risk decisions or map integration in this task.

## Evidence limits

T04 evidence proves only a deterministic mock API/UI and schema-compatible sample. `tests/integration/test_mock_contracts.py` proves static fixture/schema relations; it does not prove raw AIS replay, loader performance, session state, stale/reset runtime, model inference or production API behavior. T03's source inventory is historical and external to `DATASET_FINAL`; the locked dataset is for offline training/evaluation, not a substitute raw replay feed.
