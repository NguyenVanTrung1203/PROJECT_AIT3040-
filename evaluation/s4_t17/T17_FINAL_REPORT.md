# T17 Final Report — Replay Controls and Forecast Map

## Status

**T17_STATUS: CONDITIONAL**

| Area | Status | Evidence / limitation |
|---|---|---|
| Replay controls | PASS (automated scope) | UI/API tests cover PLAY, PAUSE, RESUME, RESET, SEEK, session replacement, and idempotent retry behavior. |
| Replay start time | PASS (fixture automated scope) | UI omits optional `start_time`; API accepts `{ "source_id": "fixture-denmark-10m-v1" }` and returns HTTP 201 at source start `2024-11-01T00:00:00Z`, READY, version 0. |
| Early marker | PASS (synthetic fixture scope) | Causal partial history displays a distinct marker for 1–9/10 points while remaining INSUFFICIENT_DATA; 10/10 at 00:09 becomes VALID. |
| HTTP 409 timing race | FIXED and regression-tested | Ordinary clock ticks no longer increment control version; auto-end increments once. Legitimate stale-version/state/idempotency 409s remain. |
| Forecast map | PASS (synthetic mock scope) | Deterministic 15-point mock layer is clearly labeled and gated on eligible VALID synthetic tracks. No model/risk inference. |
| Python regression | PASS | 327 passed; one upstream AnyIO pytest deprecation warning. |
| Frontend tests | PASS | 20 passed across 2 files. |
| Frontend build | PASS | Vite production build completed; esbuild bundle produced. |
| Browser acceptance | PENDING_MANUAL | No new end-to-end Chrome inspection was performed for this acceptance. Prior user observation of a 00:09 create request predates the start-time fix and cannot verify the corrected browser request. |
| Production readiness | NOT ESTABLISHED | AIS production source remains conditional; runtime persistence, durable idempotency/TTL, and multi-worker clock guarantees are unverified. |

## HTTP 409 classification

The verified repeated timing-related conflict came from version increments on ordinary simulation-clock advancement. Because API control synchronizes the clock before checking `expected_version`, elapsed time alone could invalidate a recently polled version. The core now leaves version unchanged for time-only ticks and increments it once for the automatic PLAYING-to-ENDED state transition. Regression coverage confirms PAUSE can use the latest polled version after clock progress. Contract-valid conflicts for stale versions, invalid control states, and idempotency-key conflicts remain expected.

## Files in T17 scope

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

`frontend/vite.config.js` is a pre-existing local cache-directory workaround and is excluded from T17. T16 evidence remains in `evaluation/s4_t16/` and is tracked separately. No Contract V1, DATASET_FINAL, AIS source, or Trung-owned Model/Risk/Alert code was changed. No commit, push, merge, or branch operation was performed.

## Latest verification

```powershell
.venv\Scripts\python.exe -m pytest tests/unit tests/integration backend/tests -q -p no:cacheprovider
cd frontend
npm test -- --reporter=dot
npm run build
cd ..
git diff --check
```

Results: **327 Python tests passed**, **20 frontend tests passed**, build **PASS**, and `git diff --check` **PASS**. Python emitted one upstream AnyIO `PytestRemovedIn10Warning`.

## Remaining limits

- Manual Chrome acceptance must verify the corrected start payload and visible replay at 00:00–00:09; automated tests do not replace browser evidence.
- Early markers and forecast output are synthetic-fixture behavior only.
- Replay session and idempotency state are process-local; durable storage, concurrency, restart recovery, and production scheduler guarantees remain unverified.
- Production AIS source identity/timezone/duplicate readiness remains conditional.
