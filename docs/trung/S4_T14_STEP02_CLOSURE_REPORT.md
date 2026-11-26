# S4 T14 STEP 02 closure — Implementation và evidence

## 1–3. Kết luận, baseline và Git

Closure **chưa đạt nghiệm thu**: `STEP02_FINAL_ACCEPTANCE=NO`, `READY_FOR_STEP_03=NO`. Đã sửa helper D2 dùng nhầm FPR tổng thể, bổ sung tests synthetic và tăng evidence lineage/adapter; còn provenance nguồn độc lập, P5/P6 evidence và full regression bị giới hạn bởi điều kiện không mở Test/không suy luận toàn Validation. Không tự chuyển STEP_03.

Worktree `trung-contract-v1-freeze`, branch `s3-t10-trung-full-training`, HEAD `4457fc2d4f485d2da832b039e8edc1cdf5837551`, tracking remote S3. Contract V1 ancestor `99bdb2649f5aec39d67a6f64645bce4f7fc49a3d`; không đổi `contracts/` hoặc `configs/risk_config.yaml`. Các file STEP_01/02/finalization đã có được giữ; không đổi branch, commit, push, merge hay reset. Full Validation inference, Test tensors/labels/predictions, calibration, actual group cross-fit và bootstrap 5.000 lần không được thực hiện ở closure.

## 4. C01 traceability

`S4_T14_REQUIREMENTS_TEST_TRACEABILITY.md` liệt kê 82 dòng P2/P3/P4-T01–T12/P5-M01–M10/P5-T01–T15/P6-T01–T18/P7-R01–R10/P7-T01–T12, kèm implementation, node/evidence, fixture, expected, observed, status, phase và action. Tại thời điểm lập: 51 PASS, 30 PARTIAL, 1 DEFERRED, 0 MISSING theo các dòng trong matrix. P7-T01–T12 được nêu tên nhưng không có mô tả từng case trong nguồn được cung cấp; policy test không tự được gán là đã chứng minh 12 case. Các limitation V1 thuộc Model Lock Review, không chặn riêng calibration CV/M5a. Full Validation exact parity và group assignment thực là STEP_03, không giả là đã chạy.

## 5. C02 support, comparison và bootstrap

P3 synthetic kiểm dưới/đúng/trên support, `NA`, `LOW_SUPPORT`, `VALID_SUPPORT`, và một metric cao nhưng thiếu support không qua D1. P4 test Fraction/grid, tie, near-tie, score equality, ordering, boundary ±1/100, ADE 1.10 và so close-positive theo ID. Đã phát hiện/sửa `comparison_gates` dùng overall FPR thay cho Real FPR: hiện bắt buộc truyền hai Real confusion counts, thiếu thì `D2_BLOCKED`; count-only pass có tên riêng `COUNT_GATES_PASS`, `evaluate_d2` mới kết hợp D1, ADE, support, close ID và severe trước `D2_PASS`.

P5 có utility paired indices với multiplicity, delta reject pairing sai/NA một model, 4.749/4.750, all-defined/qualified CI, 5.000 denominator feasible rate, execution error riêng và synthetic deterministic sample. Tests không tạo 5.000 bootstrap repetitions thật. Các test policy chứng minh hành vi đã nêu; chưa kết luận runner thống kê thực đã hoàn thành hoặc CI không thiên lệch. Xem matrix cho các ID PARTIAL.

## 6. C03 dependency lineage

Metadata-only audit: 835/835 encounter, 260 group, largest 556, mapping components từ MMSI khớp manifest SHA `f0702ca49f289ec2a2ec9169e1b5632dcaf330fc634b027a7b11cf89d60ce2ea`. 600/600 source-window parent rows khớp 300 synthetic final/original/parent mappings; 300/300 khớp synthetic metadata upstream có SHA `bd1622643fc36a73a21b3cc986814bbcd44a13a71b5c2232f699538505e75b06`; 600/600 MMSI/track khớp. 150 parent thuộc 295 Real đã chọn map được original→final; 150 thuộc unselected candidate, có source windows nhưng không phải final Real. MMSI 1.190/1.190 đúng cấu trúc và khớp namespace physical trong vessel index; 480 ID Yang là legacy `simulated_mmsi`, chưa hợp lệ production G11. Không chứng minh ownership thực.

`DEPENDENCY_LINEAGE_PARTIAL`: 0 parent row unmatched trong phép join; file upstream `validation_parent_windows_v2.csv` có SHA quan sát `4220ea18363b4f4016e7efaac56a9dd6134bcd194d203fc70f442cb858e59cac` nhưng chưa tìm thấy hash nguồn khóa độc lập của chính file; source identity gốc ngoài 295 chưa được xác minh độc lập. Cần manifest/attestation nguồn và xác minh namespace/ownership trong phạm vi yêu cầu; không sửa manifest hoặc thêm singleton. Chi tiết tại `S4_T14_DEPENDENCY_LINEAGE_REPORT.md`.

## 7–9. C04 dependency, boundary và parity

