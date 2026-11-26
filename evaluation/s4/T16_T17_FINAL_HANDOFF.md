# S4 T16–T17 Final Acceptance and Git Handoff

**Date:** 2026-11-25  
**Repository branch:** `Trinh_Toan`  
**HEAD:** `19c00fbeb9d84dd8a65ab8b8bb9e372273246ea7`

## Final status

- `T16_STATUS: CONDITIONAL`
- `T17_STATUS: CONDITIONAL` (automated implementation/regression scope passes; manual browser acceptance remains pending)
- `BROWSER_ACCEPTANCE: PENDING_MANUAL`
- `CONTROL_409_STATUS: FIXED_AND_REGRESSION_TESTED` for the confirmed timing race; contract-valid 409 cases remain expected
- `EARLY_MARKER: PASS` on the synthetic Replay fixture
- `REPLAY_START_TIME: PASS` in frontend/API tests; source default is `2024-11-01T00:00:00Z`
- `FORECAST_MOCK: PASS` for the synthetic fixture and the valid-track gate; no model/risk output
- `READY_TO_COMMIT: YES` for the separated local file groups below; no files are staged and no commit was created
- `READY_FOR_T20_T21: CONDITIONAL`

## T16 findings

The read-only DATASET_FINAL v1.0 audit reports `READY_AND_LOCKED`, 93/93 manifest artifact checksums matching, 3,595 encounters (Train 1,440; Validation 835; Test 1,320), and passing official encounter/A/B/X_row, labels, source/split mapping, tensor metadata, timestamp alignment, and audited cross-split key checks. No locked dataset file was edited. The benchmark rerun is reproducible for its bounded in-process synthetic fixture API harness, with 3 warmups and 30 measured calls; it is not production throughput, AIS ingest, network latency, or model inference.

T16 remains conditional for Sprint 5 integration: the live TrackSnapshot-to-Encounter and online Model/Rule/Forecast adapters are not implemented or verified; companion contract approval metadata needs owner reconciliation; and real AIS production source trust remains conditional. The locked Test split was not used for model scoring or calibration.

## T17 findings

### HTTP 409 root cause and correction

The previous code incremented a replay session's optimistic `version` on ordinary clock progress. Since the API synchronizes the playback clock before processing a control request, elapsed time between polling and PAUSE/RESET/SEEK could alone invalidate the client's expected version and produce repeated `409 VERSION_CONFLICT`. This was confirmed by code path inspection and reproduced as the old API-test expectation.

The correction keeps the control version stable across time-only clock ticks and increments it once when the session automatically transitions `PLAYING → ENDED`. Core and API regressions verify that PAUSE succeeds with the most recently polled version after a clock tick and that auto-end increments once. Genuine stale-version, invalid-state, and idempotency conflicts still return contract-valid 409 responses.

### Start, markers, history, controls, and forecast

Frontend session creation sends exactly `{"source_id":"fixture-denmark-10m-v1"}` and omits optional `start_time`. The API source default is `2024-11-01T00:00:00Z`; automated tests verify HTTP 201, READY, version 0, and that simulation time. The synthetic timeline has 1/10, 2/10, 6/10, and 9/10 points at 00:00, 00:01, 00:05, and 00:08 respectively, remaining `INSUFFICIENT_DATA`; at 00:09 it has 10/10 and becomes `VALID`. At 00:10 the 00:09 fix is exactly 60 seconds old and remains within the inclusive freshness boundary. No future event, interpolation, fabricated location, or relaxed VALID rule is used.

Automated frontend/API/core coverage exercises PLAY, PAUSE, RESUME, RESET, SEEK, session isolation, retry behavior, clock advancement/end, incomplete-track forecast gating, and T04 Mock mode. Forecast Mock is deterministic, explicitly labeled, and only available for eligible valid synthetic tracks. It is not Model/Risk/Alert inference.

