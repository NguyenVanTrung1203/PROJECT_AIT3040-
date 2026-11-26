# T12–T13 Integration Report

## Outcome

- **T12: CONDITIONAL.** Replay V1 paths are wired to the T09 session core and TrackBuffer, and React/Leaflet can use a synthetic runtime fixture. Contract response schemas plus G11 structural/semantic and runtime temporal checks are applied. Chrome acceptance for the Replay Fixture flow now passes as recorded in `T12_BROWSER_ACCEPTANCE.md`. Production persistence, transactional session isolation under concurrency, durable idempotency/TTL and clock scheduling are not implemented or verified.
- **T13: PASS.** DATASET_FINAL lock and all 93 checksums verified. Official tensor A/B pairing, source/split/label mapping and global encounter mapping pass without changing the locked data. A repeatable data/API benchmark harness produced JSON output.
- **Source validation: CONDITIONAL.** Real AIS source timezone semantics and physical identity trust remain conditional as documented in T08; T12 uses only a clearly synthetic fixture.
- **Contract compatibility: PASS for tested fixture responses; CONDITIONAL for production.** No Contract V1 file was edited. All five approved Replay paths are implemented and exercised; durable semantics and production operations are still open.

## Test evidence

- Backend: **317 passed, 1 upstream Pytest/AnyIO deprecation warning**. Command: `.venv\Scripts\python.exe -m pytest tests/unit tests/integration backend/tests -q -p no:cacheprovider`.
- Frontend: **6 passed**. Command: `npm test` in `frontend`.
- Frontend build: `npm run build` passed through Vite 7.3.8/esbuild.
- Dataset: `READY_AND_LOCKED`; SHA-256 matched for **93/93** artifacts; Train 1,440 / Validation 835 / Test 1,320 encounters (3,595 total); A/B indices, source mapping, labels and split mapping passed.
- Benchmark: 30 timed iterations after 3 warmups on one fixture track. Latest rerun: list median/p95 12.148/13.981 ms; detail median/p95 7.448/9.319 ms. Not a production throughput claim.
- Future leakage: fixture TrackSnapshot checks confirm `source_timestamp <= nominal_timestamp`; T08/T09 regression includes as-of/future tests.
- Reset/stale/errors: T09/API regression passes RESET isolation/idempotency/version and expiry cases, empty/invalid/not-found API scenarios; Mock `mock-vessel-004` stale refresh regression remains passing.
- `git diff --check` and `git diff --cached --check`: both passed with no whitespace errors. Git emitted only LF-to-CRLF normalization notices for four edited text files.

## Not included

No model or risk code, M5a, Risk, Alert, Test calibration, DATASET_FINAL edit, Contract V1 edit, commit, push, merge, or branch change was performed for T12/T13.

## Files added/updated for this task

- `backend/app/main.py`, `backend/app/replay_api.py`, `backend/app/fixtures/t12_replay_events.json`, `backend/tests/test_replay_api.py`
- `frontend/src/App.jsx`, `frontend/src/App.test.jsx`, `frontend/src/styles.css`
- `scripts/t13_data_benchmark.py`
- `evaluation/s3_t12/T12_DATA_API_MAP_REPORT.md`
- `evaluation/s3_t13/T13_BENCHMARK_INDEX_AUDIT.md`, `evaluation/s3_t13/t13_benchmark_results.json`
- `evaluation/s3_t12_t13/T12_T13_INTEGRATION_REPORT.md`

The worktree already contained uncommitted Contract V1 and T08/T09 changes at task start. Those staged and untracked files were preserved and not rewritten by this work. No branch movement or Git commit operation was performed.
