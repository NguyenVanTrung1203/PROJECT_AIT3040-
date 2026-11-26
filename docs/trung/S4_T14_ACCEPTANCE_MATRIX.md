# S4 T14 — Acceptance matrix

`BLOCKED` nghĩa thiếu evidence không thể đánh giá; `FAIL` nghĩa evidence có nhưng vi phạm. Cột chặn thể hiện chặn **bước/đầu ra tương ứng**, không tự suy ra production approval. Tất cả approval ở cột cuối do Trung thực hiện khi nêu; protocol D1–D7 đã phê duyệt, kết quả chưa phê duyệt.

| Decision | Gate ID | Điều kiện / comparator / threshold | Evidence bắt buộc | Thiếu | Không đạt | Chặn | Duyệt người |
| --- | --- | --- | --- | --- | --- | --- | --- |
| D1–D7 | PROTOCOL_VALID | Config đúng quyết định, parse/validator/tests pass | Config và test | BLOCKED | FAIL | STEP_03 | Review conflict/parameters |
| P1 | CONTRACT_COMPAT | Tie-break thấp phù hợp contract; P1 supersedes D1 cũ | Diff, quyết định P1 và regression | BLOCKED | FAIL | STEP_03 | Đã duyệt P1 |
| D1 | D1_GRID | `i/200`, i=0…200, 201 điểm | Grid và unit test | BLOCKED | FAIL | Calibration | Không thêm |
| D1 | D1_RECALL | Overall recall ≥0.90 và P3 support | TP/FN | BLOCKED | FAIL | D1 | Không thêm |
| D1 | D1_FPR | Real FPR ≤0.12 và P3 support | Real FP/TN | BLOCKED | FAIL | D1 | Không thêm |
| D1 | D1_SYN | Synthetic recall ≥0.90 | Synthetic TP/FN | BLOCKED | FAIL | D1 | Không thêm |
| D1 | D1_CLOSE | Close-positive recall ≥0.95 | Subgroup future haversine <0.1 nm, TP/FN | BLOCKED | FAIL | D1 | Không thêm |
| D1 | D1_QC | Severe vessel count =0 | QC theo T06 cho model | BLOCKED | FAIL | D1 | Không thêm |
| D1 | D1_SELECT | Max F1; tie FPR thấp, recall cao, threshold thấp | Candidate grid, metrics, tie rule | BLOCKED | FAIL | D1 | Fraction exact theo P4 |
| D1 | D1_NONE | Không nghiệm → `NO_FEASIBLE_THRESHOLD` | Gate violations, points, Pareto, số nghiệm | BLOCKED | FAIL | Lock | Trung review |
| D2 | D2_ABSOLUTE | M5a pass mọi D1 | Kết quả D1 | D2_BLOCKED | D2_FAIL | D2/lock | Trung review |
| D2 | D2_DELTA | M5a−CV recall ≥−0.01, Real FPR ≤+0.01, F1 ≥−0.01 absolute | Metrics cùng encounter | D2_BLOCKED | D2_FAIL | Lock | Trung review |
| D2 | D2_ADE | Overall, Real ADE M5a ≤1.10×CV | Forecast truth/mapping | D2_BLOCKED | D2_FAIL | Lock | Trung review |
| D2 | D2_CLOSE | 0 encounter `FN_M5a \ FN_CV` | FN ID hai model, ID M5a-only detection | D2_BLOCKED | D2_FAIL | Lock | Trung review |
| D2 | D2_CV | CV có D1 operating point | D1 CV | D2_CONDITIONAL nếu CV infeasible | D2_CONDITIONAL | Lock chưa đủ D2_PASS | Trung review |
| D2 | D2_V1 | Baseline V1 tái lập hoặc ghi unavailable | Code/artifact/provenance | V1_BASELINE_UNAVAILABLE | historical only nếu không tương thích | Không chặn calibration CV/M5a; review lock | Trung review |
| D3 | D3_CROSSFIT | Giữ nguyên group, cùng fold, held-out | Fold assignment/support và metrics | BLOCKED | GROUPED_CV_INFEASIBLE nếu không khả thi | Ghi giới hạn trước lock | P2 đã duyệt; review limitations |
| D4 | D4_L1 | Paired group 5.000, seed 20261124, 95% percentile, threshold fixed | CI metrics, NA counts, denominators | D4_BLOCKED | D4_PARTIAL | Phân tích/lock review | Trung chấp nhận limits |
| D4 | D4_L2 | Reselect threshold theo từng bootstrap; báo no-solution/stability | Distribution, feasibility, D2 stability | D4_PARTIAL | D4_PARTIAL | Phân tích/lock review | Trung chấp nhận limits |
| D4 | D4_L3 | S1 835, S2 279, S3 556; threshold fixed | Source/label/subgroup, metrics | D4_PARTIAL | D4_EVIDENCE_LIMITED | Phân tích/lock review | Trung chấp nhận limits |
| D5 | D5_TRAJ | Max coordinate≤5e−5 nm, ADE/FDE diff≤1e−6 nm, số vessel vượt=0 | CPU/GPU cùng input/output | BLOCKED | FAIL | Lock | Tolerance offline đã duyệt |
| D5 | D5_RISK | Max risk diff≤5e−5, 100% decision parity tại threshold T14 | Score/decisions, near-threshold cases | BLOCKED | RISK_DECISION_PARITY_REVIEW_REQUIRED | Lock | Trung review mismatch |
| D5 | D5_SEMANTIC | Shape/A-B/timestamp/error/QC khớp, severe CPU/GPU=0 | Per-device semantic/QC | BLOCKED | FAIL | Lock | Không thêm |
| D6 | PACKAGE | Integrity/regression/Contract, D1/D2/D5 PASS, D3/D4 limits và D7 | Versioned package + SHA manifest | BLOCKED | LOCK_REJECTED hoặc review | Technical lock | Trung duyệt package cuối |
| D6 | TRANSITION | Không tự chuyển sang conditional lock | State history + approval | BLOCKED | FAIL | Lock | Trung bắt buộc |
| D7 | T15_ACCESS | T14 hoàn tất, Trung duyệt lock, version/hash đúng, T15 protocol fixed | Approval + manifests | BENCHMARK_BLOCKED | BENCHMARK_BLOCKED | Mở Test | Trung bắt buộc |
| D7 | T15_RESULT | Fixed thresholds, D1/D2, metrics bắt buộc; Test reused | T15 report đã cố định, NA rõ | BENCHMARK_BLOCKED/CONDITIONAL | BENCHMARK_FAIL | Claim benchmark pass | Review kết quả |
| D7 | INDEPENDENT | Dataset mới độc lập, real positive/negative, nhãn tin cậy, package locked trước mở | Provenance/split/labels | NOT_PERFORMED | FAIL | Production | Trung/team |
| V1 | PRODUCTION | T18/T19 runtime, contract, nguồn tin cậy và independent evaluation | E2E + approval | NOT_APPROVED | FAIL | Production | Approval riêng |

