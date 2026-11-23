# Báo cáo S2_T07 — Training pipeline M5a

## Mục tiêu và baseline

Xây dựng data pipeline, scaler Train-only, loss, training/validation, checkpoint và CLI; chỉ chạy smoke, không huấn luyện chính thức hoặc calibration. Worktree hiện có `trung-contract-v1-freeze`, branch `s2-t06-trung-model-core`, base `99bdb2649f5aec39d67a6f64645bce4f7fc49a3d` chứa Contract V1. Tại thời điểm triển khai T07, các file T06 chưa commit và được giữ lại. Repository chính và branch Toàn không được sửa. Kiến trúc T06 4→48, 48→96→30 giữ nguyên.

## Dataset và scaler

`src.training.data.load_verified_data` dùng DatasetLoader, kiểm `final_dataset_1.0`, lock status và checksum manifest đã khóa `21f6bde168631928e98b6273aaab4e168bfb6eb755599a1fbc1cb8c364611441`: **93/93 artifact PASS**. Cấu hình dữ liệu phải khớp cấu hình repository; loader kiểm count, shape, index và A/B. Kiểm thêm finite/dtype, anchor, target reconstruction, UTC/grid, history/future, nguồn timestamp và tái dựng features EN/SOG/COG cho Train và Validation. Không đọc Test để tối ưu hoặc benchmark; checksum chỉ kiểm integrity file.

`fit_verified_train_scalers` tự tải từ loader đã kiểm chứng, không nhận tensor bất kỳ do caller tự gán split; chỉ lấy `splits['train']`, fit `TrainOnlyScaler` T06 cho X `(-1,4)` và residual `(-1,2)`. Validation dùng transform và không fit lại. Dữ liệu Train gồm 1.440 encounter/2.880 tàu; Validation gồm 835 encounter/1.670 tàu. Model chỉ nhận history; target được dùng cho loss, anchor và source chỉ dùng cho validation/QC và tổng hợp metrics. Không dùng label, scenario hay source làm feature.

## Loss và training

`src.training.loss.m5a_loss` dùng loss đã duyệt trước projection: `MSE(R_scaled) + 0.15 MSE(P,P_true) + 0.02 MSE((V−V_true)/10) + 0.002 MSE((ΔV−ΔV_true)/3) + 0.001 K`; `K` là tổng mean bình phương vượt speed 50 kn và scalar speed change 3 kn/phút sau chuẩn hóa. P là displacement được inverse-scale residual rồi cộng CV; velocity sai phân từ gốc 0 nhân 60; acceleration là sai phân giữa các bước dự báo. Mọi thành phần vật lý nằm trong đồ thị gradient. Đã đối chiếu công thức `MODEL_SELECTION_V3/scripts/train_candidate.py` và test giá trị tính tay.

AdamW lr 0.0025, weight decay 0.0001, batch 256; seed 20261110 mặc định. Shuffle dùng generator, `drop_last=False`, `num_workers=0`, deterministic algorithms. Không scheduler hoặc gradient clipping theo protocol. Step từ chối split khác Train, loss/gradient/gradient norm không hữu hạn; log norm để theo dõi nhưng không đặt ngưỡng clipping mới khi chưa được duyệt.

## Validation và checkpoint

Validation chạy `model.eval()`/`torch.no_grad()`, scale bằng Train scalers, dùng `forecast` T06 gồm inverse residual, CV, anchor và projection; tính ADE/FDE bằng nm tổng và từng nguồn. Real AIS ADE được tính riêng. Sau mỗi lần validation so sánh trọng số trước/sau. QC severe dùng speed >50 kn, scalar change >3 kn/phút, turn >30° khi cả hai tốc độ ≥3 kn, tolerance 1e-9; anchor–bước đầu không tính vào severe change.

`checkpoint_improved` chỉ chấp nhận severe=0 và Real AIS ADE giảm hơn `1e-7` nm. Chế độ train có min 25/max 45 epoch, patience 8; trong nhiệm vụ này **không chạy full training**. Smoke luôn ghi checkpoint `SMOKE_ONLY.pt` để thử round-trip, không coi là checkpoint được chọn chính thức. Checkpoint chứa model/optimizer state, config, seed, epoch, metrics, dataset version/hash và tên hai file scaler; smoke đã load vào model và optimizer mới, đồng thời load lại scaler và đối chiếu thống kê.

