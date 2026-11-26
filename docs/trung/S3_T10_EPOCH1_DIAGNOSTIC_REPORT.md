# Diagnostic S3_T10: CV, domain shift và checkpoint epoch 1

## 1. Kết quả chính

Trên Real AIS Validation, M5a epoch 1 có ADE **0,196332 nm**, cao hơn CV **0,186414 nm**: chênh lệch M5a–CV là **+0,009918 nm** (+5,32% so với CV). FDE M5a cũng cao hơn 0,005797 nm. Bootstrap cặp theo encounter cho chênh lệch ADE M5a–CV có khoảng 95% `[+0,007559; +0,012297]` nm, dưới giả định các encounter được lấy mẫu là độc lập. Kết quả thiên về **scenario C: cần review tính phù hợp trước khi tuyên bố M5a là model chính**. Không tự thay checkpoint, thêm gating, ensemble hoặc huấn luyện lại.

Có khác biệt phân phối history đáng kể giữa Train Yang Lei và Real AIS Validation; điều này chưa chứng minh domain shift là nguyên nhân gây kết quả kém. Train loss giảm nhưng Real AIS ADE cuối run tăng so với epoch 1; hai metric có mục tiêu, tập dữ liệu và thời điểm projection khác nhau, không đủ để khẳng định cơ chế nhân quả.

## 2. Phạm vi và toàn vẹn

Branch `s3-t10-trung-full-training`, HEAD/base T07 `f3096fd2d44471ce7bbf455932cd7c3d5634f692`, chứa T06 và Contract V1. Các file T10 chưa commit được giữ nguyên. T10 có **12/12 artifact hash PASS trước và sau**, checksum manifest T10 `5f0af2eb5a4e418026b775fa412e2fc8bbc803c7438123038a1c519e5a082eb2`; dataset `final_dataset_1.0` **93/93 PASS trước và sau**. Hash dataset có đọc byte các file Test để kiểm toàn vẹn; không nạp tensor Test để phân tích hay benchmark. Không train lại, không refit scaler, không calibration, không commit/push/merge.

Checkpoint `best_model.pt` SHA-256 `e01a19e913d14a068c6c82a1c2a52a8be2aadd2f44e3ad5d8770d7f69a1fc7bc`, epoch 1, load đúng model/scalers T10. Tái inference trên GPU ban đầu khớp chính xác prediction đã lưu (`max |Δ| = 0`); 835 encounter/1.670 tàu Validation và mapping A/B khớp loader. Sai khác CPU/GPU đã ghi trong báo cáo T10 vẫn cần quyết định riêng.

## 3. CV so với M5a

Hai phương pháp dùng cùng history, anchor, mapping, future target, 15 mốc và tính ADE/FDE theo trung bình tàu. CV dùng đúng `cv_displacement`; M5a dùng checkpoint epoch 1, hai scaler đã lưu, CV + residual và projection. CV được áp cùng projection/QC; raw CV đã thỏa QC với 0 severe, khác projected tối đa `1,11e-16` nm. QC projected CV và M5a đều 0 severe trên toàn Validation. `Improvement = CV − M5a`, dương nghĩa là M5a tốt hơn.

| Nguồn | Encounter / tàu | CV ADE | M5a ADE | Δ ADE (nm) | Δ ADE % | CV FDE | M5a FDE | Δ FDE (nm / %) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Yang Lei | 240 / 480 | 0,141801 | 0,150414 | -0,008614 | -6,07% | 0,288526 | 0,293609 | -0,005083 / -1,76% |
| Real AIS | 295 / 590 | 0,186414 | 0,196332 | -0,009918 | -5,32% | 0,413645 | 0,419442 | -0,005797 / -1,40% |
| Synthetic AIS | 300 / 600 | 0,082594 | 0,097993 | -0,015398 | -18,64% | 0,189791 | 0,201328 | -0,011537 / -6,08% |
| Tổng | 835 / 1.670 | 0,136291 | 0,147803 | -0,011512 | -8,45% | 0,297256 | 0,304910 | -0,007654 / -2,57% |

## 4. Vessel, encounter và bootstrap

Vessel-level tính ADE từng tàu. Encounter-level lấy trung bình ADE hai tàu A/B rồi so sánh cùng encounter; không coi hai tàu là độc lập khi bootstrap. Dấu `improvement` trong bảng là CV–M5a.

