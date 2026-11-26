# S4 T14 — Calibration protocol đặc tả

## Phạm vi, provenance và precedence

D1–D7 được Trung duyệt cho offline prototype/T15 benchmark; model vẫn CANDIDATE. Dataset `final_dataset_1.0`, Validation 835 encounter/1.670 tàu, 425 positive/410 negative; dataset checksum manifest `21f6bde168631928e98b6273aaab4e168bfb6eb755599a1fbc1cb8c364611441`. Checkpoint T10 epoch 1 SHA `e01a19e913d14a068c6c82a1c2a52a8be2aadd2f44e3ad5d8770d7f69a1fc7bc`, X scaler `a538be921104ed1bb2fa495c0c3f527c0385fd6c737aa69afda81ba1962d452a`, residual scaler `96b062fab9a5d4e27c9b1cc32a649e44e98d29648c7dcc3b7f482eba3d50358f`; architecture 15.390 tham số. Verify hash trước nạp. Không train/refit.

`s4_calibration_protocol.yaml` biểu diễn D1–D7 mới cho T14, không sửa `risk_config.yaml` hoặc Contract V1. **P1 supersedes D1 ban đầu:** tie-break cuối threshold thấp hơn, nhất quán `contracts/model_design.md` và `configs/risk_config.yaml`; Contract và risk_config không đổi. P1 vẫn duy trì các gates mới D1 (Real FPR 0.12, close recall 0.95), khác các gates tham chiếu cũ trong risk_config, là protocol T14 riêng, không thay config cũ. `integration_contract.md` quy định `score >= threshold`, calibrated threshold theo active model; không ghi tie-break. V1 comparator thiếu được D2 cho phép không chặn calibration CV/M5a, nhưng model-design cũ yêu cầu baseline mới hoặc quyết định protocol trước final selection; cần review quan hệ hai nguồn trước lock.

## Risk score và mapping

V4 reference bên ngoài repository `MODEL_CANDIDATE_PACKAGE/inference/risk_pipeline.py`, SHA `8e33effb06d7f2e1fe855b1cb067fb2d27eb3aba9498e2af30be1b387534be7e`, được hash pin; đóng gói/dependencies cần review. Current CPA B−A, vận tốc B−A, TCPA raw/clipped nội bộ 0 khi norm²≤1e−9 kn²; API V1 biểu diễn TCPA null kèm status. Predicted CPA là minimum separation future +1…+15, không gồm anchor. Current/Predicted dùng midpoint 0.65 nm, scale 0.16/0.14 nm, time discount `1−0.25*t/15`, exponential clamp ±100. Rule là proxy history, không phán quyết COLREG. `CC-DRI=0.68×Predicted+0.12×Current+0.20×Rule`, không phải xác suất va chạm. Cả hai model cùng encounter, history, anchor, A/B index, labels, scoring, projection/QC; chỉ khác forecast và threshold riêng. Không coi V4 là production runtime.

## Metrics và grid D1

Một dự đoán dương khi `score >= threshold`. TP/FN trên positive, FP/TN trên negative; recall `TP/(TP+FN)` overall; Real FPR `FP_real/(FP_real+TN_real)` chỉ Real AIS negative; Synthetic recall `TP_synthetic/(TP_synthetic+FN_synthetic)` chỉ Synthetic positive; precision `TP/(TP+FP)`; F1 `2TP/(2TP+FP+FN)`. Close-positive recall là TP/(TP+FN) trong subgroup dưới đây. Denominator 0, AUC thiếu một lớp hoặc thành phần không có căn cứ → NA; không tự cho 0 hay PASS. Support tối thiểu theo P3 được quy định trong phụ lục; mathematical support xét riêng. Tỷ lệ các gate là giá trị thập phân, D2 ±0.01 là **điểm tỷ lệ tuyệt đối** (1 điểm phần trăm), không phải thay đổi tương đối 1%.

