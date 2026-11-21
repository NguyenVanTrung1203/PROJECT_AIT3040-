# Nguồn gốc cấu hình M5a

Đường dẫn dưới đây tương đối với thư mục thực nghiệm tương ứng dưới `Môn học Dự án`; repo mới không phụ thuộc các thư mục đó khi chạy.

| Tham số hoặc phương pháp | Giá trị đã xác minh | Nguồn tham chiếu | Ghi chú |
|---|---|---|---|
| Kiến trúc, tham số | GRU 4–48; 48–96–30; 15.390 | V4 `M5A_FINAL_MODEL_LOCK_MANIFEST.json`; V3 `scripts/train_candidate.py` | `batch_first`, hidden cuối; default bias, dropout 0, không bidirectional |
| M5a loss | encoded MSE + 0,15 position + 0,02 velocity + 0,002 acceleration + 0,001 kinematic | V3 `scripts/train_candidate.py`; `checkpoints/M5a_seed20261110_manifest.json` | MSE trung bình; penalty xem model_design.md |
| Số epoch | min 25, max 45, patience 8 | V3 `configs/locked_kinematic_training_protocol.json`; `scripts/train_candidate.py` | 25 là số epoch thực tế của ba run cũ, không phải max |
| Checkpoint | QC zero, Real AIS Validation ADE giảm >1e-7 | V3 `scripts/train_candidate.py` | FDE được log, không là tie-break |
| Seed selection | V4 gates rồi close recall, F1, recall, Real FPR, Synthetic recall, AUC, Dmin MAE, Real ADE/FDE | V4 `configs/locked_v4_selection_protocol.json`; `scripts/select_m5a_checkpoint.py` | Khác thứ tự xếp candidate giai đoạn V3; chọn V4 cho M5a đã khóa |
| Scaler | X Train `(-1,4)`, residual Train `(-1,2)`, StandardScaler `scale_ += 1e-6` | V3 `scripts/train_candidate.py`; V1 `scripts/train_gru.py` | V3 tái dùng X scaler fit Train của V1; lần mới fit lại cả hai trên Train |
| Projection | 49,999 kn; vector 2,999 kn/phút; góc 29,9°/phút, cả hai speed ≥3 | V4 package `configs/projection_config.json`, `inference/projection.py` | QC scalar speed change khác vector change |
| QC | 50 kn; scalar 3 kn/phút; 30°/phút; tolerance 1e-9 | V3 `scripts/kinematic_qc.py`; `configs/locked_kinematic_training_protocol.json` | Anchor–bước đầu không thuộc severe flag trong source |
| Risk | 0,68 predicted + 0,12 current + 0,20 rule | V4 package `configs/risk_config.json`, `inference/risk_pipeline.py` | Điểm không phải xác suất |
| Rule và CPA | SOG/COG history; cpa r=B−A, v=B−A; score logistic có thời gian | V4 package `inference/risk_pipeline.py` | Vai trò từ ba mốc history đầu, không dùng ground truth |
| Calibration | Validation, 0:0,005:1, recall ≥0,9, max F1, tie Real FPR/recall/threshold | V4 `configs/locked_v4_selection_protocol.json`; V3 `scripts/evaluate_candidates.py` | Ngưỡng lịch sử 0,420 M5a và 0,435 CV chưa chính thức cho run mới |
| Run lịch sử | seed 20261110, best epoch 1 | V4 lock manifest; `FINAL_M5A_VALIDATION_REPORT.md` | Kết quả lịch sử, không hardcode cho run mới |
| Đánh giá | ADE/FDE/Dmin/QC và risk theo nguồn; Test tái sử dụng | V4 `M5A_DEVELOPMENT_BENCHMARK_REPORT.md`; DATASET_FINAL `protocols/EVALUATION_PROTOCOL.md` | Không coi Test là unseen |
| Thiết bị | V3 source chạy CPU; repo mới hỗ trợ auto/cpu/cuda | V3 `scripts/train_candidate.py` | Khác chủ ý; deterministic CUDA và độ tái lập cần xác nhận khi chạy |
| Input của Rule | SOG/COG history `[N,2,10,2]` ngoài X và anchor | V4 package `inference/residual_gru_inference.py` | EncounterDataset hiện chưa cung cấp trực tiếp; cần adapter khi tích hợp, không tự suy COG ở tốc độ 0 |

Đã đọc thêm V4 `FINAL_MODEL_VERIFICATION_REPORT.md`, `M5A_EPOCH1_DIAGNOSTIC_REPORT.md`, `RESIDUAL_GRU_ABLATION_REPORT.md`, và các file config/inference của package. Thứ tự seed V4 được ưu tiên hơn thứ tự xếp candidate V3; khác biệt này không phải kết quả training mới.
