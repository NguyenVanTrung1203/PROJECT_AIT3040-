# Báo cáo final audit S3 T10–T11

## Baseline và phạm vi

Worktree `trung-contract-v1-freeze`; branch `s3-t10-trung-full-training`; base `f3096fd2d44471ce7bbf455932cd7c3d5634f692`. T06 `46270e5`, T07 `f3096fd` và Contract V1 `99bdb2649f5aec39d67a6f64645bce4f7fc49a3d` thuộc ancestry. Không có diff Contract V1 từ baseline. Branch đích remote chưa tồn tại tại lần kiểm tra trước commit. Không merge, rebase, reset hoặc force push.

## Inventory

- T10: `scripts/train_s3_t10.py`, `scripts/verify_s3_t10.py`, `docs/trung/S3_T10_FULL_TRAINING_REPORT.md`.
- Diagnostic: `scripts/diagnose_s3_t10_epoch1.py`, `scripts/compare_s3_t10_risk.py`, `scripts/summarize_s3_t10_risk.py`, `scripts/evaluate_s3_close_positive.py`, hai test `test_s3_t10_epoch1_diagnostic.py`, `test_s3_post_t10_risk_comparison.py`, và hai báo cáo epoch1/risk.
- T11: `src/inference/`, `scripts/verify_s3_t11.py`, test inference/trusted boundary, báo cáo T11 và handoff T18.
- Finalization: báo cáo này.

Không đưa dataset, checkpoint `.pt`, scaler, tensor, prediction, cache, môi trường ảo, `node_modules` hay artifact sinh ra vào Git. Các artifact được giữ nguyên trong vùng ignore. Hai test reference Risk V4 dùng biến `V4_REFERENCE_RISK_PATH`; cần cung cấp reference riêng với hash đã khóa để tái lập đầy đủ, không chứa đường dẫn máy cá nhân. Các test này skip rõ ràng nếu reference không có; lượt regression dưới đây có reference và không skip.

## Dataset và artifact T10

Dataset `final_dataset_1.0`: 93/93 checksum PASS, manifest `21f6bde168631928e98b6273aaab4e168bfb6eb755599a1fbc1cb8c364611441`. Artifact T10: 12/12 checksum PASS, checksum manifest `5f0af2eb5a4e418026b775fa412e2fc8bbc803c7438123038a1c519e5a082eb2`. M5a 15.390 tham số, seed 20261110, checkpoint epoch 1 SHA-256 `e01a19e913d14a068c6c82a1c2a52a8be2aadd2f44e3ad5d8770d7f69a1fc7bc`; X scaler `a538be921104ed1bb2fa495c0c3f527c0385fd6c737aa69afda81ba1962d452a`; residual scaler `96b062fab9a5d4e27c9b1cc32a649e44e98d29648c7dcc3b7f482eba3d50358f`.

Verifier T10 chính thức chạy trên bản sao trong `artifacts/checkpoints/s3_t10_final_audit_copy_20261124/` vì script ghi kết quả và checksum; bản gốc không bị ghi đè. Kết quả `PASS_WITH_CPU_PARITY_CAVEAT`: CUDA replay max diff 0, severe QC 0; CPU max diff 3.300808803252675e-5 nm, 260 vessel vượt ngưỡng chẩn đoán T10 cũ 1e-5 nm. Không coi ngưỡng cũ đã đạt. Không training, refit scaler hoặc benchmark Test; checksum có đọc byte Test để kiểm toàn vẹn.

## Diagnostic

Real AIS Validation: M5a ADE 0.196332 nm, CV 0.186414 nm. Risk/Alert diagnostic: `SMALL_OR_UNCERTAIN_BENEFIT`, chênh lệch AUC/F1 nhỏ, bootstrap CI chứa 0 và chịu giới hạn phụ thuộc dữ liệu/chọn threshold trên cùng Validation. Không xem diagnostic threshold là threshold production, không model lock hay calibration.

## T11 offline và trust boundary

Offline validator tự mở dataset, kiểm manifest/checksum, identity/mapping, 10 history UTC, source as-of, finite và feature/anchor EN; không nhận object hoặc boolean tự khai làm bằng chứng. Runtime `predict` fail-closed; fixture test-only không chứng minh provenance. Yang Lei dùng thời gian mô phỏng, không giả AIS source timestamp; identity chỉ xác minh nhất quán với dataset, không xác nhận sở hữu thực. Code/filesystem cùng tiến trình phải được kiểm soát. T18 còn phải triển khai và kiểm thử adapter runtime.

835/835 encounter, 1.670 vessel; CPU/GPU severe QC 0. GPU dự báo khớp prediction T10 chính xác. CPU/GPU max absolute position `3.300808803252675e-5` nm, mean `2.143955438867671e-6`, P95 `7.197260856628418e-6`, P99 `1.163043081760408e-5`; 0 vessel vượt `5e-5`. ADE diff `8.06442548850761e-9` nm; FDE diff `1.0513768750053387e-7` nm. Đạt các ngưỡng đề xuất trong phạm vi offline; không hàm ý Trung phê duyệt tolerance chính thức hoặc runtime production.

## Regression và security

Một lượt chung `tests/unit tests/integration backend/tests`: **349 passed, 0 failed, 0 skipped**, 46.74 giây, 1 cảnh báo StarletteDeprecationWarning. Python 3.12.3, PyTorch 2.11.0+cu128, CUDA 12.8, RTX 4050; syntax/import PASS. Kiểm tra tên file/kích thước, chuỗi secret thông dụng và đường dẫn máy cá nhân trong file S3; không phát hiện secret hay binary/dataset trong inventory. Đây là kiểm tra nội dung, không phải chứng nhận security toàn diện.

## Trạng thái và bàn giao

MODEL_STATUS = CANDIDATE
MODEL_LOCK = NO
PRODUCTION_ALERT = NO
T11_OFFLINE_INFERENCE_READY = YES
T11_CODE_COMPLETE = YES trong phạm vi offline
T11_READY_FOR_RUNTIME_INTEGRATION = DEPENDENT_ON_T18
T14_PREPARATION = có thể chuẩn bị, chưa calibration hay quyết định model

T14 cần review kết quả đối chứng và protocol trước calibration. T18 cần trusted TrackSnapshot/G11, identity, session/pair hash, source timestamp/as-of/stale, feature EN và causal provenance; xem handoff T11. Không coi Test là holdout độc lập mới.

## Hậu kiểm Git

Ba commit công việc đã tạo và đối chiếu danh sách file:

- T10: `8797fdf51d08d5db27f2d4168add971f3e151e7d`.
- Diagnostic: `9bf62775e149a0bb650fa46d268962a626f11c92`.
- T11: `7e322c2613934bda5ecd6579b4d0485cd0daa828`.

Branch đích được kiểm tra trước push chưa tồn tại; báo cáo này được commit trước khi push. Trạng thái push sẽ được ghi nhận bằng mục hậu kiểm sau khi có kết quả; không amend.
