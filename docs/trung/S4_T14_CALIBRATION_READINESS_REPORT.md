# S4 T14 STEP 01 — Audit readiness cho calibration và model lock

## 1. Executive summary

**Kết luận: READY_FOR_PROTOCOL_REVIEW; chưa sẵn sàng chạy calibration chính thức hoặc model lock.** S3 artifact và inference ngoại tuyến có thể tái nạp; Risk Engine V4 dùng được như reference nghiên cứu, chưa có runtime production. Các quyết định về objective, so sánh CV, bias do tái sử dụng Validation, nhóm phụ thuộc, tolerance và phạm vi lock cần Trung xác nhận. Không có threshold chính thức hoặc alert production.

## 2. Git baseline

Worktree `trung-contract-v1-freeze`, branch `s3-t10-trung-full-training`, HEAD `4457fc2d4f485d2da832b039e8edc1cdf5837551`; branch remote `origin/s3-t10-trung-full-training` được `git ls-remote` xác nhận cùng SHA. Worktree sạch trước audit. Contract V1 `99bdb2649f5aec39d67a6f64645bce4f7fc49a3d` trong ancestry; `contracts/` không đổi so với baseline. Không tạo branch, commit, push hoặc merge trong audit. Kế hoạch nhóm Sprint 4/V4 được tìm trong workspace, repository và Desktop theo tên liên quan nhưng không thấy: **PLAN_NOT_AVAILABLE**; không khẳng định tài liệu không tồn tại ở nơi khác.

## 3. Traceability

| Yêu cầu T14 | Nguồn / bằng chứng | Trạng thái |
| --- | --- | --- |
| Calibration và threshold riêng model | `configs/risk_config.yaml`, `contracts/model_design.md`, `contracts/integration_contract.md` | Có protocol và gates tham chiếu; cần xác nhận áp dụng T14, threshold calibrated vẫn null |
| Risk 0.68/0.12/0.20, CPA, fallback | Contract V1 D-11/D-12, risk config, V4 reference | Công thức khớp; reference chưa có semantics/runtime production đầy đủ |
| Test không dùng chọn/calibration | risk config, model design | Bắt buộc; Test đã dùng trước đây và không phải holdout mới |
| M5a/CV và QC | T10, S3 diagnostic, T11 | Có bằng chứng offline; chưa chứng minh ưu thế M5a |
| T14 roadmap của nhóm | Tìm tài liệu có sẵn | PLAN_NOT_AVAILABLE; lộ trình dưới đây là đề xuất |

## 4. Dataset readiness

`final_dataset_1.0` READY_AND_LOCKED, manifest checksum `21f6bde168631928e98b6273aaab4e168bfb6eb755599a1fbc1cb8c364611441`, 93/93 PASS. Chỉ load Validation: 835 encounter, 1.670 tàu. Yang Lei 240 (115 âm, 125 dương), Real AIS 295 (295 âm), Synthetic AIS 300 (300 dương). Labels và source được đối chiếu qua DatasetLoader/index. Source–label confounding ngăn diễn giải hiệu quả một cách độc lập với nguồn; không có AUC riêng có ý nghĩa cho Real/Synthetic đơn nhãn.

Diagnostic đã ghi 260 dependency groups; group lớn nhất 556/835 (66,59%), 271 MMSI Real khác nhau, 142 MMSI xuất hiện ở nhiều encounter, tối đa 9 encounter/MMSI; 300 parent link không thiếu, 300 parent ID, mỗi parent xuất hiện một encounter. Missing source metadata có thể che thêm phụ thuộc. Validation đã dùng nhiều lần để chọn epoch, khảo sát threshold và báo metrics; là bằng chứng phát triển, không phải đánh giá độc lập. 93 checksum có đọc byte file Test chỉ để toàn vẹn, **không load Test tensor, label hoặc prediction** trong audit.

## 5. Artifact readiness

