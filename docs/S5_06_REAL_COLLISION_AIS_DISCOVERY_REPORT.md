# S5-06 — Khảo sát AIS va chạm thật trên máy

Ngày: 2026-11-27

Branch: `s5-integration-final`

Worktree: `C:\Users\MSI\Documents\Codex\2026-11-20\files-pasted-by-the-user-sprint-2\work\s5-integration-final`

HEAD lúc khảo sát: `8f252c522914aa30ba05bd28368ec60cab71c5a6`

## Kết luận

- Tìm thấy hai bộ dữ liệu cục bộ gắn với các vụ va chạm thật đã được NTSB xác nhận: Patrick J Studdert / Clara B và Yangze 7 / Miss Peggy. Mỗi gói có bản tin AIS của cả hai tàu trong đoạn trích trước sự cố.
- Cả hai cặp hiện có **0 anchor chung** đáp ứng đồng thời 10 mốc lịch sử cách nhau một phút với as-of source age 0–60 giây. Không có cặp nào đủ điều kiện kiểm chứng M5a + CC-DRI V4 theo temporal contract hiện có.
- **Không có vụ nào `READY_FOR_COLLISION_REPLAY`.** Yangze 7 / Miss Peggy là ứng viên ưu tiên cho lần kiểm tra nguồn kế tiếp, nhưng chỉ sau khi giải quyết độ phủ history và xác minh độc lập MMSI với tàu. Patrick / Clara không phù hợp với kiểm chứng cảnh báo sớm theo dữ liệu trích hiện có vì AIS của Patrick quá thưa.
- NOAA xác định timestamp AIS là UTC. Tệp CSV đã trích ghi timestamp không kèm hậu tố timezone; chuẩn hóa phải gắn UTC theo tài liệu nguồn, không suy diễn từ giờ máy.
- Báo cáo NTSB xác nhận sự cố và tên tàu. Mapping MMSI trong hai bộ AIS dựa trên audit cục bộ, tên/call sign/IMO trong AIS; báo cáo NTSB không cung cấp MMSI để xác nhận mapping này trực tiếp. Vì vậy, nguồn archive đã xác định được nhưng provenance của liên kết **MMSI ↔ tàu trong hồ sơ** còn một phần chưa kiểm chứng.
- Không chạy model, không đánh giá CPA/CC-DRI, không thay threshold, không đọc Test labels/future/displacement trong `DATASET_FINAL`, không sửa source hoặc dữ liệu gốc.

## Danh mục dữ liệu tìm thấy

| Vụ việc | Dữ liệu cục bộ | Nguồn gốc | Hồ sơ sự cố | AIS hai tàu |
|---|---|---|---|---|
| Patrick J Studdert / Clara B | `C:\Users\MSI\Downloads\PATRICK_CLARA_AIS_AUDIT_PACKAGE.zip`; pre-event CSV `ais_pre_collision_30min.csv` có 36 bản tin. Raw archive cục bộ: `C:\Users\MSI\Downloads\ais-2024-12-30.tgz` (199,639,097 bytes; thực tế Zstandard CSV, SHA-256 `4eef0fa761addd54211c6823b529c31f6d58f8a9ade6e94b7bd17b423f7dd8c6`). | NOAA MarineCadastre AIS; archive cục bộ khớp hash được ghi trong audit nguồn. Pre-event extract: Patrick 11 bản tin, Clara 25. | NTSB `MIR-26-13`, vụ `DCA25FM012`, Lower Mississippi River gần Luling, Louisiana. NTSB ghi sự cố khoảng 19:34 CST ngày 29/12/2024; thời điểm 19:34:27 trong audit package là mốc danh nghĩa, không phải giây chính xác do NTSB công bố. | Có: Patrick J Studdert MMSI `367534690`; Clara B MMSI `636023978`, IMO `9304083`. Mapping MMSI lấy từ audit/AIS; NTSB không ghi MMSI. |
| Yangze 7 / Miss Peggy | `C:\Users\MSI\Downloads\YANGZE7_MISSPEGGY_AIS_AUDIT_PACKAGE.zip`; pre-event CSV `YANGZE7_MISSPEGGY_NOAA_AIS_pre_collision_30min.csv` có 53 bản tin. Raw archive cục bộ: `C:\Users\MSI\Downloads\ais-2024-07-19.csv.zst` (265,691,740 bytes; SHA-256 `da02055f4ed834a03d33138ed738c051e3ce364b8f8299e449080518bf2d0c11`). | NOAA MarineCadastre AIS; archive cục bộ khớp hash được ghi trong audit nguồn. Pre-event extract: Yangze 7 26 bản tin, Miss Peggy 27. | NTSB `MIR-26-24`, vụ `DCA24FM051`, Houston Ship Channel gần Lynchburg, Texas. Event sequence ghi va chạm 14:03:35 CDT ngày 19/07/2024. | Có: Yangze 7 MMSI `636016708`, IMO `9718911`; Miss Peggy MMSI `366935050`. Mapping MMSI lấy từ audit/AIS; báo cáo NTSB không nêu MMSI của hai tàu. |

