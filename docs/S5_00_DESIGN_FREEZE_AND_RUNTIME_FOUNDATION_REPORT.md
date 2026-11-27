# S5-00 — Design freeze and runtime foundation

Date: 2026-11-26. Task: AIT3040_S5_00_DESIGN_FREEZE_AND_RUNTIME_FOUNDATION.

## Status and baseline

- S5_00_STATUS=COMPLETED_WITH_LIMITATIONS. S4 baseline origin/main verified as 8f252c522914aa30ba05bd28368ec60cab71c5a6; no new main commits.
- Branch s5-integration-final created at that SHA; isolated worktree C:\Users\MSI\Documents\Codex\2026-11-20\files-pasted-by-the-user-sprint-2\work\s5-integration-final. No checkout/reset of S4 or Trung worktrees. Worktree managed-creation tool did not complete; after checking branch/path absent, worktree was created by Git at the requested path.
- D01–D15 APPROVED_BY_TRUNG for academic prototype; D10 authorizes 0.420 M5a, 0.435 CV, comparator >= subject to the specified gates. TOAN_CONFIRMATION=NOT_RECEIVED; TEAM_INTERFACE_APPROVAL_PENDING. V4 ownership: Trung T18–T19, Toàn T20–T21, shared T22.
- Decision register and implementation plan updated in external planning directory s5_full_integration_readiness; original nine S5 documents remain untouched. Shared interface is frozen at design level by Trung for preparation; not a claim of Toàn approval or operational integration.
- Contract V1 and frozen risk_config.yaml unchanged. Model Lock and Risk V4 unchanged. T15 BENCHMARK_FAIL remains an accepted academic prototype limitation.

## Package verification and dependency binding

With Python -I -B and PYTHONDONTWRITEBYTECODE=1, independent external pin fields matched required manifest, lock and payload identity; existing immutable package verifier verify_active PASS with exact inventory and payload hashes. T11 verify_artifacts PASS, 12 T10 files, including:
- checkpoint e01a19e913d14a068c6c82a1c2a52a8be2aadd2f44e3ad5d8770d7f69a1fc7bc
- X scaler a538be921104ed1bb2fa495c0c3f527c0385fd6c737aa69afda81ba1962d452a
- residual scaler 96b062fab9a5d4e27c9b1cc32a649e44e98d29648c7dcc3b7f482eba3d50358f

Verified lock offline-t14-15980ed4f7255ddbdb943979, manifest 257e77a3a5ae2b2175926145cc0d3c483ccacdaf80f3479d9c352d69f8f6dcdc, payload 15980ed4f7255ddbdb943979df7dda320ac4ae448e24feb357fa51f3dd38dd79. Existing offline verifier validates runtime_integration_approved=false; S5-D10 is separate academic authorization and does not mutate that manifest or create production approval. Hash pin is not a signature.

Existing environment: Python 3.12.3, torch 2.11.0+cu128, CUDA runtime 12.8, CUDA available with one device. CPU/CUDA availability is not an integration parity or latency claim. Nine direct dependencies numpy, pandas, torch, joblib, scikit-learn, pyyaml, pyarrow, jsonschema, referencing imported and matched the versions in the observed T14 dependency evidence. G11, existing lock verifier, V4 reference and new config import; Risk V4 SHA-256 8e33effb06d7f2e1fe855b1cb067fb2d27eb3aba9498e2af30be1b387534be7e. Source binding is baseline 8f252c522914aa30ba05bd28368ec60cab71c5a6; observed dependency evidence SHA-256 0e6c5daa5edd9d4c4c3960962684c6ace528d4b90913ac8f60b10e6dc894781f, recorded in configs/s5_runtime_dependency_binding.json.

RUNTIME_PACKAGE_READY=NO. The observed dependency file is not a deployable, independently hashed wheel lock, and complete runtime lifecycle/integration closure has not been verified. The immutable snapshot lacks src/data/track_semantics.py, contracts/replay.schema.json and requirements.txt; use separately pinned baseline sources and dependencies rather than copying into or modifying the snapshot. No package output/bytecode was written.

## Runtime authority foundation

src/runtime/config.py provides immutable RuntimeConfig, explicit environment settings, positive demo vessel/concurrency bounds, explicit cpu/cuda device, and fail-closed threshold resolution. No risk scoring, alert decision, provider authentication, server endpoint, M5a runtime or lifecycle is implemented. Resolver reads an external pin, calls existing verify_active, checks lock/payload/model/comparator and operating point, disallows mixed active models and official alert scope. Failure returns ThresholdResult(available=False, threshold=None, reason=...) rather than an alert=false or risk=0. The trusted runtime must independently validate pair/input/source, establish active model and recheck session/version/authority before any result publication; configuration or caller-provided flags are not trusted input proof.