Protocol validation PASS chỉ chứng minh cấu hình/spec được kiểm, không chứng minh calibration runner PASS, candidate D1/D2 PASS, D5 risk parity, package lock, T15 benchmark hoặc production approval.

## Bổ sung P1–P7

| ID | Gate | Evidence | Thiếu / sai | Chặn | Approval |
| --- | --- | --- | --- | --- | --- |
| P1 | Tie thấp theo hợp đồng | Exact fixture + regression | BLOCKED / FAIL | STEP_03 | Đã duyệt thiết kế |
| P2/P3 | K adaptive, P3 support cả hai phía | Synthetic + manifest assignment khi STEP_03 | BLOCKED / INFEASIBLE hoặc search limitation | Cross-fit | Đã duyệt thiết kế |
| P4 | Fractions, i/200, ≥ comparator | Boundary fixtures | BLOCKED / FAIL | Calibration | Đã duyệt thiết kế |
| P5 | ≥4750/5000 qualified CI và metadata integrity | Per-metric counts, identity, parent/source/MMSI proof | BLOCKED / DEPENDENCY_METADATA_INVALID | D3/D4 | Đã duyệt thiết kế |
| P6 | Hash, rights, portability, exact fixture parity | Manifest + parity | RISK_REFERENCE_BLOCKED / REVIEW | STEP_03 | Quyền xác nhận; review implementation |
| P7 | Bounded V1 audit | Recovery report | REVIEW_REQUIRED / UNAVAILABLE | Không chặn riêng calibration | Limitation review trước lock |