Tìm kiếm có mục tiêu trong Downloads, Desktop `PROJECT_AIT3040`, `NaviSight_Research`, `Môn học Dự án` và thư mục làm việc AIT3040 không cho thấy thêm gói collision-case AIS có thể xác nhận ngoài hai bộ trên. Các archive AIS Denmark/AISDK và pilot nghiên cứu khác là nguồn AIS thường lệ, không phải hồ sơ va chạm được xác nhận. Một số archive AIS ngày khác có trên máy nhưng chưa có căn cứ gắn chúng với một sự cố cụ thể; không phân loại thành collision case.

## Hồ sơ và timezone

- [NTSB MIR-26-13 — Patrick J Studdert / Clara B](https://www.ntsb.gov/investigations/AccidentReports/Reports/MIR2613.pdf) xác nhận tên tàu, khu vực và sự cố khoảng 19:34 CST ngày 29/12/2024. Audit cục bộ dùng 19:34:27 CST làm mốc danh nghĩa để tạo pre-event extract. Do NTSB chỉ ghi “about 1934 CST”, kết quả neo giây cho cặp này không phải thời điểm sự cố chính xác.
- [NTSB MIR-26-24 — Yangze 7 / Miss Peggy](https://www.ntsb.gov/investigations/AccidentReports/Reports/MIR2624.pdf) xác nhận va chạm trên Houston Ship Channel; event sequence ghi 14:03:35 CDT ngày 19/07/2024.
- [NOAA MarineCadastre AIS Data Dictionary](https://coast.noaa.gov/data/marinecadastre/ais/data-dictionary.pdf) định nghĩa `BaseDateTime`/`base_date_time` là thời gian đầy đủ theo UTC và liệt kê MMSI, latitude, longitude, SOG, COG.
- [NOAA MarineCadastre AIS FAQ](https://coast.noaa.gov/data/marinecadastre/ais/faq.pdf) mô tả timestamp do trạm bờ thêm bằng đồng hồ UTC và nguồn AIS dựa trên U.S. Coast Guard NAIS.
- Đổi mốc NTSB sang UTC: Yangze/Miss Peggy `2024-07-19 19:03:35Z`; Patrick/Clara khoảng `2024-12-30 01:34Z`. Mốc `01:34:27Z` của Patrick/Clara chỉ là anchor danh nghĩa lấy từ audit package.

## Kiểm tra chất lượng các đoạn pre-event

Chỉ dùng hai thành viên pre-collision CSV để tính độ phủ. Không sử dụng full-day observations sau mốc sự cố để chọn anchor hoặc làm input. Các hàng trong đoạn trích có timestamp, MMSI, latitude, longitude, SOG và COG; không có missing field, tọa độ vượt miền hợp lệ, duplicate `(MMSI, timestamp)` hoặc timestamp đảo thứ tự theo từng MMSI. Không có conflicting duplicate key trong các đoạn này.

| Vụ / tàu | Số bản tin | Missing trường lõi | Lat/Lon không hợp lệ | Duplicate/conflict | Đảo thứ tự | Median / max gap | Nhận xét |
|---|---:|---:|---:|---:|---:|---:|---|
| Patrick J Studdert | 11 | 0 | 0 | 0 / 0 | 0 | 179.5 / 185 giây | AIS quá thưa cho 10 mốc một phút với age tối đa 60 giây. |
| Clara B | 25 | 0 | 0 | 0 / 0 | 0 | 70 / 91 giây | Một số anchor đơn tàu đạt freshness, nhưng không có anchor chung với Patrick. |
| Yangze 7 | 26 | 0 | 0 | 0 / 0 | 0 | 70 / 80 giây | Một số anchor đơn tàu đạt freshness, nhưng không có anchor chung với Miss Peggy. |
| Miss Peggy | 27 | 0 | 0 | 0 / 0 | 0 | 68.5 / 72 giây | Khoảng cách bản tin vượt 60 giây khiến không có chuỗi 10 mốc hợp lệ trong anchor scan. |

Đây là kiểm tra đoạn dữ liệu đã trích, không phải chứng nhận toàn bộ raw archive. Hợp lệ về miền số học không chứng minh mọi điểm nằm trên mặt nước; vị trí sự kiện và tên vùng nước được đối chiếu với NTSB, chưa chạy sea-mask cho từng điểm.

## Độ phủ temporal, tensor và G11

Đối chiếu [`contracts/temporal_contract.json`](../contracts/temporal_contract.json): history offsets là −9…0 phút; tại mỗi grid time chỉ chọn bản tin mới nhất không sau grid, age 0–60 giây kể cả hai biên; cho phép reuse một bản tin; thiếu history thì không nội suy và không dùng bản tin tương lai. Anchor scan dưới đây xét các anchor từng phút từ T−21 đến T−1 trong đoạn 30 phút, để cả 10 grid point nằm trong extract. Riêng anchor T−15…T−21 có toàn bộ forecast horizon +1…+15 kết thúc không muộn hơn mốc sự cố.

| Vụ / tàu | Anchor có đủ 10 mốc, age ≤60 giây | Anchor ghép đủ cho cả hai tàu | Anchor ghép T−21…T−15 có toàn bộ horizon trước sự cố |
|---|---:|---:|---:|
| Patrick J Studdert | 0/21 |  |  |
| Clara B | 10/21 |  |  |
| Yangze 7 | 10/21 |  |  |
| Miss Peggy | 0/21 |  |  |
| **Cả cặp** | — | **0/21 cho mỗi vụ** | **0/7 cho mỗi vụ** |

Các anchor đơn tàu không thể dùng để tính nguy cơ encounter giữa hai tàu. Không tạo tensor `[2,10,4]`, không padding, không nội suy và không dùng mốc sau anchor. G11 semantic validator chưa chạy trên `TrackSnapshot` đã chuẩn hóa; vì không có anchor ghép hợp lệ, **G11 readiness cho collision replay là `NOT_READY / NOT_VERIFIED`**. Trường MMSI có dạng 9 chữ số nên có thể xây dựng mapping định danh vật lý, nhưng cần xác minh mapping vụ–tàu và provenance trước khi phát hành snapshot `is_simulated=false`.

Đối với Patrick/Clara, giây chính xác của sự cố không được NTSB công bố; độ phủ tính theo mốc danh nghĩa trong audit package. AIS Patrick thưa đến mức kết luận không đủ history không phụ thuộc vài chục giây sai khác của anchor.

## Tính độc lập và rò rỉ dữ liệu

- Kiểm tra metadata/manifests và báo cáo có thể tìm kiếm trong worktree không tìm thấy case ID, tên hoặc MMSI của hai cặp trong `DATASET_FINAL`, tài liệu chọn M5a, calibration hoặc benchmark T15. `DATASET_FINAL` là bộ dữ liệu nguồn khác; không đọc Test labels, future trajectories hoặc displacement artifacts.
- Hai audit package ghi không chạy model, inference, CPA/DCPA/TCPA hoặc threshold evaluation trên các vụ này. Chúng là evidence kiểm tra dữ liệu, không phải kết quả kiểm chứng khả năng cảnh báo.
- Một lần rà soát discovery trước đó trong cùng lịch sử làm việc đã hiển thị một trường hậu sự kiện tên `near_after` từ QA JSON của gói Yangze/Miss Peggy. Giá trị đó không được dùng trong anchor scan, đánh giá chất lượng hoặc lựa chọn case ở báo cáo này; tuy nhiên người thực hiện đã thấy metadata hậu sự kiện nên không thể tuyên bố quy trình case selection mù.
- Việc không tìm thấy tên trong các tài liệu có thể tìm kiếm **không chứng minh** các case chưa từng ảnh hưởng tới lựa chọn model/threshold: chưa có access log/blinding record đầy đủ và chưa đối chiếu định danh trên toàn bộ artifact nhị phân. Vì vậy `INDEPENDENT_CASE_STUDY=NOT_VERIFIED` cho cả hai vụ.
- Nếu được phê duyệt đánh giá sau này, cần xem đây là retrospective/unblinded case study hoặc dùng một evaluator độc lập không tiếp xúc post-event evidence. Hồ sơ NTSB và quan sát sau anchor chỉ được giữ làm ground truth đánh giá tách biệt sau khi input/anchor đã khóa; không đưa vào model input hoặc lựa chọn anchor.

## Ma trận readiness và khuyến nghị

| Vụ va chạm | AIS hai tàu | Hồ sơ xác nhận | History hợp lệ | G11 | Tính độc lập | Readiness | Khuyến nghị |
|---|---|---|---|---|---|---|---|
| Patrick J Studdert / Clara B | Có | Có — NTSB MIR-26-13 | Không: 0 anchor ghép; Patrick 11 bản tin, max gap 185 giây | `NOT_READY` | `NOT_VERIFIED` | `INSUFFICIENT_HISTORY` + `PROVENANCE_NOT_VERIFIED` cho mapping MMSI ↔ tàu | Không dùng làm kiểm chứng cảnh báo sớm hiện tại. Chỉ xem xét lại nếu có AIS nguồn khác đủ dày và mốc sự cố được làm rõ hơn. |
| Yangze 7 / Miss Peggy | Có | Có — NTSB MIR-26-24 | Không: 0 anchor ghép; Miss Peggy 0/21 anchor đơn tàu đạt ngưỡng | `NOT_READY` | `NOT_VERIFIED` | `INSUFFICIENT_HISTORY` + `PROVENANCE_NOT_VERIFIED` cho identity crosswalk | Ưu tiên cho một lần kiểm tra nguồn cục bộ có giới hạn nếu có archive AIS gốc/high-rate khác; hiện chưa đủ điều kiện replay/benchmark. |

**READY_FOR_COLLISION_REPLAY: none.** Không có đủ căn cứ chọn 3–5 vụ độc lập. Yangze/Miss Peggy là ứng viên tốt hơn về hồ sơ sự cố và độ dày dữ liệu thô trong đoạn trích, nhưng điều đó không thay thế yêu cầu anchor ghép hợp lệ hay chứng minh độc lập.

### Dữ liệu còn thiếu

1. Tối thiểu một anchor chung có đủ 10 grid observations hợp lệ của cả hai tàu theo source-age 0–60 giây; ưu tiên nhiều anchor và dữ liệu cho toàn bộ horizon +15 phút.
2. Crosswalk MMSI ↔ vessel được xác minh độc lập bằng nguồn metadata/hồ sơ bổ sung. NOAA xác nhận nguồn AIS/timestamp, nhưng NTSB reports không nêu MMSI.
3. Bằng chứng blinding/access history để xác nhận case không được dùng chọn model, calibration hoặc threshold; nếu không có thì chỉ báo cáo như retrospective case study không độc lập.
4. Sea-mask/geospatial QC cho điểm AIS cụ thể và một phép chuẩn hóa EN deterministically tạo ra snapshot/tensor; chưa thực hiện ở task này.

`DOWNLOAD_REQUIRED=NO` cho bước discovery/bounded follow-up: raw NOAA archive của cả hai ngày đã có trên máy. Đoạn trích 30 phút hiện có không đạt độ phủ cặp. Chưa chứng minh rằng cần tải nguồn mới; trước tiên cần quyết định có thực hiện lượt trích lọc pre-event có giới hạn từ archive local và xác minh lại MMSI hay không. Nếu không tìm được anchor hợp lệ ở đó, cần nguồn quan sát dày hơn hoặc một vụ khác; dung lượng/nguồn bổ sung chưa thể ước tính từ evidence hiện có.

## Kế hoạch bước tiếp theo

1. Trung review báo cáo và quyết định có cho phép một lượt đọc có giới hạn, chỉ giữ record timestamp không sau mốc sự cố từ hai raw archive đã có hay không.
2. Xác minh crosswalk MMSI/tên tàu bằng nguồn chính thức hoặc metadata độc lập; ghi rõ hash, schema, timezone mapping và quy tắc duplicate.
3. Chạy một anchor scanner chỉ dùng observations tới từng anchor, áp dụng đúng as-of contract, không nội suy/padding; xuất danh sách anchor đủ điều kiện và bằng chứng G11 cho candidate snapshot.
4. Khóa trước case, anchor, provenance và independent/retrospective status. Chỉ sau phê duyệt riêng mới chạy inference M5a + Risk V4 và so sánh với ground truth giữ tách biệt. Không chỉnh Model Lock, threshold hay Contract V1.
5. Nếu không có anchor ghép đạt chuẩn, không ép dữ liệu và không benchmark case này; tìm nguồn hoặc case khác theo phê duyệt.

## Phạm vi và trạng thái

- Đã đọc các báo cáo S5-05/S5-06A, temporal/G11/Contract V1 liên quan và audit package metadata cần thiết.
- History scan chỉ đọc hai thành viên CSV `pre_collision_30min.csv`; không dùng observations hậu sự kiện, không đọc Test labels/future/displacement, không chạy model.
- Không tải dữ liệu, không sửa raw AIS, `DATASET_FINAL`, source, Model Lock, Risk V4, thresholds hoặc Contract V1.
- Giữ nguyên các thay đổi S5 chưa commit. Không commit, push hoặc merge.

**Kết quả:** `COLLISION_CASES_FOUND=2`; `CONFIRMED_REAL_COLLISION_CASES=2`; `BOTH_VESSELS_AIS_AVAILABLE=YES`; `VALID_PAIRED_HISTORY_ANCHORS=0`; `G11_READINESS=NOT_READY`; `INDEPENDENT_CASE_STUDIES=NOT_VERIFIED`; `READY_FOR_COLLISION_REPLAY=NONE`; `DOWNLOAD_REQUIRED=NO_FOR_BOUNDED_LOCAL_FOLLOW_UP`.
