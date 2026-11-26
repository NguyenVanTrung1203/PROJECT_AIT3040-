# S4 T14 STEP 02 — Targeted remediation Q1–Q4

## 1–3. Tóm tắt, baseline và phê duyệt

Trung đã duyệt D1–D7, P1–P7 và Q1–Q4 cho phạm vi offline; không duyệt threshold, model package hoặc production. Worktree `trung-contract-v1-freeze`, branch `s3-t10-trung-full-training`, HEAD `4457fc2d4f485d2da832b039e8edc1cdf5837551`, S3 local HEAD và remote SHA trùng nhau khi kiểm tra lại; Contract V1 ancestor `99bdb2649f5aec39d67a6f64645bce4f7fc49a3d`, Contract/risk_config giữ nguyên. Không commit/push, không đổi branch. Các báo cáo STEP_01/initial/finalization/closure giữ lịch sử.

## 4. Q1 — Test access và full regression

Audit test call path: `tests/unit/test_s3_t11_trusted_boundary.py::data` gọi `load_validation` → `checksum_dataset` đọc raw bytes 93 file (kể cả Test) bằng SHA-256, rồi `DatasetLoader.load_split('validation')` và Validation history; không gọi Test deserialization. Test fallback gọi `predict_validation` cho 835 Validation sau khi ép lỗi M5a; không dùng output để chọn threshold, calibration, Test benchmark hay full Risk packaging parity. `scripts/q1_test_access_guard.py` là pytest plugin giám sát trong process chính: cấm `numpy.load`, pandas CSV/parquet trên dataset Test và từ chối `Path.open` Test ngoài `checksum_dataset`; không phải sandbox bảo đảm mọi subprocess/native I/O. Source-level call-path audit bổ sung cho phạm vi guard.

Lệnh cuối: `python -m pytest -p scripts.q1_test_access_guard tests/unit tests/integration backend/tests -q`, 474 collected/passed, 0 failed/skipped/deselected, 1 StarletteDeprecationWarning, 68.37 giây. Guard: 42 Test file opens tại checksum, 0 blocked deserialization/other open; kết quả thuộc phạm vi guard và source audit, không chứng minh mọi native/subprocess I/O một cách tổng quát. Tất cả 16 test T11, gồm 15 test trước đó deselected, được chạy trong suite này. Checksum dataset 93/93, artifact 12/12 PASS; checkpoint/scaler SHA giữ nguyên. Test bytes được hash theo Q1; không deserialize Test content/labels/predictions, không Test inference hay metrics. Validation inference chỉ trong regression T11 hiện có.

## 5. Q2 — Dependency scope

Audit metadata rerun: 835 encounter, 260 groups, largest 556; parent 600/600 rows và 300/300 metadata match; 1.190 physical MMSI namespace/index rows; connected-components mapping khớp. Dependency manifest SHA `f0702ca49f289ec2a2ec9169e1b5632dcaf330fc634b027a7b11cf89d60ce2ea`. Internal consistency và partition reproduction PASS; independent upstream provenance PARTIAL, historical upstream window hash chưa tìm thấy; observed hash `4220ea18363b4f4016e7efaac56a9dd6134bcd194d203fc70f442cb858e59cac` không gọi là historical locked hash. MMSI ownership NOT_VERIFIED; Yang legacy IDs không tự thành G11 production. Trung chấp nhận grouping CONDITIONAL cho D3/D4 exploratory offline; không thay status evidence thành VERIFIED hoặc miễn integrity checks.

## 6–7. Q3 — Runner và synthetic integration

`src/protocol/clustered_bootstrap.py`: `PairedData` xác thực cùng ordered encounter IDs CV/M5a và metadata, không tự chứng thực provenance; caller phải dùng verified offline boundary. `resample_plan`: group unique sort UTF-8, NumPy `default_rng` PCG64 seed 20261124, mỗi attempt rút G group có hoàn lại, một plan chung, giữ encounter multiplicity. Không deduplicate, không retry/bù. Default 5.000; số lần, seed hoặc plan khác chỉ với `fixture_mode=True`, không đủ tư cách official qualified CI.

L1 fixed threshold dùng score `>= k/200`, tính paired delta M5a−CV cho ROC-AUC, Average Precision, F1, recall, Real FPR, ADE/FDE và close-positive recall; P3 support theo encounter, một model undefined → delta UNDEFINED. Inputs ADE/FDE là per-encounter mean hai vessel, caller phải cung cấp evidence/mapping verified; code không tự load dataset. L2 duyệt exact D1 riêng model, support và D2 Real FPR/score/close ID; lưu feasibility từng model, both-feasible, D2 status, threshold distribution, support counts và lỗi. No feasible không phải execution error. Feasible rate chia tổng attempts.

