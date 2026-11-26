# Báo cáo S3_T10 — Huấn luyện M5a

## Phạm vi và baseline

Đã chạy một lượt training chính thức cho ứng viên M5a Residual-GRU seed 20261110; chưa calibration, đánh giá Risk, benchmark Test hay tuyên bố production-ready. Branch `s3-t10-trung-full-training`, base T07 `f3096fd2d44471ce7bbf455932cd7c3d5634f692`, có T06 `46270e5ce0609874559b0c4af1ab08eeb5aee06f` và Contract V1 `99bdb2649f5aec39d67a6f64645bce4f7fc49a3d` trong ancestry. T07 cũng được xác minh trên remote. Không commit/push/merge trong T10.

Run `s3_t10_20261124_seed20261110_run01`, bắt đầu 2026-11-24 10:34:14 UTC, kết thúc 10:35:46 UTC. Runner mới `scripts/train_s3_t10.py` có SHA-256 `6169fdcae90fdc1cd1d52a368f0c0eaf317f5a477d67942b3ed549040be660d5`; nó dùng trực tiếp T06/T07 cho data, model, loss, optimizer step, validation và selection, đồng thời ghi log/artifact riêng. `scripts/verify_s3_t10.py` kiểm chứng độc lập. Chưa sửa Contract V1 hoặc dataset.

## Dữ liệu và môi trường

`final_dataset_1.0`, READY_AND_LOCKED; checksum manifest `21f6bde168631928e98b6273aaab4e168bfb6eb755599a1fbc1cb8c364611441`. Checksum **93/93 trước và sau**. Train: 1.440 encounter, 2.880 tàu Yang Lei; Validation: 835 encounter, 1.670 tàu (Yang Lei 240, Real AIS 295, Synthetic AIS 300 encounter). Tensor index, A/B, timestamps, anchors, feature EN/SOG/COG, reconstruction và finite được kiểm qua loader/verifier. 93 checksum có đọc byte file thuộc Test để xác minh toàn vẹn, nhưng không nạp tensor Test để dự báo, đánh giá, calibration hoặc chọn model.

Python 3.12.3, PyTorch 2.11.0+cu128, NumPy 2.4.4, scikit-learn 1.8.0, Windows 11, CUDA 12.8, NVIDIA GeForce RTX 4050 Laptop GPU 6.438.780.928 byte. Disk trống lúc bắt đầu khoảng 12,5 GB; CUDA forward/backward và train/validation synthetic đã kiểm trước run. `CUBLAS_WORKSPACE_CONFIG=:4096:8`, deterministic algorithms bật. Một training chính thức chạy tại một thời điểm.

## Model, scaler và loss

Input `[B,10,4]`; GRU 1 lớp 4→48, head 48→96→ReLU→30, output residual `[B,15,2]`; 15.390 tham số, khởi tạo PyTorch mặc định sau seed. AdamW lr 0.0025, weight decay 0.0001, batch 256, shuffle generator theo seed, `drop_last=False`, 12 batch/epoch; không scheduler, không gradient clipping theo cấu hình đã khóa. Min 25, max 45 epoch, patience 8.

Hai scaler StandardScaler fit mới duy nhất trên Train qua `fit_verified_train_scalers`: X reshape `(-1,4)`, residual reshape `(-1,2)`, cộng `1e-6` vào scale; không dùng scaler/checkpoint cũ. CV displacement dùng anchor velocity EN kn × phút/60; residual là true displacement trừ CV. Loss trước projection theo contract: residual encoded MSE + 0.15 position MSE + 0.02 normalized velocity MSE + 0.002 normalized acceleration MSE + 0.001 kinematic penalty. Không dùng label làm input/loss.

## Lịch sử training và validation

Mỗi epoch đã dùng đủ 2.880 lượt tàu Train và 1.670 lượt tàu Validation; không có mẫu loại hoặc báo lỗi. Loss là trung bình có trọng số theo số mẫu; ADE/FDE tính sau projection, đơn vị nm. Bảng đầy đủ thành phần loss và từng nguồn có trong `training_history.csv` và `training_history.jsonl`.

