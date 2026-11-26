# S4 T14 STEP 03 — Batch 02: D1 và D2

## 1–4. Kết quả, baseline và dữ liệu

Batch 02 sử dụng parent `s4_t14_batch01_20261125T025749Z_fbf7f18e`; reuse PASS, output checksums 8/8, dataset 93/93 và model artifact 12/12 PASS. HEAD `4457fc2d4f485d2da832b039e8edc1cdf5837551`; Contract V1 và risk config không thay đổi. Semantic protocol SHA-256 `23d427ea6416104efbc9e988aaaa6c774118a517aea528b1ecb0c8350de4bf0b`; raw SHA được ghi riêng trong run manifest. Source/config và forecast pairing được xác thực bằng verifier Batch 01. Test bytes chỉ hash integrity, không deserialize Test hay chạy Test inference; Q1 guard trong process ghi 14 hash opens, không có prohibited access. Guard không bao quát tổng quát native/subprocess I/O.

Validation có 835 encounters: Yang Lei 240 (125 positive/115 negative), Real AIS 295 negative, Synthetic AIS 300 positive; tổng 425 positive, 410 negative, 60 close-positive. Cùng identity, labels, source, group, A/B, anchor, history và projection cho cả hai model; 260 groups, lớn nhất 556. Không bỏ mẫu. Score CC-DRI là risk score, không phải calibrated collision probability.

## 5–9. D1: 402 evaluations và lựa chọn

Mỗi model đánh giá đủ 201 thresholds `k/200`, comparator `>=`, không epsilon. Count-derived gates và tie-break dùng Fraction chính xác; thứ tự chọn: F1 lớn nhất, Real AIS FPR nhỏ nhất, overall recall lớn nhất, threshold nhỏ nhất. Kiểm tra đảo thứ tự candidates cho cùng kết quả. CV 23 feasible, chọn k=87; M5a 25 feasible, chọn k=84. Hai thresholds là calibration candidates trong artifact, không ghi risk config hoặc tự promote.

| Metric | CV | M5a | Required | CV | M5a |
| --- | ---: | ---: | --- | --- | --- |
| Selected threshold | 0.435 | 0.420 | Grid k/200 | PASS | PASS |
| Feasible candidates | 23 | 25 | ≥1 | PASS | PASS |
| Overall Recall | 403/425 = 94.824% | 406/425 = 95.529% | ≥90% | PASS | PASS |
| Real AIS FPR | 31/295 = 10.508% | 30/295 = 10.169% | ≤12% | PASS | PASS |
| Synthetic Recall | 281/300 = 93.667% | 283/300 = 94.333% | ≥90% | PASS | PASS |
| Close-positive Recall | 58/60 = 96.667% | 58/60 = 96.667% | ≥95% | PASS | PASS |
| Severe QC | 0 | 0 | 0 | PASS | PASS |

Cả hai D1_PASS; minimum integer boundaries quan sát là 383/425, tối đa 35/295, 270/300, 57/60. P3 support hợp lệ cho objective và mọi mandatory gate. Danh sách mọi candidate, counts, exact fractions, support, gate và feasibility nằm trong hai grid artifacts.

## 10–12. Performance và quỹ đạo

| Metric | CV | M5a | Delta M5a−CV |
| --- | ---: | ---: | ---: |
| ROC-AUC | 0.953650 | 0.954006 | +0.000356 |
| Average Precision | 0.948910 | 0.950511 | +0.001601 |
| Precision | 0.877996 | 0.882609 | +0.004613 |
| Recall | 0.948235 | 0.955294 | +0.007059 |
| F1 | 0.911765 | 0.917514 | +0.005749 |
| Overall FPR | 0.136585 | 0.131707 | −0.004878 |
| Real AIS FPR | 0.105085 | 0.101695 | −0.003390 |
| Synthetic Recall | 0.936667 | 0.943333 | +0.006667 |
| Close-positive Recall | 0.966667 | 0.966667 | 0 |
| Overall ADE, nm | 0.136291 | 0.147803 | +0.011512 |
| Overall FDE, nm | 0.297256 | 0.304910 | +0.007654 |
| Real AIS ADE, nm | 0.186414 | 0.196332 | +0.009918 |
| Real AIS FDE, nm | 0.413645 | 0.419442 | +0.005797 |
| TP/FP/TN/FN | 403/56/354/22 | 406/54/356/19 | — |