Required environment keys: AIT3040_MODEL_PACKAGE, AIT3040_MODEL_MANIFEST_PIN (separate external file), AIT3040_RUNTIME_DEVICE (cpu/cuda), AIT3040_RUNTIME_AUTHORITY (S5-D10-TRUNG-ACADEMIC-PROTOTYPE), AIT3040_DEMO_MAX_VESSELS (integer ≥2), AIT3040_MAX_CONCURRENCY (integer ≥1). Optional overrides are checked against fixed lock/threshold/scope; AIT3040_OFFICIAL_ALERTS must be false. Resource limits are explicit, not a silent pair filter. Device availability and bounds are lifecycle responsibilities, not verified by config alone. Available result returns the verified threshold and comparator >= only, not a Contract V1 wire response or decision.

## Shared interfaces — approved design, Toàn review pending

| Interface | Producer → consumer | Required fields and binding | Validation / error semantics; V1 mapping |
|---|---|---|---|
| Trusted snapshot provider | Replay/TrackBuffer → S5 boundary | internal immutable envelope session_id, session_version, snapshot_id, anchor_utc, source_identity, verified tracks | Atomic acquisition and recheck before publish; G11 structural+semantic, provider trust, source age and no future; unavailable on missing/stale; maps existing replay session and TrackSnapshot without adding wire fields |
| Candidate Pair | Pair provider → Encounter builder | stable canonical distinct vessel IDs, pair ID, session/version/anchor, coverage and unavailable reasons | all-pairs within explicit finite bounds; over-limit reported, no silent pruning; V1 canonical NFC/UTF-8 pair rules |
| Encounter input | Encounter builder → trusted inference | canonical A/B, common anchor/session, two complete 10-step histories, source and frame evidence | same source or unavailable, 0≤age≤60s, no future, no padding, distinct IDs; maps encounter_v1 and feature/coordinate contract |
| Runtime forecast | T18 → risk/map | pair/encounter/anchor/session/version internally, model identity, status, 15-step EN, optional lat/lon, fallback/QC | finite values, alignment, valid input/artifact and QC; geographic unavailable→null; maps forecast.schema.json without adding fields |
| Runtime risk | T19 → risk/alert consumer | pair/anchor/lock/model, components, status, threshold provenance and decision where authorized | V4 unchanged, near-zero TCPA null/status, mixed model/invalid input unavailable; no fabricated zero/false; maps risk_response_v1 |
| Alert lifecycle | alert manager → API/UI | session/pair, evaluation identity, state, timestamps | atomic/idempotent, max one unresolved per pair/session; DATA_UNAVAILABLE not RESOLVED, no cooldown/hysteresis; maps alert_v1 |
| UI availability | API client → map/panel | existing availability/status, active model, fallback, session/anchor | unavailable/null displayed explicitly, stale result invalidated, mock clearly labeled; maps existing V1 fields, extension requires separate approval |

Envelope/candidate/encounter/provider/forecast/risk/alert implementations remain future work. Any internal types or semantics must be reviewed jointly and any wire/schema extension requires separate approval.

## Tests and S5-01 gate

Targeted: tests/unit/test_s5_00_runtime_config.py: 16 passed in 0.22s (final run), Q1 guard hash_opens=0, blocked_deserialization=0, blocked_other_opens=0. Includes valid M5a/CV, missing authority/package/pin, mismatched lock/threshold/active model, mixed model, official scope, invalid bounds, failed verifier and tampered pin. Verifier is mocked in unit tests; independent real package verification above used the actual existing verifier. No full S4 regression, benchmark, training or calibration run.

S5-01 implementation input: approved D01–D06/D11/D12/D14, frozen V1/G11 vectors, source provider and verified synthetic multi-vessel fixture. Work on internal fixture-level provider/pair tests can be prepared after user instructs S5-01; integration acceptance remains blocked by Toàn interface review, atomic provider/trust, synthetic cases, runtime dependency closure and external package handoff. Real AIS source/provenance remains separate. Do not silently prune when candidate bounds exceeded.

## Files and commit scope

New: src/runtime/__init__.py, src/runtime/config.py, configs/s5_runtime_dependency_binding.json, tests/unit/test_s5_00_runtime_config.py, this report. Planning files updated outside Git worktree: S5_PENDING_DECISIONS.md and S5_UNIFIED_IMPLEMENTATION_PLAN.md. Proposed later commit: code/config/tests/report only after review, excluding external planning files unless intentionally imported, package/artifact/dataset, secrets, bytecode and nine untracked S5 documents in the other worktree. Nothing staged, committed or pushed.