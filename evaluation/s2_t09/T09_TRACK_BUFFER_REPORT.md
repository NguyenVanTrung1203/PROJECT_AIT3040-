# S2_T09 Track Buffer and As-of Report

**Date:** 2026-11-24
**Branch:** `Trinh_Toan`
**Status:** `BUFFER_STATUS: PASS`; `ASOF_HISTORY: PASS`; `STALE_STATUS: PASS`; overall T09 remains CONDITIONAL.

The implementation follows the D-01/D-02/D-05 decisions, the production TrackSnapshot schema, and G11. The repository's `temporal_contract.json` still labels itself `proposed_pending_team_review`, while the final lock-readiness report describes the V1 design as locked. T09 leaves those contract artifacts untouched; this companion-status mismatch is recorded as a compatibility review item rather than silently resolved here.

## Implementation

`src/data/track_buffer.py` provides `TrackBuffer`, scoped to a single replay session. `src/data/replay_time.py` parses explicit known UTC timestamps at nanosecond precision without converting through floating-point time. The buffer:

- Accepts T08 ordered event objects while also tolerating deterministic out-of-order ingestion inside the retention window.
- Separates vessels by NFC canonical `vessel_id`; rejects a session ID mismatch and identity/source changes for an existing ID.
- Keeps selected `timestamp_utc`, original source timestamp, and `source_file`/`source_row` provenance. As-of uses only selected source time.
- Requires a caller-supplied source identity verifier for `REAL_AIS` and any `physical_mmsi:` ID. With no verifier, the default is fail-closed. This enforces a policy hook; it does not establish a trusted production AIS registry.
- Enforces finite coordinates, SOG/COG ranges, identity semantics, UTC, and provenance before accepting an event. It does not interpolate or write a QC field to the TrackSnapshot wire.
- Bounds memory by 900-second per-vessel retention, 4,096 events/vessel, 10,000 vessels, and 1,000,000 total buffered events by default. Limits are configurable. Out-of-window late events and full buffers fail explicitly.

For each anchor, it builds the 10 nominal points at offsets -9 through 0 minutes. Each point selects the latest buffered event with selected timestamp `<=` nominal time and age `0..60` seconds inclusive. Repeated use of one selected source message at adjacent grid points is allowed by the temporal contract. It never selects a future source message or uses `original_source_timestamp` for as-of.

Status rules implemented:

- `VALID`: all 10 nominal points exist; `current_state == history[-1]`.
- `STALE`: the newest event known by the anchor is older than 60 seconds.
- `INSUFFICIENT_DATA`: no event is available by anchor or fewer than 10 valid as-of points exist while current data is fresh.
- `INVALID_DATA`: a recorded invalid source marker is at or after the latest accepted point and not later than anchor. Rejected payload values are not retained or exposed.

Non-VALID snapshots carry `current_state: null`; their `history` may contain only the valid as-of points that can be formed. Every emitted snapshot passes production JSON Schema + G11 and additional session-clock/history/temporal validation. G11 is not treated as the full contract validator.

## Verification

```powershell
python -m pytest tests/unit/test_track_buffer.py -q -p no:cacheprovider
```

Use through the session core by creating a session, feeding each ordered T08 event with that session ID, then requesting a snapshot at the session simulation clock. Configure a source verifier that checks an approved source registry and provenance before accepting REAL_AIS; the test verifier is not suitable for production.

Cases cover per-session isolation, out-of-order ordering, NFC identities, physical-ID source-verification gate, synthetic trajectory semantics, nanosecond/UTC handling, event QC, future leakage, exact 0/60/61-second ages, incomplete/stale/invalid states, stable same-time selection, retention/capacity, selected versus original timestamps, and G11-valid snapshots.

The companion integration test also runs the real T08 Parquet reader against a small checked-in fixture and passes its ordered output into T09.

## Limits

The actual cleaned AIS source remains identity/timezone CONDITIONAL per `evaluation/s2_t08/T08_SOURCE_VALIDATION.md` and `T08_IDENTITY_VALIDATION.md`. T09 therefore requires an explicit verifier at runtime; no default real-world source trust is asserted. The buffer is process-memory only and is not safe as a cross-process shared state store.