| Real AIS | Số mẫu | M5a tốt hơn | M5a kém hơn | Hòa | Win rate | Median Δ | P10 / P90 Δ (nm) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Vessel | 590 | 230 | 360 | 0 | 38,98% | -0,008357 | -0,047606 / +0,022666 |
| Encounter | 295 | 99 | 196 | 0 | 33,56% | -0,007787 | -0,039964 / +0,014018 |

Trong Real AIS, encounter kém nhất theo CV–M5a là `VAL_REAL_0224` (-0,061735 nm), `VAL_REAL_0295` (-0,057364) và `VAL_REAL_0214` (-0,057072); cải thiện lớn nhất là `VAL_REAL_0200` (+0,062415), `VAL_REAL_0242` (+0,037798), `VAL_REAL_0019` (+0,032578). Danh sách đầy đủ theo vessel/encounter có trong `extreme_cases.csv` và hai file comparison.

Bootstrap percentile paired 5.000 lần, seed `20261124`, resample theo encounter: Real AIS 295 encounter, trung bình **M5a–CV +0,009918 nm**, CI 95% **[+0,007559; +0,012297]**; Yang Lei 240 encounter, trung bình **+0,008614 nm**, CI **[+0,003625; +0,013680]**. Các tàu hoặc parent/source có thể lặp giữa encounter; bootstrap encounter không xử lý phụ thuộc đó, nên CI có thể quá hẹp và không chứng minh khả năng tổng quát ngoài tập này.

## 5. Nhóm hành vi history

Nhóm được gán **từng tàu**, chỉ từ 10 mốc history; một encounter có thể xuất hiện ở nhiều nhóm nếu hai tàu thuộc nhóm khác nhau. Ngưỡng là phân vị exploratory lấy từ history Real AIS Validation, không phải threshold sản phẩm: mean absolute circular turn Q75 `6,536°/phút`; speed change đầu–cuối Q25 `-0,100 kn`, Q75 `+0,200 kn`; straight/stable dùng median turn `2,667°/phút` và median absolute speed change `0,200 kn`. Góc bỏ qua cặp điểm nếu một speed <0,5 kn; các trường hợp không xác định vào mixed. Thứ tự ưu tiên: turn cao → giảm/tăng tốc → straight/stable → mixed. Không dùng future/label để phân nhóm.

| Real AIS, nhóm tàu | Tàu / encounter xuất hiện | CV ADE | M5a ADE | Δ ADE % | CV FDE | M5a FDE | M5a thắng theo tàu |
|---|---:|---:|---:|---:|---:|---:|---:|
| Tương đối thẳng/ổn định | 194 / 147 | 0,057948 | 0,077505 | -33,75% | 0,137481 | 0,152744 | 26,29% |
| Đổi hướng cao | 146 / 115 | 0,417755 | 0,418414 | -0,16% | 0,887364 | 0,886259 | 49,32% |
| Giảm tốc | 97 / 87 | 0,184195 | 0,188270 | -2,21% | 0,451135 | 0,446932 | 48,45% |
| Tăng tốc | 70 / 62 | 0,176730 | 0,190698 | -7,90% | 0,398946 | 0,408859 | 38,57% |
| Hỗn hợp/không rõ | 83 / 74 | 0,090509 | 0,097598 | -7,83% | 0,194435 | 0,198462 | 39,76% |

QC severe đều 0. Nhóm thẳng có mức kém tương đối lớn; nhóm đổi hướng gần hòa về ADE và hơi tốt hơn CV về FDE trên mẫu này. Đây là phân tích khám phá, không có CI riêng cho nhóm và không chứng minh model giúp hay không giúp mọi tàu đang quay.

## 6. Domain shift history

So sánh 2.880 tàu Train Yang Lei với 590 tàu Real AIS Validation, một vector đặc trưng/tàu. SOG được lấy từ norm velocity EN; acceleration proxy là norm sai phân vector kn/phút; heading difference dùng circular wrap. Mean absolute turn loại cặp speed <0,5 kn, khiến 8 tàu Real thiếu turn hợp lệ. History CV residual dùng anchor velocity và các mốc history, không dùng future. Bảng đầy đủ mean, median, standard deviation, min/max, P10/P25/P75/P90, tỷ lệ vùng so với tứ phân vị Train, KS và Wasserstein nằm trong `domain_shift_features.csv`.