Severe QC theo T06/T07: bất kỳ tốc độ >50 kn, scalar speed change >3 kn/phút, hoặc turn >30°/phút khi cả hai tốc độ ≥3 kn; tolerance 1e−9, các cặp forecast liên tiếp, anchor→bước đầu chỉ diagnostic. Count theo vessel; CV/M5a đều 0. ADE là trung bình norm lỗi EN 15 bước và các vessel; FDE trung bình norm lỗi bước 15 theo vessel. So sánh cùng vessel/encounter, ratio 1.10 = tăng tương đối tối đa 10%, không phải +0.10 nm. Nếu denominator ratio bằng 0 thì NA/review, không tự pass.

Grid chính xác `i/200`, i nguyên 0…200 inclusive (201). Với từng model: đủ tất cả recall≥0.90, Real FPR≤0.12, Synthetic recall≥0.90, close-positive recall≥0.95, severe=0; chọn max F1, tie Real FPR thấp → recall cao → threshold thấp. P4 dùng integer counts và Fraction chính xác; không thêm epsilon. Không có nghiệm: `NO_FEASIBLE_THRESHOLD`, số nghiệm 0, báo gate vi phạm, operating points và Pareto, không nới gate. Threshold diagnostic 0.435/0.420 không phải threshold được calibration.

Close-positive: encounter Synthetic AIS positive, **minimum haversine** giữa hai vị trí ground truth ở 15 mốc future +1…+15 **<0.1 nm**, strict; script S3 dùng `6880.13*asin(sqrt(clip(h,0,1)))` nm. V1 config và S3 nhất quán về định nghĩa. Outcome future được dùng sau scoring cố định để xác định subgroup và, theo D1 mới, kiểm gate threshold; không vào model hoặc Risk Score. S3 diagnostic cũ chỉ dùng subgroup hậu kiểm, không dùng làm threshold gate — không nhầm hai protocol.

## D2 comparison và V1

M5a phải pass D1; so CV các hiệu M5a−CV: recall≥−0.01, Real FPR≤+0.01, F1≥−0.01; overall và Real ADE≤1.10×CV; severe=0. Kiểm từng encounter close-positive: `FN_M5a \ FN_CV` phải rỗng; đồng thời báo số FN mỗi model, ID bỏ sót thêm và ID M5a phát hiện nhưng CV bỏ sót. CV infeasible → `D2_CONDITIONAL`, không suy ra pass hoặc thất bại M5a; metric thiếu → `D2_BLOCKED`. Không trình bày đây là statistical non-inferiority. V1 nếu artifact/code/provenance so sánh được thì đánh giá tương thích; metric cũ chỉ historical; không có → `V1_BASELINE_UNAVAILABLE`, không tự dựng, không chặn calibration CV/M5a nhưng phải review trước lock.

## D3 và D4

Main 835 Validation → `IN_SAMPLE_CALIBRATION`; công bố selection bias checkpoint, threshold, protocol và reuse. Grouped cross-fit exploratory dùng group khóa nguyên vẹn, cùng fold CV/M5a, fit threshold phía calibration và evaluate nhóm held-out; trước tiên kiểm source/label/close-positive support mỗi phía. Không chọn fold theo metric M5a; P2 thử K=[5,4,3,2], seed 20261124, largest-first, bounded deterministic search; thiếu khả thi → `GROUPED_CV_INFEASIBLE`, không tách group. Cross-fit không là independent evaluation.

Bootstrap L1 paired 5.000, seed 20261124, group là sampling unit, giữ multiplicity và cùng sample hai model, 95% percentile, delta M5a−CV. Threshold D1 cố định. Báo paired CI AUC, **Average Precision** (khác PR area hình thang), F1, recall, Real FPR, ADE/FDE, close-positive recall; báo aggregation (encounter cho risk/subgroup, vessel cho ADE/FDE), denominators và số/tỷ lệ NA. L2 chọn lại threshold từng model trong mỗi bootstrap, báo phân bố, feasible/infeasible, D2 stability và no-solution rate; đây không phải out-of-sample. L3 giữ threshold D1, báo S1 tất cả 835, S2 bỏ group lớn còn 279, S3 chỉ group lớn 556; source/label/subgroup counts và metrics hợp lệ, không chọn lại threshold. 260 group với group 556; P5 yêu cầu ≥4750/5000 mẫu đạt support P3 cho từng metric và metadata không hợp lệ phải dừng grouping/bootstrap; công bố hạn chế, không thay NA bằng 0 hoặc loại để làm đẹp CI. D4 status tách analysis pass/evidence limited/partial/blocked; không yêu cầu CI dương, CI chứa 0 không chứng minh tương đương.