ROC-AUC và Average Precision dùng sklearn; AP không phải trapezoidal PR-AUC. Yang Lei ROC-AUC CV/M5a 0.951235/0.956243, AP 0.948142/0.954064; recall 122/125 và 123/125, FPR 25/115 và 24/115. Real AIS không có positive: AUC/AP NA. Synthetic chỉ có positive: AUC NA; AP toán học 1 nhưng LOW_SUPPORT theo P3, không phải bằng chứng phân biệt hai lớp. Các source/subgroup counts, support, ADE/FDE và precision đầy đủ nằm trong performance artifact. Aggregation trajectory float64, nautical miles, mean hai vessel/encounter.

## 13–18. D2 và phân tích lỗi

| Gate | Observed | Required | Status |
| --- | --- | --- | --- |
| M5a D1 | D1_PASS | PASS | PASS |
| Recall delta | +3/425 = +0.007059 | ≥−0.01 | PASS |
| Real AIS FPR delta | −1/295 = −0.003390 | ≤+0.01 | PASS |
| F1 delta | +173/30090 = +0.005749 | ≥−0.01 | PASS |
| Overall ADE ratio | 1.084467 | ≤1.10 | PASS |
| Real AIS ADE ratio | 1.053204 | ≤1.10 | PASS |
| New close-positive misses | 0 | 0 | PASS |
| Severe QC | 0 | 0 | PASS |

D2_PASS là engineering acceptance, không phải kiểm định non-inferiority thống kê. Real AIS FPR dùng 295 negative Real AIS, không dùng denominator 410 của overall FPR. Cả hai model bỏ sót `VAL_SYN_0171`, `VAL_SYN_0270`; không có close-positive mới bị M5a bỏ sót.

Positive pairing: cả hai phát hiện 401, cả hai bỏ sót 17, M5a phát hiện khi CV bỏ sót 5, M5a bỏ sót khi CV phát hiện 2. Negative pairing: cả hai bác bỏ đúng 350, cả hai false alarm 50, M5a loại false alarm của CV 6, M5a tạo false alarm mới 4. Với Real AIS: CV 31 FP, M5a 30 FP, chung 28, M5a loại 3 và thêm 2. Encounter IDs, source counts và score deltas có trong error analysis; không suy diễn nguyên nhân hành vi tàu.

Không có case nào nằm trong 5e−5 quanh threshold của mỗi model. Case gần nhất CV `VAL_SYN_0161` margin +0.0007895065506331456; M5a `VAL_REAL_0163` margin −0.0011023714893276249. Đây chỉ là descriptive sensitivity, không thay comparator hoặc thực hiện D5.

## 19–24. Giới hạn, artifacts và acceptance

Epoch 1 đã chọn trên Validation và threshold cũng chọn trên toàn bộ Validation: kết quả `IN_SAMPLE_CALIBRATION`, không phải independent evaluation hoặc production safety proof. Dependency lineage/provenance PARTIAL, grouping CONDITIONAL, MMSI ownership NOT_VERIFIED; không coi 835 encounters là độc lập. Clean environment NOT_VERIFIED; V1 baseline review required. D3/D4/D5 chưa chạy; không tự chuyển state/config hoặc lock. M5a có thể được đề xuất `CALIBRATED_CANDIDATE` sau review, status config vẫn CANDIDATE.

Run `s4_t14_batch02_20261125T031911Z_cb53e739` nằm ngoài Git tại `C:\Users\MSI\Documents\Codex\2026-11-20\files-pasted-by-the-user-sprint-2\s4_t14_batch02_runs\s4_t14_batch02_20261125T031911Z_cb53e739`. Manifest ghi parent SHA, input hashes, protocol, dataset, dependency, checkpoint/scalers, source/config và environment. 9 output checksums phải được kiểm tra trước reuse; `performance_metrics.json` là định dạng tương đương parquet. Manifest và checksums là integrity evidence, không phải chữ ký. Raw dataset/checkpoint/predictions không đưa vào Git.

Targeted tests: 14 passed. Full regression: 505 passed, 0 failed, 0 skipped, 0 deselected, 1 StarletteDeprecationWarning, 97.77 giây; chạy `python -m pytest -p scripts.q1_test_access_guard tests/unit tests/integration backend/tests -q` ngoài sandbox vì backend TestClient từng treo trong sandbox. Q1 guard ghi 42 hash opens, không có prohibited deserialization/other open. Targeted tests không cộng vào full regression. Independent output verification 9/9 và 27 source/config hashes PASS.

BATCH02_EXECUTION_ACCEPTANCE=PASS; MODEL_QUALITY_ACCEPTANCE=PASS theo D1/D2; READY_FOR_BATCH03=YES. Không tự chuyển Batch 03. Không commit/push.
