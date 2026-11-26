# T17 Replay Controls Report

## Scope and implementation

- Replay fixture UI controls: `PLAY`, `PAUSE`, `RESUME`, `RESET`, and `SEEK`.
- Control payloads carry the most recently observed server `expected_version`. `RESET` and `SEEK` send an `Idempotency-Key`; retry reuses the same key and payload.
- `RESET` and `SEEK` adopt the successor session returned by Replay V1 and clear the selected track, snapshot, and forecast layer before loading that session.
- The UI polls the Replay session and snapshot. Simulation UTC is server-authoritative; browser wall time is not used as AIS or simulation time.
- Replay Fixture creation omits optional `start_time`, allowing the backend source start to apply.
- Mock API mode remains separate from Replay fixture mode.

## Backend clock and control version

`ReplayAPI` advances a PLAYING session from backend monotonic elapsed time when a session or track REST read/control occurs. The frontend polls once per second. The API catches up elapsed server time and clamps at source end.

Acceptance identified a timing race where time-only advancement incremented the optimistic control version before checking a control request. This could produce `409 VERSION_CONFLICT` without another control action. The core now leaves version unchanged on normal clock ticks and increments it once for automatic `PLAYING → ENDED`. Real version/state/idempotency conflicts continue to return HTTP 409 as required.

This remains an in-process, on-demand fixture clock. It does not establish durable scheduling, cross-worker consistency, transactionally durable idempotency/TTL, persistence, or restart recovery.

## Evidence

- Full Python regression: **327 passed**, one upstream `PytestRemovedIn10Warning`.
- Frontend Vitest: **20 passed** across 2 files.
- Frontend production build: **PASS**, Vite transformed 74 modules and emitted the production bundle.
- API/core tests verify source-end clamp, stable version across ticks, PAUSE after clock progress, RESUME, 409 on ended-session control, SEEK session isolation, and as-of bounds.
- Frontend tests verify controls, version payloads, reset/seek session replacement, idempotent retry key stability, source-start create payload, and mode/fixture UI.
- `git diff --check`: **PASS**.
- Browser acceptance: **PENDING_MANUAL**. The previously supplied Chrome observation showed the old 00:09 start request. No new Chrome observation verifies the corrected browser request or controls.

## Run locally

From the repository root:

```powershell
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```powershell
cd frontend
npm run dev -- --host 127.0.0.1
```

Open `http://127.0.0.1:5173`, select **Replay fixture**, and exercise PLAY/PAUSE/RESUME/RESET/SEEK. The source is `fixture-denmark-10m-v1`, a synthetic fixture, not production AIS.