Run `s3_t10_20261124_seed20261110_run01`: manifest ghim và 12/12 checksum PASS, epoch 1, seed 20261110; checkpoint `e01a19e913d14a068c6c82a1c2a52a8be2aadd2f44e3ad5d8770d7f69a1fc7bc`; input scaler `a538be921104ed1bb2fa495c0c3f527c0385fd6c737aa69afda81ba1962d452a`; residual scaler `96b062fab9a5d4e27c9b1cc32a649e44e98d29648c7dcc3b7f482eba3d50358f`. T11 loader đối chiếu config/checkpoint/scaler và nạp CPU PASS; strict architecture GRU 4→48, head 48→96→30, 15.390 tham số. Không có model lock, không train/refit. Cần quản lý phân phối artifact ngoài Git và tái kiểm hash trước mỗi lần sử dụng.

## 6. T11 inference readiness

Offline trusted Validation và fallback đã được S3 xác minh; runtime `predict` fail-closed, adapter T18 chưa có. Báo cáo final S3 ghi GPU replay so với T10 max 0, severe QC 0 trên 1.670 tàu; CPU–GPU max `3.3008088e-5 nm`, ADE diff `8.0644e-9 nm`, FDE diff `1.0514e-7 nm`. Các giá trị đạt tolerance **đề xuất** 5e-5/1e-6/1e-6 cho tập offline này; không có bằng chứng Trung phê duyệt tolerance chính thức và không chứng nhận runtime. Ngưỡng diagnostic cũ 1e-5 nm không đạt. Kết quả parity là bằng chứng S3, không chạy lại benchmark trong audit này.

## 7. Audit Risk Engine và khác biệt V4–Contract

Reference thực tế `MODEL_FINAL_VERIFICATION_V4/MODEL_CANDIDATE_PACKAGE/inference/risk_pipeline.py`, SHA-256 `8e33effb06d7f2e1fe855b1cb067fb2d27eb3aba9498e2af30be1b387534be7e`, khớp manifest S3. Các hàm `cpa`, `score`, `infer_roles`, `rule_component`, `calculate` tính Current CPA, predicted CPA, rule và CC-DRI; relative vector B−A, predicted minimum trên phút +1…+15, weights 0.68/0.12/0.20. T06 projection/QC áp bên ngoài reference; rule yêu cầu SOG/COG history gốc. `scripts/compare_s3_t10_risk.py` dùng adapter mapping/index và validate history riêng, thay vì mặc định `history_features` của V4 an toàn cho mọi thứ tự.

| Chủ đề | V4 nghiên cứu | Contract V1 / khoảng trống |
| --- | --- | --- |
| Near-zero CPA | Trả raw/clipped nội bộ 0 | API phải trả TCPA null kèm status, DCPA/score còn hợp lệ; cần adapter presentation |
| Mapping | `history_features` reshape, có nhánh Test | Offline phải dùng index; runtime phải kiểm identity/pair/session. Không gọi nhánh Test trong audit |
| Input/QC/availability | Hàm tính giả định input hợp lệ, assert hữu hạn; QC không nằm trọn trong `calculate` | Runtime phải fail-closed, xử lý missing components, QC, status và fallback theo V1 |
| Threshold/alert | Diagnostic dùng threshold chọn trên Validation | Chưa có calibrated threshold, API decision null; CV fallback cần calibration riêng |
| Rule | History proxy, không phải phán quyết COLREG | Cần history SOG/COG `[N,2,10,2]` đáng tin cậy và adapter causal |
| Replay/alert lifecycle | Không triển khai | Atomicity, idempotency và lifecycle là công việc runtime |

Không phát hiện sai trọng số trong reference; những khác biệt trên là phạm vi triển khai/biểu diễn và không cho phép tự sửa Contract. Không có bằng chứng Risk Engine production end-to-end đã triển khai.

## 8. Protocol calibration hiện có

