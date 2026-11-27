# AIT3040 — Bản demo V1

Ứng dụng minh họa phát lại dữ liệu tàu, dự báo quỹ đạo M5a và đánh giá nguy cơ va chạm trên fixture tổng hợp. Đây là prototype học thuật để trình bày đồ án; không dùng cho điều hướng, vận hành tàu hoặc cảnh báo hàng hải thực tế.

## Phạm vi V1

- Replay có PLAY, PAUSE, RESUME, SEEK và RESET. Backend giữ session và replay clock trong bộ nhớ của một process.
- Chế độ `S5 nhiều tàu` dùng fixture `s5-01-synthetic-denmark-v1`, không phải AIS thật đã xác minh.
- V1 dùng đánh giá thủ công khi PAUSED. PLAY chỉ phát lại chuyển động; automatic scheduler bị vô hiệu hóa.
- Forecast sử dụng model M5a thật từ Model Package T14 bên ngoài repository. Risk dùng CC-DRI V4 và operating point được khóa cho prototype. Mỗi kết quả có trạng thái model, forecast, QC và quyết định alert/no-alert/unavailable.
- `official_alerts=false`. Các giá trị operating point không phải ngưỡng cảnh báo hàng hải chính thức. Review tích hợp của Toàn còn pending.

## Kiến trúc tổng thể

React/Leaflet hiển thị tàu và điều khiển Replay qua FastAPI. Backend giữ session và snapshot của fixture, dựng cặp tàu và gọi M5a từ Model Package đã khóa; Risk Engine V4 tính CPA, risk và alert cho yêu cầu thủ công khi PAUSED. Source automatic scheduler được giữ cho phiên bản mở rộng nhưng không được khởi chạy trong V1.

## Yêu cầu

- Windows PowerShell 7 hoặc Windows PowerShell 5.1.
- Python 3.12 với dependencies trong `requirements-dev.txt`, gồm PyTorch CPU hoặc wheel CUDA tương thích.
- Node.js và npm.
- Model Package M5a T14 cùng external manifest pin hợp lệ, được chuyển riêng cho máy chạy ứng dụng.
- Bộ dữ liệu nghiên cứu không cần cho demo Replay; `DATASET_ROOT` chỉ cần khi chạy dataset tools hoặc tests có Q1 access guard.

Không đưa `DATASET_FINAL`, raw AIS, checkpoint, scaler, Model Package hoặc file `.env` vào Git. `.env` đã được ignore. Không sửa package bất biến hoặc external pin để làm cho kiểm tra thành công.

## Chuẩn bị môi trường

