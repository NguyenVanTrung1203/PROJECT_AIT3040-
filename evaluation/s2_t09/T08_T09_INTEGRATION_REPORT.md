# T08 → T09 Integration Report

**Date:** 2026-11-24
**Status:** `T08_T09_INTEGRATION: PASS` for fixture flow and a controlled local AIS slice; actual-source identity acceptance remains CONDITIONAL.

## Verified flow

`tests/integration/test_t08_t09_replay_integration.py` writes a 10-row AIS-shaped Parquet fixture using T08's actual schema/reader and `run_replay`, checks ordered events and QC, ingests them into a new T09 session buffer under an explicit fixture-only identity verifier, then creates a production TrackSnapshot. The result has 10 valid anchor-grid points, no future source timestamps, selected source time retained, and passes `validate_production_track_g11` plus temporal checks. The test then RESETs the source session and proves the new READY session has an empty buffer while the ended source session retains only its own old snapshot.

The same test runs T08 over the controlled local source interval `[2024-11-01T00:00:00Z, 2024-11-01T00:00:15Z)` for MMSI `338443451`, feeds the resulting real Parquet event to a separate T09 session, and verifies it yields one as-of point with `INSUFFICIENT_DATA` and no future leakage. The test verifier is explicitly a test hook that checks the known file/MMSI mapping; it is not a production source-owner or vessel-ownership attestation.

The fixture is `tests/fixtures/t09_ais_rows.json`. It is test data, not a replacement for the AIS replay source or `DATASET_FINAL`.

## Run

```powershell
python -m pytest tests/integration/test_t08_t09_replay_integration.py -q -p no:cacheprovider
python -m pytest tests/unit tests/integration backend/tests -q -p no:cacheprovider
```

The second command includes the existing T04 mock API regression suite: **313 passed, 0 failed**, with one existing AnyIO/PytestRemovedIn10Warning.

## Not covered

- Actual cleaned-AIS-to-TrackSnapshot production flow is intentionally not accepted because upstream source timezone and vessel identity verification remain conditional. T08 actual-source CLI smoke is separately documented in the T08 reports.
- No production HTTP API, cross-process transaction, durable idempotency, session/snapshot pagination, TTL worker, or frontend replay controls.
- M5a, CPA, Risk, Alert, forecast, and alert lifecycle are not implemented here.

## Carryover

The repository does not contain the sprint task plan defining T12–T13/T16–T17, so assignment by exact task number must be confirmed against that plan. Proposed follow-up areas are:

- **T12–T13 candidate:** REST API wiring to this core, source registry/verification integration, durable session/idempotency transactions, multi-worker concurrency, session expiry, and API-level contract tests.
- **T16–T17 candidate:** frontend replay controls and end-to-end wiring after the API contract is implemented. Model, Forecast, CPA, Risk, and Alert remain with their designated owner/scope; T09 adds none of them.
