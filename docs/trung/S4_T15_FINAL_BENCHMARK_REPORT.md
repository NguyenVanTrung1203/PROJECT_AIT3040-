# T15 — Kết quả benchmark và giới hạn audit

## Kết luận

Benchmark trên reused development dataset cho kết quả `BENCHMARK_FAIL`: cả hai model không đạt D1 do Real AIS FPR vượt 0,12. CV 41/300 = 0,136667; M5a 38/300 = 0,126667. D2 FAIL vì M5a không đạt D1; so sánh bổ sung cũng cho Real AIS ADE ratio 1,136158 > 1,10. Không thay model hoặc threshold.

Inference, scoring và tính metric đã hoàn thành. `T15_EXECUTION_ACCEPTANCE=BLOCKED` và `T15_COMPLETED=NO` vì sự kiện đọc future trong evaluation chỉ được ghi trước lệnh đọc, không có observed event trực tiếp. Việc evaluation hoàn thành và sinh output phụ thuộc future hỗ trợ suy luận read thành công, nhưng không cung cấp timestamp observed trực tiếp; không được coi đó là access audit hoàn chỉnh.

## Dữ liệu Test

| Nguồn | Encounter | Positive | Negative | Close-positive |
| --- | ---: | ---: | ---: | ---: |
| Yang Lei | 720 | 375 | 345 | 0 |
| Real AIS Denmark | 300 | 0 | 300 | 0 |
| Synthetic AIS Denmark | 300 | 300 | 0 | 45 |
| Tổng | 1320 | 675 | 645 | 45 |

Metadata history: 26.400 dòng; Real AIS source age 0–55 s, Synthetic 0–60 s; không phát hiện vi phạm các kiểm tra được thực hiện. Có 2.640 vessel, A/B và khung tọa độ đã qua trusted validation.

## Kết quả fixed threshold

| Metric | CV | M5a |
| --- | ---: | ---: |
| Threshold (>=) | 0,435 | 0,420 |
| ROC-AUC | 0,944774 | 0,946398 |
| Average Precision | 0,936678 | 0,939125 |
| Accuracy | 0,883333 | 0,883333 |
| Precision | 0,839635 | 0,836129 |
| Recall | 0,954074 | 0,960000 |
| F1 | 0,893204 | 0,893793 |
| Overall FPR | 0,190698 | 0,196899 |
| Real AIS FPR | 0,136667 | 0,126667 |
| Synthetic Recall | 0,930000 | 0,933333 |
| Close-positive Recall | 0,977778 | 0,977778 |
| ADE, nm | 0,132429 | 0,144276 |
| FDE, nm | 0,284690 | 0,292495 |
| Real AIS ADE, nm | 0,123330 | 0,140122 |
| TP / FP / TN / FN | 644 / 123 / 522 / 31 | 648 / 127 / 518 / 27 |
| Severe QC | 0 | 0 |

Cả hai forecast có shape `[1320,2,15,2]`; không dùng fallback M5a. Recall delta +0,005926, Real FPR delta −0,010000, F1 delta +0,000589 và overall ADE ratio 1,089457 đạt gate so sánh; Real AIS ADE ratio 1,136158 không đạt. Hai model đều bỏ sót close-positive `TEST_SYNTH_0105`; không có close-positive miss mới của M5a.

## Kỹ thuật và bằng chứng

Lock ID `offline-t14-15980ed4f7255ddbdb943979`; active verifier sau run PASS, package identity `15980ed4f7255ddbdb943979df7dda320ac4ae448e24feb357fa51f3dd38dd79`. Dataset 93/93 hash PASS sau run. R2 protocol SHA-256 `606bf33104c88bb0feac4ce24ef0b95f1efc7966fa5d479d3ec5cd7296c8a735`; pre-access gate được ghi và hash trước current run semantic access đầu tiên lúc 2026-11-25T15:25:16.013672+00:00.

Targeted tests 92 passed; full Q1 regression 589 passed, 0 failed/skipped/deselected, một warning deprecation. Q1: 42 hash opens, 0 blocked deserialization. Báo cáo blocked và evidence hai lần lỗi vẫn được bảo toàn. R1 đã chạy inference/scoring nhưng lỗi tổng hợp missing difficulty; R2 là technical retry, không chọn theo chất lượng metric.

Trong môi trường offline ghi nhận RTX 4050 Laptop GPU, batch 128, timed warm-up 1 batch: CPU mean 0,015852 s/batch, CUDA mean 0,058508 s/batch; đây là forecast/projection/QC theo batch, không phải API latency. Không suy diễn parity Test từ latency.

Đây là `REUSED_DEVELOPMENT_BENCHMARK`, không phải independent external validation hoặc chứng nhận an toàn. Clean environment, runtime và production chưa được phê duyệt. Không có commit/push. Bằng chứng chi tiết, metrics theo nguồn, trajectory, so sánh Validation và checksum nằm trong run artifacts và reporting supplement ngoài Git.

## Addendum — Full technical rerun theo C1–C5

Run `s4_t15_full_20261125T161605Z_f54829ac` đã tái lập chính xác forecasts, risk scores, decisions, metrics và membership của R2. Audit access của run mới PASS với materialization observed cho input và evaluation sau gate; full regression 626 passed. Vì vậy `T15_EXECUTION_ACCEPTANCE=PASS`, `T15_COMPLETED=YES`, trong khi `T15_BENCHMARK_STATUS=BENCHMARK_FAIL` và Model Lock vẫn giữ.

Trạng thái audit lịch sử R2 không thay đổi: event tensor R2 chỉ chứng minh tạo memory map và future read không có observed event trực tiếp. Báo cáo full rerun và evidence độc lập ghi chi tiết. Benchmark vẫn là reused development benchmark; không có production hoặc runtime approval.
