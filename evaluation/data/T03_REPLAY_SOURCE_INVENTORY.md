# T03 — AIS replay source inventory

**Ngày kiểm tra:** 2026-11-22 (Asia/Saigon)
**Kết quả:** Có nguồn AIS lịch sử local để chuẩn bị replay; chưa xây dựng replay engine.

## Nguồn tìm thấy

Nguồn nằm ngoài repository AIT3040; đường dẫn local đã được lược bỏ khỏi báo cáo:

| Tầng dữ liệu | Đường dẫn / format | Phạm vi |
|---|---|---|
| Raw AIS hàng ngày | `data/raw/ais/2024/11/ais-2024-11-DD.tgz`; magic bytes là Zstandard (`28 b5 2f fd`), nội dung giải nén là CSV, không phải tar/gzip dù suffix `.tgz` | 30 file, 2024-11-01 đến 2024-11-30. CSV có `mmsi`, `base_date_time`, `longitude`, `latitude`, `sog`, `cog`, `heading` và AIS metadata. Raw timestamp là chuỗi không có timezone marker. |
| AIS đã chuẩn hóa | `data/processed/ais_cleaned/year=2024/month=11/day=DD/part-00000.parquet` | 30 Parquet ngày; 237,960,745 records theo cleaning summary/dataset manifest; report kiểm tra Parquet ghi 30/30 ngày PASS, manifest COMPLETE. |
| Điểm quỹ đạo Houston | `data/processed/trajectory_runs/houston_nov2024/points/day=DD/part-00000.parquet` | 19,659,725 điểm trong bbox Houston, UTC 2024-11-01 00:00:00 đến 2024-11-30 23:59:59; 2,843 MMSI duy nhất đếm trực tiếp trên 30 file. Manifest báo 217,203 trajectory segments, không phải số tàu duy nhất. |

## Format và trường

- Parquet cleaned có `mmsi` dạng chuỗi; `timestamp_utc` là timestamp timezone-aware UTC; `latitude`, `longitude`, `sog`, `cog` là số thực. Mẫu record đọc được có timestamp UTC và đủ 6 trường cần cho replay.
- Schema còn có cờ `flag_invalid_mmsi`, `flag_invalid_timestamp`, `flag_off_date`, `flag_invalid_position`, `flag_invalid_sog`, `flag_invalid_cog`, `flag_core_valid`, `source_file`, `source_row`.
- `cleaning_summary.csv`: 30/30 ngày COMPLETE, tổng 237,960,745 record. `parquet_validation_full_month.csv`: 30/30 ngày PASS.
- Raw CSV đặt tên thời gian `base_date_time`, không kèm timezone marker trong chuỗi. Dùng `timestamp_utc` chuẩn hóa khi replay; raw giữ làm provenance và cần tuân parser timezone của pipeline nguồn.

## Phạm vi và vấn đề dữ liệu quan sát được

- AIS raw/cleaned ngày có điểm ngoài bbox Houston: mẫu ngày 1 có vị trí New England, Texas, Washington và Gulf Coast. Houston points là lát cắt riêng, không đại diện mọi điểm trong các file raw.
- Houston subset có 2,843 MMSI, 19.66 triệu điểm và 217,203 trajectory segments. Một MMSI có thể có nhiều segment do track breaks.
- Row group đầu ngày 1 có 249 null SOG và 17,716 null COG. Summary toàn ngày có cờ invalid SOG/COG; dùng cờ chất lượng, không coi thiếu là zero hoặc tự động nội suy khi replay.
- Báo cáo chất lượng Houston ghi 91,730 lần bắt đầu lại sau gap >15 phút, 5,585,095 điểm là ứng viên gap 2–15 phút; 17,280,026 điểm nội suy nằm trong file riêng. Cờ chất lượng chỉ để review; không gộp điểm nội suy vào AIS quan sát hoặc ground truth.
- Đây là dữ liệu lịch sử, không phải live feed. Parquet ngày lớn khoảng 220–303 MiB/ngày theo validation report; replay nên đọc theo ngày/bucket.

## Đề xuất

Ưu tiên Parquet `ais_cleaned` cho replay quan sát: timestamp UTC rõ, schema đồng nhất, quality flags và provenance. Áp dụng `flag_core_valid` cùng quy tắc timestamp/as-of đã được thống nhất; phân vùng theo ngày UTC. Giữ raw Zstandard CSV làm provenance. `trajectory_runs/.../points` nhẹ hơn cho demo Houston, nhưng không thay thế raw AIS toàn vùng.

Raw/cleaned AIS replay là chuỗi quan sát theo thời gian. DATASET_FINAL v1.0 là tập encounter đã khóa gồm history/target, tensor, nhãn và split cho huấn luyện/đánh giá. Hai nguồn khác vai trò, không thay thế/trộn lẫn nhau. DATASET_FINAL hiện có trong repo và checksum/integrity đã PASS theo `T03_DATASET_AUDIT.md`.

**Giới hạn T03:** Chỉ inventory và đề xuất nguồn. Không tạo replay engine, clock/session, track manager, pair candidate, map hoặc UI (T08–T09).
**REPLAY_SOURCE_READY: YES** cho nguồn local khả dụng làm đầu vào chuẩn bị replay; không có nghĩa replay integration đã sẵn sàng.
