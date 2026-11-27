# S5-06A — Báo cáo sẵn sàng nguồn AIS thật

Ngày khảo sát: 2026-11-27
Branch: s5-integration-final
Worktree: C:\Users\MSI\Documents\Codex\2026-11-20\files-pasted-by-the-user-sprint-2\work\s5-integration-final

## Kết luận

- Tìm thấy AIS thật dạng raw CSV trên máy, nổi bật là ba archive AISDK ngày 01–03/10/2025 trong Downloads. Cùng các archive này đã được dùng trong audit AIS Đan Mạch đang có trên máy.
- Nguồn phù hợp nhất để chuẩn bị S5-06B là ba archive AISDK, sử dụng vùng Great Belt hoặc Skagerrak đã có thống kê track từ audit. Đây là lựa chọn có điều kiện; chưa đủ bằng chứng để đưa thẳng vào runtime.
- Không có nguồn nào hiện đạt READY_FOR_REPLAY đầy đủ theo G11. Blocker chính là timestamp nguồn không ghi timezone; UTC chỉ là giả định từ tài liệu thứ cấp. Quyền phân phối/upstream metadata chưa xác minh độc lập và xử lý duplicate/conflicting keys cần đối chiếu chính sách Contract V1.
- Có thể tiếp tục đánh giá local source mà không tải thêm dữ liệu. Exact replay anchor có 3–5 tàu, đặc biệt trong Kattegat, chưa được chọn/xác minh theo quy tắc chỉ dùng observations tại anchor.
- Không mở hoặc deserialize Test labels, future trajectories hay displacement artifacts. Không sửa dữ liệu gốc, source S5, Model Lock, Risk V4, thresholds hoặc Contract V1.

## Data inventory

| Source | Path | Format | Size | Time range | Vessel count | Provenance | Replay suitability |
|---|---|---|---:|---|---|---|---|
| AIS Denmark / AISDK ngày 01–03/10/2025 | C:\Users\MSI\Downloads\aisdk-2025-10-01.zip; C:\Users\MSI\Downloads\aisdk-2025-10-02.zip; C:\Users\MSI\Downloads\aisdk-2025-10-03.zip | Mỗi ZIP chứa một CSV UTF-8-SIG | 599,933,019; 620,060,722; 618,868,680 bytes; tổng 1,838,862,421 bytes. CSV giải nén khoảng 9,125,206,356 bytes | Theo ba file và audit: 2025-10-01 đến 2025-10-03; mỗi archive ứng với một ngày. Exact first/last timestamp toàn file chưa được quét lại | Audit ghi 50,418,897 dòng raw. Unique MMSI toàn raw chưa tính. Sau clean trong các bbox đã chọn: 3,020–3,254 MMSI/ngày; không cộng các ngày/vùng thành số tàu duy nhất | Source integrity manifest ghi SHA-256 từng ZIP khớp bản đầu vào của audit; không có official checksum. Tài liệu gọi nguồn AISDK/Denmark; upstream chính thức và điều khoản phân phối chưa xác minh độc lập. CSV không ghi timezone | **PROVENANCE_NOT_VERIFIED**. Raw cần clean/QC; có thể chuẩn bị replay sau khi khóa timezone, duplicate và G11 |
| AIS raw theo ngày, các archive .csv.zst | C:\Users\MSI\Downloads\ais-2023-01-09.csv.zst; ais-2023-01-22.csv.zst; ais-2024-07-19.csv.zst | Zstandard-compressed CSV | 230,313,757; 213,327,122; 265,691,740 bytes; giải nén lần lượt khoảng 801, 741, 872 MiB | Ngày theo tên archive; exact time range chưa xác minh | NOT_VERIFIED | Chỉ có tên file/metadata nén; upstream và license chưa đối chiếu | **NEEDS_CLEANING**; không ưu tiên cho demo Denmark |
| AIS raw ngày 30/12/2024 | C:\Users\MSI\Downloads\ais-2024-12-30.tgz | Tên .tgz, thực tế Zstandard CSV | 199,639,097 bytes; khoảng 690 MiB giải nén | Tên archive chỉ ra 2024-12-30; sample bắt đầu 00:00:02–00:00:04; full range NOT_VERIFIED | NOT_VERIFIED | Header/sample và assessment local khớp schema AIS raw; không xác nhận nguồn cấp hoặc timezone | **NEEDS_CLEANING**; nguồn Hoa Kỳ không phải lựa chọn ưu tiên cho demo vùng Đan Mạch |
| AIS static metadata | C:\Users\MSI\Downloads\ais_static.zip | ZIP chứa CSV metadata/từ điển AIS; không có stream timestamp-position | 255,019 bytes compressed | Không có thời gian quan sát | NOT_APPLICABLE | Archive local; upstream/license chưa xác minh | **NOT_SUITABLE** độc lập làm replay; chỉ có thể hỗ trợ metadata sau provenance review |
| Curated audit packages hai tàu | C:\Users\MSI\Downloads\PATRICK_CLARA_AIS_AUDIT_PACKAGE.zip; C:\Users\MSI\Downloads\YANGZE7_MISSPEGGY_AIS_AUDIT_PACKAGE.zip | ZIP chứa audit JSON và CSV full-day/pre-collision | 11,070 và 28,005 bytes | NOT_VERIFIED trong lượt này | 2 tên tàu mỗi gói theo package; không phải census nguồn | Gói audit local; upstream/provenance chưa xác minh lại | **NOT_SUITABLE** làm nguồn chọn demo nguy hiểm: tình huống đã được tuyển chọn, chỉ 2 tàu; không đọc nội dung pre-collision || AIS cleaned Houston trong T03 inventory | Đường dẫn tương đối được ghi là data/processed/ais_cleaned/year=2024/month=11/day=DD/part-00000.parquet; vị trí gốc đã bị lược khỏi tài liệu | Parquet theo ngày | 30 file; dung lượng chính xác NOT_VERIFIED tại vị trí hiện tại | 2024-11-01 đến 2024-11-30 theo T03 report | 237,960,745 bản ghi cleaned toàn tháng; Houston points có 2,843 MMSI theo inventory. Không xác nhận file còn ở đâu trên máy | T03 report ghi 30/30 ngày COMPLETE và Parquet validation 30/30 PASS; vị trí gốc không xác định được trong các thư mục đã kiểm tra | **PROVENANCE_NOT_VERIFIED** cho phiên này do không xác nhận được local path; không dùng để đề xuất demo trực tiếp |
| DATASET_FINAL v1.0 | C:\Users\MSI\Desktop\PROJECT_AIT3040\DATASET_FINAL | Locked Parquet/NumPy tensors, manifests, labels | Đã kiểm tra tên file/manifest metadata; không đọc nội dung Test | Các split encounter, không phải raw continuous feed | Dataset card: 3,595 encounters; không phải số tàu hoạt động đồng thời trong replay | Nghiên cứu đã locked; manifests chứa nguồn/split và artifacts đánh giá | **NOT_SUITABLE** làm replay source. Giữ nguyên; không đọc Test labels/future/displacement |