`configs/risk_config.yaml` và `contracts/model_design.md` **đã ghi** Validation, grid 0…1 bước 0.005, recall ≥0.90, max F1, tie-break Real FPR thấp hơn → recall cao hơn → threshold thấp hơn; riêng threshold cho CV/M5a, không chọn bằng Test. Config cũng ghi gates: severe=0, AUC≥0.945, F1≥0.903, recall≥0.90, Synthetic recall≥0.93, Real FPR≤0.132, close-positive recall drop so CV≤0.02, Real ADE/FDE và Dmin MAE ratio so CV≤1.10, Real ADE so V1≤0.90. Đây là baseline đã được ghi trong repo, không phải tài liệu trống; chưa có bằng chứng nó được Trung tái phê duyệt là protocol chính thức cho T14 trên dữ liệu hiện tại. Gate V1 thiếu baseline mới có thể so sánh hoặc quyết định protocol rõ ràng. Close-positive trong config định nghĩa Synthetic có future minimum haversine <0.1 nm: future chỉ dùng nhãn đánh giá sau khi score cố định, không là input inference.

Diagnostic reference CV 0.435/M5a 0.420 là ngưỡng lịch sử/khám phá; config `calibrated_cv` và `calibrated_m5a` null, `not_calibrated`. `optimal_threshold` trong script S3 là code diagnostic, không chứng minh implementation calibration production hoặc phê duyệt T14. Audit này không chạy tối ưu threshold.

## 9. Bằng chứng M5a so với CV

| Metric Validation | CV | M5a |
| --- | ---: | ---: |
| Overall ADE nm | 0.136291 | 0.147803 |
| Real AIS ADE nm | 0.186414 | 0.196332 |
| ROC-AUC | 0.953650 | 0.954006 |
| F1 | 0.911765 | 0.917514 |
| Recall | 0.948235 | 0.955294 |
| Real AIS FPR | 0.105085 | 0.101695 |

M5a kém CV về ADE; Risk/Alert là `SMALL_OR_UNCERTAIN_BENEFIT`, không có bằng chứng độc lập đủ mạnh để khẳng định ưu thế tổng quát. F1 dùng threshold riêng chọn trên chính Validation, bị selection bias; bootstrap nhóm với threshold cố định cho ΔAUC CI 95% `[-0.001791,+0.007488]`, ΔF1 `[-0.005000,+0.018583]`, đều chứa 0. Bootstrap không bao gồm bất định selection và group rất lớn làm CI bất ổn. Close-positive 60 mẫu, cả hai recall 0.9667 theo threshold diagnostic; không coi là bằng chứng calibration/đảm bảo an toàn.

## 10. Tái sử dụng Validation và dependency

Validation dùng để chọn checkpoint epoch 1, diagnostic và threshold historical, do đó metric cùng tập không ước lượng khách quan hiệu quả deployment. Chia theo encounter ngẫu nhiên không giải quyết phụ thuộc group/MMSI. Nên xác định tập độc lập mới tách theo nguồn, thời gian, tàu và parent khi khả thi; nếu không, chỉ công bố exploratory/giới hạn, cân nhắc group-aware validation hoặc nested selection nhưng phải đánh giá tính khả thi do group 556/835. Không gọi Test là holdout độc lập vì đã tham gia nghiên cứu trước.

## 11. Ma trận model lock

| Nhóm điều kiện | Trạng thái | Bằng chứng / blocker |
| --- | --- | --- |
| Dataset integrity | PASS | 93/93; giới hạn provenance và confounding |
| Artifact integrity | PASS | 12/12, checkpoint/scaler hash; lưu ngoài Git |
| Model reproducibility | OFFLINE PASS CÓ GIỚI HẠN | T10 GPU exact cùng môi trường; không bảo đảm thiết bị khác |
| Inference correctness | OFFLINE PASS | T11 835 encounter, severe=0; runtime chưa có |
| CPU/GPU parity | CANDIDATE PASS | Đạt ngưỡng đề xuất offline; D5 chưa phê duyệt |
| Risk Engine compatibility | PARTIAL | V4 khớp công thức nhưng thiếu production semantics/adapter/QC |
| Calibration criteria | DECISION_REQUIRED | Config đã ghi protocol/gates; cần chốt phạm vi T14 và V1 comparator |
| False alarm control | DECISION_REQUIRED | Real chỉ âm; max FPR 0.132 là gate cấu hình, tính đại diện/chấp thuận chưa xác nhận |
| High-risk detection | PARTIAL | Synthetic recall/close-positive diagnostic có kết quả; không đại diện đủ nguy cơ thực |
| Dependency robustness | BLOCKED | 556/835 cùng group; CI không bao gồm selection |
| Independent evaluation | NOT AVAILABLE | Validation tái sử dụng, Test cũng từng dùng; chưa có dữ liệu mới |
| Runtime trust boundary | NOT IMPLEMENTED | T18/G11/session/source/feature adapter cần triển khai |
| Contract V1 compliance | SPEC PASS / RUNTIME UNVERIFIED | Contract không đổi; chưa có end-to-end production |

