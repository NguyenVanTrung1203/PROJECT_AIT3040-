# S4 T14 — Decision register D1–D7

Trung phê duyệt D1–D7 cho T14 offline và T15 development benchmark theo chỉ thị STEP_02. Đây là phê duyệt thiết kế protocol, **không** phải phê duyệt kết quả, threshold, model package hoặc production. Các tham số còn thiếu và xung đột với đặc tả cũ phải được review; xem báo cáo STEP_02.

| ID | Phương án phê duyệt | Tham số / acceptance chính | Giới hạn và điều không được thay đổi |
| --- | --- | --- | --- |
| D1 | Recall + FPR gate | Recall≥0.90, Real FPR≤0.12, Synthetic recall≥0.90, close-positive recall≥0.95, severe=0; grid 0:0.005:1 gồm 201 điểm; max F1, tie Real FPR thấp, recall cao, threshold **thấp** (P1 supersedes D1 ban đầu) | Không có nghiệm → `NO_FEASIBLE_THRESHOLD`; không nới gate. Future chỉ cho subgroup/evaluation, không cho score/inference |
| D2 | M5a pass D1 và suy giảm có giới hạn so CV | Δrecall≥−0.01, ΔReal FPR≤+0.01, ΔF1≥−0.01 theo M5a−CV; overall và Real ADE≤1.10×CV; 0 close-positive FN mới theo encounter; severe=0 | Cùng dữ liệu/risk/projection/QC; CV infeasible → `D2_CONDITIONAL`; V1 unavailable không tự chặn calibration. Không gọi là formal non-inferiority |
| D3 | Toàn Validation + group cross-fitting exploratory | Main `IN_SAMPLE`; cùng dependency groups và fold cho CV/M5a, threshold chỉ fit bên calibration, đánh giá held-out | Không chia group, train model/scaler hay dùng Test; P2 K=[5,4,3,2], search deterministic bounded; infeasible → `GROUPED_CV_INFEASIBLE`; không phải independent |
| D4 | Paired clustered bootstrap + stability + sensitivity | Resample group có multiplicity, 5.000 lần, seed 20261124, 95% percentile, Δ M5a−CV; L1 fixed threshold, L2 reselect từng mẫu, L3 all/ngoài group lớn/chỉ group lớn | Undefined=NA, báo số/tỷ lệ; không tự chọn min valid, không bỏ mẫu để làm đẹp CI; CI chứa 0 không chứng minh tương đương |
| D5 | Trajectory + risk/decision parity | Max absolute coordinate≤5e−5 nm; ADE/FDE diff≤1e−6 nm; 0 vessel vượt; risk diff≤5e−5; 100% decision parity tại threshold T14; semantic/QC khớp, severe=0 | Trajectory tolerance được phê duyệt cho offline; risk parity phải kiểm ở STEP_03, mismatch review; không làm tròn/epsilon/đổi threshold để ép pass |
| D6 | Conditional technical lock cho prototype offline | Đóng gói checkpoint/scaler/config/schema/projection/risk/threshold hợp lệ/QC/fallback/tolerance/provenance/version/hash; D1/D2/D5 pass và prerequisites trong protocol | Không auto lock; Trung duyệt package cuối; D2 conditional hoặc giới hạn D3/D4/V1 phải review; không production |
| D7 | Benchmark hai tầng | Tier 1 Test 1.320 = `REUSED_DEVELOPMENT_BENCHMARK`, chỉ sau T14, Trung duyệt lock, kiểm manifest/version và cố định T15; Tier 2 dataset độc lập mới trước production | Không reselect threshold/retrain/model selection trên Test; không được mở Test trong STEP_02, threshold chưa có; metric thiếu không tự pass |

Các state: `CANDIDATE`, `CALIBRATED_CANDIDATE`, `CONDITIONAL_TECHNICAL_LOCK`, `LOCK_REJECTED`. State hiện tại `CANDIDATE`, lock=false, production=false. P1–P7 thay thế các tham số đã chốt; bằng chứng implementation, metadata integrity và compatibility V1 vẫn cần được kiểm tra trước thực nghiệm.

## P1–P7 bổ sung (Trung phê duyệt)

| ID | Phương án hiệu lực | Implementation / evidence | Giới hạn |
| --- | --- | --- | --- |
| P1 | A: tie-break threshold thấp, supersedes D1 ban đầu | YAML + exact comparator/tests; Contract và risk_config giữ nguyên | Chỉ đóng conflict khi regression pass |
| P2 | B: K=[5,4,3,2], seed 20261124, deterministic bounded search | Group utility synthetic; feasibility P3 | Heuristic failure không chứng minh bất khả thi |
| P3 | B: minimum support + mathematical support | Count support primitives và tests | Có support utility; chưa tích hợp runner hoặc xác minh toàn bộ P3-T15 |
| P4 | B: exact rational count comparisons và k/200 | Fraction/grid/decision utilities synthetic | Không chạy trên Validation |
| P5 | B: paired 5000, min qualified 4750, strict metadata | CI coverage/group identity primitives | Synthetic lineage utility có; chưa chứng minh completeness/provenance thực tế P5-M07–M09 |
| P6 | B: V4 byte-identical + offline adapter | Trung xác nhận quyền phân phối; SHA ghim | Fixture parity và validation parity phân biệt |
| P7 | B: bounded recovery audit | Source/checkpoint/scaler V1 được tìm thấy | Chưa chứng minh tái lập đầy đủ |

## Q1–Q4 — Quyết định bổ sung đã duyệt

