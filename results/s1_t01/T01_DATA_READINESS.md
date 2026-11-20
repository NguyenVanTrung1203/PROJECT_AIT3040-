# T01 — Data readiness

## Trạng thái

- Repository và branch `trungnguyen` đã được chuẩn bị; các thay đổi vẫn chưa commit.
- DATASET_FINAL `final_dataset_1.0` ở trạng thái `READY_AND_LOCKED`. Checksum manifest 93/93 đạt; 97/97 file giữa nguồn và bản sao khớp SHA-256 sau kiểm tra. Dataset được Git ignore.
- Môi trường Python 3.12.3 và Jupyter trong `.venv`; `pip check` đạt.
- Dataset Loader, VesselDataset và EncounterDataset đã được triển khai. Không fit scaler hoặc huấn luyện trên dataset.
- 24/24 unit test đạt. Smoke test môi trường và loader đạt. Hai Notebook đã chạy thành công với output bảng/biểu đồ.
- Tensor contract Train/Validation đạt các kiểm tra shape, dtype, finite, anchor, reconstruction, index, label, timestamp và input isolation. Sai số reconstruction lớn nhất 2.3760727341226584e-7 nm, dưới dung sai cố định 1e-6 nm. Test chỉ được kiểm tra integrity, shape, dtype và index/metadata.

## Mã và cách chạy

- Loader: `src/data/dataset_loader.py`, `src/data/vessel_dataset.py`, `src/data/encounter_dataset.py`.
- Cấu hình: `configs/data_config.yaml`. Dùng `DatasetLoader().load_split("train")`; `DATASET_ROOT` hoặc đối số `dataset_root` có thể thay đổi vị trí dataset.
- Kiểm chứng: `.\.venv\Scripts\python.exe scripts/verify_tensor_contract.py`.
- Unit test: `.\.venv\Scripts\python.exe -m pytest tests/unit -v`.
- Notebook: `.\.venv\Scripts\python.exe -m jupyterlab` hoặc chạy lại cả hai qua `.\.venv\Scripts\python.exe scripts/execute_notebooks.py`.

## Lưu ý trước huấn luyện

Train chỉ có Yang Lei, còn Validation có Real/Synthetic AIS: có domain shift và source–label confounding. Nhãn là proxy, có quan hệ phụ thuộc parent; không diễn giải kết quả mô tả là bằng chứng an toàn thực tế. Chỉ fit scaler trên Train trong giai đoạn huấn luyện chính thức; không sử dụng Test để lựa chọn model, scaler hoặc threshold. Kiểm tra mutation chứng minh cách ly đầu vào của loader với các giá trị đã thay đổi trong bộ nhớ, không chứng minh không có leakage trong toàn bộ pipeline tạo dữ liệu. Kiểm tra tái dựng sâu và các giả định khoa học khác cần tiếp tục trong giai đoạn model development.

Không có blocker cho bước phát triển model tiếp theo theo phạm vi T01; chưa đánh giá hiệu năng M5a hoặc Test.
