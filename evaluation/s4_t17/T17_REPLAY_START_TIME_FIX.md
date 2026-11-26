# T17 Replay Start Time Fix

## Result

Replay Fixture creation now omits the optional `start_time` field and sends exactly:

```json
{"source_id":"fixture-denmark-10m-v1"}
```

In `frontend/src/App.jsx`, `startReplay` posts only `source_id`. The replay source registered by the backend starts at `2024-11-01T00:00:00Z`; the API regression posts without `start_time` and verifies HTTP 201, READY, version 0, and that exact simulation time. The UI test checks the request payload and displayed source-start time.

## Early marker and history behavior

Replay API tests cover the fixture timeline:

| Anchor UTC | History | Status |
|---|---:|---|
| 00:00 | 1/10 | INSUFFICIENT_DATA |
| 00:01 | 2/10 | INSUFFICIENT_DATA |
| 00:05 | 6/10 | INSUFFICIENT_DATA |
| 00:08 | 9/10 | INSUFFICIENT_DATA |
| 00:09 | 10/10 | VALID |
| 00:10 | 10/10 | VALID at the inclusive 60-second freshness boundary |

The UI selects only an as-of eligible observed history point for an incomplete marker. It does not interpolate, set `current_state`, relax the VALID requirement, or enable Forecast Mock/Model/Risk inference for incomplete data. RESET/SEEK session replacement clears the old selection and forecast state. Mock Mode remains independently covered by the frontend regression suite.

## HTTP 409 control race

Final acceptance also found and fixed a related verified timing race: the replay clock previously incremented the optimistic control `version` on each time-only tick. The API synchronizes playback before checking a control request, so elapsed time alone could cause a repeated `409 VERSION_CONFLICT`. Time-only ticks now preserve version; the automatic PLAYING-to-ENDED transition increments it once. Core and API regression tests cover this behavior. Valid 409 responses for genuine version/state/idempotency conflicts remain expected.

## Latest test results

- Full Python regression (`tests/unit`, `tests/integration`, `backend/tests`): **327 passed**, one upstream AnyIO `PytestRemovedIn10Warning`.
- Focused session core + Replay API checks: **20 passed**.
- Frontend Vitest: **20 passed** across 2 files.
- Frontend production build: **PASS**, 74 modules transformed.
- `git diff --check`: **PASS**.

## Browser evidence and limits

The user previously observed Chrome submitting `start_time=2024-11-01T00:09:00Z` and receiving a READY session at 00:09. That observation confirms the old behavior. No fresh Chrome network/visual evidence was gathered after this fix, so current browser acceptance remains pending manual verification. The source and early-marker timeline are synthetic fixture evidence; they do not establish production AIS readiness. Runtime persistence and multi-worker behavior remain outside this change.

## Files changed for the start-time fix and acceptance correction

- `frontend/src/App.jsx`
- `frontend/src/App.test.jsx`
- `backend/tests/test_replay_api.py`
- `src/data/replay_session_core.py` (control-version race fix)
- `tests/unit/test_replay_session_core.py`
- `evaluation/s4_t17/T17_REPLAY_START_TIME_FIX.md`
- `evaluation/s4_t17/T17_SESSION_CLOCK_TEST_REPORT.md`
- `evaluation/s4_t17/T17_FINAL_REPORT.md`

No Contract V1, DATASET_FINAL, AIS source, or Trung-owned Model/Risk/Alert code was modified.
