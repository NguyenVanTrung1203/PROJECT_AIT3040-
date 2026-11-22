# T03 — DATASET_FINAL v1.0 audit

**Ngày kiểm tra:** 2026-11-22 (Asia/Saigon)
**Repository:** repository root (local machine path omitted)
**Branch:** `Trinh_Toan`
**Kết quả:** **PASS** — dataset hiện diện, lock hợp lệ và các kiểm tra integrity đã chạy đạt.

## Kết luận

| Hạng mục | Trạng thái | Bằng chứng |
|---|---|---|
| DATASET_READY | YES | `DATASET_FINAL/` tồn tại; lock `final_dataset_1.0` là `READY_AND_LOCKED`. |
| CHECKSUM_STATUS | PASS | 93/93 file khớp manifest; SHA-256 manifest `21f6bde168631928e98b6273aaab4e168bfb6eb755599a1fbc1cb8c364611441`. |
| COUNT_STATUS | PASS | 1,440 Train + 835 Validation + 1,320 Test = 3,595 encounter; source counts trong lock khớp phân bố thực tế đã đối chiếu. |
| INDEX_STATUS | PASS | Loader xác minh encounter/vessel index, A/B, labels, metadata, shape và dtype cho cả ba split. |
| T03_STATUS | PASS | Bằng chứng checksum, count, split mapping, tensor/index và UTC đã thu được trong lượt này. |
| READY_FOR_T04 | YES | T03 đã hoàn tất; đây là trạng thái handoff, chưa bắt đầu công việc T04. |

## Repository audit

- Working directory là repository root; branch `Trinh_Toan`, working tree sạch trước khi thêm/cập nhật deliverable, ahead 4 commit so với `origin/Trinh_Toan`. Không checkout, commit, push hoặc merge.
- `configs/data_config.yaml` trỏ đến `./DATASET_FINAL`, khai báo history 10 bước, 4 feature, forecast 15 bước và các file/số record của từng split. Đường dẫn thực tế này tồn tại.
- `.gitignore` loại `/DATASET_FINAL/`; README và `.env.example` quy ước dataset local tại `DATASET_FINAL` hoặc qua `DATASET_ROOT`.
- Mã tái sử dụng: `src/data/dataset_loader.py` kiểm tra lock/version, shape/dtype, metadata và mapping A/B; `src/data/vessel_dataset.py` và `encounter_dataset.py` cung cấp sample huấn luyện/đánh giá; `src/data/tensor_verification.py` kiểm checksum, timestamp, anchor/reconstruction và input isolation. Script sẵn có gồm `scripts/verify_tensor_contract.py`, `scripts/smoke_test_dataset.py`, `scripts/verify_feature_contract.py`.
- Contract liên quan: `contracts/feature_contract.json`, `temporal_contract.json`, `coordinate_contract.md`, `encounter.schema.json`. Một số quy ước replay A/B/temporal vẫn là đề xuất/chờ review. Không sửa code hoặc nội dung Trung đã triển khai.

## Dataset, counts và source mapping

`DATASET_FINAL/DATASET_LOCK_MANIFEST.json` ghi version `final_dataset_1.0`, `READY_AND_LOCKED`, 3,595 encounter, 179,750 record, 7,190 vessel instances và 93 artifact checksum.

| Split | Source trong lock | Source quan sát trong parquet | Encounter | Rows |
|---|---|---|---:|---:|
| Train | 1,440 Yang Lei | `yang_lei`: 1,440 | 1,440 | 72,000 |
| Validation | 240 Yang Lei + 295 Real AIS + 300 Synthetic AIS | `yanglei`: 240; `real_ais_kattegat_v3`: 295; `augmented_real_ais_kattegat_v3`: 300 | 835 | 41,750 |
| Test | 720 Yang Lei + 300 Real AIS + 300 Synthetic AIS | `yang_lei`: 720; `real_ais_denmark_oct2025`: 300; `synthetic_ais_denmark_oct2025`: 300 | 1,320 | 66,000 |
| **Tổng** |  |  | **3,595** | **179,750** |

