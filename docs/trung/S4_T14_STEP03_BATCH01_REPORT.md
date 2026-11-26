# S4 T14 STEP 03 — Batch 01

## 1. Kết quả

Run `s4_t14_batch01_20261125T025749Z_fbf7f18e` hoàn thành inference và exact Risk packaging parity trên 835 Validation encounters, mỗi model 1.670 vessel forecasts; không chọn threshold. STEP03_BATCH01_ACCEPTANCE=PASS; READY_FOR_D1_D2=YES trong phạm vi offline đã phê duyệt. CC-DRI là risk score, không phải xác suất va chạm đã hiệu chỉnh.

## 2–4. Baseline, protocol và môi trường

Worktree `trung-contract-v1-freeze`; branch `s3-t10-trung-full-training`; HEAD và remote `4457fc2d4f485d2da832b039e8edc1cdf5837551`. Contract V1 `99bdb2649f5aec39d67a6f64645bce4f7fc49a3d` là ancestor; `contracts/` và `configs/risk_config.yaml` không có diff so với HEAD. S4 chưa commit được bảo toàn. Semantic protocol SHA-256 `23d427ea6416104efbc9e988aaaa6c774118a517aea528b1ecb0c8350de4bf0b`; validator pin pass, D1–D7/P1–P7/Q1–Q4 theo baseline đã duyệt; trạng thái candidate, hai threshold null, model lock/test benchmark/production false.

Python 3.12.3, NumPy 2.4.4, PyTorch 2.11.0+cu128, CUDA 12.8, NVIDIA GeForce RTX 4050 Laptop GPU, pandas 3.0.3, joblib 1.5.3, scikit-learn 1.8.0, pyarrow 26.0.1. Device CUDA, batch 128, model float32, projection float64, seed 20261124, deterministic algorithms enabled. Clean-environment rebuild NOT_VERIFIED; không tuyên bố D5 CPU/GPU parity.

## 5–8. Integrity, trusted input và Test

`final_dataset_1.0`, READY_AND_LOCKED; lock SHA `036d9c0e3652e526613238b91151002cbca35615552eba687b588da01b0fe764`; checksum manifest SHA `21f6bde168631928e98b6273aaab4e168bfb6eb755599a1fbc1cb8c364611441`; 93/93 PASS. Dependency manifest SHA `f0702ca49f289ec2a2ec9169e1b5632dcaf330fc634b027a7b11cf89d60ce2ea`; 835 identity, 260 groups, largest 556, remaining 279; grouping CONDITIONAL offline, lineage PARTIAL, independent provenance PARTIAL và MMSI ownership NOT_VERIFIED.

T10 artifact manifest SHA `5f0af2eb5a4e418026b775fa412e2fc8bbc803c7438123038a1c519e5a082eb2`, 12/12 PASS. Checkpoint epoch 1/seed 20261110 SHA `e01a19e913d14a068c6c82a1c2a52a8be2aadd2f44e3ad5d8770d7f69a1fc7bc`, input scaler SHA `a538be921104ed1bb2fa495c0c3f527c0385fd6c737aa69afda81ba1962d452a`, residual scaler SHA `96b062fab9a5d4e27c9b1cc32a649e44e98d29648c7dcc3b7f482eba3d50358f`. T11 verified model/config and 15.390 parameters; architecture Residual-GRU 4→48, one layer, head 48→96→30, forecast CV plus residual.

T11 trusted loader xác minh dataset, history, identity, A/B, timestamps, source age, input order và frame; M5a chạy `allow_fallback=False`. Loader memory-map Validation target/labels và đối chiếu label/index để kiểm tra cấu trúc; call path prediction/scoring chỉ truyền history, anchors và verified metadata, không truyền giá trị future hoặc labels. Sau scoring mới truy cập future/labels để tạo evaluation metadata. Test bytes chỉ được đọc để checksum Q1; không deserialize Test content hoặc Test inference. Guard trong process ghi nhận 28 lượt mở Test để hash, 0 chặn deserialize, 0 chặn open khác; guard không chứng minh tổng quát native/subprocess I/O.

## 9–13. Inference, pairing và QC

