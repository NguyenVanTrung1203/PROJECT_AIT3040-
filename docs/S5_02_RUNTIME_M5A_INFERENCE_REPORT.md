# S5-02 — Runtime M5a inference for the synthetic fixture

Date: 2026-11-26. Branch `s5-integration-final`, baseline `8f252c522914aa30ba05bd28368ec60cab71c5a6`.

## Result and scope

- MODEL_LIFECYCLE_READY=PASS within this process-local synthetic service.
- S5_02_FIXTURE_INFERENCE=PASS for the CPU fixture acceptance checks below. CUDA has a smoke measurement only, not approved numerical parity.
- S5_02_INTEGRATION_ACCEPTANCE=PENDING_TEAM_INTERFACE_REVIEW. Toàn has not approved the interface.
- RUNTIME_LOCAL_DEPENDENCY_CLOSURE=PASS in the observed environment; DEPLOYMENT_DEPENDENCY_CLOSURE=PARTIAL. REAL_AIS_RUNTIME_READY=NOT_VERIFIED.
- S5_03_IMPLEMENTATION_READY=CONDITIONAL on interface review and remaining runtime/deployment work. No Risk Engine, alert or UI is implemented here. D10 is academic prototype authorization; the immutable lock still states offline prototype and `runtime_integration_approved=false`, with no production approval.

## Architecture and lifecycle

The internal service binds a `RuntimeConfig` to an exact `FixtureProvider` instance. It accepts a provider-issued snapshot and candidate, obtains the encounter and features itself, and does not accept arbitrary tensors or provenance booleans. It verifies shape, dtype, finite values, frame and source, while the existing provider validates G11, temporal grid and binding. The provider rechecks session/snapshot after inference under its own lock before result construction; the lock is not held throughout model execution. SEEK and RESET during inference were deterministically tested as stale-result discard. The boundary is in-process Python, not isolation from malicious code able to replace private attributes or methods. Returned forecasts are internal types, not new frozen V1 wire fields.

At service initialization the external pin is checked against the fixed manifest, payload and lock identity, then `verify_active` verifies the immutable package and the T11 verifier checks the twelve T10 artifacts before `M5aInference` loads the actual checkpoint and two scalers. The model is loaded once per service, set to eval, uses explicit CPU/CUDA device and `torch.inference_mode()`, with a bounded semaphore and explicit `close()`. Package, pin and artifacts are checked again before inference and before publication. Artifact failures occur outside the fallback handler. No package bytecode or outputs are written. This preserves the existing external-pin limitation: hashes provide integrity, not signatures, and verification is not a sandbox against malicious in-process mutation or a filesystem transaction.

Model inputs use own-relative history, common EN anchors and the original coordinates supplied by the trusted adapter. The locked T11/model core applies X scaling, Residual-GRU, residual inverse scaling, CV displacement, anchor reconstruction and kinematic projection, then severe QC. The geographic inverse uses the common A t−9 origin and is returned only for finite, in-range latitude/longitude; unavailable geographic mapping remains null. Per-vessel output records M5a/CV, fallback reason and QC; a mixed-model pair is represented accurately. Risk eligibility is deliberately false for every pair because no risk decision is implemented.

Fallback is limited to M5a technical failure or severe QC after valid trusted input and successful integrity checks. CV itself must pass projection and severe QC; otherwise its output is unavailable. Invalid input, stale session and invalid artifacts never trigger CV. Mock-injected failure tests exercise fallback and unavailable paths; they do not stand in for real model inference.

## Fixture and numerical evidence

Real checkpoint/scalers produced finite M5a forecasts for all six eligible pairs at 00:09 and all ten pairs at 00:15. At 00:09 the remaining four pairs returned unavailable without inference. Early/reset anchor had no eligible pair. Outputs have `[2,15,2]` EN positions when both vessels are available, canonical order and minute offsets +1 through +15. Seek-back/reset and concurrent seek/reset reject stale completions. The fixture contains no research Test labels or future positions in model inputs.

The CPU reference uses the same locked model/scalers and existing offline core on identical fixture inputs; it is an implementation consistency check, not an independent model or benchmark. An instrumented separate test observed exact max absolute differences of **0** for scaled inputs, scaled residual outputs and CV displacements. Manual CV+inverse residual+projection matched the existing pipeline within `1e-12` in its test; service EN matched the batch reference within the existing `1e-6 nm` position tolerance. Geographic roundtrip was within `1e-10` degrees/coordinate-test tolerance, and QC passed. Tests do not establish parity over a dataset.

