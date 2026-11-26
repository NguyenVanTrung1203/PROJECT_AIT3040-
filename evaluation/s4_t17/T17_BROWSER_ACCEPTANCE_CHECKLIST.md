# T17 Browser Acceptance Checklist

**Status: `BROWSER_ACCEPTANCE=PENDING_MANUAL`**

The Chrome automation attempt ended before page inspection because the helper could not determine the current URL with sufficient confidence. No screenshot or visual browser result was obtained. Automated UI tests and the production build are separate evidence and do not replace this checklist.

## Manual procedure

1. Start the backend from the repository root:
   ` .venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000`
2. Start the frontend in a second terminal:
   `cd frontend` then `npm run dev -- --host 127.0.0.1`
3. Open `http://127.0.0.1:5173` in Chrome and confirm the Mock mode still loads independently.
4. Choose **Replay fixture**, start the session, and verify source, session ID, UTC, status, version, track list, marker, and history.
5. Run PLAY, wait for backend UTC/version to advance, then PAUSE and confirm UTC stops. RESUME and confirm it advances again.
6. Set SEEK to a valid in-range time and verify a new `PAUSED` session ID/version zero is shown, with prior marker/selection/forecast cleared.
7. RESET and verify a new `READY` session at source start with version zero; inspect the expected `INSUFFICIENT_DATA` result at the source boundary.
8. Select the synthetic track and enable Forecast Mock. Confirm a 15-point dashed layer and the **MOCK FORECAST — NOT MODEL OUTPUT** label. Confirm no forecast appears for invalid/stale or real-AIS tracks.
9. Inspect Chrome Console and Network for JavaScript errors, API failures, control request payloads (`expected_version`, idempotency key for RESET/SEEK), and polling responses.
10. Record screenshots, observed HTTP statuses, session IDs, and console result in this report before changing status to PASS.

