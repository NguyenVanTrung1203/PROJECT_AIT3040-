# S4 T14 C04 — Risk adapter verification

## Source và dependency

Original V4 `MODEL_CANDIDATE_PACKAGE/inference/risk_pipeline.py` và package `src/risk/reference_v4/risk_pipeline.py` SHA-256 `8e33effb06d7f2e1fe855b1cb067fb2d27eb3aba9498e2af30be1b387534be7e`; byte-identical, algorithm không đổi. Trung đã xác nhận quyền phân phối file. Raw reference nhập pathlib/json (stdlib), numpy/pandas/joblib/torch; scoring CPA/rule dùng numpy. `history_features` trong raw source hỗ trợ Test, không phải trusted API, adapter không gọi hàm này. Import source chỉ tạo hằng đường dẫn/hàm/class; không đọc dataset khi import. Adapter kiểm hash source trước import và trước suy luận.

`configs/s4_t14_observed_dependency_closure.yaml` ghi 25 distribution và các active dependency edges trong môi trường hiện có: Python 3.12.3, numpy 2.4.4, pandas 3.0.3, torch 2.11.0+cu128, joblib 1.5.3, scikit-learn 1.8.0, pyarrow 26.0.1, v.v.; `pip check` không báo broken requirements. Đây là observed environment, chưa rebuild môi trường sạch, chưa khóa wheel hashes/index hoặc xác minh toàn bộ license/runtime CUDA driver; không coi là deployment lockfile. T06/T11/DatasetLoader và các package transitive được mô tả trong manifest. Installed dependencies không được vendored.

## Trust boundary và failure

`evaluate_validation` chỉ nhận dataset root và artifact path; gọi `load_validation` kiểm manifest/index/history/provenance rồi `M5aInference.predict_validation(...,allow_fallback=False)`, không nhận object VERIFIED từ caller. `predict_runtime` fail-closed. Adapter kiểm mapping X_row/A-B, identity encounter, forecast timestamp, shape `[N,2,15,2]` float64, finite, duplicate/coverage, status và severe M5a; CV tính qua T06 projection/severe QC. Không score khi các kiểm tra trên thất bại. Reference `calculate` được gọi cùng một implementation hai lần cho CV/M5a; component hoặc score không finite bị từ chối. CV technical failure trả FORECAST_UNAVAILABLE. Để so sánh hai candidate, adapter không tự thay forecast M5a bằng CV; T11 fallback riêng chỉ được phép theo V1 và được test synthetic trong suite T11. Không phát alert/threshold production.

Synthetic spies ở `tests/integration/test_s4_t14_risk_adapter_closure.py` kiểm call path, cùng engine, fake runtime rejection, missing/duplicate/wrong identity/A-B, forecast shape/dtype/timestamp, NaN/Inf, severe/fallback/QC, score nonfinite, CV failure và model failure. Dữ liệu fixture bị mock không được coi là provenance production. Kiểm trusted validator trên dữ liệu Validation thực trong module T11 trước đây đọc checksum bytes Test và có một test suy luận 835 encounter; trong closure này những test phụ thuộc fixture đó không chạy vì ràng buộc không mở Test/không full Validation inference. Do vậy không khẳng định toàn bộ input/timestamp/source/NaN history và fallback được xác minh lại ở boundary thực trong lượt này.

## Parity và portability

`tests/unit/test_risk_reference_v4.py` đối chiếu exact original/package trên fixture cho Current/Predicted CPA, role/rule, components, CC-DRI, threshold decisions và near-zero; raw error behavior được xem riêng với rejection của adapter. `test_portable_scoring_from_external_cwd_without_research_path` dùng subprocess `-I`, cwd tạm, không env trỏ reference gốc, import theo vị trí repo và chạy CPA/score synthetic. Portable import/execution trong môi trường hiện có: PASS khi tests chạy; clean-environment setup: NOT_VERIFIED. Không chạy full Validation parity ở STEP_02; đó là first gate STEP_03.

## P6-T01–T18

Xem matrix `S4_T14_REQUIREMENTS_TEST_TRACEABILITY.md` cho từng ID; các phần dependency clean-environment, test access/read boundary đầy đủ và một số failure/QC với trusted validator thực vẫn PARTIAL. P6 chưa được coi hoàn tất cho STEP_02_CLOSURE; không dùng D5 tolerance để che khác biệt packaging. Không triển khai T18/T19.

## Addendum Q4 — offline acceptance scope

Trung chấp nhận xem xét offline Risk trên môi trường đã kiểm chứng, không bắt buộc clean rebuild để vào STEP_03. Clean-environment setup vẫn NOT_VERIFIED và bắt buộc trước integration handoff. Không sửa raw reference hay cho phép raw `history_features` bypass trusted adapter. Full Validation original/package exact parity vẫn là first gate STEP_03; runtime T18/T19 và production chưa phê duyệt.

## Addendum Q4 — điều kiện offline

Q4 chấp thuận đánh giá reference/adapter trong môi trường đã kiểm; clean-environment rebuild chưa kiểm không tự chặn STEP_03, nhưng bắt buộc trước integration handoff. P6 fixture exact parity, portable import/execution và synthetic failure/QC được phân biệt với full Validation parity chưa thực hiện. Trusted-boundary regression T11 chạy theo Q1; các kết quả cụ thể nằm trong báo cáo targeted remediation, không suy diễn production runtime.
