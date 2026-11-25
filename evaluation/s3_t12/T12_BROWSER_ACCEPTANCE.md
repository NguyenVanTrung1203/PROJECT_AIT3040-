# T12 Browser Acceptance — Replay Fixture

**T12_BROWSER_ACCEPTANCE=PASS** for the Replay Fixture scope observed in Chrome.

**Evidence basis:** Chrome observations and HTTP response details supplied for this acceptance run. This report records those observations; it does not extend them into unobserved persistence or production-source claims.

## Observed results

- React rendered the Leaflet map and Replay Fixture view in Chrome.
- Replay session creation succeeded with **HTTP 201**.
- Track list and selected track detail each returned **HTTP 200**.
- The selected synthetic fixture rendered its marker/track and **10 history points**.
- Chrome Console showed no JavaScript errors during the observed flow.
- Two independent RESET operations each returned **HTTP 200** and created distinct session IDs:
  - `2fca914b-cfdf-44ac-a5e6-595b5f26c1a4`
  - `348a8cdb-bfe4-4061-997b-c8df4bb91103`
- Both RESET responses contained:

  | Field | Value |
  |---|---|
  | `source_id` | `fixture-denmark-10m-v1` |
  | `simulation_time` | `2024-11-01T00:00:00Z` |
  | `status` | `READY` |
  | `version` | `0` |

- After RESET, the track reported `INSUFFICIENT_DATA`, as expected at the source start where the ten-point history window is not yet available.

## Scope boundary

PASS applies only to the observed Chrome Replay Fixture flow. It does not establish durable idempotency, persistence, concurrency safety, cross-process session isolation, or production AIS source readiness. The fixture is synthetic and does not verify actual AIS ingestion.

## Related automated regression

See `backend/tests/test_replay_api.py` and `frontend/src/App.test.jsx` for automated API and React coverage. The browser observations above are separate from those automated tests.
