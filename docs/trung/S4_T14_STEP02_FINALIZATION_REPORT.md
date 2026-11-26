# S4 T14 STEP 02 finalization — P1–P7

## 1–3. Kết luận và baseline

P1 tie-break đã được sửa về threshold thấp theo quyết định thay thế của Trung; nguyên Contract V1 và risk_config. Đã tạo utilities P2–P5 và đóng gói V4 sau khi Trung xác nhận quyền phân phối. V1 core artifacts đã tìm thấy và hash khớp manifest. **READY_FOR_STEP_03=NO**: chưa đủ bằng chứng các kiểm thử P4/P5/P6 yêu cầu, dependency lineage thực và adapter Risk chưa được kiểm đầy đủ. Không thực hiện calibration, model lock hoặc Test benchmark.

Worktree `trung-contract-v1-freeze`, branch `s3-t10-trung-full-training`, HEAD và remote `4457fc2d4f485d2da832b039e8edc1cdf5837551`; Contract V1 ancestor `99bdb2649f5aec39d67a6f64645bce4f7fc49a3d`. Các file STEP_01/02 untracked được giữ và những file STEP_02 được cập nhật theo yêu cầu. Không commit/push/merge/rebase/reset. Kết quả trước đó 25 protocol tests và 374 regression PASS là lịch sử STEP_02, không bị ghi đè.

## 4–6. Traceability P1–P7 và conflict

| Decision | Thiết kế đã duyệt | Implementation/evidence hiện tại |
| --- | --- | --- |
| P1 | Threshold thấp cuối, supersedes D1 ban đầu | YAML, docs và synthetic exact tie tests cập nhật; contract cũ không đổi |
| P2 | K 5,4,3,2, seed 20261124; group nguyên vẹn | Utility deterministic 32-attempt greedy với P3 support và synthetic fixture; không chạy Validation |
| P3 | Mathematical vs evaluation support | Helper support + boundaries synthetic; chưa tích hợp calibration runner và toàn bộ tiêu chí P3 |
| P4 | Fraction/count, k/200, score≥ | Grid, count/tie/score/delta primitives; synthetic tests một phần P4-T01–T12 |
| P5 | 5000 paired group, min 4750, strict metadata | Synthetic multiplicity, CI coverage, manifest checks và component reconstruction; chưa chứng minh đầy đủ parent/source/MMSI provenance và P5-T01–T15 |
| P6 | Byte-identical V4 + thin offline adapter | Bản gói hash khớp; quyền do Trung xác nhận; fixture parity/portable import đã kiểm ở phạm vi hạn chế, còn gate P6 |
| P7 | Audit V1 bounded, optional baseline | Tìm thấy core artifacts và hash khớp; `V1_BASELINE_REVIEW_REQUIRED`, cần review mapping/QC trước gọi là tái lập |

P1 thay thế tie cuối threshold cao trong D1 ban đầu; D1 hiệu lực max F1 → thấp Real FPR → cao recall → thấp threshold. `contracts/model_design.md` và `configs/risk_config.yaml` cùng threshold thấp, nên **xung đột tie-break được giải quyết** theo P1; regression và diff checks PASS. Gates T14 mới vẫn là config riêng, không sửa config cũ; trạng thái conflict đóng chỉ sau regression và contract/risk-config diff PASS. Các gates D1/D2/D5/D6/D7 giữ số liệu đã duyệt; model vẫn CANDIDATE và cả hai thresholds null.

## 7–9. Support, exact semantics, group và bootstrap

`calibration_primitives.py` cung cấp Fraction/count, grid index, `score >= k/200`, hỗ trợ NA/LOW_SUPPORT, comparator D2 count và policy CI; các hàm không đọc dataset hoặc train. Precision predicted-positive≥20; recall positive≥30; Real FPR negative≥30; Synthetic positive≥30; close≥10; F1/AUC/AP mỗi lớp≥30; ADE/FDE source hoặc overall≥30 encounter; Yang≥30 mỗi fold. Severe QC kiểm toàn bộ mẫu. Helper support không thay thế sự tích hợp/kiểm thử toàn bộ runner; không claim mọi required test đã hoàn tất.

`group_assignment.py`: thử K 5,4,3,2, seed 20261124, mỗi K 32 attempt. Sort nhóm theo kích thước giảm, hòa bằng SHA-256 của seed/attempt/id rồi ID; greedy gán fold có tổng bình phương normalized load nhỏ nhất theo encounter/positive/negative/Real-negative/Synthetic-positive/close/Yang, hòa fold index nhỏ hơn; kiểm support P3 cho cả held-out và complement. Tổng support <K×minimum là bất khả thi cấu trúc; không tìm được nghiệm trong 32 attempt chỉ là giới hạn search. Utility chỉ được chạy trên fixture, chưa kiểm assignment thật. Không dùng predicted scores.