Technical checkpoint/config lock có thể **đề xuất** sau quyết định D5/D6 và xác nhận dependency/artifact; threshold lock phụ thuộc protocol/calibration; production approval còn cần đánh giá độc lập, runtime T18, risk/alert contract và bằng chứng vận hành. Không suy diễn một loại lock thành loại khác.

## 12. Decision register — chờ Trung phê duyệt

**D1 — Objective/gates.** Evidence: baseline recall≥90%, max F1 và Real FPR≤0.132 có trong config. Phương án A giữ nguyên để so lịch sử, dễ tái lập nhưng FPR ràng buộc chỉ tại gate và có thể chưa phù hợp sản phẩm; B chọn FPR constraint chặt hơn với recall tối thiểu, kiểm soát cảnh báo tốt hơn nhưng có thể bỏ sót nguy hiểm; C nêu utility/cost và nhóm nguy cơ nhưng cần dữ liệu chi phí. Đề xuất review A làm baseline và xác định ràng buộc FPR/close-positive trước chạy, không tự thay gate. Trung duyệt objective, ngưỡng, tie-break, cách xử lý không có nghiệm và provenance.

**D2 — CV vs M5a.** Evidence M5a ADE kém CV, risk nhỏ/không chắc; config cho tỷ số ADE/FDE/Dmin MAE so CV≤1.10, không mặc định phải thắng CV. A đạt gates tối thiểu thì ứng viên hợp lệ nhưng không chứng minh lợi ích; B yêu cầu ưu thế CV rõ theo metric và bất định, bảo thủ nhưng có thể NO-GO; C giữ cả hai candidate cho đối chiếu không chọn model. Đề xuất C cho đến khi xác định utility và independent evidence; Trung chốt gate và vai trò từng model.

**D3 — Selection bias.** A dùng cùng Validation minh bạch là exploratory, dễ làm nhưng lạc quan; B nested/group-aware threshold selection + đánh giá ngoài fold, giảm bias nhưng phụ thuộc group lớn; C validation mới tách biệt, mạnh hơn nhưng tốn dữ liệu. Đề xuất C nếu có, kết hợp B khi khả thi, nếu không chỉ kết luận hạn chế; Trung duyệt split, report và tiêu chí không đủ dữ liệu.

**D4 — Dependency.** A bootstrap theo encounter đơn giản nhưng không hợp lệ khi phụ thuộc; B resample group nguyên vẹn phản ánh kết nối nhưng group lớn chi phối và có thể thiếu lớp; C dữ liệu/nhóm độc lập mới cho bằng chứng mạnh hơn nhưng cần thu thập. Đề xuất B như sensitivity có kiểm feasibility, báo group size và CI không ổn định, ưu tiên C; không hứa CI hợp lệ nếu không đủ group. Trung duyệt đơn vị phân tích và quy tắc undefined.

**D5 — Parity.** A chấp nhận offline 5e-5 vị trí, 1e-6 ADE/FDE cho môi trường/Validation đã kiểm; B giữ 1e-5 cũ, hiện FAIL với 260 vessel; C yêu cầu kiểm thêm sensitivity/thiết bị trước chọn. Đề xuất A chỉ cho offline có version thiết bị và kiểm thay đổi quyết định gần threshold, không chứng nhận production. Trung phê duyệt phạm vi/tolerance.

