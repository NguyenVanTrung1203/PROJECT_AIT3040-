# S4 T14 STEP 03 — Batch 03: D3, D4 và D5

## 1–4. Tóm tắt và parent verification

Batch 01 `s4_t14_batch01_20261125T025749Z_fbf7f18e` và Batch 02 `s4_t14_batch02_20261125T031911Z_cb53e739` đã verify 8/8 và 9/9 checksums; source/config 27 hashes, parent linkage, protocol, dataset 93/93 và model artifacts 12/12 PASS. HEAD `4457fc2d4f485d2da832b039e8edc1cdf5837551`, Contract V1 ancestor, Contract/risk_config unchanged. Semantic protocol SHA `23d427ea6416104efbc9e988aaaa6c774118a517aea528b1ecb0c8350de4bf0b`. 835 Validation encounters, 260 groups; primary CV/M5a thresholds 0.435/0.420. Independent provenance PARTIAL, grouping CONDITIONAL, MMSI ownership NOT_VERIFIED.

D1 CV/M5a và D2 primary vẫn PASS. D3 infeasible theo chứng minh cấu trúc; D4 evidence limited; D5 PASS. Đây là readiness để review, không phải lock hay production approval.

## 5–7. D3 grouped cross-fitting

Assignment search chỉ dùng group metadata/source/label/close support; không dùng scores. Bounded search deterministic seed 20261124, 32 attempts cho từng K; không tìm thấy assignment.

| K | Attempts | Support result | Assignment | Reason |
| --- | ---: | --- | --- | --- |
| 5 | 32 | Không đạt | Không | Cấu trúc close-positive |
| 4 | 32 | Không đạt | Không | Cấu trúc close-positive |
| 3 | 32 | Không đạt | Không | Cấu trúc close-positive |
| 2 | 32 | Không đạt | Không | Cấu trúc close-positive |

Chứng minh độc lập với heuristic: group `DEP_VAL_REAL_0001` chứa 556 encounters, trong đó 56/60 close-positive; ngoài group chỉ còn 4. Với mọi K≥2, fold giữ group này có calibration complement tối đa 4 close-positive, thấp hơn P3 minimum 10. Không chia group, hạ support hay loại mẫu. `GROUPED_CV_INFEASIBLE`; không có fold threshold hay out-of-fold decisions, coverage CV/M5a/paired 0/835. D3 không phải external validation; limitation cần Trung review.

## 8–9. D4-L1: fixed-threshold paired clustered bootstrap

5.000 attempts, 260 group draws có hoàn lại mỗi lượt, seed 20261124, NumPy default_rng PCG64, nhóm sort theo UTF-8; cùng plan và multiplicity cho CV/M5a, không lấy bù. Delta = M5a−CV. Error 0. Plan được lưu checksum; support counts là số encounter sau multiplicity, không phải số quan sát độc lập. All-defined CI là descriptive; qualified CI yêu cầu ≥4750 valid-support và không có execution error.

| Metric Δ | Full Validation Δ | Defined | Valid support | All-defined 95% CI | Support-qualified 95% CI |
| --- | ---: | ---: | ---: | --- | --- |
| ROC-AUC | +0.000356 | 5000 | 5000 | [−0.001779, 0.007649] | [−0.001779, 0.007649] |
| Average Precision | +0.001601 | 5000 | 5000 | [−0.001523, 0.010649] | [−0.001523, 0.010649] |
| F1 | +0.005749 | 5000 | 5000 | [−0.005245, 0.018497] | [−0.005245, 0.018497] |
| Recall | +0.007059 | 5000 | 5000 | [0, 0.020690] | [0, 0.020690] |
| Real AIS FPR | −0.003390 | 5000 | 3370 | [−0.003601, 0] | Không đủ 4750 |
| ADE | +0.011512 nm | 5000 | 5000 | [0.006005, 0.012995] | [0.006005, 0.012995] |
| FDE | +0.007654 nm | 5000 | 5000 | [0.001582, 0.010882] | [0.001582, 0.010882] |
| Close-positive recall | 0 | 4969 | 3152 | [0, 0] | Không đủ 4750 |

Real FPR có 1.630 LOW_SUPPORT; close recall có 1.817 LOW_SUPPORT và 31 UNDEFINED. Hai qualified CI báo `CI_INSUFFICIENT_VALID_REPETITIONS`. Các CI còn lại reportable exploratory; không coi CI chứa 0 là equivalence, không coi CI khác 0 là independent superiority, và không thêm CI gate vào D2.

## 10–11. D4-L2 threshold stability

Cùng plan 5.000 attempts như L1, D1/P3/P4/P1 được áp dụng lại từng sample. Bộ chọn histogram exact được đối chiếu với implementation gốc trên 32 sample thực × 2 model và synthetic boundary/tie tests; không đổi comparator hoặc tie-break. Correction tại Batch 03 wrapper: khi M5a không feasible, D2 là BLOCKED thay vì conditional chỉ dựa vào CV; không sửa parent source hoặc Batch 02 D1/D2. Trên run này 1.863 cases đều là cả hai infeasible; không có trường hợp chỉ một model feasible.

| Metric | CV | M5a |
| --- | ---: | ---: |
| Total attempts | 5000 | 5000 |
| Feasible | 3137 | 3137 |
| Feasible rate | 62.74% | 62.74% |
| Min threshold | 0.405 | 0.420 |
| Median threshold | 0.435 | 0.420 |
| Max threshold | 0.515 | 0.485 |
| Distribution denominator | 3137 | 3137 |

