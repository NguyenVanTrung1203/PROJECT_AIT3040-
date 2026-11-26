# S4 T14 STEP 02 — Báo cáo protocol finalization

**Lịch sử:** báo cáo phản ánh STEP_02 trước P1–P7; P1 đã supersede tie-break cao. Trạng thái hiện hành xem `S4_T14_STEP02_FINALIZATION_REPORT.md`.

## 1. Executive summary

Đã đặc tả D1–D7 do Trung phê duyệt cho T14 offline/T15 development benchmark, tạo YAML, validator chỉ kiểm protocol, acceptance matrix và unit tests synthetic. Không chạy calibration, threshold selection trên Validation, cross-fitting/bootstrap thực hay Test benchmark. `PROTOCOL_SPEC_COMPLETE=YES` đối với việc ghi lại quyết định và kiểm thử config; `READY_FOR_STEP_03=NO` vì conflict/precedence và các tham số ảnh hưởng kết quả chưa được phê duyệt. Đây không phải model lock hoặc production approval.

## 2. Git baseline

Worktree `trung-contract-v1-freeze`, branch `s3-t10-trung-full-training`, HEAD `4457fc2d4f485d2da832b039e8edc1cdf5837551` đồng bộ remote tại thời điểm kiểm tra. Contract V1 `99bdb2649f5aec39d67a6f64645bce4f7fc49a3d` trong ancestry; `contracts/` không đổi. Báo cáo STEP_01 đã untracked trước khi bắt đầu và được giữ nguyên. Không tạo branch, commit, push, merge hoặc rebase.

## 3. Nguồn và risk reference

Nguồn: STEP_01, S3 T10/diagnostic/T11/final audit/handoff, `contracts/model_design.md`, `contracts/integration_contract.md`, configs model/projection/risk, model/training/inference/trusted validator và scripts diagnostic. Kế hoạch nhóm Sprint 4 gốc vẫn `PLAN_NOT_AVAILABLE`, không tự suy diễn. V4 risk reference bên ngoài repo SHA `8e33effb06d7f2e1fe855b1cb067fb2d27eb3aba9498e2af30be1b387534be7e` được xác minh; score 0.68 predicted + 0.12 current + 0.20 rule, không là xác suất. Reference là nghiên cứu, chưa production runtime; packaging/hash pinning cần review.

## 4. D1–D7 traceability

| Decision | Nội dung thể hiện trong protocol/config | Trạng thái |
| --- | --- | --- |
| D1 | Recall/FPR/Synthetic/close/severe gates; grid exact, max F1, tie threshold cao | APPROVED_BY_TRUNG; conflict review với thiết kế cũ |
| D2 | CV matched comparison, ±0.01 absolute, ADE 1.10 ratio, zero added close FN theo ID, CV infeasible conditional, V1 unavailable | APPROVED_BY_TRUNG |
| D3 | Main in-sample và group cross-fit exploratory, group không chia, không train/Test | APPROVED_BY_TRUNG; fold chưa duyệt |
| D4 | Paired group 5.000 seed 20261124; L1 fixed, L2 reselect, L3 835/279/556 | APPROVED_BY_TRUNG; min valid/NA policy chi tiết review |
| D5 | Coordinate≤5e−5, ADE/FDE≤1e−6, risk≤5e−5, decision parity 100%, semantic/QC | APPROVED_BY_TRUNG offline; risk tại T14 chưa kiểm |
| D6 | Conditional technical package lock với prerequisites và Trung approval | APPROVED_BY_TRUNG về cơ chế; package chưa duyệt |
| D7 | T15 reused benchmark locked thresholds, Tier 2 độc lập trước production | APPROVED_BY_TRUNG về protocol; Test chưa authorized |

## 5. Protocol config và metric

`configs/s4_calibration_protocol.yaml` tách khỏi config cũ; parse/semantic validation PASS, semantic SHA-256 `2a8659ab4dbf0f1a7ec9de248ea52a1574767d96dade830ece0ed021463891d4`. Validator reject duplicate YAML key và bất kỳ thay đổi semantic so với bản đã ghim; thay protocol cần review/version/pin mới, không ngầm cho phép. `threshold_grid` dùng Decimal i/200 đủ 201 điểm, không tối ưu trên scores. Unit test group assignment synthetic kiểm chia group; không tạo fold thực. Validator/config không phải enforcement runtime/Test và không phải calibration runner.

Positive khi score≥threshold; recall/precision/F1 và source-denominator đặc tả tại protocol. Undefined=NA, không auto PASS. D2 ±0.01 là absolute percentage points; ADE 1.10 là ratio tương đối. Close-positive = Synthetic AIS positive có minimum haversine future +1…+15 <0.1 nm, theo config và script S3. S3 dùng subgroup hậu kiểm sau threshold cố định; D1 mới dùng subgroup làm gate selection, future chỉ dùng subgroup/evaluation không vào inference/risk score. Định nghĩa subgroup đủ rõ theo nguồn; support tối thiểu và tie numeric còn cần review.