### AISDK schema và kiểm tra sơ bộ

Đã mở stream sample từ entry CSV trong ZIP ngày 01/10, không giải nén ra đĩa. Header ghi:

- Timestamp, Type of mobile, MMSI, Latitude, Longitude, Navigational status, ROT, SOG, COG, Heading, cùng trường IMO/name/type/kích thước/destination và metadata nguồn.
- Có đủ trường lõi timestamp, identity, tọa độ, SOG và COG để tạo TrackSnapshot sau chuẩn hóa.
- Sample thô có loại Base Station, MMSI không đủ chín chữ số và một vị trí latitude=91. Đây là ví dụ về dữ liệu cần loại/QC; không dùng dòng này như tàu replay.
- Audit 3 ngày ghi thiếu SOG 1,122,405–1,190,349 dòng/ngày và thiếu COG 2,071,587–2,371,708 dòng/ngày. Không được đổi missing thành 0 hoặc nội suy từ tương lai.
- Audit ghi 4,597,740–4,897,147 duplicate rows đã loại mỗi ngày và 33,260–41,691 conflicting keys. Chưa xác minh quy tắc xử lý conflicting (MMSI,timestamp) khớp D-03: giữ stable-first với duplicate giống hệt, loại toàn nhóm khi xung đột.
- Audit đã chuẩn hóa/sắp track theo MMSI và timestamp, nhưng raw file ordering đầy đủ chưa được kiểm chứng trong khảo sát này.
- Hashes trong source-integrity manifest:
  - 2025-10-01: 047bd25d379b646e45678c0c8146b64c681a9d943a0f4173506fe9e341c91043
  - 2025-10-02: 7dc0284fa1bab9e248480fcf712375a7b7140903bd115c7ab343b6bce9b30464
  - 2025-10-03: 8bb40809a626d49bbfb242160e920e38a56c3d13ece4b8002be482838eafa88d

## Candidate replay windows và phạm vi địa lý

Audit local về nguồn AISDK báo có track pool đa tàu với tối thiểu 25 mốc trong một số bbox/ngày. Đây là evidence về khả năng nguồn chứa track đủ dài, không phải lựa chọn encounter theo nhãn nguy hiểm. Số track/MMSI sau đây là thống kê riêng từng bbox trong audit; một MMSI có thể xuất hiện ở nhiều ngày hoặc vùng:

| Candidate ngày và vùng | Track có ít nhất 25 mốc | MMSI trong vùng | Trạng thái chọn anchor |
|---|---:|---:|---|
| 2025-10-01 — Great Belt | 1,123 | 424 | Chỉ là candidate theo ngày/vùng; exact 3–5 vessel anchor NOT_VERIFIED |
| 2025-10-01 — Skagerrak | 570 | 248 | Chỉ là candidate theo ngày/vùng; exact anchor NOT_VERIFIED |
| 2025-10-02 — Great Belt | 1,144 | 420 | Chỉ là candidate theo ngày/vùng; exact anchor NOT_VERIFIED |
| 2025-10-02 — Skagerrak | 485 | 213 | Chỉ là candidate theo ngày/vùng; exact anchor NOT_VERIFIED |
| 2025-10-03 — Great Belt | 1,041 | 369 | Chỉ là candidate theo ngày/vùng; exact anchor NOT_VERIFIED |
| 2025-10-03 — Skagerrak | 329 | 170 | Chỉ là candidate theo ngày/vùng; exact anchor NOT_VERIFIED |

Các số track 25 mốc thể hiện khả năng dữ liệu có cửa sổ đủ dài; không chứng minh đồng thời 3–5 tàu ở một anchor cụ thể. Audit 3 ngày có danh sách bbox cho Great Belt, Oresund và Skagerrak; cấu hình loại bbox Kattegat (lat 56–58, lon 10–13) khỏi phần candidate extraction. Vì vậy:

- AISDK raw archive là nguồn Denmark rộng; sample đầu file có record ở gần Kattegat nhưng là Base Station, không phải bằng chứng về tàu hoặc replay window tại đó.
- Không có Kattegat window nào được xác minh trong audit candidate đã đọc. Nếu Kattegat là yêu cầu demo, cần một lượt chọn anchor riêng chỉ dùng raw observations đến anchor.
- Từ dữ liệu ngày 01–03/10, có thể dự kiến replay trong ngày với lịch sử tối thiểu 10 mốc và tiếp tục playback 15 phút; độ liên tục thực tế, age từng mốc và 3–5 tàu đồng thời cần kiểm tra trên anchor được chọn.
- Không dùng các trường/metrics dựa trên future (dmin, CPA sau anchor, EASY/MEDIUM/HARD hoặc nhãn) để chọn cảnh huống. Các báo cáo audit có các chỉ số đánh giá offline; chúng chỉ được trích dẫn ở đây cho inventory/provenance, không dùng làm tiêu chí chọn demo.

## G11 và source-age readiness

Contract V1 yêu cầu structural validation và semantic G11; G11 một mình không chứng minh mọi invariant temporal/session.

| Yêu cầu | Evidence hiện có | Trạng thái |
|---|---|---|
| Identity vật lý: physical_mmsi:<9 digits> khớp MMSI, real track is_simulated=false | AISDK có trường MMSI. Audit lọc MMSI chín chữ số; raw cũng có base-station/invalid records. Không xác minh ownership của MMSI | PARTIAL |
| Timestamp gốc và timestamp đã chọn | CSV có Timestamp; audit source pointers lưu source timestamp cùng grid timestamp | PARTIAL; raw timezone chưa được xác nhận |
| UTC / source-age | Audit giả định UTC từ tham chiếu thứ cấp, dùng as-of tối đa 60 giây. Audit báo P95 age 18–19 giây, max 60 giây | PARTIAL; chưa chứng minh UTC từ metadata chính thức của nguồn |
| Vị trí hợp lệ và ở vùng nước phù hợp | Audit có valid latitude/longitude QC và bbox nghiên cứu xấp xỉ. Sample raw có giá trị invalid | PARTIAL; chưa có sea-mask/shoreline check cho candidate anchor |
| SOG/COG và missing | Trường có trong CSV, missing counts lớn như trên | NEEDS_CLEANING; thiếu phải thành quality/status, không bịa giá trị |
| Duplicate và ordering xác định | Audit có duplicate/conflicting-key counts; không chứng minh conflict policy G11/D-03 | NOT_VERIFIED |
| Provenance/identity ownership | ZIP hash giữ nguyên so với bản đầu vào audit; không có official checksum hoặc source/license evidence độc lập | NOT_VERIFIED |

**G11_READINESS=CONDITIONAL_NOT_READY_FOR_RUNTIME.** Có thể chuẩn bị adapter isolated sau khi giải quyết timezone, duplicate, identity/provenance và water/QC gates; chưa đưa raw AIS vào provider production.

## Nguồn được khuyến nghị và dữ liệu còn thiếu

**Đề xuất nguồn S5-06B:** bộ ba AISDK ZIP 01–03/10/2025 tại Downloads; ưu tiên Great Belt hoặc Skagerrak vì audit hiện có source-quality evidence ở các vùng này. Không gọi các artifact audit là API/provider sẵn sàng. Nếu cần đúng Kattegat, chưa có candidate window được xác minh.