## Addendum C02 closure

D2 FPR phải tính riêng trên tập âm Real AIS; `comparison_gates` yêu cầu hai Real confusion counts và chỉ báo `COUNT_GATES_PASS`, không suy ra D2_PASS. `evaluate_d2` còn yêu cầu D1, support, hai ADE ratio, close-positive theo ID và severe QC. Các trường hợp không đủ dữ liệu là D2_BLOCKED; CV không khả thi là D2_CONDITIONAL. Bằng chứng fixture và trạng thái từng P4/P5/P6 tại `S4_T14_REQUIREMENTS_TEST_TRACEABILITY.md`; dữ liệu thực/parity vẫn thuộc STEP_03.

## Q1–Q4 — approval scope và pha

| Quyết định | Evidence status | Acceptance scope | Hành động còn lại |
| --- | --- | --- | --- |
| Q1 | Full regression theo scope hash-only Test | Test bytes chỉ integrity; Validation inference chỉ regression T11 | Không deserialize Test; full Risk parity thuộc STEP_03 |
| Q2 | Internal mapping/partition PASS; independent provenance PARTIAL | Trung chấp nhận điều kiện cho D3/D4 offline | Ghi limitation; không production provenance |
| Q3 | Runner + synthetic integration | 5.000/seed giữ nguyên; fixture nhỏ không là thực nghiệm | Bootstrap/grouped CV thật thuộc STEP_03 |
| Q4 | Source + fixture parity + observed environment | Offline; clean environment không là gate STEP_03 | Rebuild sạch trước integration; full Validation parity STEP_03 |

## STEP_04 — final evidence và phạm vi được chấp nhận

| Requirement | Evidence status | Acceptance status | Human approval | Remaining limitation |
| --- | --- | --- | --- | --- |
| D1 CV | D1_PASS | Đạt | D1/R1 | In-sample Validation |
| D1 M5a | D1_PASS | Đạt | D1/R1 | In-sample Validation |
| D2 | D2_PASS | Đạt engineering gate | D2/R1 | Không phải statistical non-inferiority |
| D3 | GROUPED_CV_INFEASIBLE | Limitation được chấp nhận offline | R2 | OOF 0/835; largest group giữ 56/60 close |
| D4 | D4_EVIDENCE_LIMITED | Limitation được chấp nhận offline | R3 | Real FPR/close qualified CI không đủ support; L2 không ổn định tuyệt đối |
| D5 | D5_PASS | Đạt trên Validation | D5 | Không chứng minh parity mọi dữ liệu runtime |
| P6 | Full Validation original/package exact parity PASS | Đạt offline | P6 | Runtime chưa được nghiệm thu |
| P7/V1 | V1_BASELINE_REVIEW_REQUIRED | V1 loại khỏi primary T14/T15 | R4/P7 | Không so sánh superiority với V1 |
| Q2 | Internal consistency PASS; independent provenance PARTIAL | CONDITIONAL offline | Q2 | MMSI ownership NOT_VERIFIED |
| Q4 | Observed environment/import/pip check PASS | Được chấp nhận offline | Q4 | Clean rebuild bắt buộc trước integration |

D6 review chỉ đề xuất readiness chờ final approval; không tự khóa, không authorize T15. Xem `S4_T14_MODEL_LOCK_REVIEW_REPORT.md` và `S4_T14_APPROVED_LIMITATIONS.md`.

## Final lock completion — F1–F4

Full T10 artifact set và source snapshot đã verify, trusted Validation smoke/parity exact và full regression 531/531 PASS. Active release ID `offline-t14-15980ed4f7255ddbdb943979`, manifest SHA `257e77a3a5ae2b2175926145cc0d3c483ccacdaf80f3479d9c352d69f8f6dcdc`; scope offline, Test/production authorization false. D3 infeasible, D4 evidence limited, V1 review required và Q2/Q4 limitations vẫn giữ nguyên. Xem final completion report và package guide; clean-environment rebuild và runtime verification vẫn yêu cầu trước integration handoff.
