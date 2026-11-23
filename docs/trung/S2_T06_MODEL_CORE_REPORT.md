# Báo cáo S2_T06 — lõi mô hình M5a

## Phạm vi và baseline

Triển khai lõi Residual-GRU, CV, residual, scaler, projection và inference composition để T07 tích hợp; chưa huấn luyện chính thức, calibration hay benchmark Test. Repository `PROJECT_AIT3040-`; worktree hiện có `trung-contract-v1-freeze` được dùng lại với branch mới `s2-t06-trung-model-core`, HEAD/base `99bdb2649f5aec39d67a6f64645bce4f7fc49a3d`. Commit này đã được xác minh là ancestor của remote main tại `d8d0cfc018bef01d73ec8d9409743f0899c9d183`. Không merge hoặc sửa branch nguồn.

Quyết định áp dụng từ Contract V1, tensor contract và `contracts/model_design.md`, `configs/model_config.yaml`, `configs/projection_config.yaml`. Kế hoạch PDF V4 không tìm thấy trong thư mục dự án được kiểm tra; mã projection V4 được đối chiếu trực tiếp. Không thay contract hay dataset.

## Kiến trúc và biểu diễn

`src.models.m5a.ResidualGRU`: input float `[B,10,4]`, GRU một lớp 4→48, hidden cuối, head 48→96→ReLU→30, output `[B,15,2]`; 15.390 tham số, khởi tạo PyTorch mặc định theo seed. Không sử dụng future, label, source hay scenario. Raw history theo thứ tự own-relative East/North nm và East/North velocity kn.

`cv_displacement(velocity_kn, forecast_minutes=...)` trả displacement `v_anchor × k/60`, k=1…15; COG theo chiều kim đồng hồ từ Bắc, East=SOG sin(COG), North=SOG cos(COG). Hàm nhận vận tốc EN đã chuyển đổi, không tự đoán đơn vị; offsets nếu cung cấp phải đúng +1…+15 phút. `residual_target(Y, CV)` tính `Y_displacement−CV`, target giữ anchor riêng và đơn vị nm; reconstruction `CV+residual=Y`.

## Scaler và pipeline

`TrainOnlyScaler('input'|'residual')` yêu cầu `fit(..., split='train')`; fit StandardScaler theo từng kênh trên `(-1,4)` hoặc `(-1,2)` rồi cộng `1e-6` vào scale. Transform trả float32; inverse giữ shape; save/load JSON chứa mean/scale, không ghi artifact chính thức trong nhiệm vụ này. Từ chối NaN/Inf, shape sai và transform trước fit. Tham số `split` là khai báo của caller, không thể chứng minh provenance của một tensor tùy ý: T07 phải lấy trực tiếp Train từ DatasetLoader và bảo vệ provenance, không truyền Validation/Test với nhãn giả `train`.

`forecast(model, x_scaler, residual_scaler, raw_history, anchors_en_nm, forecast_minutes=...)` nhận history vật lý chưa scale và anchor riêng common EN; kiểm vị trí cuối tương đối anchor gần 0. Pipeline scale X → model → inverse residual → cộng CV displacement → cộng anchor đúng một lần → projection; không nhận future target hoặc label. Nó không tự xác minh timestamp nguồn hay phân biệt mọi trường hợp đã chuẩn hóa nhầm: adapter T07 phải xác minh clock, history và provenance trước khi gọi. Model và dữ liệu phải cùng device; model inference theo dtype float32 đã khóa, anchor/output giữ dtype floating của anchor.

## Projection

`project_forecast(raw_common_nm, anchor_common_nm, anchor_velocity_kn)` xử lý từng bước nhân quả theo V4: desired velocity từ raw point và projected position trước, giới hạn speed 49.999 kn, vector change 2.999 kn/phút, góc 29.9°/phút khi cả hai speed ≥3 kn, sau đó tích phân `/60`. Mẫu chia tối thiểu `1e-12`; từ chối input/output không hữu hạn. So sánh 30 trajectory ngẫu nhiên float64 với implementation V4 cho sai số tuyệt đối tối đa `4.440892098500626e-16` nm. Phép chiếu tuần tự không bảo đảm mọi giới hạn với mọi input bất thường; QC severe độc lập và fallback kỹ thuật thuộc runtime tương lai. Không tuyên bố đây là chứng nhận an toàn hoặc phép chiếu idempotent tổng quát.

## Kiểm thử và dữ liệu

- `.venv` hiện có: torch 2.11.0+cu128, numpy 2.4.4, sklearn 1.8.0; test CPU, không huấn luyện.
- `pytest tests/unit/test_s2_t06_model_core.py -q -p no:cacheprovider`: 13 passed. Kiểm tra architecture/shape/gradient/seed, CV, residual, scaler, projection, batch 1, input sai và pipeline không nhận future.
- `pytest tests/unit tests/integration backend/tests -q -p no:cacheprovider --ignore=tests/unit/test_s2_t06_model_core.py`: 277 passed, một cảnh báo deprecation Starlette/TestClient.
- Checksum manifest DATASET_FINAL và các artifact: 93/93 khớp trước sử dụng. `DatasetLoader` chỉ dùng Train cho kiểm tra T06: 1.440 encounter, 2.880 tàu, 28.800 history; A/B theo tensor index; timestamp/grid history và không có future PASS. Sai số lớn nhất velocity `9.53e-7` kn, anchor `0` nm, position `1.20e-7` nm, target reconstruction `2.38e-7` nm.
- `UNTRAINED_MODEL_SMOKE`: một encounter Train, output `[2,15,2]` hữu hạn; hai scaler fit trên fixture zero, không fit scaler chính thức trên DATASET_FINAL. Không đánh giá chất lượng model. Các test regression T01 sẵn có cũng đọc Validation theo phạm vi test hiện hữu; không fit Validation/Test và không benchmark Test.
- `git diff --check` cần chạy trước bàn giao. Không yêu cầu frontend build vì không đổi frontend.

## File và nghiệm thu

File mới: `src/models/{m5a,kinematics,scalers,pipeline}.py`, `tests/unit/test_s2_t06_model_core.py`, và báo cáo này. File sửa: `src/models/__init__.py`. Không sửa file contract, loader hoặc dataset.

`T06_CODE_COMPLETE: YES`; `T06_UNIT_TEST_PASS: YES`; `T06_REAL_DATA_VERIFIED: YES` trong phạm vi checksum, Train tensor/mapping/time và smoke chưa huấn luyện; `T06_READY_FOR_T07: YES` để xây pipeline training, không có nghĩa model đã sẵn sàng production. Nguồn AIS thực, semantic online, QC runtime, checkpoint và chất lượng dự báo vẫn chưa được kiểm chứng.

## Checklist T07

- Dùng `DatasetLoader.load_split('train')` và duy trì split/provenance thực; fit hai scaler riêng đúng reshape, chỉ một lần trên Train.
- Kiểm history UTC/grid và anchor trước pipeline; bảo đảm input là raw EN/kn, không scale hai lần; không dùng future khi inference.
- Dùng residual output và inverse scale, cộng CV và anchor một lần; chạy QC riêng sau projection và xử lý trạng thái lỗi theo contract.
- Quản lý dtype/device, serialization scaler, checkpoint và cấu hình được duyệt; kiểm hợp nhất A/B theo tensor index.
- Viết training loop/CLI, đánh giá Validation và review riêng trong T07; không tự coi model chưa huấn luyện là kết quả dự báo chính thức.
