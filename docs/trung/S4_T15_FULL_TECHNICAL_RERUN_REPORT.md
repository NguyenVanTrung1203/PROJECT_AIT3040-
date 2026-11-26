# T15 — Báo cáo full technical rerun

## Kết luận

`T15_EXECUTION_ACCEPTANCE=PASS` và `T15_COMPLETED=YES`: full rerun hoàn tất với audit access ở mức ứng dụng, không có mục bắt buộc bị thiếu, kết quả tái lập chính xác R2 và integrity đạt. `T15_BENCHMARK_STATUS=BENCHMARK_FAIL`: cả CV và M5a không đạt D1 do Real AIS FPR vượt 0,12. Nghiệm thu kỹ thuật không thay đổi kết quả chất lượng này.

## Phê duyệt và lịch sử

Trung phê duyệt C1–C5 và full technical rerun để sửa audit, không phải để chọn model theo metric. Phương án evaluation-only replay được thay thế và draft được bảo toàn, không dùng làm bằng chứng nghiệm thu. R2 vẫn giữ nguyên hạn chế lịch sử: event observed của tensor được ghi lúc tạo memory map; future read thiếu observed event trực tiếp. Không tạo event hoặc timestamp hồi tố cho R2.

Run mới `s4_t15_full_20261125T161605Z_f54829ac`; R3 protocol SHA-256 `a0de7a49c15d33051c160b8bf5f282e7577bbf0db46ac1e726a8a98e79f63412`; authorization `t15-full-7ea06c658e1548048f5e0e12b52ec7f0`. R2 protocol và authorization được giữ nguyên. Protocol revision chỉ bổ sung audit, boundary và danh tính thực thi; threshold, scoring, metric, D1/D2 và phân loại benchmark không đổi.

## Integrity và preflight

Active lock `offline-t14-15980ed4f7255ddbdb943979` xác minh PASS trước và sau run; manifest SHA-256 `257e77a3a5ae2b2175926145cc0d3c483ccacdaf80f3479d9c352d69f8f6dcdc`, payload identity `15980ed4f7255ddbdb943979df7dda320ac4ae448e24feb357fa51f3dd38dd79`. Dataset raw-byte checksum 93/93 PASS trước và sau run; không có Test deserialization trong guard. R2 29/29 checksum và supplement 5/5 được xác minh, không ghi đè.

Synthetic preflight đi qua authorization giả lập, cả ba nguồn, A/B, input map và owned copy, validator, CV/M5a forecast, Risk V4, evaluation, missing difficulty, report và audit verifier. Model tổng hợp dùng đúng kiến trúc với zero weights và identity scalers; không train hoặc fit. Negative tests kiểm tra thiếu event, map-only, sai thứ tự/coverage/authorization, truy cập ngoài boundary và lỗi persistence. Targeted: 129 passed. Full regression theo Q1: 626 passed, 0 failed/skipped/deselected; Q1 ghi 42 lượt raw hash, 0 blocked deserialization. Một warning deprecation TestClient được giữ trong log.

## Access audit và trust boundary

Inventory nêu các đường input, index, metadata, history, inference, scoring, evaluation và reporting. Boundary T15 đọc các cột input cần thiết; labels, target và metadata đánh giá được trì hoãn tới sau scoring. `X` và anchors được map rồi sao chép đầy đủ sang owned arrays giữ dtype/shape/order; chính các arrays này đi vào validator và inference. Future và labels được materialize ở evaluation. Test-only displacement không cần cho benchmark và không được đọc.

Gate và pin được ghi trước semantic read. Event application-level đầu tiên cho input `X` là `2026-11-25T16:25:12.861015+00:00`; anchor observed `16:25:12.874943`, history `16:25:13.091762`, labels `16:25:14.861263`, target `16:25:14.877075`, future `16:25:14.930643` UTC. Inference phase hoàn tất `16:25:14.816412`, scoring hoàn tất `16:25:14.832315`, trước evaluation reads. Completeness verifier PASS cho 12 category, không có failure được ghi. Guard chặn các Python Test path ngoài boundary trong supported runner; đây không phải OS/native/subprocess sandbox, không quan sát từng page fault hoặc thời điểm đọc vật lý của từng byte.

## Dataset, inference và scoring

| Nguồn | Encounter | Positive | Negative | Close-positive |
| --- | ---: | ---: | ---: | ---: |
| Yang Lei | 720 | 375 | 345 | 0 |
| Real AIS Denmark | 300 | 0 | 300 | 0 |
| Synthetic AIS Denmark | 300 | 300 | 0 | 45 |
| Tổng | 1320 | 675 | 645 | 45 |

Có 2.640 tàu; raw IDs và canonical source types được bảo toàn. Source timestamp provenance đã được audit trong metadata-only run riêng. CV và M5a mỗi model hoàn thành forecast `[1320,2,15,2]` với cùng encounter/A-B/anchor/frame/timestamps. M5a epoch 1, 15.390 parameters, không fallback; severe QC của cả hai bằng 0. Mỗi model có 1.320 risk scores. Labels/future không được đưa vào prediction hoặc Risk V4.

## Kết quả fixed threshold

| Metric | CV | M5a |
| --- | ---: | ---: |
| Threshold (`>=`) | 0,435 | 0,420 |
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
| Overall ADE / FDE, nm | 0,132429 / 0,284690 | 0,144276 / 0,292495 |
| Real AIS ADE, nm | 0,123330 | 0,140122 |
| TP / FP / TN / FN | 644 / 123 / 522 / 31 | 648 / 127 / 518 / 27 |

CV D1 FAIL với 41/300 Real AIS FP; M5a D1 FAIL với 38/300. D2 FAIL vì M5a D1 FAIL và Real AIS ADE ratio `1,136158 > 1,10`. Recall delta `+0,005926`, Real FPR delta `−0,010000`, F1 delta `+0,000589`, overall ADE ratio `1,089457`; không có close-positive miss mới. Cả hai cùng bỏ sót `TEST_SYNTH_0105` trong 45 close-positive.

## Tái lập, latency và giới hạn

Forecast CV/M5a, toàn bộ bảng risk scores/components, decisions, metrics, D1/D2, distribution, evaluation metadata và paired outcomes khớp **chính xác** R2; không dùng tolerance. So sánh bao gồm source membership và close-positive IDs. 41/41 checksum của run được xác minh; source cuối khớp source đã regression-test.

Trong môi trường offline RTX 4050 Laptop GPU, batch 128, một batch warm-up và 11 batch đo: CPU forecast/projection/QC trung bình 0,007826 s/batch; CUDA 0,030305 s/batch. Input/evaluation owned-array copies được đo tổng 0,000583 s với 782.760 bytes; audit logging được đo 0,116689 s đến thời điểm tổng hợp timing. Các phạm vi này không phải latency API hoặc yêu cầu so khớp latency R2.

Phân loại là `REUSED_DEVELOPMENT_BENCHMARK`, không phải independent external validation hay chứng nhận an toàn. Clean environment chưa được xác minh; production và runtime integration chưa được phê duyệt. Model lock giữ nguyên; không commit, push hoặc chuyển sang T18/T19. Trung review kết quả và quyết định phạm vi sử dụng prototype.
