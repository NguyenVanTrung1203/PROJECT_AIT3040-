# T11 → T18: ranh giới tin cậy đầu vào

T11 cung cấp `M5aInference.predict_validation(dataset_root)` chỉ cho Validation checksum-pinned. `predict` từ chối runtime object. `_predict_test_only` chỉ dành cho fixture, không chứng minh provenance và không được dùng để phát quyết định.

Trước khi mở runtime entrypoint, T18 phải triển khai và kiểm thử:

1. TrackSnapshot schema và semantic G11; session/version và identity nguồn ổn định, NFC, namespace, MMSI khi hợp lệ; pair ID/hash và thứ tự A/B theo Contract V1.
2. Timestamp lưới, anchor UTC, source và ingest timestamp khi contract/source cung cấp; phân biệt thời gian mô phỏng, original provenance và simulated source time. Áp dụng as-of 0–60 giây, stale policy và dữ liệu đến sau anchor; không giả timestamp thiếu.
3. Đủ 10 history mốc nhân quả, cùng session/anchor, current state và chất lượng track, không sử dụng future/label. Làm rõ và xác minh phạm vi hoạt động được duyệt.
4. Tái tạo EN gốc A t−9, feature order, velocity và anchor riêng; kiểm thử tính hữu hạn, timestamp +1…+15, mapping và adapter LAT/LON được phê duyệt.
5. Đảm bảo validator và inference được kiểm soát cùng boundary; không chấp nhận boolean hay object tự khai là bằng chứng. Ngăn biến đổi dữ liệu sau xác minh theo mô hình threat và lifecycle của runtime.
6. Lỗi input/provenance/artifact fail-closed, không CV fallback; chỉ lỗi kỹ thuật model trên input hợp lệ trong phạm vi được xét fallback, sau đó CV phải qua QC. Không phát alert khi chưa calibration model active.

Offline checksum xác minh tập dữ liệu cố định, không xác minh quyền sở hữu MMSI thực, nguồn thực hay replay session online. Ngưỡng numerical parity T11 chưa được Trung phê duyệt; model còn CANDIDATE. Không dùng code T11 làm runtime adapter mà thiếu các kiểm chứng trên.