**D6 — Scope lock.** A khóa hash checkpoint/config/scaler kỹ thuật trước, dễ truy vết nhưng không phê duyệt alert; B đồng thời khóa threshold sau calibration, cần bằng chứng và quyết định; C production lock sau runtime/đánh giá độc lập, chậm hơn nhưng phù hợp triển khai. Đề xuất A chỉ khi Trung duyệt, B/C tách cổng; xác định rollback, version và tiêu chí NO-GO, kể cả comparator V1 thiếu.

**D7 — Test benchmark.** Test 1.320 đã dùng V1/V3/V4: A mô tả là benchmark phát triển tái sử dụng, không suy ra hiệu quả holdout; B tạo external holdout mới có phân tách nguồn/thời gian/tàu để đánh giá độc lập, tốn thu thập; C hoãn kết luận đến khi có B. Đề xuất A+C, ưu tiên B. Trung duyệt nội dung T15 và bất kỳ quyền dùng Test sau lock; audit không load Test.

## 13. Đề xuất lộ trình T14

| Bước | Input / dependencies | Output | Acceptance | Blocker |
| --- | --- | --- | --- | --- |
| 01 Audit | Contract, S3 artifacts, dataset metadata | Báo cáo này | Hash, traceability, register | PLAN_NOT_AVAILABLE, các D1–D7 |
| 02 Protocol finalization | D1–D7, V1 comparator, nhóm/nguồn độc lập | Protocol version hóa để Trung duyệt | Objective, gates, split, CI, failure, lock scope và no-Test rõ | Chưa có phê duyệt và nguồn độc lập |
| 03 Calibration implementation | Protocol đã duyệt, artifact locked, data cho phép | Code/test và candidate threshold provenance | Chạy đúng split, no Test, CV/M5a riêng, invalid fail-closed | Chưa duyệt protocol; Risk adapter cần kiểm chứng |
| 04 Model lock review | Metrics sau 03, artifact/hash, baseline, CI và limits | GO/NO-GO theo từng scope | Gates và evidence được duyệt, rủi ro tồn dư ghi rõ | Independent evaluation/runtime tùy phạm vi lock |

Đây không phải phân rã chính thức của kế hoạch nhóm. Không thực hiện bước 02–04 trong audit.

## 14–15. Blockers và khuyến nghị

`CALIBRATION_READY = NO`; `TECHNICAL_LOCK_READY = CONDITIONAL`; `PRODUCTION_APPROVAL_READY = NO`. Trung cần chốt D1–D7, đặc biệt baseline V1 tương đương, selection bias/dependency và objective; tìm kế hoạch Sprint 4 nhóm, bảo đảm nguồn artifact/reference V4; T18 còn phụ thuộc runtime. Khuyến nghị duy trì M5a candidate và CV baseline, không phát alert, không calibration cho đến khi protocol được duyệt.

MODEL_STATUS = CANDIDATE
MODEL_LOCK = NO
PRODUCTION_ALERT = NO
CALIBRATION_PERFORMED = NO
TEST_BENCHMARK_PERFORMED = NO

## 16. Appendix — nguồn đã kiểm chứng

`contracts/integration_contract.md`, `docs/contracts/CONTRACT_V1_DECISION_RECORD.md`, `contracts/model_design.md`, `configs/model_config.yaml`, `configs/projection_config.yaml`, `configs/risk_config.yaml`; các báo cáo T10, epoch1, post-T10 risk, T11, T18 handoff và final audit trong `docs/trung/`; `src/models/`, `src/training/`, `src/inference/`, `src/data/dataset_loader.py`; `scripts/compare_s3_t10_risk.py`; artifact manifest/checksums T10, `dependency_audit.json`, `comparison_manifest.json`, `close_positive_metrics.json`, CSV metric S3; V4 risk reference hash nêu trên. Số liệu từ diagnostic là bằng chứng lịch sử, không được tính lại threshold trong STEP_01.