## 6. State machine và acceptance

`CANDIDATE` hiện tại; có thể `CALIBRATED_CANDIDATE` sau calibration nhưng không auto lock. `CONDITIONAL_TECHNICAL_LOCK` cần D1/D2/D5 PASS, D3 hoàn tất hoặc ghi giới hạn, D4 analysis và giới hạn được chấp nhận, D7, integrity/regression/contract và Trung duyệt package cuối. `LOCK_REJECTED` theo review. T15 chỉ mở sau lock được duyệt, manifest/version xác minh, T15 protocol fixed; production approval luôn NO ở T14/T15. Acceptance matrix tách protocol, implementation, candidate, comparison, evidence, parity, package, benchmark, production.

## 7. Kiểm thử

Protocol-specific: **25 passed**, fixture tổng hợp. Full regression một lượt `tests/unit tests/integration backend/tests`: **374 passed, 0 failed, 0 skipped**, 100.83 giây, 1 cảnh báo `StarletteDeprecationWarning`; số protocol tests nằm trong 374, không cộng trùng. Python 3.12.3, PyTorch 2.11.0+cu128; syntax/import và YAML parse/validation PASS. Reference Risk V4 được cấu hình qua biến môi trường, các test reference không skip. Không chạy threshold selection với Validation thật; các test S3 liên quan được chạy regression, không thay model/threshold.

## 8. Contract compatibility

**CONTRACT_CONFLICT_REVIEW_REQUIRED**: `contracts/model_design.md:44` và `configs/risk_config.yaml:64` ghi tie-break cuối threshold thấp hơn; D1 mới của Trung yêu cầu threshold cao hơn. Các gates Real FPR và close-positive cũng khác config lịch sử; `contracts/integration_contract.md` quy định `score >= threshold` và threshold calibrated theo active model, không quy định tie-break. `contracts/model_design.md` còn yêu cầu baseline V1 tương đương hoặc quyết định protocol trước final selection; D2 cho phép V1 unavailable không tự chặn calibration nhưng review lock. Cần Trung/team xác nhận relationship/precedence và cách xử lý đặc tả trong `contracts/` trước STEP_03; không sửa hay tự diễn giải lại Contract. Threshold cũ 0.435/0.420 diagnostic only, calibrated values null.

## 9. Open implementation parameters

| Vấn đề | Ảnh hưởng | Đề xuất trung tính; không tự phê duyệt |
| --- | --- | --- |
| Số fold, deterministic construction và support nguồn/nhãn/subgroup | Cross-fit metrics và feasibility | Chốt trước thực nghiệm; tôn trọng group lớn, không tối ưu theo M5a |
| Equality/tie số học | Chọn threshold | Chốt số học so sánh trước chạy, không tự epsilon |
| Min valid bootstrap replicates, CI NA/partial | Mức có thể công bố | Chốt ngưỡng và báo tỷ lệ NA; không lọc để làm đẹp |
| Missing dependency metadata | Tính độc lập/CI | Quy định fail-closed hoặc phân loại evidence limited trước chạy |
| Reference V4 packaging và dependency | Reproducibility/compatibility | Đóng gói tối thiểu, hash/version pin, test behavior, Trung review |
| V1 baseline | Final selection/lock | Xác minh artifact/provenance hoặc ghi V1_BASELINE_UNAVAILABLE, xử lý khác biệt model-design |
| Close-positive outcome availability và D2 bootstrap aggregation | Feasibility, subgroup pairing | Cố định mapping ID/denominator và failure trước chạy; không dùng score Validation để chọn |

Các mục trên có thể ảnh hưởng calibration hoặc lock nên cần Trung review trước STEP_03. Diagnostic về group 556/835 chỉ là evidence lịch sử, không đảm bảo group cross-fit khả thi.

## 10. Giới hạn và readiness

`PROTOCOL_SPEC_COMPLETE=YES` cho đặc tả được duyệt và validator; `CONTRACT_CONFLICT_REVIEW_REQUIRED`; `READY_FOR_STEP_03=NO`. Dataset Validation có source–label confounding, reuse/selection bias, dependency group lớn; Test từng dùng trong nghiên cứu là benchmark phát triển, không độc lập. Chưa có Tier 2 độc lập hoặc runtime T18/T19. Giữ MODEL_STATUS=CANDIDATE, MODEL_LOCK=NO, PRODUCTION_APPROVED=NO; thresholds null, TEST_BENCHMARK_PERFORMED=NO.

## 11. Files

Mới: `configs/s4_calibration_protocol.yaml`; `src/protocol/__init__.py`, `src/protocol/calibration_protocol.py`; `tests/unit/test_s4_t14_protocol.py`; `docs/trung/S4_T14_DECISION_REGISTER.md`, `S4_T14_CALIBRATION_PROTOCOL.md`, `S4_T14_ACCEPTANCE_MATRIX.md`, `S4_T14_STEP02_REPORT.md`. Báo cáo STEP_01 cũ giữ nguyên. Contract/config cũ/model/risk/dataset không sửa.
