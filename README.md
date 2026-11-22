# PROJECT_AIT3040-

Prototype phát hiện và cảnh báo sớm nguy cơ va chạm tàu biển dựa trên dữ liệu AIS và học sâu. Dự án đang ở giai đoạn thiết kế và kiểm thử hợp đồng; mô hình Residual-GRU M5a chưa được triển khai, huấn luyện hoặc đánh giá trong repository này.

Bộ dữ liệu `final_dataset_1.0` được lưu cục bộ tại `DATASET_FINAL/`, không đưa lên GitHub. Sử dụng nguyên các tập Train, Validation và Test đã khóa.

## Cấu trúc và phân công

- `configs/`, `contracts/`: cấu hình, hợp đồng dữ liệu và API.
- `src/`: mã dữ liệu và các thư mục dành cho mô hình, huấn luyện, đánh giá và risk.
- `backend/`, `frontend/`: Mock Track API và React/Leaflet map cho S1_T04; chưa có replay engine, inference hoặc Risk API.
- `artifacts/`, `scripts/`, `tests/`, `results/`: artifact, script, kiểm thử và kết quả kiểm chứng.
- Trung phụ trách mô hình, risk, alert và tích hợp; Toàn phụ trách dữ liệu, replay và bản đồ. Các giao diện chung được phối hợp giữa hai thành viên.

## Môi trường Python

Dùng Python 3.12 64-bit. Tại thư mục repository trên Windows:

```powershell
py -3.12 -m venv .venv
# Chọn một bản PyTorch trước khi cài các dependency còn lại.
.\.venv\Scripts\python.exe -m pip install torch==2.11.0 --index-url https://download.pytorch.org/whl/cpu
# Nếu có GPU NVIDIA tương thích, thay lệnh CPU bằng:
# .\.venv\Scripts\python.exe -m pip install torch==2.11.0 --index-url https://download.pytorch.org/whl/cu128
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe scripts/check_environment.py
.\.venv\Scripts\python.exe -m pip check
```

Nếu cần cấu hình riêng, sao chép `.env.example` thành `.env` và đặt `DATASET_ROOT`. Đường dẫn tương đối tính từ thư mục repository; `.env` không được đưa vào Git.

## Đọc dataset

`configs/data_config.yaml` xác định hợp đồng dataset. `DATASET_ROOT` hoặc đối số `dataset_root` có thể thay đổi thư mục dữ liệu.

```python
from src.data.dataset_loader import DatasetLoader
from src.data.vessel_dataset import VesselDataset
from src.data.encounter_dataset import EncounterDataset

train = DatasetLoader().load_split("train")
vessel_sample = VesselDataset(train)[0]       # History và target tương đối anchor
encounter_sample = EncounterDataset(train)[0] # Input và ground truth được tách riêng
```

Kiểm tra bằng `scripts/smoke_test_dataset.py` và `scripts/verify_tensor_contract.py`. Các script dùng interpreter `.venv`, chỉ kiểm tra cấu trúc Test và không đánh giá mô hình trên Test.

## Notebook

`notebooks/01_dataset_overview.ipynb` tổng quan dữ liệu; `notebooks/02_feature_tensor_analysis.ipynb` phân tích feature và tensor. Chạy `.\.venv\Scripts\python.exe -m jupyterlab` và chọn kernel của môi trường, hoặc chạy lại cả hai bằng `scripts/execute_notebooks.py`.

## Thiết kế và hợp đồng

- `configs/model_config.yaml`, `projection_config.yaml`, `risk_config.yaml`: cấu hình mô hình, ràng buộc động học và risk.
- `contracts/model_design.md` giải thích phương pháp; `model_config_provenance.md` lưu nguồn gốc cấu hình.
- Các contract feature, temporal, coordinate, Rule input và forecast mô tả đơn vị, thời gian và tọa độ. `scripts/verify_feature_contract.py` kiểm chứng khả năng đọc dữ liệu Train/Validation.
- Các file `*.schema.json`, `api_contract.yaml` và `integration_contract.md` mô tả giao diện dự kiến. Backend hiện có các endpoint mock riêng; route/envelope Track API đang chờ nhóm review để bổ sung vào API contract dùng chung. Xem `evaluation/s1_t04/T04_MOCK_DATA_API_AND_MAP.md`.
- `contracts/mock/` chứa ví dụ giả lập cho Risk/Alert và Replay/Map; xem README trong thư mục đó để sử dụng.

Chạy kiểm thử từ repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit -v
.\.venv\Scripts\python.exe -m pytest tests/integration -v
```