Validation có khác biệt cách đặt nhãn nguồn: lock chuẩn hóa 300 encounter là `synthetic_ais`, còn metadata parquet ghi `augmented_real_ais_kattegat_v3` và encounter IDs `VAL_SYN_*`. `validation_parent_mapping.csv` có đủ 300 ánh xạ (150 `selected_295`, 150 `unselected_candidates`); split mapping CSV khớp đầy đủ ID/source/split/label với metadata. Đã ghi nhận tên alias để không nhầm chúng với 295 encounter Real AIS nguyên gốc.

Parent mapping test nằm trong `test/manifests/real_synthetic_dependency_mapping.csv` và source windows. Manifest dependency có 3,595 encounter. Các artifact ghi nhận parent/vessel dependency trong cùng split; lock cũng liệt kê đây là giới hạn cần lưu ý. Không dùng sự hiện diện của dependency để diễn giải test như dữ liệu độc lập hoàn toàn.

## Kiểm tra checksum, schema, tensor, index và thời gian

- `src.data.tensor_verification.verify()` chạy read-only và trả `data_readiness=PASS`, lock `READY_AND_LOCKED`, 93/93 checksum PASS.
- Cả ba split có shape/dtype và index/metadata/label kiểm tra PASS. `X`: Train `[2880,10,4]`, Validation `[1670,10,4]`, Test `[2640,10,4]`, float32. `displacement` lần lượt `[2880,15,2]`, `[1670,15,2]`, `[2640,15,2]`, float32. `common`: `[1440,2,15,2]`, `[835,2,15,2]`, `[1320,2,15,2]`, float32. `anchors`: `[1440,2,2]`, `[835,2,2]`, `[1320,2,2]`, float64. Labels int8, số lượng 1,744 nhãn 0 và 1,851 nhãn 1.
- Loader xác nhận encounter index liên tục/duy nhất, vessel `A/B` đủ mỗi encounter, X row không lặp và metadata/label khớp tensor mapping. Mỗi encounter có 2 tàu × 25 mốc.
- Kiểm tra timestamp trực tiếp trên cả ba parquet: timezone UTC; offsets khớp `relative_minute`; mỗi vessel có đủ phút -9 đến 15 và cờ `is_history`/`is_future` phù hợp.
- Train và Validation có finite/anchor/reconstruction/input-isolation PASS. Sai số reconstruction tối đa: `2.3760727341226584e-7 nm` (Train), `2.3515755742664624e-7 nm` (Validation), dưới ngưỡng `1e-6 nm`. Test được kiểm integrity, shape, dtype, index/metadata; không đánh giá mô hình.
- Không ghi vào DATASET_FINAL. Kiểm hash xác nhận nội dung file được manifest liệt kê khớp giá trị khóa tại thời điểm kiểm toán.

## Giới hạn và lịch sử

Manifest nêu proxy labels khác nhau theo source, domain shift vì Train chỉ có dữ liệu mô phỏng Yang Lei, source-label confounding và dependency giữa parent/vessel trong split. Đây là giới hạn dataset; PASS ở T03 chỉ xác nhận trạng thái lock, integrity, count, schema/index/tensor và mapping theo artifact, không xác nhận chất lượng nhãn như ground truth tai nạn hay mức an toàn ngoài thực tế.

`results/s1_t01/*` và `results/s1_t02/*` là các báo cáo trước đây. Lượt này tái chạy `verify()` trực tiếp trên dataset hiện có; không chạy unit/integration test suite và không fit scaler/train/evaluate model.

**TEST_RESULTS:** `tensor_verification.verify()` PASS; count/source/split-mapping/parent-mapping và UTC checks PASS. Unit/integration suites không chạy.
**FILES_CHANGED:** Báo cáo T03 trong `evaluation/data/`; không sửa dữ liệu nguồn hay code.
