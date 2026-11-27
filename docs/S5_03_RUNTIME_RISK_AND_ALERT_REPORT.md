# S5-03 — Runtime risk and alert fixture harness

Date: 2026-11-26. Branch `s5-integration-final`, baseline `8f252c522914aa30ba05bd28368ec60cab71c5a6`.

## Scope and architecture

S5_03_FIXTURE_RISK_IMPLEMENTATION=PASS within the process-local synthetic fixture. Actual locked CPU M5a output feeds the unchanged, hash-verified V4 reference. The internal `FixtureRiskHarness` accepts only the issued snapshot and candidate and calls the bound `M5aRuntime` itself: it never accepts client forecasts, tensors, score or trust flags. It rechecks session/version/snapshot/anchor, pair and encounter IDs, vessel ordering, 15-minute horizon, lock, QC and common-frame feature provenance. The provider lock protects final revalidation, deduplication and alert commit; inference does not hold that lock. The fixture's process-local Python boundary is not isolation from malicious code modifying private fields.

Risk V4 SHA-256: `8e33effb06d7f2e1fe855b1cb067fb2d27eb3aba9498e2af30be1b387534be7e`. V4 `infer_roles`, `rule_component`, `cpa`, `score`, `calculate` remain unchanged. Current CPA, predicted minimum over +1…+15 minutes, rule proxy, and final 0.68/0.12/0.20 score use the reference implementation. Validity and score finiteness/range are checked. Relative velocity squared ≤1e-9 retains internal V4 TCPA zero while wire raw/clipped TCPA are null with `UNDEFINED_LOW_RELATIVE_VELOCITY`. Predicted ties use the earliest minimum. The score is not a collision probability and the rule proxy is not a legal COLREGS conclusion.

The existing resolver checks authority, external pin and lock. Academic prototype thresholds are M5a 0.420 and CV 0.435, with comparator >=. No authority produces null decision; invalid or unavailable input does not become risk zero or false. Mixed-model results return unavailable and do not enter risk calculation. Official alerts are prohibited. No notification or navigation system is connected.

Alert state is process-local and serialized. There is at most one unresolved alert per session/pair. Duplicate request/evaluation is deduplicated, a reused request ID with different identity conflicts, a different snapshot for the same encounter conflicts, and older/same-anchor results do not reverse state. DATA_UNAVAILABLE retains last valid values and is not RESOLVED. Reset/seek replace session namespace; stale results cannot commit in the new session. This is not a distributed database transaction or durable multi-worker implementation. No cooldown, hysteresis or unapproved severity was added.

## API mapping and integration limits

RUNTIME_API_INTEGRATION=FIXTURE_LOCAL_HARNESS_ONLY. `FixtureRiskHarness.evaluate(snapshot, candidate, request_id)` returns a V1-shaped `risk_response_v1`; its embedded forecast is `forecast.schema.json`. `alerts(snapshot)` returns V1-shaped `alert_v1` entries. Tests resolve the frozen schema references and validate risk responses and alert objects. These are Python harness methods, not HTTP routes and not the existing authoritative backend replay lifecycle. No claim of integrated `/api/v1/risk/evaluate`, forecast or alert API PASS is made; coverage is supplied by the provider internally, not as a new wire schema. Existing backend routes and frontend were not modified. Joint interface review and Toàn's approval are pending. The fixture provider controls its own ReplayAPI and simulated clock; production replay integration must share an authoritative lifecycle before API integration can be accepted.

## Actual fixture results

All eligible rows used real M5a and Risk V4, threshold 0.420. `T`/`F` are decision true/false; `—` means unavailable/null. Distances are nm, times minutes. Scores are rounded to six decimals for display. Per-row values are paired with the full canonical pair IDs below; unavailable rows have forecast NOT_RUN and reason `INSUFFICIENT_OR_INVALID_HISTORY`. Predicted time is the earliest minimum in the 15 forecast steps.

| Pair | Full pair ID (`pair:v1:` prefix included) |
|---|---|
| AB | `pair:v1:79666b06429dcbeafa4f5741c24620490a9e08aeb0fa745a1c79cad38f6567bd` |
| AC | `pair:v1:b0bcfc59e131fb92c70a3bcbed6260147adcd30a82754e00900df4772ff7ef47` |
| AD | `pair:v1:54650387d9d16bb02114218e338f130232bfc1ac9ef5deaf7b804746712c3b4d` |
| AE | `pair:v1:4849198bc17289c3013d6dd79f062435d14220c23897370ef9787c8371313a0f` |
| BC | `pair:v1:b125f903c3c62731bb3c8c1f9d045e9480836341b54ff01f1c964d11cfead9c9` |
| BD | `pair:v1:e7b7d9ff8e44d59449fd74bca1d3cf6946f2303446b2d5a9d4f7180df90b9513` |
| BE | `pair:v1:7a2187e031f71ea910332e613847e76c8b28d19d48306adcb1c782692443e060` |
| CD | `pair:v1:03cd4418334d08037f1b10561c9350410bf070219fd8e2288c6bc76fe394c3f8` |
| CE | `pair:v1:c01eb8bf25df999effa5752dc38a3346cff3267896fd69e2b92732fe448fd5f8` |
| DE | `pair:v1:ccaae752c5ae85a5b4692adb83314daa98361abd8ada79a03cda11e6920882c2` |

