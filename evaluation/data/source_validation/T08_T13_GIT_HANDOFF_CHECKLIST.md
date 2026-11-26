# T08–T13 Git Handoff Checklist

**Checked:** 2026-11-25
**Repository:** project root (task checkout)
**Branch:** `Trinh_Toan` (unchanged)
**HEAD:** `6b2de9a6c63fa64b2afda9094acf54b0086a061c` (`wip: save local changes`)
**Remote tracking:** `origin/Trinh_Toan` is one commit behind local HEAD, zero ahead of local according to the local tracking refs. No fetch/pull was performed for this audit. The current task requested inspection only; do not infer remote freshness from these cached refs.

## Working tree snapshot

The tree was already dirty before this report was created:

- **33 staged paths**: primarily Contract V1, G11 shared semantics and contract tests, expected to be reviewed/owned by Trung (see Contract group below).
- **5 unstaged modified paths**: T12 backend/frontend integration attributed to Toàn.
- **Untracked paths**: T08–T13 implementation, tests/fixtures, prior audit reports, plus this task's three new reports.
- No existing staged/unstaged/untracked file was reset, staged, unstaged, deleted, or overwritten by this task.

The three new reports are expected to appear as untracked until explicitly reviewed by their owner.

## File ownership and recommended commit separation

### Group 1 — Trung: Contract V1 / G11 baseline

The following paths were already **staged** at audit start. Preserve their staging and have Trung review/commit them as one independently reviewed contract change:

- `backend/app/mock_tracks.py`
- `contracts/alert_v1.schema.json`, `contracts/api_contract.yaml`, `contracts/encounter_v1.schema.json`, `contracts/feature_contract.json`, `contracts/integration_contract.md`, `contracts/replay.schema.json`, `contracts/risk_request_v1.schema.json`, `contracts/risk_response_v1.schema.json`, `contracts/track_snapshot.schema.json`, `contracts/validation_vectors/g11_track_v1.json`
- `docs/contracts/CONTRACT_V1_API_PROPOSAL.md`, `CONTRACT_V1_DECISION_RECORD.md`, `CONTRACT_V1_FINAL_LOCK_READINESS.md`, `CONTRACT_V1_FREEZE_REPORT.md`, `CONTRACT_V1_G11_SEMANTIC_VALIDATION_REPORT.md`, `CONTRACT_V1_IMPLEMENTATION_REPORT.md`, `CONTRACT_V1_P005_P006_VERIFICATION.md`, `CONTRACT_V1_PAIR_ID_TEST_VECTORS.md`, `CONTRACT_V1_REPLAY_SESSION_PROPOSAL.md`, `CONTRACT_V1_SPECIFICATION_GAPS.md`, `CONTRACT_V1_TEAM_HANDOFF.md`
- `scripts/contract_identity_reference.py`, `scripts/verify_feature_contract.py`, `src/data/track_semantics.py`
- `tests/integration/test_mock_contracts.py`, `tests/unit/test_api_contract.py`, `tests/unit/test_approved_contract_v1.py`, `tests/unit/test_contract_v1_final_lock.py`, `tests/unit/test_contract_v1_freeze.py`, `tests/unit/test_g11_semantic_validation.py`, `tests/unit/test_p005_p006.py`, `tests/unit/test_replay_session_proposal.py`

`src/data/track_semantics.py` is a dependency of Toàn's T08/T09 production boundary. Keep it in the Contract/G11 group and sequence dependent replay commits after the reviewed contract baseline is available. Do not silently duplicate or rewrite it in the Toàn group.

### Group 2 — Toàn: T08/T09 replay core

Review and commit separately after Group 1 dependency is established:

- `src/data/ais_replay.py`, `src/data/replay_cli.py`, `src/data/replay_time.py`, `src/data/track_buffer.py`, `src/data/replay_session_core.py`
- `tests/unit/test_ais_replay.py`, `tests/unit/test_track_buffer.py`, `tests/unit/test_replay_session_core.py`, `tests/integration/test_ais_replay_cli.py`, `tests/integration/test_t08_t09_replay_integration.py`, `tests/fixtures/`
- `evaluation/s2_t08/`, `evaluation/s2_t09/`

### Group 3 — Toàn: T12 Data API and map

The paths were a mix of unstaged modifications and untracked files. Review the final diff, then commit as a distinct feature group:

- Modified: `backend/app/main.py`, `frontend/src/App.jsx`, `frontend/src/App.test.jsx`, `frontend/src/styles.css`, `frontend/vite.config.js`
- Untracked: `backend/app/replay_api.py`, `backend/app/fixtures/`, `backend/tests/test_replay_api.py`, `evaluation/s3_t12/`

Keep the synthetic fixture path separate from actual AIS source claims.

### Group 4 — Toàn: T13 benchmark/index audit

- `scripts/t13_data_benchmark.py`
- `evaluation/s3_t13/`
- `evaluation/s3_t12_t13/`

Keep DATASET_FINAL artifacts themselves out of Git. Commit reproducible scripts and appropriately sized reports only after confirming they do not embed dataset rows, model artifacts, or machine-specific paths.

### Group 5 — Toàn: Real AIS validation evidence

- Existing and new Markdown reports under `evaluation/data/source_validation/`, including this checklist, evidence matrix, and gap closure plan.
- Keep raw and cleaned AIS files outside the commit. Do not add checksum inventories if they reveal local-only absolute paths; use repository-relative source IDs and digests instead.

## Review before any future commit

- [ ] Confirm `git status --short`, `git diff --cached --name-status`, and `git diff --name-status` with both owners; preserve existing staged changes.
- [ ] Confirm the staged Contract V1/G11 changes are approved and keep their commit isolated from Toàn feature commits.
- [ ] Confirm T08/T09 references the approved `src/data/track_semantics.py` and no contract file is changed in its commit.
- [ ] Review every untracked directory recursively before staging; exclude `DATASET_FINAL/`, raw/cleaned AIS, checkpoints/scalers/model artifacts, `.env`, secrets, caches and machine-specific output.
- [ ] Inspect staged content for absolute `D:\...` paths and private data; update reports to repository-relative paths where needed.
- [ ] Run each group's relevant tests and `git diff --cached --check` after staging is authorized by the owner.
- [ ] Do not amend/rewrite the existing `wip: save local changes` HEAD commit. Do not switch branch, reset, commit, push, or merge as part of this handoff.

## Files changed by this audit

Only these deliverables were created in the working tree:

- `evaluation/data/source_validation/REAL_AIS_GAP_CLOSURE_PLAN.md`
- `evaluation/data/source_validation/REAL_AIS_EVIDENCE_MATRIX.md`
- `evaluation/data/source_validation/T08_T13_GIT_HANDOFF_CHECKLIST.md`

No Git staging or commit operation was performed.
