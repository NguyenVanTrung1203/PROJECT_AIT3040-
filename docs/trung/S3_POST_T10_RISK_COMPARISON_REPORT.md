# So sánh Risk/Alert CV và M5a sau T10

## 1. Mục tiêu và kết luận

So sánh forecast CV và checkpoint M5a T10 trên cùng 835 encounter Validation, cùng CPA/CC-DRI reference, Rule, mapping A/B và QC. **Kết luận: `SMALL_OR_UNCERTAIN_BENEFIT`**. M5a có tăng nhỏ về AUC và F1 tại operating point riêng trên chính Validation, nhưng chênh lệch AUC/F1 có khoảng bootstrap nhóm chứa 0, lệ thuộc ngưỡng và dữ liệu có phụ thuộc mạnh. Đây không chứng minh lợi ích Risk/Alert tổng quát hay phê duyệt model production.

## 2. Baseline và toàn vẹn

Branch `s3-t10-trung-full-training`, HEAD T07 `f3096fd2d44471ce7bbf455932cd7c3d5634f692`; T06 và Contract V1 có trong ancestry. Các thay đổi T10/diagnostic chưa commit được giữ lại. Dataset `final_dataset_1.0`: checksum **93/93 PASS**; T10 artifact **12/12 hash PASS trước và sau**, manifest hash `5f0af2eb5a4e418026b775fa412e2fc8bbc803c7438123038a1c519e5a082eb2`. Checkpoint T10 epoch 1 SHA-256 `e01a19e913d14a068c6c82a1c2a52a8be2aadd2f44e3ad5d8770d7f69a1fc7bc`; scaler, config, predictions được đối chiếu cùng manifest. Không load checkpoint/scaler cũ, không refit hoặc train lại.

Chỉ nạp split Validation: 835 encounter, 1.670 tàu. Các file Test chỉ được đọc byte khi xác minh checksum 93/93; không nạp tensor/labels/predictions Test, không benchmark Test. Train không được load. Không sửa dataset, Contract V1, artifact T10 hoặc runtime; không commit/push.

## 3. Provenance forecast và Risk Engine

M5a dùng model epoch 1, scaler T10, anchor và projection T06; tái inference GPU khớp prediction đã lưu chính xác. CV dùng vận tốc anchor và `cv_displacement`, cùng projection/QC; diagnostic T10 trước xác nhận raw/projected khác tối đa `1,11e-16` nm. Mapping dùng `vessel_tensor_index`/`pairs`, không giả định thứ tự A/B. Cả hai có severe QC 0/1.670 tàu.

Repository chưa có Risk/Alert runtime production. Phép này **tái sử dụng trực tiếp** hàm `infer_roles`, `rule_component`, `calculate` của Risk Engine nghiên cứu V4 `MODEL_CANDIDATE_PACKAGE/inference/risk_pipeline.py`, hash `8e33effb06d7f2e1fe855b1cb067fb2d27eb3aba9498e2af30be1b387534be7e` khớp manifest V4; không viết engine thay thế. V4 hàm load Test và trọng số cũ không được gọi. Adapter chỉ đọc 10 history SOG/COG quan sát, đối chiếu timestamp/index và vận tốc EN; không dựa vào nhãn/source/future để tính score.

Công thức khớp `configs/risk_config.yaml`: current CPA theo r/v, ngưỡng `v·v≤1e-9`, TCPA clip 0–15; predicted CPA là khoảng cách nhỏ nhất +1…+15 phút; sigmoid midpoint 0,65 nm, scale 0,16/0,14 và hệ số thời gian; `CC-DRI=0,68×predicted+0,12×current+0,20×rule`. Rule là proxy theo history, không phải kết luận COLREGs pháp lý. Điểm CC-DRI không phải xác suất va chạm. Thiếu runtime production, lifecycle alert và live adapter nên chúng **chưa được kiểm chứng**.

## 4. Nhãn, score và sự phụ thuộc nguồn

Nhãn từ locked encounter index khớp `labels.npy`: tổng 425 positive/410 negative. Yang Lei 125 positive/115 negative; Real AIS 0/295; Synthetic AIS 300/0. Có source–label confounding. Không báo AUC, AP hoặc F1 riêng cho nguồn một nhãn; Real ưu tiên FPR, Synthetic ưu tiên recall.