| UTC anchor | Pair | Forecast / model | Current DCPA / TCPA | Predicted DCPA / time | Current / predicted / rule score | CC-DRI | Threshold | Decision |
|---|---|---|---|---|---|---|---|---|
| 00:09 | AB | AVAILABLE / M5a | 0 / 7.905781 | 0.058816 / 8 | 0.853551 / 0.854146 / 1 | 0.883246 | 0.420 | T |
| 00:09 | AC | AVAILABLE / M5a | 3.979323 / -15.547109 | 4.056096 / 1 | 0.000000 / 0.000000 / 1 | 0.200000 | 0.420 | F |
| 00:09 | AD | AVAILABLE / M5a | 3.979323 / -15.547109 | 4.053809 / 1 | 0.000000 / 0.000000 / 1 | 0.200000 | 0.420 | F |
| 00:09 | AE | NOT_RUN / — | — / — | — / — | — / — / — | — | — | — |
| 00:09 | BC | AVAILABLE / M5a | 3.979323 / -15.547109 | 4.038617 / 1 | 0.000000 / 0.000000 / 1 | 0.200000 | 0.420 | F |
| 00:09 | BD | AVAILABLE / M5a | 3.979323 / -15.547109 | 4.065807 / 1 | 0.000000 / 0.000000 / 1 | 0.200000 | 0.420 | F |
| 00:09 | BE | NOT_RUN / — | — / — | — / — | — / — / — | — | — | — |
| 00:09 | CD | AVAILABLE / M5a | 7.800000 / -39.000000 | 7.988405 / 1 | 0.000000 / 0.000000 / 0.5 | 0.100000 | 0.420 | F |
| 00:09 | CE | NOT_RUN / — | — / — | — / — | — / — / — | — | — | — |
| 00:09 | DE | NOT_RUN / — | — / — | — / — | — / — / — | — | — | — |
| 00:15 | AB | AVAILABLE / M5a | 0 / 1.905781 | 0.029867 / 2 | 0.951859 / 0.955280 / 1 | 0.963813 | 0.420 | T |
| 00:15 | AC | AVAILABLE / M5a | 4.504034 / -21.547109 | 4.595076 / 1 | 0.000000 / 0.000000 / 1 | 0.200000 | 0.420 | F |
| 00:15 | AD | AVAILABLE / M5a | 4.504034 / -21.547109 | 4.595471 / 1 | 0.000000 / 0.000000 / 1 | 0.200000 | 0.420 | F |
| 00:15 | AE | AVAILABLE / M5a | 2.208239 / -10.047109 | 2.296351 / 1 | 0.000059 / 0.000008 / 1 | 0.200012 | 0.420 | F |
| 00:15 | BC | AVAILABLE / M5a | 4.504034 / -21.547109 | 4.582518 / 1 | 0.000000 / 0.000000 / 1 | 0.200000 | 0.420 | F |
| 00:15 | BD | AVAILABLE / M5a | 4.504034 / -21.547109 | 4.607391 / 1 | 0.000000 / 0.000000 / 1 | 0.200000 | 0.420 | F |
| 00:15 | BE | AVAILABLE / M5a | 2.208239 / -10.047109 | 2.283126 / 1 | 0.000059 / 0.000008 / 1 | 0.200013 | 0.420 | F |
| 00:15 | CD | AVAILABLE / M5a | 9.000000 / -45.000000 | 9.188402 / 1 | 0.000000 / 0.000000 / 0.5 | 0.100000 | 0.420 | F |
| 00:15 | CE | AVAILABLE / M5a | 2.300000 / null | 2.300000 / 14 | 0.000033 / 0.000006 / 0.5 | 0.100008 | 0.420 | F |
| 00:15 | DE | AVAILABLE / M5a | 6.700000 / -33.500000 | 6.888408 / 1 | 0.000000 / 0.000000 / 0.5 | 0.100000 | 0.420 | F |

CE at 00:15 uses near-zero relative velocity convention; TCPA is null, not zero. G4_CASE_COVERAGE=PASS_WITHIN_SYNTHETIC_FIXTURE: actual alert, no-alert and insufficient data cases all exist. This is not full E2E or operational acceptance and does not assert that geometry alone determines the decision.

## Tests, preservation and remaining work

Actual fixture tests check all 20 rows, V1 risk and alert schemas, session isolation and coverage. Deterministic tests exercise V4 parity, near-zero velocity, earliest predicted tie, threshold equality for both models, authority/lock/official-alert failures, idempotency, out-of-order results, unavailable state retention, concurrent retries, mixed-model/forecast unavailability and stale seek during evaluation. The combined Q1-guarded run before the final lifecycle-lock adjustment passed **43 tests in 216.27 s**, including 33 S5-00/01 regression nodes; two relevant final-source tests passed separately in 51.46 s, including the newly added alert-state schema test. Both runs reported `hash_opens=0`, `blocked_deserialization=0`, `blocked_other_opens=0`. No S5-02 source was changed, and its complete actual-model suite was not rerun. No S4 engine, backend lifecycle or TrackBuffer changed; no full regression, training, calibration, T15 or CUDA run.

Known limitations: no integrated HTTP routes, real AIS provider, distributed alert state or frontend; fixture service serializes evaluations and rechecks package integrity without optimization. Latency has no SLA. The internal V1 response cannot carry per-vessel mixed-model metadata; mixed-model risk is therefore unavailable rather than represented as an authorized decision. If an existing same-encounter cached result conflicts with a changed authority/model/score, the harness fails closed with an evaluation conflict instead of rewriting history. Model Lock, Contract V1, Risk V4, thresholds and artifacts are unchanged. No commit, push or merge. TEAM_INTERFACE_APPROVAL=PENDING; S5_03_INTEGRATION_ACCEPTANCE=PENDING; S5_04_IMPLEMENTATION_READY=CONDITIONAL on shared backend/API and interface work.