CV và M5a mỗi model hoàn tất shape `[835,2,15,2]`, dtype float64, finite, 835 encounters và 1.670 vessels. Đối chiếu identity, rows, vessel IDs, slots A/B và timestamp từng encounter, không chỉ nối theo thứ tự; pairing 100%. History, anchors, frame và source dùng cùng trusted Validation input. Cả hai model severe QC: 0 encounters, 0 vessels; không loại mẫu, không fallback. Không có warning QC riêng được phát ra bởi interface này; không suy diễn một phép đếm warning bổ sung.

## 14–15. Risk V4 exact parity

Original và packaged source byte-identical SHA `8e33effb06d7f2e1fe855b1cb067fb2d27eb3aba9498e2af30be1b387534be7e`. Hai implementation dùng bản sao bằng nhau của cùng scoring inputs và forecasts. Với mỗi model, tất cả 13 fields từ `calculate` được so sánh exact, gồm 12 trường scalar/encounter và `cv_common` (60.120 values/model); 3 fields role/scene/rule có 2.505 values. Tổng 122.745 values, exact match 122.745, numeric/semantic mismatch 0, max absolute difference 0, affected IDs rỗng. 835/835 scores cho từng model; 1.670 model-encounter pairs. Predicted CPA và current CPA, rule, components và CC-DRI đều khớp. Không thực hiện grid decision parity; không chọn threshold.

## 16–17. Evaluation metadata

Quan sát: Yang Lei 240 (125 positive, 115 negative); Real AIS 295 negative; Synthetic AIS 300 positive; tổng 425 positive/410 negative. Sau khi scoring hoàn tất, future được đối chiếu theo vessel A/B và 15 timestamps. Strict haversine `<0.1 nm` cho synthetic positive: 60 encounters. ADE/FDE mỗi encounter là trung bình hai vessel, float64, nautical miles, dùng cho evaluation sau; chưa dùng để chọn model hoặc đánh giá D2.

## 18. Handoff

Artifacts nằm ngoài Git tại `C:\Users\MSI\Documents\Codex\2026-11-20\files-pasted-by-the-user-sprint-2\s4_t14_batch01_runs\s4_t14_batch01_20261125T025749Z_fbf7f18e`. Gồm `run_manifest.json`, `run_status.json`, `cv_predictions.npz`, `m5a_predictions.npz`, `risk_scores.parquet`, `evaluation_metadata.parquet`, `parity.json`, `qc_summary.json`, `checksums.sha256`. Tám output checksums PASS. `verify_reuse` kiểm tra checksums, identity protocol/dataset/dependency/model/original source/source-config, dữ liệu dataset và pairing predictions/risk/metadata; independent reuse check PASS. Manifest/checksums không tự xác thực bằng chữ ký; run immutable theo quy ước. Run tiền nhiệm được giữ lại, không ghi đè.

## 19. Regression

Targeted runner tests: 17 passed, bao gồm original/package nhận cùng scoring input và phát hiện sai lệch exact. Full regression phiên bản runner cuối: 491 passed, 0 failed, 0 skipped, 0 deselected, 1 StarletteDeprecationWarning, 125.82 giây. Lệnh `python -m pytest -p scripts.q1_test_access_guard tests/unit tests/integration backend/tests -q`; guard ghi 42 lượt hash Test, 0 blocked deserialization và 0 blocked other opens. Backend TestClient bị treo trong sandbox; chạy lại full regression ngoài sandbox với cùng Q1 guard. `git diff --check` PASS, có cảnh báo line ending tại file T11 đã sửa từ trước. Syntax và protocol YAML validation PASS. Targeted tests được chạy riêng và không cộng vào tổng full regression.

## 20–22. Limitations và acceptance

Dependency provenance PARTIAL, grouping CONDITIONAL, MMSI ownership NOT_VERIFIED, clean environment NOT_VERIFIED trước integration handoff, V1 baseline review trước Model Lock, Validation reuse và T18/T19 runtime chưa xác thực. STEP03_BATCH01_ACCEPTANCE=PASS; READY_FOR_D1_D2=YES. Không có blocker hiện hữu trong phạm vi offline. D1–D5 chưa thực hiện, không test benchmark, calibration, model lock hay production approval. Không commit/push. Không tự chuyển sang D1/D2.