Both-feasible/joint D2 evaluable 3.137; D2_PASS 1.565, D2_FAIL 1.572, D2_CONDITIONAL 0, D2_BLOCKED 1.863. Trong các fold sample có thể đánh giá, số failure theo gate: new close misses 1.397, Real FPR delta 145, recall delta 78, overall ADE 31; các gate có thể đồng thời fail. Không có pass-rate gate bổ sung. L2 là in-sample bootstrap stability, không phải held-out evaluation và không thay operating points chính thức.

## 12–13. D4-L3 và diễn giải

| Subset | Encounters | CV F1 | M5a F1 | Recall delta | Real FPR delta | ADE ratio | Support limitations |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| S1 Full | 835 | 0.911765 | 0.917514 | +0.007059 | −0.003390 | 1.084467 | Đủ P3 |
| S2 Without largest | 279 | 0.894737 | 0.901316 | +0.007092 | 0 | 1.061776 | Real negatives 23; close-positive 4 |
| S3 Largest only | 556 | 0.920690 | 0.925990 | +0.007042 | −0.003676 | 1.097695 | Không có Yang Lei |

Full metrics, confusion counts, subgroup support và IDs lưu trong artifact. Dấu delta AUC/AP đổi giữa S2 và S3; S2 thiếu support Real FPR/close. Không điều chỉnh threshold hoặc loại group. `D4_EVIDENCE_LIMITED`: imbalance, Validation dùng để chọn epoch và threshold, grouping provenance conditional, khả năng phụ thuộc chưa quan sát và qualified CI không đủ support. Filtered CI không được coi là unbiased hoặc bảo đảm nominal coverage.

## 14–19. D5 CPU/CUDA

M5a T11 trusted offline trên CPU và CUDA, batch 128, cùng checkpoint/scalers, frame/history/anchor/A-B và Risk V4; không fallback. Python 3.12.3, PyTorch 2.11.0+cu128, CUDA 12.8, GPU NVIDIA GeForce RTX 4050 Laptop GPU. Fresh CUDA forecast, score và decision trùng exact Batch 01 reference; CV được tính cùng deterministic CPU path, không tuyên bố có GPU CV implementation riêng.

| Gate | Observed | Required | Status |
| --- | ---: | ---: | --- |
| Max coordinate difference | 3.300808803252675e−05 nm | ≤5e−5 | PASS |
| Aggregate ADE difference | 8.064425682796639e−09 nm | ≤1e−6 | PASS |
| Aggregate FDE difference | 1.0513774906240059e−07 nm | ≤1e−6 | PASS |
| Max Risk Score difference | 1.493624194515153e−05 | ≤5e−5 | PASS |
| M5a decision parity | 835/835 | 100% | PASS |
| Vessels vượt tolerance | 0 | 0 | PASS |
| Severe QC | 0 | 0 | PASS |
| Semantic parity | Exact | Exact | PASS |

50.100 coordinate values; mean absolute difference 2.143955438867671e−06, median 1.3010576367378235e−06, P95 7.197260856628418e−06, P99 1.163043081760408e−05 nm. Score mean difference 9.692403043924308e−07. M5a threshold 0.420 và CV threshold 0.435 dùng `>=` không epsilon; CV reference decision consistency exact. Không case nào trong 5e−5 của operating points. CPU/CUDA M5a gần nhất `VAL_REAL_0163`, margin lần lượt −0.0011014950235126997 và −0.0011023714893276249. Điều này không bảo đảm decision parity tại runtime tương lai.

## 20–25. Tổng hợp và bàn giao

D1 CV/M5a PASS; D2 PASS; D3 GROUPED_CV_INFEASIBLE; D4 D4_EVIDENCE_LIMITED; D5 PASS. `BATCH03_EXECUTION_ACCEPTANCE=PASS`, `STEP03_ANALYSIS_COMPLETE=YES`, `READY_FOR_STEP04_REVIEW=YES_WITH_LIMITATIONS`, phụ thuộc Trung review các limitation; không tự lock. `MODEL_STATUS=CANDIDATE`; có thể đề xuất CALIBRATED_CANDIDATE, chưa chuyển state. Không Test benchmark, production approval hay T15.

Run `s4_t14_batch03_20261125T033810Z` nằm ngoài Git; 15/15 output checksums và 8 source hashes đã được verify độc lập. Manifest và checksums bao gồm group assignment, 5.000-draw plan, L1/L2 attempts/summaries, gate failure evidence, S1/S2/S3, D5 evidence và final evaluation. CPU/CUDA forecasts và scores được giữ tại device run directories có checksums; manifest tham chiếu. Checksum không phải chữ ký. Q1 guard chỉ cho phép Test raw-byte hashing, không deserialize Test; guard không bao quát tổng quát native/subprocess I/O. Clean environment chưa rebuild, V1 baseline review required; không coi Validation là evaluation độc lập.

Targeted tests Batch 03: 6 passed; full regression: 511 passed, 0 failed, 0 skipped, 0 deselected, một StarletteDeprecationWarning, 74.54 giây. Lệnh `python -m pytest -p scripts.q1_test_access_guard tests/unit tests/integration backend/tests -q` chạy ngoài sandbox vì backend TestClient từng treo trong sandbox. Q1 guard: 42 Test hash opens, 0 blocked deserialization, 0 blocked other open. Không cộng targeted tests vào full suite.

Không commit/push. Dừng trước STEP_04 để Trung review.