## CLI và logging

Không chọn mode mặc định. Ví dụ smoke (thư mục output phải mới và nằm dưới `artifacts/checkpoints`, vốn bị Git ignore):

```powershell
python scripts/train_m5a.py --smoke --device cpu --dataset-root "$env:DATASET_ROOT" --output-dir artifacts/checkpoints/<thu-muc-moi> --smoke-batches 2
```

CLI có `--config`, `--data-config`, `--seed`, `--device`, `--output-dir`, `--smoke` và `--train` tường minh. Config phải khớp repository; không load pretrained hoặc resume. `run.json` ghi `SMOKE_ONLY`, dataset version/checksum, seed/device, từng loss, gradient norm lớn nhất, số batch, validation theo nguồn và checkpoint. Thư mục smoke không ghi đè artifact chính thức. Không cung cấp resume trong T07; cần review thiết kế resume trước khi sử dụng.

## Kết quả smoke

CPU, seed 20261110, **1 epoch / 2 batch Train**, scaler fit toàn Train đã xác minh. Loss trung bình: residual 1.210598, position 0.048728, velocity 0.045663, acceleration 0.587848, penalty 0.046957, total 1.220043; max gradient norm 0.124984. Các giá trị hữu hạn; trọng số thực sự thay đổi, validation không thay đổi trọng số.

Validation 1.670 tàu: ADE 0.141049 nm, FDE 0.297459 nm; Real AIS 590 tàu ADE 0.190959 nm; severe QC 0. Đây là **số liệu smoke sau hai batch**, không đánh giá chất lượng hoặc chọn model chính thức. Hai lượt cùng seed trên CPU cho model state, scaler và validation giống nhau. Không khẳng định tái lập số học giữa CPU/GPU.

## Kiểm thử và giới hạn

- `pytest tests/unit tests/integration -q -p no:cacheprovider`: **289 passed**, gồm T06 và T07; `pytest backend/tests -q -p no:cacheprovider`: **8 passed**. Tổng **297 passed, 0 failed, 0 skipped** trong lượt regression cuối, một cảnh báo deprecation Starlette/TestClient.
- Smoke kiểm checkpoint/model/optimizer/scaler save/load, parameter update, validation no-update và finite values. Trước đó một assertion tính tay bỏ sót penalty đã được sửa theo công thức; bộ regression cuối PASS.
- Checksum sau smoke vẫn 93/93. T06 inference không nhận future; timestamp/feature offline được kiểm bằng DatasetLoader và verifier. Không chứng minh AIS raw/source provenance, causal pipeline upstream hoặc production runtime.
- Syntax được parse, `git diff --check` và kiểm whitespace file mới trước bàn giao. Frontend không thay đổi và không chạy lại.
- T07 đã được smoke trên CPU; CUDA, training nhiều epoch, early stopping thực tế, resume và quality model chưa được kiểm thử. Raw AIS/source validation vẫn pending; không có threshold calibration hay benchmark Test.

## S3 readiness và file thay đổi

`T07_CODE_COMPLETE: YES`; `T07_READY_FOR_S3: YES` trong phạm vi pipeline đã smoke và contract tests, không khẳng định model được train hay production-ready. Trước S3 cần Trung review code, bảo đảm output mới, kiểm môi trường/device, theo dõi gradient/QC và dùng Validation theo protocol, không chọn bằng Test.

File T07 mới: `src/training/data.py`, `engine.py`, `loss.py`, `scripts/train_m5a.py`, `tests/unit/test_s2_t07_training.py` và báo cáo này. File T07 sửa: `src/training/__init__.py`. Các thay đổi T06 được giữ nguyên khi triển khai T07; không sửa Contract V1 hoặc dataset. Artifacts smoke nằm dưới `artifacts/checkpoints/` được ignore, không đưa vào Git.