Score median overall cho nhãn âm: CV 0,200146, M5a 0,200102; nhãn dương: CV 0,764138, M5a 0,754031. `score_distributions.csv` chứa n, mean, std và quantile theo nguồn/nhãn. ROC-AUC dùng cùng 835 encounter; PR-AUC ở đây là **average precision** theo stepwise precision-recall, không phải diện tích hình thang.

## 5. Threshold và metrics

Operating point chẩn đoán riêng mỗi phương pháp theo protocol đã duyệt: grid 0…1 bước 0,005; recall≥0,90; max F1; hòa chọn Real FPR thấp hơn, recall cao hơn, threshold thấp hơn. Kết quả là CV **0,435**, M5a **0,420**. Hai ngưỡng này trùng reference lịch sử nhưng vẫn **chỉ diagnostic**, không cập nhật config hay khóa alert. Chọn threshold và báo F1 trên cùng Validation tạo selection bias; không xem là hiệu năng ngoài mẫu.

| Metric | CV | M5a | M5a − CV |
|---|---:|---:|---:|
| Overall ADE (nm) | 0,136291 | 0,147803 | +0,011512 |
| Real AIS ADE (nm) | 0,186414 | 0,196332 | +0,009918 |
| ROC-AUC | 0,953650 | 0,954006 | +0,000356 |
| PR-AUC / average precision | 0,948910 | 0,950511 | +0,001601 |
| Precision | 0,877996 | 0,882609 | +0,004613 |
| Recall / high-risk-label recall | 0,948235 | 0,955294 | +0,007059 |
| F1 | 0,911765 | 0,917514 | +0,005749 |
| Real AIS FPR | 0,105085 | 0,101695 | -0,003390 |
| Synthetic AIS recall | 0,936667 | 0,943333 | +0,006667 |
| Close-positive recall¹ | 0,966667 | 0,966667 | 0 |
| FP / FN | 56 / 22 | 54 / 19 | -2 / -3 |
| Severe QC tàu | 0 | 0 | 0 |

¹ 60 Synthetic Validation positives có khoảng cách haversine future tối thiểu <0,1 nm theo config; mỗi phương pháp bỏ sót 2. Future chỉ dùng **sau khi đã cố định score/threshold** để định nghĩa subgroup đánh giá, không dùng cho scoring hay chọn threshold.

Tại ngưỡng chung **0,420**, F1 CV 0,909091, M5a 0,917514; tại **0,435**, F1 CV 0,911765, M5a 0,910125. Đổi ngưỡng chung làm đảo chiều chênh lệch F1. `operating_points.csv` và `threshold_sensitivity.csv` còn ghi ngưỡng tham khảo, recall mục tiêu 0,90/0,95/0,98 và Real FPR mục tiêu 0,10/0,15; các threshold chọn trên cùng tập chỉ là in-sample.

## 6. Paired encounter và source

Ở hai ngưỡng riêng: cả hai đúng **751**, cả hai sai **67**, M5a đúng/CV sai **11**, CV đúng/M5a sai **6**. Trong nhãn âm có 6 CV-positive→M5a-negative và 4 chiều ngược lại (FP giảm 2); trong nhãn dương có 5 CV-negative→M5a-positive và 2 chiều ngược lại (FN giảm 3). Đây là thay đổi dự đoán diagnostic, không phải alert production.

Real AIS: CV 31/295 FP, M5a 30/295 FP. Synthetic AIS: CV bỏ sót 19/300, M5a 17/300. Yang Lei: CV TP/TN/FP/FN = 122/90/25/3; M5a = 123/91/24/2. Toàn bộ ID, score, CPA dự báo, nhãn, source, nhóm và category có trong `risk_scores_by_encounter.csv`; các chuyển trạng thái chi tiết có trong `alert_transitions.csv`.

## 7. Bootstrap và robustness

Bootstrap cặp 2.000 lần, seed `20261124`, lấy mẫu **nguyên dependency_group_id** từ manifest khóa, cùng mẫu cho cả hai phương pháp. Threshold CV/M5a giữ cố định như đã chọn trên toàn bộ Validation; CI không phản ánh bất định do chọn threshold. Hiệu M5a−CV, percentile 95%:

| Đại lượng | CI 95% |
|---|---:|
| ROC-AUC | [-0,001791; +0,007488] |
| Average precision | [-0,001523; +0,010417] |
| F1 | [-0,005000; +0,018583] |
| Recall | [0; +0,020548] |
| Real AIS FPR | [-0,003601; 0] |
| Số FP | [-7; +3] |
| Số FN | [-8; 0] |