| Epoch | Train loss | Validation ADE | Validation FDE | Real AIS ADE | Severe QC |
|---:|---:|---:|---:|---:|---:|
| 1 | 0.953768 | 0.147803 | 0.304910 | 0.196332 | 0 |
| 2 | 0.811708 | 0.171273 | 0.354246 | 0.216701 | 0 |
| 3 | 0.779908 | 0.157010 | 0.341725 | 0.203575 | 0 |
| 4 | 0.776819 | 0.165110 | 0.353377 | 0.211019 | 0 |
| 5 | 0.772490 | 0.161359 | 0.344340 | 0.207637 | 0 |
| 6 | 0.772941 | 0.159932 | 0.341310 | 0.206565 | 0 |
| 7 | 0.771625 | 0.162476 | 0.347258 | 0.209043 | 0 |
| 8 | 0.768055 | 0.162778 | 0.347774 | 0.209073 | 0 |
| 9 | 0.765711 | 0.163301 | 0.348604 | 0.209617 | 0 |
| 10 | 0.763087 | 0.160753 | 0.343587 | 0.208191 | 0 |
| 11 | 0.766275 | 0.161787 | 0.344805 | 0.208464 | 0 |
| 12 | 0.758418 | 0.161922 | 0.345865 | 0.208625 | 0 |
| 13 | 0.756299 | 0.163021 | 0.347011 | 0.210019 | 0 |
| 14 | 0.750406 | 0.158157 | 0.338577 | 0.205528 | 0 |
| 15 | 0.748797 | 0.164141 | 0.348354 | 0.211208 | 0 |
| 16 | 0.739499 | 0.159328 | 0.340961 | 0.206446 | 0 |
| 17 | 0.732001 | 0.159708 | 0.341360 | 0.207398 | 0 |
| 18 | 0.725608 | 0.152867 | 0.328157 | 0.202288 | 0 |
| 19 | 0.705738 | 0.149058 | 0.321345 | 0.199595 | 0 |
| 20 | 0.694942 | 0.147555 | 0.319368 | 0.199807 | 0 |
| 21 | 0.679930 | 0.149188 | 0.322213 | 0.201850 | 0 |
| 22 | 0.691055 | 0.147385 | 0.318978 | 0.200881 | 0 |
| 23 | 0.666136 | 0.145227 | 0.314525 | 0.199817 | 0 |
| 24 | 0.649096 | 0.144848 | 0.315149 | 0.200600 | 0 |
| 25 | 0.639443 | 0.156129 | 0.335392 | 0.211598 | 0 |

## Chọn checkpoint

Epoch **1** được chọn vì có Real AIS Validation ADE thấp nhất trong các epoch thỏa severe QC=0; không dùng loss train hoặc overall ADE để chọn. Sau epoch 1 không có cải thiện theo Real AIS ADE; training dừng ở epoch 25 do đã đạt min epoch và patience ≥8. Đây là checkpoint ứng viên theo quy tắc T10, không phải model lock hoặc kết quả calibration.

| Validation epoch 1 | Encounter | Tàu | ADE (nm) | FDE (nm) |
|---|---:|---:|---:|---:|
| Yang Lei | 240 | 480 | 0.150414 | 0.293609 |
| Real AIS | 295 | 590 | 0.196332 | 0.419442 |
| Synthetic AIS | 300 | 600 | 0.097993 | 0.201328 |
| Tổng | 835 | 1.670 | 0.147803 | 0.304910 |

## Artifact và kiểm chứng

Artifact nằm trong `artifacts/checkpoints/s3_t10_20261124_seed20261110_run01/`, được Git ignore. `checksums.sha256` liệt kê toàn bộ file; các SHA-256 chính:

| File | SHA-256 |
|---|---|
| `best_model.pt` | `e01a19e913d14a068c6c82a1c2a52a8be2aadd2f44e3ad5d8770d7f69a1fc7bc` |
| `x_scaler.json` | `a538be921104ed1bb2fa495c0c3f527c0385fd6c737aa69afda81ba1962d452a` |
| `residual_scaler.json` | `96b062fab9a5d4e27c9b1cc32a649e44e98d29648c7dcc3b7f482eba3d50358f` |
| `training_history.csv` | `bc299390b003dcf4d54808041c0127437fe6647a4532dd505c9f56b692699966` |
| `training_history.jsonl` | `18717e2dc5749753ae80addd9e7835580fe33960cbe2617e6b5e4f6b8fd99ca1` |
| `validation_predictions.npz` | `0f0a2389ba90721d74c73c62494524864da9eb9794748cb54609793cbd804915` |
| `validation_metrics.json` | `e7b2d4a23792b9821b93c78bef9d7b498e166213ec45673b6c8e4d94fa004cd9` |
| `training_manifest.json` | `608eb8dac61e5b564385485f691d9ad49e6a8ae1ba374f47cc16a324dc71b17c` |
| `run_config.yaml` | `b1e3503b44e92e152cac6db2ce8102d9e8d556b150d1092585046ea7459d12f6` |
| `environment.json` | `36214d6f4cba8819b40f2ac66c7178a9d13dafa8751d8d04c95fb4280bd53fde` |
| `artifact_verification.json` | `ea457877093d91fd415228435a610d299ecdfc914ac4263e9984ca1c670ca369` |

Checkpoint đã load trên CPU với đúng state keys, shape và 15.390 tham số; scaler load/inverse PASS. Inference Validation shape `[1670,15,2]` hữu hạn, mapping A/B đúng, severe QC CPU và GPU đều 0. Prediction tái tạo trên GPU ban đầu khớp chính xác bản đã lưu. Trên CPU, sai khác lớn nhất `3.300808803252675e-05` nm (khoảng 6,1 cm); **260 tàu vượt ngưỡng chẩn đoán `1e-5` nm**. Đây là ngưỡng do lượt kiểm chứng đặt ra, chưa có tolerance cross-device được phê duyệt; không tuyên bố parity CPU đạt ngưỡng đó. Chênh lệch CPU–GPU overall ADE `8.06e-9` nm, Real AIS ADE `-6.69e-8` nm. Trung cần quyết định tolerance/thiết bị cho wrapper trước khi coi CPU deployment đã được kiểm chứng.

## Regression và bàn giao

Sau training: **289 unit/integration PASS + 8 backend PASS = 297 PASS, 0 failed, 0 skipped**; gồm T06/T07, loader, Contract V1 và G11. Một cảnh báo deprecation Starlette/TestClient. Không chạy training lần hai; tái tạo prediction dùng checkpoint đã lưu. GPU/CPU không được giả định tái lập bitwise trên các thiết bị khác.

`T10_FULL_TRAINING_COMPLETE: YES` theo số epoch, checkpoint và regression; artifact verification là `PASS_WITH_CPU_PARITY_CAVEAT`, với ngưỡng chẩn đoán CPU nêu trên chưa đạt. `T10_READY_FOR_T11: CONDITIONAL` cho đến khi Trung review sai khác CPU/GPU và chọn thiết bị/tolerance. `T10_READY_FOR_T14: CONDITIONAL`: artifact Validation có sẵn nhưng chưa calibration, chưa duyệt parity và selection protocol cuối còn yêu cầu baseline đối chứng có thể so sánh. Dataset có domain shift/source-label confounding; Test từng được tái sử dụng trong nghiên cứu trước, không phải holdout độc lập mới.

Checklist T11/T14: xác minh artifact hashes trước nạp; dùng đúng scaler/model/config và anchor EN; quyết định CPU/GPU tolerance; kiểm tra no-future và QC runtime; review baseline đối chứng và calibration bằng Validation theo protocol; không đánh giá/chọn bằng Test trước khi được phép.