The user-provided Chrome observation showed the old 00:09 `start_time` request and the matching READY response. No new Chrome session/network/visual observation was performed after removing that field. Automated tests establish the corrected payload and backend source start, but they do not replace a fresh browser check; Browser acceptance therefore remains `PENDING_MANUAL`.

## Test results

- Focused replay core + API regression: **20 passed**.
- Full Python regression (`tests/unit`, `tests/integration`, `backend/tests`): **327 passed**, 1 upstream AnyIO `PytestRemovedIn10Warning`.
- Frontend Vitest: **20 passed** across 2 test files.
- Frontend production build: **PASS**, Vite 7.3.8 transformed 74 modules and emitted the bundle.
- `git diff --check`: **PASS**.
- No T16 benchmark or dataset-integrity rerun was needed for the T17 versioning correction; the existing T16 JSON evidence remains unchanged.

## Git state and inventory

- Current branch: `Trinh_Toan`; HEAD: `19c00fbeb9d84dd8a65ab8b8bb9e372273246ea7`.
- No staged changes. No commit/push/merge/reset/rebase/branch operation was performed.
- Dirty paths are classified into the T16, T17, local workaround, and this handoff groups below.
- No changes were observed in `DATASET_FINAL`, Contract V1/G11, AIS source data, or Trung-owned Model/Risk/Alert files.

### Proposed T16 commit files

- `evaluation/s4_t16/T16_BENCHMARK_REVIEW.md`
- `evaluation/s4_t16/T16_INDEX_INTEGRITY_REPORT.md`
- `evaluation/s4_t16/T16_TRUNG_INTEGRATION_READINESS.md`
- `evaluation/s4_t16/T16_FINAL_REPORT.md`
- `evaluation/s4_t16/t13_benchmark_rerun.json`

### Proposed T17 commit files

- `src/data/replay_session_core.py`
- `tests/unit/test_replay_session_core.py`
- `backend/app/replay_api.py`
- `backend/tests/test_replay_api.py`
- `frontend/src/App.jsx`
- `frontend/src/App.test.jsx`
- `frontend/src/styles.css`
- `frontend/src/forecastMock.js`
- `frontend/src/forecastMock.test.js`
- `evaluation/s4_t17/T17_REPLAY_CONTROLS_REPORT.md`
- `evaluation/s4_t17/T17_FORECAST_MAP_REPORT.md`
- `evaluation/s4_t17/T17_SESSION_CLOCK_TEST_REPORT.md`
- `evaluation/s4_t17/T17_BROWSER_ACCEPTANCE_CHECKLIST.md`
- `evaluation/s4_t17/T17_EARLY_MARKER_DISPLAY_REPORT.md`
- `evaluation/s4_t17/T17_REPLAY_START_TIME_FIX.md`
- `evaluation/s4_t17/T17_FINAL_REPORT.md`

### Separate local / handoff paths

- `frontend/vite.config.js` — pre-existing local Vite cache-directory workaround; keep separate and do not include in T16/T17 commits without separate review.
- `evaluation/s4/T16_T17_FINAL_HANDOFF.md` — this combined handoff report; documentation-only grouping.

Files listed above are recommendations by scope, not staged changes. Recheck each path and staged diff before committing.

## Limits and readiness

- `T16_STATUS: CONDITIONAL`; real AIS remains conditional for production due to source evidence/trust gaps, and Trung-owned live adapters remain dependencies.
- `T17_STATUS: CONDITIONAL`; fresh Chrome acceptance of the corrected 00:00 startup and UI controls remains outstanding.
- Replay session persistence, durable idempotency/TTL, restart recovery, and multi-worker concurrency are not established by process-local tests.
- `READY_FOR_T20_T21: CONDITIONAL`, pending manual browser acceptance and resolution of the T16 integration/source dependencies relevant to the planned work.

No commit, push, merge, reset, rebase, branch switch, Contract V1 edit, dataset edit, or Model/Risk/Alert change was performed.
