# S5-01 — Trusted fixture, pair and encounter

Date: 2026-11-26. Baseline: `8f252c522914aa30ba05bd28368ec60cab71c5a6`, branch `s5-integration-final`.

## Result and scope

- S5_01_FIXTURE_IMPLEMENTATION=PASS, within the deterministic synthetic fixture and targeted tests described here.
- S5_01_INTEGRATION_ACCEPTANCE=PENDING_TEAM_INTERFACE_REVIEW. Trung approved D01–D15; Toàn's interface approval has not been received. This does not establish joint integration approval or deployment readiness.
- REAL_AIS_PROVIDER_TRUST=NOT_VERIFIED. No real AIS or locked research data is used for fixture inputs; no claim of real-source provenance verification.
- S5_02_IMPLEMENTATION_READY=CONDITIONAL: fixture-level output exists, but shared interface review, production provider, dependency closure and runtime lifecycle remain open. No model, risk or alert execution is implemented.

## Design and trust boundary

`FixtureProvider` owns an in-process ReplayAPI with a fixed, generated synthetic source and a lock protecting its session/control/snapshot/feature operations. The caller cannot supply a source, replay instance, track payload or trust boolean. It freezes the validated snapshot recursively and binds it to session ID/version, snapshot ID, UTC anchor, source ID and a SHA-256 of the canonical generated fixture. A new snapshot, session, seek, reset or clock advance invalidates earlier issued objects. Current session/version/anchor are checked at acquisition and again before each result leaves the boundary. This is an internal Python capability boundary for an academic fixture, not process isolation or protection against malicious code with access to private attributes.

Replay and TrackBuffer provide as-of history; the existing G11 structural/semantic and temporal validator is applied before freeze. The fixture supplies selected source timestamps but deliberately omits original source timestamps, which therefore remain null. Nominal grid timestamps remain distinct. TrackBuffer rejects nonfinite observations; the adapter checks finiteness again. Only synthetic identity is allowed. Mixed sources, forged snapshots/candidates, and stale session bindings cannot enter via the public fixture provider. Other source policies are not implemented. The underlying replay reads its registered event stream, but snapshot histories and features are causal and do not include observations after the anchor.

The fixture identity is `s5-01-synthetic-denmark-v1`, canonical generated JSON SHA-256 `63280728ebd47f69fd23118d82bb7b1ac8f82cb426d8b52391f3bca423e5d06b`. This digest identifies the generated fixture, not a signature or an independently pinned artifact. The generator records synthetic source file and source-row provenance in each event; the envelope retains the source identity and fixture digest. The TrackSnapshot wire shape does not expose individual event provenance.

## Fixture and candidate coverage

Five named synthetic vessels in Danish waters have deterministic minute observations over 00:00–00:20 UTC. A/B approach; C/D diverge; E starts at 00:05 and has insufficient history at 00:09. Coordinates, 6-knot speed and courses follow the same local EN motion model. These geometries make no risk or alert claim. No labels or future positions are passed to the feature adapter.

At 00:09, five observed vessels give expected/evaluated 10 pairs, eligible 6 and unavailable 4, with an explicit history reason. At 00:15 all 10 pairs are eligible. ID-only tests cover 2, 3 and 5 vessel all-pairs counts, duplicate/invalid IDs and over-bound rejection. The provider does not silently prune by distance. At an earlier anchor, a vessel with no observation yet is not in the observed replay scope; coverage describes observed tracks, not a registry of vessels not yet seen.

Pairs use the existing V1 NFC/UTF-8 identity reference and bind session/version/snapshot/anchor. Encounter IDs use the separate V1 reference; eligible encounters consist only of the provider-issued canonical A/B tracks. Insufficient history returns an explicit unavailable reason. The existing TrackBuffer validator enforces the ten-point minute grid, selected time no later than nominal, and inclusive source age 0–60 seconds. Source identity remains synthetic and the two tracks come from the same snapshot.

## Feature semantics and checks

The adapter emits bytes-backed read-only float32 `[2,10,4]` data with feature order own-relative east/north nautical miles, east/north velocity knots. Common EN origin is canonical A at t−9; per-vessel position features subtract each vessel's own anchor. Float64 common EN anchors, origin coordinates, original SOG/COG and bound encounter metadata are retained. No scaler is applied. Tests compare position and velocity to `scripts.verify_feature_contract` helpers with position tolerance 1e-6 nm and velocity tolerance 1e-5 kn, and exercise causal history, session isolation, stale seek/reset/playback, immutable objects, invalid source/timestamp/age, nonfinite events and bounds. G11 validation alone is not a trust proof.

## Verification

Final targeted command used the existing Python environment and `-p scripts.q1_test_access_guard` on `tests/unit/test_s5_01_trusted_fixture.py` and `tests/unit/test_s5_00_runtime_config.py`: **33 passed in 11.58 s**, comprising 17 S5-01 and 16 S5-00 tests. Q1 counters: `hash_opens=0`, `blocked_deserialization=0`, `blocked_other_opens=0`. Intermediate runs exposed the Replay API's required idempotency keys and its session replacement on seek; adapter and tests were corrected and the final run passed. No S4 regression was required because Replay Engine and TrackBuffer were not changed. No full regression, benchmark, training, calibration or package reverification was run.

The tests do not establish real AIS trust, adversarial in-process isolation, distributed atomicity, runtime model integration, risk results, or Toàn's interface approval. Mixed-source rejection is enforced by the provider's synthetic-only acquisition and issuance boundary; no mixed-source provider is installed. Unavailable reasons currently group insufficient and invalid history; detailed operational diagnostics are future work. Candidate count tests for 2 and 3 operate on the identity helper; actual replay integration uses the five-vessel fixture.

## Files and preservation

Created for S5-01: `src/runtime/trusted_fixture.py`, `tests/unit/test_s5_01_trusted_fixture.py`, and this report. The fixture is generated in the source module; no S4 fixture was changed. The five pre-existing S5-00 untracked files remain present and unmodified. No frozen Contract V1, Model Lock, risk engine, model artifacts, thresholds or dataset files were changed by this task. No commit, push, merge or S5-02 implementation performed.
