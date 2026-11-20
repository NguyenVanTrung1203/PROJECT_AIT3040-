# Phân tích DATASET_FINAL

Hai Notebook chạy độc lập từ đầu, sử dụng `.venv` và `DATASET_ROOT` theo README gốc. `01_dataset_overview.ipynb` mô tả dữ liệu; `02_feature_tensor_analysis.ipynb` giải thích feature và kiểm chứng contract. Dữ liệu Test chỉ được kiểm tra cấu trúc; không dùng cho EDA định hướng mô hình.

Từ repository root chạy `.\.venv\Scripts\python.exe -m jupyterlab`, chọn kernel Python của môi trường. Chạy lại cả hai và ghi báo cáo bằng `.\.venv\Scripts\python.exe scripts/execute_notebooks.py`. Không fit scaler, huấn luyện hoặc đánh giá Test trong các Notebook.