P5: pair multiplicity, 5.000 repetitions seed 20261124, ≥4.750 support-qualified mỗi metric, không resample bù; all-defined descriptive CI và support-qualified CI tách biệt, execution error không biến thành undefined. L2 feasible rate chia 5.000 không thêm gate 95%; S1/S2/S3 cố định threshold. `check_dependency_rows` kiểm version/hash, identity, duplicate/group; `validate_dependency_lineage` tái dựng component trên input synthetic đã được chứng minh đầy đủ. Kiểm metadata Validation thực tế: 835 encounter, 260 group, lớn nhất 556, không thiếu group hoặc duplicate; tái dựng mapping từ MMSI trong source windows PASS, manifest SHA `f0702ca49f289ec2a2ec9169e1b5632dcaf330fc634b027a7b11cf89d60ce2ea`. Có 600 dòng parent không null nhưng không trực tiếp khớp encounter ID của package, cần đối chiếu mapping gốc; chưa chứng minh đầy đủ parent/source/MMSI provenance P5-M07–M09; không tự tạo singleton hoặc bỏ encounter. Đó là blocker verification, không được báo D3/D4 PASS.

## 10–12. P6 packaging, fixture parity và portability

Trung xác nhận quyền phân phối V4 qua hội thoại. Original/package SHA `8e33effb06d7f2e1fe855b1cb067fb2d27eb3aba9498e2af30be1b387534be7e`; file byte-identical, algorithm modified NO. Manifest ghi import/dependency và versions quan sát. Synthetic fixture so sánh original/package cùng môi trường exact cho CPA, role, rule, components/score và một số decision/error; subprocess import không cần đường dẫn original. Không gọi raw V4 `history_features` (có nhánh Test). Adapter runtime fail-closed, offline adapter là code candidate chưa chạy full Validation. P6 required test/error/QC coverage và transitive environment lock chưa đầy đủ; không tự tuyên bố toàn bộ P6 PASS. Full Validation exact parity là first gate STEP_03, không chạy trước đó. Xem `S4_T14_RISK_REFERENCE_REPORT.md`.

## 13. P7 recovery

Có V1 checkpoint seed 20261112 epoch 27, hash `81daa4f4b86b111169a610747598af13c1fc12c57af73bceb342648138454129` và scaler hash khớp manifest lịch sử; source cho thấy V1 dự báo displacement trực tiếp, không thay bằng M5a residual. Chưa chứng minh R07–R09 projection/QC, risk compatibility và A/B mapping; predictions Validation có file/hash nhưng provenance/mapping chưa xác thực. Bounded audit phân loại `V1_BASELINE_REVIEW_REQUIRED`, không gọi tái lập thành công. Xem `S4_T14_V1_BASELINE_RECOVERY_REPORT.md`. Không nạp Test predictions hoặc benchmark.

## 14. Acceptance và state

Acceptance matrix cập nhật P1–P7. Không nhầm protocol checks với runner, calibration D1/D2, D5, T15 hay production. D6 technical lock đòi D1/D2 PASS, D3/D4 hoặc limitations được review, D5/P6, P7 review, integrity/regression/contract và Trung duyệt cuối. Không tự chuyển state.

## 15–16. Test và contract integrity

Protocol/risk synthetic tests: 61 passed trong full regression cuối, không cộng trùng. Full regression: 410 passed, 0 failed, 0 skipped trong 94.52 giây; 1 StarletteDeprecationWarning. Các test riêng nằm trong tổng, không cộng trùng. `contracts/` và `configs/risk_config.yaml` không được sửa. Test synthetic không gọi calibration trên Validation, full grouped cross-fitting, 5.000 bootstrap thực hay Test benchmark. Quyền user xác nhận chỉ cho phân phối source, không phải phê duyệt model package.

## 17. File

Cập nhật config STEP_02, validator, test protocol, decision register, calibration protocol, acceptance matrix, STEP_02 report (đánh dấu lịch sử). Tạo `src/protocol/calibration_primitives.py`, `src/protocol/group_assignment.py`, tests finalization; `src/risk/` reference/adapter, `configs/risk_reference_manifest.yaml`, tests risk; risk reference report, V1 recovery report và báo cáo này. Giữ nguyên STEP_01; không sửa code của Toàn, dataset, checkpoint hay scalers.

## 18–20. Giới hạn, blocker, readiness

Blockers: hoàn thiện P4-T01–T12, P5-T01–T15 và P6-T01–T18 theo coverage yêu cầu; kiểm đủ P3 integration; chứng minh dependency manifest lineage/MMSI/version/hash trên dữ liệu hợp lệ đúng thời điểm cho phép; kiểm đủ adapter invalid/NaN/QC và dependency closure. P7 mapping/compatibility cần review, nhưng V1 không tự chặn calibration CV/M5a. Bằng chứng full Validation packaging parity phải là gate đầu STEP_03, trước threshold selection. Đây là các thiếu sót implementation/evidence, không phải quyền nới gate.

`STEP02_FINAL_ACCEPTANCE=NO`; `READY_FOR_STEP_03=NO`. `CALIBRATION_PERFORMED=NO`, calibrated thresholds null, `MODEL_STATUS=CANDIDATE`, `MODEL_LOCK=NO`, `TEST_BENCHMARK_PERFORMED=NO`, `PRODUCTION_APPROVED=NO`. Dừng để Trung review, không tự chuyển STEP_03.