## D5 parity

CPU/GPU cùng checkpoint/scaler/config/input: max absolute **coordinate** difference≤5e−5 nm, ADE/FDE aggregate absolute diff≤1e−6 nm, 0 vessel vượt, max absolute risk-score diff≤5e−5, decision parity 100% Validation tại threshold T14. Shape/A-B/timestamps, validation/error và QC classification khớp; severe=0 cả hai, kiểm case gần threshold. Mismatch → `RISK_DECISION_PARITY_REVIEW_REQUIRED`; không đổi threshold, rounding hoặc epsilon để ép pass. auto ưu tiên CUDA hoạt động rồi CPU; cuda bắt buộc CUDA, thiếu CUDA không tự CV fallback; artifact failure fail-closed. Trajectory tolerance đã duyệt offline; chưa chứng nhận runtime, risk parity phải chạy mới trong STEP_03.

## D6 state/lock và D7 Test

`CANDIDATE` → sau calibration có thể là `CALIBRATED_CANDIDATE`; chỉ sau D1 PASS, D2 PASS, D3 completed hoặc giới hạn được nêu, D4 analysis và giới hạn được chấp thuận, D5 PASS, D7 approved, integrity/regression/Contract PASS và Trung duyệt package cuối mới thiết lập `CONDITIONAL_TECHNICAL_LOCK`. `LOCK_REJECTED` khi review từ chối. Không auto transition; conditional/V1 unavailable phải đưa review. Package gồm checkpoint, architecture, scaler, schema, projection, risk reference, hai threshold nếu CV feasible, QC/fallback V1, D5, provenance, D1–D7, Git/source, version và SHA-256 manifest. Không production approval/alert.

Tier 1 T15 Test 1.320 (Yang 720, Real 300, Synthetic 300) là `REUSED_DEVELOPMENT_BENCHMARK`: chỉ mở sau T14 hoàn thành, Trung duyệt conditional lock, manifest/version verified, protocol T15 fixed. Giữ checkpoint/scalers/risk/projection/QC/threshold/metric cố định, áp D1/D2 với threshold cố định; không reselect, train, recalibrate hay model selection bằng Test. Báo ADE/FDE, AUC, AP, precision, recall, F1, FPR, confusion, close-positive, severe, latency CPU/GPU, EASY/MEDIUM/HARD nếu có; thiếu metric bắt buộc → NA/PARTIAL/INCONCLUSIVE, không tự PASS. Bug fix cần version mới và nhật ký mọi benchmark lại, không coi là independent.

Tier 2 trước production: dataset version mới độc lập, không trùng encounter/parent/group với development, khác thời gian hoặc vùng phù hợp, AIS thật có positive/negative, nhãn tin cậy ưu tiên expert, package/protocol lock trước mở; không sửa `final_dataset_1.0`.

## Failure, reproducibility và tham số mở

Sai checksum, thiếu metadata bắt buộc, dữ liệu sai/không nhân quả → fail closed, không CV fallback; chỉ lỗi kỹ thuật model trên input hợp lệ/in-scope mới xét CV theo V1, CV cần calibration riêng để có official decision. Không threshold/decision production nếu chưa calibrated. Manifest package ghi hash dataset, checkpoint, scaler, risk reference, config, code/Git, device, seed, split/index/group mapping, versions và mọi hạn chế; hash kiểm trước khi sử dụng.