Tạo virtual environment và cài dependencies một lần. Chọn bản PyTorch phù hợp máy trước khi cài requirements:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install torch==2.11.0 --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Set-Location frontend
npm ci
Set-Location ..
```

Đối với GPU, cài wheel PyTorch tương thích với driver/CUDA của máy. Không cài hoặc ghi file vào Model Package.

Tạo cấu hình riêng trên máy:

```powershell
Copy-Item .env.example .env
notepad .env
```

Điền đường dẫn tuyệt đối của `AIT3040_MODEL_PACKAGE` và `AIT3040_MODEL_MANIFEST_PIN`. External pin phải nằm ngoài thư mục package. Giữ nguyên các trường authority, scope, Model Lock ID, thresholds và `AIT3040_OFFICIAL_ALERTS=false`. `AIT3040_PYTHON` mặc định là `.venv\Scripts\python.exe`; có thể đặt đường dẫn virtual environment khác. Để chạy dataset tools/Q1 tests, điền `DATASET_ROOT`; trường này không bắt buộc cho demo synthetic.

Backend startup script kiểm tra Python/import dependencies, các trường cấu hình, package, external pin, dataset path nếu được điền và port trước khi khởi động. Integrity verifier kiểm tra Model Package khi runtime được khởi tạo để đánh giá lần đầu.

## Khởi chạy

Mở hai cửa sổ PowerShell tại thư mục repository.

Cửa sổ 1 — backend:

```powershell
.\scripts\start_backend.ps1
```

Cửa sổ 2 — frontend:

```powershell
.\scripts\start_frontend.ps1
```

Mặc định:

- Ứng dụng: <http://127.0.0.1:5173/>
- Backend health: <http://127.0.0.1:8000/health>
- API documentation: <http://127.0.0.1:8000/docs>
- Runtime status: <http://127.0.0.1:8000/api/v1/runtime/status>
- Scheduler status: <http://127.0.0.1:8000/api/v1/runtime/scheduler>

Dừng mỗi server bằng `Ctrl+C` trong cửa sổ tương ứng. Scripts sử dụng port 8000 và 5173; giải phóng các port này trước khi khởi chạy.

## Kịch bản demo 5–10 phút

1. Chọn **S5 nhiều tàu** và đợi session/track xuất hiện trên bản đồ.
2. Dùng SEEK tới `2024-11-01 00:09 UTC`; session chuyển sang PAUSED. Chọn cặp A–B và bấm **Đánh giá Risk và forecast**.
3. Tại 00:09, kiểm tra A–B alert, A–C no-alert, A–E insufficient data. Dùng **Đánh giá tất cả 10 cặp** để xem toàn bộ kết quả.
4. Pause. Có thể đánh giá thủ công một cặp hoặc toàn bộ cặp khi session ở PAUSED.
5. SEEK tới `2024-11-01 00:15 UTC` và đánh giá thủ công tất cả 10 cặp khi PAUSED.
6. Thử SEEK/RESET. Kết quả thuộc session/generation cũ phải hết hiệu lực; bản đồ không được trình bày forecast cũ như forecast hiện hành.

Anchor 00:09 được kiểm chứng với 1 alert, 5 no-alert và 4 unavailable; A–B risk tham chiếu khoảng `0.8832455466`. Anchor 00:15 được kiểm chứng với 1 alert và 9 no-alert; A–B risk khoảng `0.9638132257`. Đây là kết quả của fixture và model hiện có, không phải giá trị được hardcode cho demo. Hiệu năng đo được trên máy tham chiếu nằm trong báo cáo bàn giao.

Fixture là dữ liệu tổng hợp có dạng minh họa, không đại diện tuyến hàng hải thật. Không gán nhãn va chạm AIS thật.

## Kiểm thử mục tiêu

Sau khi cấu hình `.env`, từ thư mục gốc có thể chạy:

```powershell
$env:DATASET_ROOT = '<đường-dẫn-DATASET_FINAL>'
.\.venv\Scripts\python.exe -m pytest -p scripts.q1_test_access_guard tests/unit/test_s5_07b_batch_runtime.py tests/unit/test_s5_07b_http_surface.py -q
```

Frontend checks:

```powershell
Set-Location frontend
npm test -- --reporter=dot
npm run build
Set-Location ..
```

Không bỏ Q1 guard để làm tests pass. Full regression, training, calibration và T15 benchmark không thuộc quy trình chạy demo.

## Giới hạn đã biết

- V1 chỉ dùng fixture tổng hợp; Real AIS và Real Collision Case Study được hoãn.
- Automatic evaluation bị vô hiệu hóa trong V1. Một backend process hỗ trợ một active S5 session; session, alert state và cache không bền qua restart.
- Runtime trust model dành cho prototype học thuật. Đường manual kiểm tra integrity và authority khi đánh giá; process/RAM tampering không được bảo vệ.
- Model Lock không phê duyệt runtime integration hoặc production use. Không phát cảnh báo hàng hải chính thức.
- Trung đã xác nhận manual V1 và zoom/pan trên Chrome; Toàn chưa review interface.
- Basemap có thể cần kết nối internet nếu tile provider không cache tile cục bộ.
- V1 không chứng minh benchmark superiority, operational safety, generalization sang AIS thật hoặc khả năng triển khai production.

Xem `docs/trung/S4_FINAL_HANDOFF.md` để biết quy trình chuyển Model Package và external pin. Báo cáo phạm vi V1, kiểm thử, Git handoff và các giới hạn hiện tại nằm tại `docs/S5_FINAL_V1_HANDOVER_REPORT.md`.
