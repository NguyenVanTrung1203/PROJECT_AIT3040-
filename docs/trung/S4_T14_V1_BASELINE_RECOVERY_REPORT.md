# S4 T14 — P7 bounded V1 recovery audit

## Phạm vi

Kiểm kê repository hiện tại, Git refs/history theo tên V1 và bốn workspace nghiên cứu đã xác định `MODEL_END_TO_END_EXPERIMENT_V1`, `MODEL_HYBRID_IMPROVEMENT_V2`, `MODEL_SELECTION_V3`, `MODEL_FINAL_VERIFICATION_V4`; kiểm file metadata/config/code, tên artifact và hash của các artifact V1 liên quan. Không quét dữ liệu cá nhân toàn máy, không tải dataset, không train V1, không load Test tensors/labels/predictions. Không mở các file mixed/không rõ split để tính metrics.

## Evidence tìm thấy

V1 workspace có `scripts/train_gru.py`, `scripts/risk_pipeline.py`, model/training/risk configs, `MODEL_EVALUATION_LOCK_MANIFEST.json`, checkpoint `best_gru.pt`, scaler X/Y và scaler fit manifest. Lock manifest SHA `85019a0bf6ea9d5443d9f1e8db98499164c352e1def5639d61d26d41172e44d2`, trùng `MODEL_HYBRID_IMPROVEMENT_V2/manifests/V1_reference.json`. Checkpoint SHA `81daa4f4b86b111169a610747598af13c1fc12c57af73bceb342648138454129`; X scaler `6915778f8ac08bca793a3d850f82440dc8ad9b98e2b539110ddaac04b57ca92a`; Y scaler `ceabedfc7e30fd07a783c5ad7eeb73546f7ac1d9626979061b2672a7236f2ca3`, đều trùng reference. `risk_pipeline.py` SHA `8e33effb06d7f2e1fe855b1cb067fb2d27eb3aba9498e2af30be1b387534be7e`, trùng V4 reference. V1 metadata: seed 20261112, epoch 27, GRU 4→48→96→30, scalers train-only, dataset version `final_dataset_1.0`; Y scaler dùng future displacement trực tiếp, khác residual M5a.

Có file tên `predictions/validation_trajectory_predictions.parquet`, SHA `589365d55673d36ee26931ee5b7faa0209751d96bb9eb48a01e4c28f01b119a3`, và `validation_risk_predictions.csv`, SHA `b3d5770d1918466ce8e216739cf6a42592fbbbe235f87b0ae0809696fc177037`. Chỉ hash bytes, không load predictions; chưa xác nhận các hash này bằng manifest độc lập và chưa kiểm mapping/semantics. V2 có V1 reference manifest; V3 có các script/metrics tên V1; V4 package đã xem metadata và risk reference, không load prediction Test. Git refs có Contract V1 nhưng không tự chứng minh V1 ML artifact nằm trong lịch sử dự án.

## R01–R10 và phân loại

R01 source identity: tìm thấy, cần hoàn tất pin các script. R02 architecture/config: có. R03 checkpoint: hash trùng lock. R04 scaler/preprocessing: X/Y và train-only manifest có. R05 dataset version/lock: historical lock hash có, chưa chứng minh toàn bộ environment/split tương thích ở lần audit này. R06 input/output: V1 trực tiếp dự báo displacement; không dùng M5a residual/scaler thay thế. R07 projection/QC và R08 risk: code/weight tham chiếu có, chưa chứng minh áp cùng protocol T14. R09 encounter/A-B: V1 helper reshape, chưa xác nhận mapping index và predictions từng encounter. R10 core artifact hash khớp, nhưng chưa kiểm toàn dependency/script/environment và prediction provenance.

`V1_BASELINE_REVIEW_REQUIRED`: đã tìm thấy nhiều thành phần, không còn phù hợp nói đơn giản là không tìm thấy; chưa có bằng chứng end-to-end reproduction/compatible prediction nên không gán `V1_BASELINE_REPRODUCIBLE` hay `V1_PREDICTIONS_ONLY`. Chưa chạy inference V1 hoặc dùng historical Test metrics. P7 bounded audit hoàn thành trong phạm vi trên; limitation không tự chặn calibration CV/M5a nhưng phải được Trung review trước model lock. T15 chỉ so V1 nếu được tái lập tương thích; không tuyên bố M5a vượt V1.
