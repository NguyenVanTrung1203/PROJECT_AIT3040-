# Dữ liệu mẫu cho hợp đồng tích hợp

Bộ dữ liệu này dùng giá trị **giả lập** để kiểm tra cách trao đổi giữa phần Replay/Map và phần Risk/Alert. Tất cả định danh, quỹ đạo, điểm nguy cơ và ngưỡng đều là ví dụ; không phải kết quả mô hình đã huấn luyện hay ngưỡng cảnh báo chính thức. Quỹ đạo forecast trong ví dụ là Constant Velocity để minh họa định dạng và phép tính.

## Thư mục

- `tracks/`, `encounters/`, `requests/`: trạng thái tàu, cặp tàu và yêu cầu đánh giá.
- `responses/`, `alerts/`, `model_status/`: kết quả, vòng đời cảnh báo và trạng thái mô hình giả lập.
- `invalid/`: các ví dụ cố ý lỗi JSON, schema hoặc ngữ nghĩa.
- `manifest.json`: danh sách fixture, schema đích và lớp validation mong đợi. Đường dẫn trong manifest tương đối với thư mục này.

## Kiểm tra và sử dụng

Từ thư mục repository, chạy:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_mock_contracts.py -v
```

Backend Risk có thể dùng request để kiểm tra đọc dữ liệu và response để phát triển serializer. Replay/Map có thể dùng track, encounter, forecast và alert để thử hiển thị, lọc theo session và xử lý trạng thái không khả dụng. Khi hiển thị forecast địa lý, tọa độ có thứ tự `[latitude, longitude]`.

Điểm nguy cơ được tính bằng `0,68 × predicted_cpa_score + 0,12 × current_cpa_score + 0,20 × rule_score`. Khi bình phương vận tốc tương đối không vượt `1e-9 kn²`, TCPA nội bộ bằng 0 để tính DCPA và Current-CPA score; API trả TCPA `null` vì không có thời điểm tiếp cận duy nhất. Ngưỡng trong ví dụ `CALIBRATED` chỉ phục vụ test; ngưỡng chính thức phải được hiệu chỉnh trên Validation.

Bộ kiểm thử chỉ đánh giá các fixture tĩnh và quan hệ hợp đồng. API, model inference, replay và alert manager production chưa được triển khai hay kiểm thử end-to-end.
