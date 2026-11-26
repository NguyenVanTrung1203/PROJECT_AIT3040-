# AIT3040 — Maritime Collision Risk Prediction and Early Warning

Đồ án là academic prototype cho dự báo quỹ đạo và phân tích nguy cơ va chạm từ AIS. Sprint 4 đã ghép source của Trung và Toàn trên nhánh integration. T15 được nghiệm thu kỹ thuật nhưng benchmark là `BENCHMARK_FAIL`, đã được chấp nhận cho prototype nghiên cứu. Hệ thống chưa được phê duyệt cho điều hướng, cảnh báo vận hành hoặc sử dụng production.

## Phạm vi hệ thống

- `DATASET_FINAL/` chứa bộ dữ liệu `final_dataset_1.0` đã khóa, gồm Train, Validation và Test. Dataset được lưu ngoài Git. Không đổi split, fit scaler trên Test hoặc ghi dữ liệu mới vào thư mục này.
- `src/models/`, `src/inference/`, `src/protocol/`, `src/release/` và `src/risk/` chứa M5a, các quy trình offline, kiểm tra lock và CC-DRI V4. Model package đã khóa nằm ngoài repository.
- `src/data/` chứa dataset loader offline, AIS reader, replay clock/session core và TrackBuffer.
- `backend/` cung cấp T04 Mock Track API và Replay V1 API cho fixture cục bộ. Session, snapshot và idempotency state hiện chỉ ở memory của một process.
- `frontend/` là React/Leaflet demo cho Mock Track và Replay fixture. Forecast trên bản đồ có nhãn **FORECAST MOCK**; đây không phải dự báo M5a.
- `contracts/` mô tả frozen Contract V1 và API. Các metadata companion còn trạng thái draft/pending thì chưa được tự xem là phê duyệt.

## Dataset và Model Lock

Dataset phải được cung cấp riêng trên máy chạy dự án. Đặt `DATASET_ROOT` tới thư mục chứa `train/`, `validation/` và `test/` khi chạy công cụ đọc dataset hoặc Q1 guard:

```powershell
$env:DATASET_ROOT = '<duong-dan-DATASET_FINAL-tren-may>'
```

Model M5a là Residual-GRU 15,390 tham số, nhận 10 bước history và tạo forecast 15 bước. Model Lock và checkpoint/scalers nằm trong package ngoài Git `m5a-cc-dri-offline-v1.0-20261125T133930Z`. Package cần được chuyển và kiểm tra riêng; không dùng một đường dẫn máy của thành viên khác. Đặt `AIT3040_MODEL_PACKAGE` tới thư mục package trên máy nhận và làm theo identity/hash/verification command tại [S4_FINAL_HANDOFF.md](docs/trung/S4_FINAL_HANDOFF.md).

Môi trường tham chiếu của package là Python 3.12.3, PyTorch 2.11.0+cu128 và CUDA 12.8. Đây là môi trường tham chiếu cho lần nghiệm thu offline, không phải yêu cầu production runtime. `requirements.txt` và `configs/s4_t14_observed_dependency_closure.yaml` ghi các dependency liên quan.

Risk implementation sử dụng CC-DRI V4. Các giá trị tham chiếu M5a 0.420 và CV 0.435 là operating point offline; `configs/risk_config.yaml` vẫn giữ `not_calibrated`, calibrated thresholds là null và không bật official alert decision. Không đổi ngưỡng hoặc coi benchmark fail là pass.

## Chạy Replay Fixture

### Môi trường phát triển

Tạo Python environment một lần. Chọn torch CPU hoặc CUDA phù hợp trước khi cài phần dependency còn lại:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install torch==2.11.0 --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe scripts/check_environment.py
.\.venv\Scripts\python.exe -m pip check
```

Nếu dùng CUDA, thay wheel CPU bằng wheel tương thích với máy. Không cài package vào snapshot model immutable.

### Khởi chạy fixture

Trong một cửa sổ PowerShell tại thư mục gốc, chạy backend:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Trong cửa sổ PowerShell thứ hai, chạy frontend:

```powershell
Set-Location frontend
npm ci
npm run dev
```

Mở URL Vite hiện trên terminal, thường là `http://127.0.0.1:5173`. Backend API docs ở `http://127.0.0.1:8000/docs`.

- `/api/v1/mock/tracks` phục vụ T04 mock tracks.
- `/api/v1/replay/sessions` tạo Replay session cho source demo `fixture-denmark-10m-v1`.
- Replay hỗ trợ PLAY, PAUSE, RESUME, SEEK và RESET. Clock dùng thời gian mô phỏng của source, không dùng wall clock làm timestamp AIS.
- ReplayAPI nạp AIS events đến replay clock; mỗi session khởi tạo lookback tối đa 10 phút, đủ cho 10 điểm history và giới hạn source age 60 giây trong TrackBuffer retention 900 giây. Snapshot không nhận event tương lai. Nếu `original_source_timestamp` không có, API giữ null; không suy diễn parent timestamp.
- Partial history có thể hiển thị vị trí quan sát với trạng thái `INSUFFICIENT_DATA`. `current_state` vẫn null cho đến khi có đủ 10 điểm.
- Forecast chỉ là mock xác định, giới hạn ở synthetic fixture và track `VALID`. Không có Risk/Alert runtime.

## Kiểm thử

Từ thư mục gốc, sau khi đặt `DATASET_ROOT`, chạy Python suites với Q1 Test access guard:

```powershell
.\.venv\Scripts\python.exe -m pytest -p scripts.q1_test_access_guard tests/unit tests/integration backend/tests -q
```

Q1 guard chỉ cho phép đọc Test split để kiểm tra checksum; không cho deserialize Test content. Không bỏ guard để ép tests pass. Frontend checks:

```powershell
Set-Location frontend
npm test
npm run build
```

## Giới hạn đã biết

- Replay mặc định chỉ đăng ký synthetic 10-minute fixture. AIS source reader và local source reports chưa thay thế được xác nhận timezone, source authority, duplicate policy hoặc vessel identity từ source owner.
- Session, snapshots, clock và idempotency state chưa durable; không có multi-worker consistency hoặc restart recovery.
- Candidate-pair provider, Encounter builder và TrackSnapshot-to-feature adapter chưa được nối vào backend.
- Runtime model inference, Risk V4, threshold authorization và Alert chưa được tích hợp. T18/T19 còn pending; T20/T21 cần xác nhận assignment.
- Forecast mock không dùng M5a và không được trình bày như output model thật.
- T15 benchmark fail đã được chấp nhận trong prototype scope. Kết quả không chứng minh model superiority hoặc operational safety.

Xem `docs/trung/S4_FINAL_HANDOFF.md` để biết deliverables T14/T15, kết quả historical và hướng dẫn chuyển model package. Sprint 5 integration cần được duyệt và nghiệm thu riêng.
