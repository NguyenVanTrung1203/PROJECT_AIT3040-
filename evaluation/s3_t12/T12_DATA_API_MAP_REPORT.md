# T12 Data API & Map Report

**Status: CONDITIONAL**
**Branch:** `Trinh_Toan` · **HEAD at audit:** `6b2de9a6c63fa64b2afda9094acf54b0086a061c`

## Implementation

The FastAPI app now exposes the five approved Replay V1 paths from `contracts/api_contract.yaml`. The adapter in `backend/app/replay_api.py` wraps the existing T09 `ReplaySessionCore` and TrackBuffer; it serves a clearly synthetic, ten-event fixture only. `/api/v1/mock/...` remains separate and unchanged in behavior. The React/Leaflet app keeps Mock as its default, adds an explicit Replay fixture mode, draws runtime marker/history, fetches selected TrackSnapshot details using the pinned snapshot ID, and offers Refresh and RESET controls.

Track snapshots pass the production TrackSnapshot JSON Schema and G11 structural + semantic validator, then T09 temporal/history checks before API response. Tests assert selected source times do not exceed nominal times, history has ten points at the full anchor, and `current_state` equals the final history point. No risk, alert, forecast or M5a result was added.

## Contract and limits

API request/response tests cover all five paths, schema validation, valid UTC Z input, pagination validation and snapshot pinning, 5 minute snapshot expiry (410), unknown source/session/vessel errors, session expiry (410), reset isolation and idempotent retry in one process. The T09 core already enforces the tested state/version transitions.

Runtime session state, idempotency records and snapshot pages are memory-only. There is no transactional durable persistence, multi-worker isolation, persistent TTL, playback scheduler/clock advancement, or cross-restart idempotency. The route accepts controls, but this build is not a production session service. Pagination was exercised for a pinned fixture response, but persistence and concurrent consistency are not verified. The source AIS timezone and identity validation remains CONDITIONAL; the endpoint uses the synthetic fixture and DATASET_FINAL is not used as AIS replay.

## Verification

- Backend regression: `317 passed, 1 warning` (`python -m pytest tests/unit tests/integration backend/tests -q -p no:cacheprovider`). Includes T08/T09 and T04 mock API regression.
- Frontend: `6 passed` (`npm test`). Tests include Replay fixture create, selected detail fetch and RESET with a fresh session, alongside all five existing Mock-map cases.
- Production frontend build: `npm run build` completed successfully with Vite 7.3.8/esbuild; production bundle generated.
- API contract: all five Replay routes exercised via TestClient; schema checks applied to session/list/TrackSnapshot responses.
- Map: React tests assert Leaflet latitude/longitude order, runtime history, and selection behavior using a mocked `react-leaflet` layer. A separate Chrome Replay Fixture acceptance was observed and recorded as `T12_BROWSER_ACCEPTANCE=PASS` in [`T12_BROWSER_ACCEPTANCE.md`](T12_BROWSER_ACCEPTANCE.md); that pass applies only to the fixture flow.
- `DATASET_FINAL` remains read-only; T13 checksum verification passed for all 93 locked files.

## Run locally

From repository root, start backend:

```powershell
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

In a second terminal:

```powershell
cd frontend
npm run dev
```

Open `http://localhost:5173`, choose **Replay fixture**, then **Bắt đầu replay fixture**. The endpoint is fixture-only in this task. Use **Mock** to return to the independent T04 API.

## Remaining for production

Durable session/track storage, atomic reset/seek and idempotency persistence, TTL cleanup under concurrent requests, playback clock scheduling, and source-owner evidence for real AIS UTC/identity remain open. These limitations prevent a production-ready claim.