Cả 2.000 mẫu có metric xác định, nhưng có **260 nhóm**, trong đó nhóm lớn nhất chứa **556/835 encounter** (66,6%). Real AIS có 271 MMSI khác nhau, 142 MMSI xuất hiện trong nhiều encounter, tối đa 9 encounter/MMSI; metadata có 300 parent link không thiếu, mỗi parent xuất hiện một encounter. Một connected component lớn và khả năng thiếu metadata làm bootstrap bất ổn; CI số đếm còn dựa trên mẫu resample có tổng số encounter thay đổi. Không khẳng định statistical significance hay tổng quát hóa từ các khoảng này.

Spearman giữa hai risk score là 0,995327. Trong phạm vi ±0,005 quanh ngưỡng riêng có 5 encounter CV và 3 M5a; `near_threshold_cases.csv` lưu chi tiết. Làm tròn score tới 3–6 chữ số không đổi quyết định tại hai ngưỡng riêng. CPU–GPU forecast M5a lệch cực đại `3,3008e-5` nm, risk score lệch cực đại `1,4936e-5`; 0/835 quyết định đổi tại ngưỡng M5a 0,420 (và cũng 0 tại ngưỡng chung 0,435). Đây là kiểm tra giới hạn của checkpoint/tập/ngưỡng này, không phải chấp thuận parity CPU/GPU toàn hệ thống.

## 8. Đối chiếu nghiên cứu V4 cũ

Cùng Validation và dataset lock hash `036d9c0e3652e526613238b91151002cbca35615552eba687b588da01b0fe764`; cùng Risk Engine reference và protocol threshold. CV hiện tái tạo AUC 0,953650, F1 0,911765 và Recall 0,948235 theo số V4 làm tròn. M5a mới tái tạo F1 0,917514, Recall 0,955294 và Real FPR 0,101695; AUC mới 0,954005739 so với cũ 0,953994261, chênh khoảng `1,15e-5`. Dùng checkpoint T10 hash `e01a...`; checkpoint package V4 lịch sử có hash `d55d...`, không dùng để thay T10. File prediction Validation lịch sử hiện có khác forecast T10 tối đa `0,000568238` nm; hash file lịch sử chưa được xác thực bằng manifest được kiểm tra. Khác forecast là bằng chứng phù hợp với khác biệt nhỏ về AUC, nhưng nguyên nhân chi tiết của sai khác checkpoint/thiết bị chưa được chứng minh. Kết quả rất gần nhau trên **cùng Validation**, không phải xác nhận độc lập trên dữ liệu mới.

## 9. Hạn chế, quyết định và tài liệu

`BENEFIT_CLASSIFICATION: SMALL_OR_UNCERTAIN_BENEFIT`; `DECISION_APPROVED_BY_TRUNG: NO`. Đề xuất có thể tiếp tục T11 **kỹ thuật có điều kiện**, nhưng chưa chọn M5a làm model chính, chưa calibration T14 và không tự chuyển hệ thống sang CV. Trung cần quyết định vai trò model, policy tolerance CPU/GPU và phương án đánh giá độc lập/nhóm phụ thuộc. CV fallback và official alert vẫn phải tuân thủ Contract V1, bao gồm threshold calibration riêng; reference thresholds không phải ngưỡng production.

Artifact tại `artifacts/checkpoints/s3_post_t10_risk_comparison_20261124/` được Git ignore, gồm metrics, score từng encounter, operating points, threshold sensitivity, transitions, bootstrap, distributions, near-threshold cases, dependency audit, close-positive metrics, manifest và `checksums.sha256`. Script `compare_s3_t10_risk.py` không fit scaler, chỉ load Validation và gọi reference engine; hai script phụ tạo tổng hợp và subgroup outcome sau khi score đã cố định.

Regression: lượt toàn bộ **304 unit/integration + 8 backend PASS**, sau đó bổ sung một test kiểm tra hash checkpoint/scaler; chạy lại riêng 9 test Risk mới đều PASS. Tổng cộng **313 test riêng biệt PASS**, không failed/skipped trong các lượt cuối. Các test Risk kiểm tra hash, CPA, threshold, bootstrap cặp, undefined metrics, nhãn, mapping/history, no-future và paired categories. Một cảnh báo deprecation Starlette/TestClient. `git diff --check` được kiểm tra trước bàn giao.