P1–P7 đã xác định K, support, exact tie, bootstrap tối thiểu, dependency integrity và phương án P6/P7. Cần review phần implementation chưa hoàn tất, đặc biệt integrity quan hệ parent/source/MMSI, mọi P3 metrics và parity P6. Không dùng Validation score để lựa chọn các tham số còn thiếu. P1 giải quyết tie-break cũ theo quyết định mới; readiness còn phụ thuộc bằng chứng implementation và regression.

## Phụ lục P1–P7: hiệu lực và thực thi

P1 giữ tie-break thấp, thay thế tie cao trong D1 ban đầu. P2 thứ tự group giảm kích thước, hòa bằng SHA256(seed:attempt:group ID) rồi group ID; với mỗi K 5,4,3,2 thử 32 attempt, greedy fold tối thiểu tổng bình phương load đã chuẩn hóa theo encounter/positive/negative/Real-negative/Synthetic-positive/close/Yang, hòa fold index thấp; kiểm cả held-out và complement theo P3. K đầu tiên tìm được là lớn nhất trong phạm vi search. Tổng support <K lần minimum chứng minh bất khả thi cấu trúc; không tìm thấy trong search hữu hạn chỉ là search limitation. Không tính folds trên Validation trong bước này.

P3: recall positive≥30; overall negative/Real negative≥30; Synthetic positive≥30; close≥10; precision predicted-positive≥20; F1/AUC/AP positive≥30 và negative≥30; ADE/FDE overall/source≥30 encounter; Yang≥30 mỗi fold. LOW_SUPPORT báo giá trị và không PASS; NA không thay 0.

P5: L1 all-defined CI riêng support-qualified CI; đủ ≥4750/5000 mỗi metric cho support-qualified, không resample bù; L2 feasible rate chia 5000 không thêm gate ≥95%, threshold distribution chỉ feasible; L3 giữ thresholds. Integrity đầy đủ yêu cầu coverage, uniqueness, hash/version, group, parent/source/MMSI và reproducible construction; primitives hiện kiểm subset, không dùng làm chứng cứ hoàn tất.

## Addendum C02 closure

D2 sử dụng Real AIS FPR riêng; không dùng FPR overall thay thế. Count-gates PASS đơn lẻ không được diễn giải D2_PASS khi thiếu D1, ADE, close-positive theo encounter ID hoặc severe QC. Exact ratios, support và fixture được ghi trong matrix traceability.

## Q1–Q4 — phạm vi hiệu lực

Q1 cho phép hash bytes Test và Validation inference trong regression T11 hiện có, không deserialize Test hoặc chọn threshold. Q2: dependency internal consistency và partition reproduction PASS; lineage và independent upstream provenance PARTIAL, MMSI ownership NOT_VERIFIED; Trung chấp thuận grouping có điều kiện cho D3/D4 exploratory offline, không phê duyệt production provenance.

Q3 implementation `src/protocol/clustered_bootstrap.py`: unique group IDs sort theo UTF-8 bytes; `numpy.random.default_rng(seed=20261124)` PCG64; mỗi attempt rút G group có hoàn lại, giữ thứ tự/multiplicity; một index plan dùng chung CV/M5a. L1 dùng k cố định; L2 chọn lại k riêng, exact D1 và D2 sử dụng Real AIS FPR; output tách CV/M5a feasible, both feasible, D2 counts, sample support và execution error. Không retry/bù. 5.000 và seed 20261124 là mặc định; repetition/seed khác hoặc explicit plan chỉ được gọi với `fixture_mode=True`, chỉ cho synthetic tests. CI all-defined và support-qualified khác nhau; qualified chỉ công bố nếu 5.000 attempt và ≥4.750 valid paired samples, không có execution error. Synthetic override không cho official qualified CI. Không có gate feasible rate 95%.

Q4: offline package tham chiếu được review với observed environment/pip check/portable execution và fixture parity; clean-environment rebuild vẫn NOT_VERIFIED và bắt buộc trước integration handoff; raw V4 không phải trusted API. Full Validation original/package parity là gate đầu STEP_03, chưa thực hiện trong STEP_02.