| Đặc trưng | Mean Train | Mean Real | SMD Real–Train | KS | Tỷ lệ Real dưới P25 Train |
|---|---:|---:|---:|---:|---:|
| History displacement (nm) | 2,071 | 0,948 | -2,102 | 0,748 | 87,80% |
| Mean speed (kn) | 13,833 | 6,524 | -2,064 | 0,743 | 87,29% |
| Anchor speed (kn) | 13,576 | 6,775 | -1,899 | 0,721 | 85,25% |
| Mean absolute turn (°/phút) | 1,154 | 7,727 | +0,589 | 0,490 | 14,78% |
| Mean absolute speed change (kn/phút) | 0,121 | 0,336 | +0,464 | 0,297 | 43,22% |

SMD là chênh lệch mean chia độ lệch chuẩn gộp; KS đo chênh lớn nhất giữa hai CDF; Wasserstein đo độ dịch chuyển phân phối theo đơn vị đặc trưng. Xếp theo `|SMD|`; không dùng p-value. Các đặc trưng có tương quan và tàu/encounter không độc lập, nên đây không phải thứ hạng nguyên nhân.

## 7. Diễn biến 25 epoch

`epoch_analysis.csv` chứa train loss và ADE của ba nguồn cùng overall theo từng epoch. Best ADE: Real AIS **epoch 1**, Yang Lei **epoch 24**, Synthetic AIS **epoch 24**, overall **epoch 24**. Từ epoch 1 đến 25: train loss giảm `0,314325`; Real ADE tăng `0,015266 nm`, Yang ADE giảm `0,003226 nm`, Synthetic ADE tăng `0,010744 nm`, overall ADE tăng `0,008326 nm`. Spearman mô tả giữa train loss và Real AIS ADE qua 25 epoch là **+0,3346**: không có quan hệ nghịch biến đơn điệu rõ ràng. Chỉ checkpoint/prediction epoch 1 được lưu; không suy diễn dự báo từng mẫu cho epoch 2–25.

## 8. Đánh giá giả thuyết

| Giả thuyết | Đánh giá | Bằng chứng và giới hạn |
|---|---|---|
| H1 — Domain shift | `PARTIALLY_SUPPORTED` | Phân phối speed/displacement khác mạnh và Real ADE xấu đi giữa epoch đầu/cuối. Tuy nhiên M5a cũng kém CV ở Yang Validation; không chứng minh shift là nguyên nhân. |
| H2 — CV baseline mạnh | `SUPPORTED` trong mẫu này | CV có ADE/FDE tốt hơn M5a tại Real AIS và trong từng nguồn; CI cặp encounter ủng hộ chênh lệch ADE. M5a vẫn thắng một phần tàu; phụ thuộc encounter giới hạn suy rộng. |
| H3 — Loss/selection mismatch | `PARTIALLY_SUPPORTED` | Train loss trước projection giảm trong khi Real ADE sau projection tăng từ epoch 1 đến 25; mục tiêu khác nhau. Spearman dương yếu và thiếu prediction epoch sau ngăn suy luận cơ chế. |

## 9. Khuyến nghị và quyết định cần Trung xem xét

Ưu tiên **scenario C**, kèm khác biệt theo hành vi của scenario D: review tính phù hợp của M5a trước khi gọi là model chính; giữ nguyên checkpoint để điều tra và không tự thay đổi selection. Có thể chuẩn bị phương án nghiên cứu riêng với baseline đối chứng có thể so sánh và đánh giá phụ thuộc theo parent/vessel; không tự huấn luyện lại hoặc điều chỉnh protocol. CV fallback vẫn phải tuân thủ điều kiện kỹ thuật và calibration riêng trong Contract V1, không suy ra có thể tự phát alert từ kết quả này. Quyết định tiếp tục T11, tolerances CPU/GPU và hướng cải thiện cần Trung phê duyệt.

## 10. Dữ liệu và kiểm thử

File diagnostic nằm tại `artifacts/checkpoints/s3_t10_epoch1_diagnostic_20261124_final/`, được Git ignore: metrics, comparison cấp tàu/encounter, nhóm hành vi, domain shift, epoch, bootstrap, extremes, win summary, hypothesis assessment và manifest. Script `scripts/diagnose_s3_t10_epoch1.py` cấm Test split và scaler fit; checkpoint dùng inference không gradient. T10 artifacts và dataset không đổi sau phân tích.

Regression: **296 unit/integration + 8 backend = 304 PASS, 0 failed, 0 skipped**, gồm 7 test diagnostic về CV/horizon, ADE/FDE, aggregation, bootstrap, circular heading, history-only và guard Test/scaler. Một cảnh báo deprecation Starlette/TestClient. `git diff --check` được kiểm tra khi bàn giao.
