# S2_T09 Session and Reset Verification

**Date:** 2026-11-24
**Status:** `RESET_ISOLATION: PASS`; `SESSION_CORE: CONDITIONAL`.

Compatibility is implemented against the V1 decision record/session proposal and production schemas. The companion `temporal_contract.json` remains marked `proposed_pending_team_review`; no contract file was changed to reconcile that repository status.

## Core scope

`src/data/replay_session_core.py` implements a thread-serialized, process-memory session core. It does not register FastAPI/REST routes, persist state, provide a scheduler, or claim production availability.

- New IDs are canonical lowercase UUIDs; new sessions start at version 0.
- States: READY, PLAYING, PAUSED, ENDED, EXPIRED.
- PLAY/PAUSE/RESUME follow the approved 25-case transition matrix. Valid same-session controls increment version once; invalid controls return a typed 409/410 error.
- Simulation clock is authoritative. It advances only while PLAYING, cannot move backward or beyond source end, and reaching source end sets ENDED without any Alert side effect.
- RESET returns a new READY session at source start. SEEK returns a new PAUSED session at an in-range target. Both increment the old source session version once, mark it ENDED, and allocate a new empty TrackBuffer. No vessel state is copied across sessions.
- RESET/SEEK require `Idempotency-Key` (1–128 chars). The canonical payload order is action, target_time for SEEK only, expected_version. In-process retry lookup precedes current version/state checks; identical retries return the same result, and reusing a key with a different payload returns 409.
- Expected version mismatch is 409. ENDED controls are 409; EXPIRED controls are 410. Targets outside the source interval are 422.

## Persistence and API status

`PENDING_API_PERSISTENCE: NOT_IMPLEMENTED`. Idempotency records have a 24-hour process-memory retention policy, but all sessions and keys are lost on process restart. The lock protects only this Python process; it does not provide database transactions or cross-worker race safety. No production REST routes, durable idempotency store, session expiry worker, or deployment configuration were added. The Contract V1 proposal itself says a memory-only model does not prove runtime atomicity.

## Verification

```powershell
python -m pytest tests/unit/test_replay_session_core.py -q -p no:cacheprovider
```

The tests exercise all 25 state/action cases, reset and seek version behavior, UUID form, expiry status codes, expected_version conflicts, canonical idempotent retry, key collision, 24-hour expiry, source-end clock behavior, and reset buffer isolation. These are core tests, not API/persistence/concurrency acceptance tests.