CI 95% percentile tách all-defined descriptive và support-qualified. Per metric require cả hai model valid-support; ≥4750/5000 và không execution error để reportable qualified CI. Không thay NA bằng 0, không resample bù, không coi filtered CI unbiased hoặc thêm CI positivity/feasible-rate gate. Synthetic fixtures cover determinism, multiplicity, pairing mismatch, 20 attempts/3 low support, 4749/4750 policy từ tests primitives, threshold reselection, K fallback, support của held-out/complement và bounded-search limitation. Không chạy grouped cross-fit thật hay 5.000 bootstrap trên Validation.

## 8–9. Q4 — Offline Risk và environment

Raw V4/source packaged byte-identical SHA `8e33effb06d7f2e1fe855b1cb067fb2d27eb3aba9498e2af30be1b387534be7e`, Trung xác nhận quyền. 25 installed distributions khớp observed dependency manifest, Python 3.12.3, torch 2.11.0+cu128/CUDA 12.8, pip check PASS. Fixture exact parity và portable scoring từ cwd riêng; adapter dùng T11/loader và cùng reference CV/M5a, fail-closed invalid/identity/A-B/time/NaN/Inf/QC, không dùng raw Test helper; benchmark comparison không giả M5a bằng fallback CV. Full T11 trusted-boundary regression theo Q1 bổ sung evidence. `CLEAN_ENVIRONMENT_VERIFICATION=NOT_VERIFIED`; vẫn bắt buộc trước integration handoff. Raw Python module không là security sandbox; T18/T19 runtime và production chưa duyệt.

## 10–11. P7 và traceability

P7-T01…T12 được mô tả trong decision register và traceability; bounded recovery hoàn thành, `V1_BASELINE_REVIEW_REQUIRED` do projection/QC, dataset split, A/B mapping và prediction provenance chưa được chứng minh. Không tự cho V1 reproducible, không retrain hay dùng Test để recovery; limitation review trước Model Lock, không chặn riêng D1/D2 CV/M5a.

Traceability phân biệt evidence PASS/PARTIAL, phê duyệt limitation Q2/Q4, và deferred STEP_03/MODEL_LOCK/integration. PARTIAL không đổi thành PASS chỉ vì được chấp nhận; full Validation Risk packaging parity, actual grouped CV/bootstrap là STEP_03, clean rebuild trước integration, V1 compatibility trước lock.

## 12–14. Regression, Contract và files

Full regression 474 passed, 0 failed, 0 skipped, 0 deselected, 1 warning; 68.37 giây. Targeted suite chạy riêng: 140 passed trong 45.84 giây; không cộng vào tổng full regression. Guard và giới hạn nêu tại mục Q1. Contract V1, risk_config, dataset và T10 model artifacts không đổi. Mới trong lượt này: `src/protocol/clustered_bootstrap.py`, `scripts/q1_test_access_guard.py`, `tests/unit/test_s4_t14_bootstrap_runner.py` và báo cáo này. Cập nhật `src/protocol/group_assignment.py`, `src/protocol/calibration_protocol.py`, `configs/s4_calibration_protocol.yaml`, decision register, calibration protocol, acceptance matrix, traceability matrix và addendum lineage/risk. Các thay đổi S4 có sẵn từ trước vẫn chưa commit. Không sửa raw V4 hoặc công việc Toàn.

## 15–18. Limitation, blockers và bước tiếp

Approved limitations: V1 review required, upstream independent provenance PARTIAL, MMSI ownership NOT_VERIFIED, clean environment NOT_VERIFIED, group mất cân bằng, Validation reuse, runtime T18/T19 chưa kiểm. Các mục này không tự chặn STEP_03 theo Q2/Q4; không suy diễn production readiness.

Actual blockers: không phát hiện sau full regression, integrity và fixture checks trong phạm vi offline được Trung duyệt. `STEP02_FINAL_ACCEPTANCE=YES`, `READY_FOR_STEP_03=YES`, `READINESS_SCOPE=OFFLINE_WITH_APPROVED_LIMITATIONS`. Sau Trung review, STEP_03 bắt đầu bằng dataset/artifact/protocol integrity, config và trusted input, full Validation original/package exact Risk parity, CV/M5a forecast/score completeness, encounter/A-B pairing và severe QC; chỉ sau đó mới chọn threshold D1. Không tự chuyển bước.

MODEL_STATUS=CANDIDATE; MODEL_LOCK=NO; calibrated CV/M5a=NULL; CALIBRATION_PERFORMED=NO; TEST_BENCHMARK_PERFORMED=NO; PRODUCTION_APPROVED=NO.