CUDA smoke on the same pair completed with finite outputs: maximum CPU/CUDA EN difference **0.000011272728443145752 nm**. One end-to-end call measured CPU **3.1043 s**, CUDA **2.9592 s**, including integrity checks and without a benchmarking protocol. These single measurements do not establish speed superiority. No runtime CUDA tolerance is approved; CUDA parity remains NOT_VERIFIED pending a separately approved tolerance and broader evaluation.

## Dependencies and source binding

Observed: Python 3.12.3, PyTorch 2.11.0+cu128, CUDA runtime 12.8, NumPy 2.4.4, pandas 3.0.3, FastAPI 0.165.0, Pydantic 2.14.4, jsonschema 4.26.0, referencing 0.37.0, PyYAML 6.0.3, scikit-learn 1.8.0, joblib 1.5.3. The existing S5-00 dependency binding remains unchanged; this is not a deployable wheel lock or clean-environment rebuild.

The service verifies the source/config files needed for model loading and inference against pinned package snapshot bytes, allowing only CRLF/LF normalization on the worktree side. The snapshot hashes include M5a `b48fac19c003bc68bb0bc6df533de67fb766a4a403de8ac266886618dd8924ac`, pipeline `d5cf7f9228a736b5a8e227210e0a5c18e9d8a4d6a4244d641b589fc97219a49c`, kinematics `b27720ae51582a82d301e9f314a54c0563ad5ddd320622c75d5768e9c4740900`, scalers `309c5c11d8a3262001099999c4323b562912d963c46f223d36f2e1e1764010d6`, and T11 wrapper `694efe1a3ff9c9161cb642c38a1e15a6b6aae5ed93c7b299f3769fc4aab282be`. Entire snapshot verification supplies the remaining package hashes.

Observed worktree SHA-256: runtime service `fec5a2e4f9c5a98486f892534e9f333781002df98b5b8bb66ea58b621dace9d5`, fixture provider `89d002e57cb46285b450ea8321c9d63b02269d6c9c6c9508baf9bd8dfce367fe`, config `31ccde8959c42c90a3ff5c5f42cadf543d5fe724bfff77248be33cacc22bd8a9`, G11 semantics `7568ab1a497b13a44f7f496d7fa81597b1552985ae28ad7bba51a421ac7f3fcf`, TrackBuffer `24b514ea56d5a5a5c74e20b0bd1dc68b56afdc557989aa896025c2dadc6845bc`, replay API `6b77f19fde7e935825193a8bbb903527a8b676c4b2a936aedb909d7749a20a8d`, replay schema `a7575b3af153e88bcc6e9e6c5957be7c0bee1bec823501b93dd81043355aeff9`. These are observed bindings, not an independently signed release.

## Tests and limitations

Q1-guarded combined run: **49 passed in 128.82 s**, comprising 16 S5-02 cases and the S5-01/S5-00 regressions (17+16). After adding the focused intermediate parity test, that test separately passed in 16.05 s; total S5-02 cases covered are 17. Q1 counters in both runs: `hash_opens=0`, `blocked_deserialization=0`, `blocked_other_opens=0`. An earlier run had three test setup failures caused by Windows temporary-path length; extended-length temp paths fixed them and the negative artifact tests then passed. Invalid pin, modified copied checkpoint, missing copied scaler, post-load invalid pin, invalid features, technical/severe-QC fallback, failed CV, mixed model metadata, capacity and stale races are covered. No existing S4 module changed, so no S4 regression was run.

Initialization rechecks the complete small local package, and rechecks on every prediction before and after inference; this is deliberately conservative and adds latency. Real AIS, process-distributed lifecycle/atomicity, resource sizing under load, complete deployment dependency closure and joint interface review remain open. Geographic mapping is a local approximation and does not certify an operational navigational domain. T15 benchmark, training and calibration were not rerun. Model Lock, Contract V1, Risk V4, artifacts, thresholds and datasets were not modified. No commit, push, merge or S5-03 work occurred.

Created files: `src/runtime/m5a_service.py`, `tests/unit/test_s5_02_runtime_m5a.py`, this report. Existing uncommitted S5-00/S5-01 files remain unchanged.