V4 original/package byte-identical SHA `8e33effb06d7f2e1fe855b1cb067fb2d27eb3aba9498e2af30be1b387534be7e`, Trung đã xác nhận quyền phân phối. Adapter verify hash trước import, chỉ gọi trusted offline loader/T11, dùng cùng reference cho CV/M5a, không gọi raw `history_features`, runtime fail-closed; kiểm identity/A-B, forecast shape/dtype/timestamp/finite/coverage, M5a/CV severe QC và nonfinite risk components trước trả score. Adapter comparison không fallback M5a thành CV giả; T11 có fallback policy riêng.

Fixture exact parity trên CPA, role/rule, components/score và decisions; subprocess `-I` từ cwd tạm chạy scoring không dùng path V4 ngoài repo. Observed dependency manifest ghi 25 packages/active edges, pip check PASS; không coi là reproducible clean-environment install hay production lockfile. Raw reference vẫn chứa helper đọc Test; nó không phải public production boundary và Python cùng process không là sandbox. Risk adapter validity/fallback test mới là synthetic spies; real trusted boundary tests bị giới hạn như C05. P6 status PARTIAL cho dependency/provenance/access và failure coverage; chi tiết `S4_T14_RISK_ADAPTER_VERIFICATION_REPORT.md` và matrix.

## 10–12. V1, regression, contract

V1 `V1_BASELINE_REVIEW_REQUIRED`: core checkpoint/scaler hash khớp manifest nhưng projection/QC, split, A/B và prediction provenance chưa chứng minh; không retrain/infer V1 và không tự gọi reproducible. Limitation review trước lock, không chặn riêng CV/M5a calibration.

Targeted protocol/risk: 107 passed. Regression cuối có giới hạn: 441 passed, 0 failed, 0 skipped, 15 deselected, 1 StarletteDeprecationWarning, 142.04 giây. Targeted nằm trong regression và không cộng trùng. Full suite không thể chạy nguyên vẹn cùng ràng buộc hiện tại: 15 test trong `tests/unit/test_s3_t11_trusted_boundary.py` dùng fixture `load_validation` kiểm checksum 93 file trong đó có Test; một test còn chạy `predict_validation(...,batch_size=835)`. Không sửa/làm yếu test; chỉ loại đúng 15 test đó khỏi lượt hiện tại và chạy test fake-verified không dùng fixture. Báo số deselected riêng, không gọi lượt này full regression PASS hoặc tính tests đó thành passed/skipped. Lịch sử 410 PASS ở lần trước là evidence khác thời điểm và phạm vi, không thay cho regression cuối.

## 13–17. Gates, blockers và bước tiếp

Mandatory first gates STEP_03 nếu closure được duyệt về sau: verify dataset/artifact/protocol, candidate và trusted input; full Validation original/package exact parity; CV/M5a scoring coverage/identity và severe QC; chỉ sau đó threshold D1. Không chạy các gate này ở STEP_02.

| Blocker | Nguyên nhân / requirement | Evidence hiện có | Còn thiếu / hành động | Đóng? |
| --- | --- | --- | --- | --- |
| Regression | C05; `tests/unit/test_s3_t11_trusted_boundary.py::data` và `::test_offline_verified_input_and_technical_fallback` | Suite giới hạn và synthetic boundary tests | Cần giải quyết chỉ thị full regression với lệnh cấm mở Test/inference toàn Validation, hoặc bổ sung test isolation được review mà không làm yếu suite | NO |
| Lineage | P5-M07/M08; `scripts/audit_s4_t14_lineage.py` | 600 joins + metadata hash, partition MMSI match | Hash độc lập upstream windows, provenance source/namespace ngoài final và MMSI ownership theo phạm vi Contract | NO |
| Paired statistics | P5-T01–T15; `src/protocol/calibration_primitives.py` | Synthetic counts/CI/pairing tests | Một số sampler/feasibility/paired-support integration còn PARTIAL theo matrix | NO |
| Risk adapter | P6-T03/T11/T12/T16/T17; `src/risk/adapter.py` | Exact fixture + subprocess + synthetic rejection | Trusted boundary real/failure cases bị giới hạn, clean environment chưa verify, raw reference có Test helper; đánh giá access boundary | NO |
| V1 | P7; recovery report | Checkpoint/scalers/architecture tìm thấy | Mapping/QC/prediction provenance trước lock; không chặn riêng CV/M5a | OPEN, nonblocking riêng |

File mới: lineage audit script, closure primitives tests, adapter integration tests, dependency environment manifest và bốn báo cáo closure/lineage/risk/traceability. File S4 protocol primitives, S3 finalization test được sửa theo lỗi D2, risk adapter và risk reference report được cập nhật; source V4, Contract, risk config, T10 model/dataset không sửa. Chi tiết status Git lúc kết thúc do `git status` ghi nhận.

MODEL_STATUS=CANDIDATE; MODEL_LOCK=NO; calibrated thresholds=NULL; PRODUCTION_APPROVED=NO; TEST_BENCHMARK_PERFORMED=NO. Không tạo commit/push; đợi Trung review blocker và hướng dẫn tiếp theo.