**Chưa cần tải thêm dữ liệu** để bắt đầu xác minh kỹ thuật có giới hạn: local archive đã có 3 ngày và hơn 50 triệu raw records theo inventory. Trước khi đưa vào runtime cần bổ sung hoặc xác nhận:

1. Tài liệu upstream chính thức cho archive AISDK, điều khoản sử dụng/phân phối và checksum chính thức nếu có.
2. Bằng chứng timezone của Timestamp; nếu không có, quyết định nguồn/timestamp mapping theo Contract V1 trước khi gán UTC.
3. Quy tắc deterministic cho conflicting duplicate keys và stable raw row/source identity.
4. Observation-only anchor scan để xác nhận cùng 3–5 MMSI có 10 history points, source-age 0–60 giây, vị trí trên mặt nước và đủ 15 phút dữ liệu playback. Không đọc future labels/target để chọn.
5. Kiểm chứng quyền dùng dữ liệu cho demo/chia sẻ sản phẩm. Nếu cần ngày/khu vực khác, Trung quyết định trước khi tải; report này không đề xuất dung lượng ngoài các archive đã có căn cứ.

## Đề xuất synthetic fixture trong vùng biển thực

Phương án bổ sung, chưa tạo: fixture synthetic có 3–5 tàu di chuyển trong bbox Great Belt đã dùng trong audit (lat 54.5–56.0, lon 10.0–11.6), với các quỹ đạo hình học crossing, parallel và chậm/đứng, kèm một trường hợp thiếu history. Trước khi chọn tọa độ cụ thể cần xác minh bằng coastline/sea mask để không đặt điểm trên đất liền.

Gán provenance synthetic rõ ràng: is_simulated=true, stable ID theo namespace Contract V1 simulated:<dataset>:<stable-id>, không gán MMSI giả. Tạo observation/fixture theo thời gian, sau đó để M5a và Risk V4 tính forecast/score/decision thông thường; không hardcode risk score, alert hay kết quả mong muốn. Giữ S5-01 fixture nguyên vẹn. Fixture này chỉ là backup/demo supplement, không thay Real AIS validation.

## Kế hoạch S5-06B ngắn

1. Đóng gói quyết định provenance/rights/timezone/MMSI/duplicate cho AISDK; giữ raw read-only và pin hashes.
2. Tạo observation-only replay window selector trên Great Belt/Skagerrak (hoặc riêng Kattegat nếu được yêu cầu), chỉ đọc đến anchor để chọn 3–5 tàu; xác thực history, age, UTC, ID và vùng nước.
3. Map CSV → normalized observation → TrackSnapshot theo Contract V1; QC/drop/partial-history semantics được test riêng. Không dùng Test labels, future trajectories hoặc displacement.
4. Tích hợp provider sau review contract/interface, với seek/reset/session isolation và provenance rõ; giữ nguyên Model Lock/Risk V4/thresholds.
5. Demo synthetic fixture trong vùng biển thực nếu raw source còn chờ phê duyệt; ghi rõ synthetic và không thay S5-01.

## Phạm vi đã kiểm tra

- Đọc S5-05 report, T08/T09 readiness, T03 source inventory, DATASET_FINAL card/manifest metadata, AIS Denmark 3-day inventory/report/source-integrity và G11/Contract V1 rules.
- Kiểm tra danh sách file có mục tiêu tại Desktop PROJECT_AIT3040, DATASET_FINAL, Downloads và thư mục nghiên cứu AIS Đan Mạch đã được provenance dẫn chiếu.
- Mở header/sample raw AISDK trong ZIP stream và sample raw Zstandard CSV; không giải nén/ghi dữ liệu ra ổ đĩa.
- Không mở dữ liệu Test, không đọc labels/future/displacement, không chạy test, training, calibration, T15 benchmark hoặc full regression.
- Không sửa source, dataset, config hoặc các thay đổi S5 chưa commit. Chỉ báo cáo này được tạo.

## Trạng thái

- REAL_AIS_SOURCE_FOUND=YES — AISDK Denmark raw archives present locally.
- RECOMMENDED_SOURCE=CONDITIONAL — AISDK 01–03/10/2025; Great Belt/Skagerrak first; Kattegat anchor NOT_VERIFIED.
- G11_READINESS=CONDITIONAL_NOT_READY_FOR_RUNTIME.
- MULTI_VESSEL_REPLAY_READY=CONDITIONAL — multi-vessel/long-track availability is supported by prior source audit; exact anchor concurrence remains NOT_VERIFIED.
- DOWNLOAD_REQUIRED=NO for the bounded local-source assessment and initial S5-06B planning.
- S5_06B_IMPLEMENTATION_READY=NO_PENDING_PROVENANCE_AND_G11_GATES.
- CODE_MODIFIED=NO. No commit, push or merge.