| ID | Effective approval | Evidence và giới hạn |
| --- | --- | --- |
| Q1 | Full regression nguyên vẹn; Test chỉ hash raw bytes; inference Validation chỉ trong regression T11 | Không deserialize Test, không Test labels/predictions/inference; không calibration hoặc full Risk parity |
| Q2 | Chấp nhận grouping có điều kiện cho D3/D4 exploratory offline | Internal/partition PASS; lineage/provenance vẫn PARTIAL, MMSI ownership NOT_VERIFIED; không production |
| Q3 | Paired group sampler/runner L1/L2; fixture synthetic có thể dùng repetition nhỏ rõ ràng | 5.000 default, seed 20261124, multiplicity, support/NA và không bù; không chạy trên Validation trong bước này |
| Q4 | Offline Risk acceptance trên môi trường đã kiểm; clean rebuild không là gate STEP_03 | Pin observed environment, pip check, portable execution, fixture parity/trust/QC; clean environment bắt buộc trước integration handoff |

## P7-T01–T12 — tiêu chí đã được Trung bổ sung

T01 source availability; T02 checkpoint provenance; T03 scaler/preprocessing; T04 dataset compatibility; T05 encounter mapping; T06 availability classification; T07 không thay artifact V1 bằng M5a; T08 không retrain V1; T09 tách historical metrics khỏi current benchmark; T10 V1 thiếu không vô hiệu D1/D2; T11 lock cần human approval; T12 không dùng Test để recovery/selection. T04/T05 và compatibility còn review trước lock; P7 bounded audit đã hoàn tất, không tự cản CV/M5a calibration.

## R1–R5 — phê duyệt STEP_04 và giới hạn

Trung đã phê duyệt 23/23 quyết định D1–D7, P1–P7, Q1–Q4 và R1–R5. Các mục dưới đây là approval/review scope; semantic protocol snapshot dùng bởi các parent run không thay đổi. Các mô tả theo pha trong phần lịch sử phía trên được bảo toàn và không mô tả lại kết quả STEP_03 đã hoàn thành.

| ID | Quyết định được Trung phê duyệt | Giới hạn còn hiệu lực |
| --- | --- | --- |
| R1 | Giữ M5a epoch 1, CV đã verify, threshold M5a 0.420/CV 0.435, V4, projection/QC hiện có | Chỉ candidate offline; không phải phê duyệt lock cuối |
| R2 | Chấp nhận D3 infeasible cho prototype offline | `GROUPED_CV_INFEASIBLE`, OOF 0/835; không gọi D3 PASS |
| R3 | Chấp nhận D4 evidence limited và threshold stability cho prototype offline | `D4_EVIDENCE_LIMITED`; CI Real FPR/close không đủ 4750, không tuyên bố ưu thế thống kê |
| R4 | Chấp nhận loại V1 khỏi primary comparison T14/T15 vì provenance/compatibility chưa đủ | `V1_BASELINE_REVIEW_REQUIRED`; không khẳng định M5a vượt V1 |
| R5 | Cho phép chuẩn bị conditional technical lock review | Không phải final lock approval; không authorize T15 hay production |

Final model lock approval NOT_GRANTED; model lock false; test benchmark authorization false; production false. D1/D2/D5 vẫn là mandatory gates; các limitation Q2/Q4 và yêu cầu clean-environment verification trước integration vẫn còn.

## F1–F4 — final lock approval, T15 tách biệt

Trung đã phê duyệt 27/27 D1–D7, P1–P7, Q1–Q4, R1–R5 và F1–F4 trong yêu cầu `AIT3040_S4_T14_FINAL_CONDITIONAL_TECHNICAL_MODEL_LOCK`. Đây là provenance từ cuộc trao đổi, không phải chữ ký số.

| ID | Phê duyệt | Giới hạn |
| --- | --- | --- |
| F1 | Thực hiện conditional technical lock offline prototype/research/controlled integration preparation | Không production, không certification an toàn |
| F2 | Giữ đủ 12 T10 artifacts và manifest; giữ nguyên T11 verifier | Không rút gọn, bypass hay dummy artifacts |
| F3 | Giữ checkpoint/scalers, CV, projection/QC, V4, thresholds, Contract, dataset và protocol | Không retrain, recalibrate hoặc sửa frozen config |
| F4 | Hoàn tất T14 sau khi gates/lock đạt, rồi dừng | Không authorize T15, Test benchmark, T18/T19, production, commit/push |

FINAL_MODEL_LOCK_APPROVAL=GRANTED; TEST_BENCHMARK_AUTHORIZATION=NOT_GRANTED; PRODUCTION_APPROVAL=NOT_GRANTED. Phê duyệt cho phép thực hiện lock sau khi kiểm tra thành công, không tự chứng minh lock đã kích hoạt. Historical proposed inventory giữ nguyên; bản snapshot review references được giữ trong package staging trước khi cập nhật tài liệu này.

### Kết quả thực hiện F1–F4

Conditional technical lock đã activate sau package validation: `offline-t14-15980ed4f7255ddbdb943979`, manifest SHA-256 `257e77a3a5ae2b2175926145cc0d3c483ccacdaf80f3479d9c352d69f8f6dcdc`. Release lifecycle: `CANDIDATE → CALIBRATED_CANDIDATE → CONDITIONAL_TECHNICAL_LOCK`; frozen protocol snapshot vẫn là historical CANDIDATE, không đổi semantic hash. Scope OFFLINE_PROTOTYPE; Test benchmark authorization, runtime integration approval và production approval đều false. Lock metadata/integrity verification không phải chữ ký số; T15 executable authorization gate chưa triển khai, phải làm và verify trước khi đọc Test.
