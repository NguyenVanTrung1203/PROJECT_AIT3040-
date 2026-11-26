# T17 Session Clock and HTTP 409 Verification

## Verified HTTP 409 cause

Before this correction, `ReplaySessionCore.advance_clock()` incremented `session.version` whenever simulation time advanced. `ReplayAPI` synchronizes the playback clock before processing a control request. Therefore, normal PLAYING clock progress between a session poll and PAUSE/RESET/SEEK could change the expected control version and return `409 VERSION_CONFLICT`, even without another control request. This is the confirmed source of the repeated timing-related 409 race.

The control version now tracks control-visible state transitions rather than ordinary clock ticks. Time-only advancement preserves the version. Automatic transition from `PLAYING` to `ENDED` increments the version once. Contract-expected 409 responses remain for a real stale expected version, invalid state/action, or idempotency conflict; those are not treated as defects.

## API and core evidence

- PLAY starts at version 1.
- An elapsed monotonic clock tick advances UTC while retaining version 1.
- PAUSE using the last polled version succeeds and changes version to 2.
- PAUSE freezes simulation time and version.
- RESUME changes version to 3; ordinary subsequent ticks retain version 3.
- Automatic source-end transition sets `ENDED` and increments to version 4 exactly once.
- Controls against an ended session still return HTTP 409 as specified.
- Track history remains causal: `source_timestamp <= nominal_timestamp <= simulation_time`.
- A core regression verifies ordinary advancement does not increment version and auto-end increments once.

## Latest regression results

- Focused session-core and Replay API tests: **20 passed**.
- Full Python regression (`tests/unit`, `tests/integration`, `backend/tests`): **327 passed**, one upstream AnyIO `PytestRemovedIn10Warning`.
- Frontend Vitest: **20 passed** across 2 files.
- Frontend production build: **PASS**, Vite transformed 74 modules.
- `git diff --check`: **PASS**.

The runtime remains process-local and on-demand. These tests do not establish durable persistence, transactionally durable idempotency/TTL, or multi-worker consistency.
