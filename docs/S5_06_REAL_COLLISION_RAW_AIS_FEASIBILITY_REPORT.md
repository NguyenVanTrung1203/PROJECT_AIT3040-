# S5-06 — Khả năng dùng raw AIS cho replay va chạm thật

Ngày khảo sát: 2026-11-27

Branch: `s5-integration-final`

Worktree: `C:\Users\MSI\Documents\Codex\2026-11-20\files-pasted-by-the-user-sprint-2\work\s5-integration-final`

HEAD: `8f252c522914aa30ba05bd28368ec60cab71c5a6`

## Kết luận điều hành

- Đã stream hai archive NOAA gốc, chỉ giữ các observation của bốn MMSI trong tối đa 120 phút trước mốc sự cố. SHA-256 khớp hash đã ghi trong discovery report. Không ghi extraction ra ổ đĩa.
- Hai đoạn CSV 30 phút trong audit package khớp raw chính xác: Yangze/Miss Peggy `53/53` hàng; Patrick/Clara `36/36` hàng. Không có hàng bị audit package bỏ sót, hàng thừa hoặc khác payload lõi.
- Với history 10 grid point, as-of age `0–60s`, Yangze/Miss Peggy có `0/21` cặp anchor trong 30 phút, `0/51` trong 60 phút và `7/111` trong 120 phút. Anchor hợp lệ gần sự cố nhất cách sự cố 60 phút. Không có anchor ghép hợp lệ trong 15 phút trước va chạm.
- Patrick/Clara không có cặp anchor hợp lệ trong cả ba khoảng. Patrick có AIS thưa: gap median `180s`, max `362s` trong 120 phút quan sát được. Archive ngày 30/12 chỉ phủ từ 00:00 UTC; thiếu khoảng `25 phút 33 giây` đầu của cửa sổ 120 phút danh nghĩa, nhưng thiếu đoạn đầu này không giải thích được tần suất thấp sát sự cố.
- Nguyên nhân chính là tần suất AIS raw không đáp ứng ngưỡng freshness hiện hành. Nới freshness lên 90/120 giây chỉ được tính như sensitivity chẩn đoán; không thay đổi temporal contract.
- Có thể tạo hai candidate TrackSnapshot của Yangze/Miss Peggy tại anchor `2024-07-19 18:03:35Z` (T−60 phút). Structural schema, G11 và temporal validation đều PASS; biểu diễn common EN theo coordinate contract là hữu hạn. Đây là kiểm chứng cấu trúc của snapshot, **không** xác nhận MMSI ngoài đời, water-mask, cảnh báo va chạm hay hiệu năng model.
- **Yangze/Miss Peggy: `CONDITIONAL_READY` cho bước kiểm chứng dữ liệu isolated; chưa sẵn sàng đánh giá cảnh báo va chạm gần thời điểm sự cố.** **Patrick/Clara: `INSUFFICIENT_RAW_AIS_FREQUENCY`.** Không chạy M5a, Risk V4 hoặc benchmark.

## Phạm vi và cách trích xuất

Đọc [`S5-06 discovery report`](S5_06_REAL_COLLISION_AIS_DISCOVERY_REPORT.md), [`temporal_contract.json`](../contracts/temporal_contract.json), Contract V1/G11 và các file Markdown audit trong hai gói. Môi trường hiện có PyArrow Zstandard codec; không cài dependency.

Archive được stream, không giải nén ra đĩa. Chỉ giữ MMSI, timestamp, LAT/LON, SOG/COG, tên tàu, IMO/call sign và số thứ tự record cho hai MMSI đã nêu. Với record có timestamp sau sự cố, bộ lọc chỉ kiểm tra timestamp để loại record; không đọc, giữ hoặc thống kê MMSI/vị trí/SOG/COG sau sự cố. Vì thứ tự raw không theo thời gian, stream tiếp tục tới cuối archive để không bỏ sót record pre-event xuất hiện ở phần sau; các trường khác của hàng sau cutoff bị bỏ ngay.

Timestamp AIS được chuẩn hóa UTC theo NOAA [Data Dictionary](https://coast.noaa.gov/data/marinecadastre/ais/data-dictionary.pdf) và [AIS FAQ](https://coast.noaa.gov/data/marinecadastre/ais/faq.pdf). Các file nguồn ghi `base_date_time` không có hậu tố timezone; UTC dựa trên quy ước chính thức của NOAA, không dựa vào timezone máy.

## Xác minh archive và đối chiếu audit extract

| Vụ | Raw archive và format | Size | SHA-256 đã xác minh | Raw record của hai MMSI trong 120 phút |
|---|---|---:|---|---:|
| Yangze 7 / Miss Peggy | `C:\Users\MSI\Downloads\ais-2024-07-19.csv.zst` — Zstandard CSV | 265,691,740 bytes | `da02055f4ed834a03d33138ed738c051e3ce364b8f8299e449080518bf2d0c11` | Yangze `104`; Miss Peggy `107` |
| Patrick J Studdert / Clara B | `C:\Users\MSI\Downloads\ais-2024-12-30.tgz` — phần mở rộng `.tgz`, thực tế là Zstandard CSV | 199,639,097 bytes | `4eef0fa761addd54211c6823b529c31f6d58f8a9ade6e94b7bd17b423f7dd8c6` | Patrick `34`; Clara `59` |

`source_row` bên dưới là ordinal CSV record trong raw archive, tính header là row 1. File có 17 field. Các record raw không được sắp toàn cục theo timestamp; trong cửa sổ trích xuất, số lần timestamp giảm theo source row là Yangze `27`, Miss Peggy `37`, Patrick `6`, Clara `13`. Các thống kê/generation history sort theo UTC timestamp và tie-break source row; không dựa vào thứ tự row để tạo tensor.

Source-row spans trong 120-minute selection: Yangze `6,086,398–8,876,141`; Miss Peggy `6,080,289–8,882,098`; Patrick `2,901–653,034`; Clara B `501–2,526,811`. Anchor-level references bên dưới cho phép tái tạo hai candidate snapshot đã kiểm tra.

| Vụ | Raw 30 phút | Audit pre-event CSV | Record raw audit bỏ sót | Record audit không có trong raw | Payload lõi khác nhau |
|---|---:|---:|---:|---:|---:|
| Yangze 7 / Miss Peggy | 53 | 53 | 0 | 0 | 0 |
| Patrick J Studdert / Clara B | 36 | 36 | 0 | 0 | 0 |

Do đó, việc không có paired anchor gần sự cố không phải do audit extract bỏ sót bản tin. Hai bộ trích 30 phút phản ánh đúng các bản tin trong raw archive ở cùng khoảng thời gian.

## Thời điểm và identity

- Yangze 7 / Miss Peggy: NTSB ghi event sequence `14:03:35 CDT = 2024-07-19 19:03:35Z` trong [MIR-26-24, DCA24FM051](https://www.ntsb.gov/investigations/AccidentReports/Reports/MIR2624.pdf). MMSI theo audit/raw: Yangze 7 `636016708`, Miss Peggy `366935050`.
- Patrick J Studdert / Clara B: [NTSB MIR-26-13, DCA25FM012](https://www.ntsb.gov/investigations/AccidentReports/Reports/MIR2613.pdf) ghi sự cố khoảng `19:34 CST` ngày 29/12/2024. Anchor `2024-12-30 01:34:27Z` dùng để tái lập audit là **mốc danh nghĩa**, không phải giây chính xác do NTSB xác nhận. MMSI theo audit/raw: Patrick `367534690`, Clara `636023978`.

| MMSI | AIS metadata trong cửa sổ | Đối chiếu | Identity status |
|---|---|---|---|
| `636016708` | `YANGZE 7`, IMO `9718911`, call sign `D5HJ7` | NTSB xác nhận tàu Yangze 7 và IMO; raw name/IMO khớp. | Đối chiếu tên/IMO tốt; MMSI ownership ngoài đời vẫn chưa được G11 xác minh. |
| `366935050` | `MISS PEGGY`, call sign `WDH7675`, không có IMO trong AIS window | NTSB xác nhận tên Miss Peggy, nhưng không nêu MMSI/call sign. | `IDENTITY_NOT_VERIFIED` độc lập cho MMSI ↔ tàu. |
| `367534690` | `PATRICK J STUDDERT`, call sign `WDG4262`, không có IMO trong AIS window | Tên khớp tàu trong NTSB; audit package có mapping AIS/tàu. | Mapping MMSI dựa vào AIS/audit; cần crosswalk độc lập hơn. |
| `636023978` | `CLARA B`, IMO `9304083`, call sign `5LQJ3` | Tên/IMO khớp thông tin trong audit package. | Mapping hỗ trợ bởi metadata, nhưng chưa có bằng chứng MMSI được NTSB công bố trực tiếp. |

G11 xác nhận tính nhất quán giữa `vessel_id=physical_mmsi:<MMSI>` và trường MMSI; nó không chứng minh quyền sở hữu MMSI của tàu thật.

## Chất lượng và nhịp quan sát

Trong các bản tin target ở từng cửa sổ, không có missing timestamp/MMSI/LAT/LON/SOG/COG, tọa độ vượt miền hợp lệ, duplicate `(MMSI,timestamp)` hay conflicting duplicate key. Không có giá trị SOG/COG invalid theo miền builder (`0 ≤ SOG ≤ 50`, `0 ≤ COG < 360`). D-03 xử lý trùng lặp theo payload latitude/longitude/SOG/COG; không có record nào bị loại trong các gói này.

| Vụ / tàu | 30 phút: rows; median/max gap | 60 phút: rows; median/max gap | 120 phút: rows; median/max gap | Ghi chú |
|---|---|---|---|---|
| Yangze 7 | 26; `70/80s` | 51; `70/80s` | 104; `70/81s` | AIS khoảng 70 giây một bản tin. |
| Miss Peggy | 27; `68.5/72s` | 53; `69.5/72s` | 107; `69/72s` | AIS khoảng 69 giây một bản tin. |
| Patrick J Studdert | 11; `179.5/185s` | 20; `179/362s` | 34; `180/362s` | Raw daily archive bắt đầu `00:00Z`, trong khi cửa sổ 120 phút bắt đầu `23:34:27Z` ngày trước; thiếu 25m33s đầu cửa sổ. |
| Clara B | 25; `70/91s` | 29; `70/91s` | 59; `70/1561s` | Gap 120 phút gồm một khoảng mất quan sát dài; trong 30–60 phút gần sự cố, nhịp bản tin gần 70 giây. |

Các số gap là chênh lệch giữa timestamp của các bản tin hợp lệ liền nhau sau sort. Các bảng source-age dưới đây đo tuổi as-of cho grid points có bản tin trước đó; chúng không gán tuổi cho slot không có prior observation. P95 và max cho thấy một số slot vượt 60 giây dù median thấp hơn.

| Vụ / tàu | 30 phút min/p50/p95/max age | 60 phút min/p50/p95/max age | 120 phút min/p50/p95/max age |
|---|---:|---:|---:|
| Yangze 7 | `0/30/60/61s` | `0/30/60/61s` | `0/31/60/61s` |
| Miss Peggy | `4/35/64/65s` | `4/34/65/65s` | `1/34/65/65s` |
| Patrick J Studdert | `9/72/135/135s` | `9/72/192/312s` | `9/72/135/312s` |
| Clara B | `0/41/60/80s` | `0/40/80/80s` | `0/49/1281/1521s` |

Đối với Patrick/Clara, thống kê 120 phút là trên phần raw archive ngày 30/12 có sẵn, không phủ đủ 120 phút theo yêu cầu. Cần archive 29/12 để khôi phục phần đầu cửa sổ; việc thiếu phần đó không làm thay đổi kết luận về tần suất Patrick trong 30–60 phút cuối.

## Temporal coverage và tái lập audit grid

Anchor minute grid được neo vào mốc event đã nêu. Để so sánh theo từng khoảng W, candidate anchor là T−1 đến T−(W−9) phút để đủ 10 target point trong chính cửa sổ W: lần lượt `21`, `51`, `111` anchor. Hệ thống chọn latest source không sau grid time, cho phép reuse, không padding và không nội suy. Freshness `90s/120s` chỉ là sensitivity, không có runtime authority.

| Vụ | Cửa sổ | Candidate anchors | Pair hợp lệ age ≤60s | Pair sensitivity ≤90s | Pair sensitivity ≤120s | Anchor gần nhất theo contract |
|---|---:|---:|---:|---:|---:|---|
| Yangze 7 / Miss Peggy | 30 phút | 21 | `0` | `20` | `20` | Không có |
| Yangze 7 / Miss Peggy | 60 phút | 51 | `0` | `49` | `49` | Không có |
| Yangze 7 / Miss Peggy | 120 phút | 111 | `7` | `109` | `109` | T−60 phút |
| Patrick J Studdert / Clara B | 30 phút | 21 | `0` | `0` | `0` | Không có |
| Patrick J Studdert / Clara B | 60 phút | 51 | `0` | `0` | `0` | Không có |
| Patrick J Studdert / Clara B | 120 phút* | 111 | `0` | `0` | `0` | Không có |

`*` Raw archive Patrick không phủ hết phần đầu cửa sổ 120 phút. Single-vessel strict history counts là:

| Vụ / tàu | 30 phút | 60 phút | 120 phút* |
|---|---:|---:|---:|
| Yangze 7 | 10/21 | 39/51 | 66/111 |
| Miss Peggy | 0/21 | 0/51 | 10/111 |
| Patrick J Studdert | 0/21 | 0/51 | 0/111 |
| Clara B | 10/21 | 13/51 | 19/111 |

Nguyên nhân invalid history theo cửa sổ (format `valid / stale age>60s / no prior`):

| Tàu | 30 phút | 60 phút | 120 phút* |
|---|---:|---:|---:|
| Yangze 7 | `10 / 10 / 1` | `39 / 10 / 2` | `66 / 45 / 0` |
| Miss Peggy | `0 / 20 / 1` | `0 / 50 / 1` | `10 / 99 / 2` |
| Patrick J Studdert | `0 / 20 / 1` | `0 / 50 / 1` | `0 / 85 / 26` |
| Clara B | `10 / 10 / 1` | `13 / 12 / 26` | `19 / 66 / 26` |

### Legacy audit grid

Audit cũ kiểm tra current-state last-known freshness, không kiểm tra full 10-step history. Trên grid 31 điểm T−30…T, latest observation ≤120 giây tái lập được:

- Yangze 7 / Miss Peggy: cả hai tàu fresh tại `31/31` điểm, khớp báo cáo audit gói.
- Patrick / Clara: Patrick `21/31`, Clara `31/31`, ghép `21/31`, khớp báo cáo audit gói.

Kết quả này giải thích tại sao audit cũ có thể báo cặp current-state fresh trong khi full input history theo ngưỡng 60 giây không đủ. Không được diễn giải legacy freshness như quyền chạy production inference.

### Yangze/Miss Peggy: candidate hợp lệ xa sự cố

Bảy anchor ghép có offsets `T−60`, `T−61`, `T−95`, `T−96`, `T−97`, `T−108`, `T−109` phút. Anchor hợp lệ gần nhất là `2024-07-19 18:03:35Z` (T−60). 10 input source row references tại anchor đó:

| Tàu / MMSI | Raw source row : timestamp UTC |
|---|---|
| Yangze 7 / `636016708` | `6435065:2024-07-19T17:53:55Z`, `8822482:2024-07-19T17:55:05Z`, `6473690:2024-07-19T17:56:15Z`, `6517000:2024-07-19T17:57:25Z`, `6517595:2024-07-19T17:58:35Z`, `6517595:2024-07-19T17:58:35Z` (reuse), `6473720:2024-07-19T18:00:04Z`, `6509887:2024-07-19T18:01:15Z`, `6519065:2024-07-19T18:02:24Z`, `6520100:2024-07-19T18:03:34Z` |
| Miss Peggy / `366935050` | `6434278:2024-07-19T17:53:49Z`, `6497043:2024-07-19T17:55:00Z`, `6471202:2024-07-19T17:56:10Z`, `6460762:2024-07-19T17:57:14Z`, `6460810:2024-07-19T17:58:16Z`, `6520115:2024-07-19T17:59:17Z`, `6528165:2024-07-19T18:00:02Z`, `6487690:2024-07-19T18:01:04Z`, `6515670:2024-07-19T18:02:10Z`, `6549830:2024-07-19T18:03:11Z` |

Cả bảy anchor strict 60s đều cách sự cố ít nhất 60 phút; +15 phút của chúng kết thúc trước sự cố. Điều này **không** là điều kiện bắt buộc cho input readiness. Tuy vậy, các anchor này không thể dự báo vụ va chạm trong horizon 15 phút: sự cố nằm ngoài horizon M5a. Trong bảy đoạn +15 phút pre-event, `0/7` có đầy đủ 15 target grid observations cho cả hai tàu với as-of age ≤60 giây theo cùng quy tắc; vì vậy full-trajectory forecast evaluation cũng chưa đủ dữ liệu ở độ phân giải hiện tại. Không đọc hoặc phân tích AIS sau sự cố.

## Candidate snapshot, G11 và tọa độ

Tại anchor Yangze/Miss Peggy T−60, tạo hai candidate snapshot trong bộ nhớ từ **chỉ 10 source observation causal của từng tàu**. `build_production_track_snapshot` kiểm tra structural schema, `validate_track_snapshot_temporal` và `validate_production_track_g11`:

- Structural schema: PASS cho cả hai snapshot.
- G11 identity/provenance consistency: PASS cho cả hai (`REAL_AIS`, `is_simulated=false`, `physical_mmsi:<MMSI>` khớp field MMSI).
- Temporal: PASS; đúng grid −9…0, source không sau grid, age `[0,60]`, reuse theo contract.
- Common EN: PASS phép chuyển đổi hữu hạn trong cùng frame theo [`coordinate_contract.md`](../contracts/coordinate_contract.md); không lưu feature tensor hoặc artifact.
- Water/shoreline QC: `NOT_VERIFIED`; không chạy sea-mask, nên không kết luận mọi vị trí nằm trên mặt nước.
- MMSI ownership: `PARTIAL/NOT_VERIFIED` ở cấp G11; semantic pass không chứng minh MMSI thuộc đúng tàu ngoài đời.

Không có cặp snapshot hợp lệ cho Patrick/Clara nên G11 không chạy cho vụ đó.

## Root cause

| Nhóm nguyên nhân | Kết quả | Evidence |
|---|---|---|
| A. Audit extract bỏ sót bản tin | Không | Raw 30 phút khớp audit package 100% về key và payload lõi ở cả hai vụ. |
| B. Tần suất raw AIS không đủ | **Có — nguyên nhân chính** | Yangze/Miss Peggy gap khoảng 69–70 giây khiến không có cặp 10-step history ≤60s trong 60 phút gần sự cố; chỉ có 7 cặp ở offsets ≥60 phút. Patrick có gap 180 giây median và 362 giây max; không có history hợp lệ của Patrick. |
| C. Lỗi timezone/grid parsing | Không thấy | NOAA UTC convention áp dụng; current-state audit grid 31 điểm tái lập được; source age được tính từ UTC event-relative minute grid. |
| D. MMSI mapping | Không phải nguyên nhân coverage; identity còn partial | Cả hai MMSI đều có AIS observations và name metadata; G11 candidate Yangze pass. Miss Peggy/Patrick cần crosswalk độc lập mạnh hơn. |
| E. Missing/invalid fields | Không | Target rows trong 120 phút không có missing lat/lon/SOG/COG hoặc tọa độ/motion invalid. |
| F. Raw ordering | **Có, cần chuẩn hóa** | Archive không time-sorted; record order có inversion ngay trong từng MMSI. Deterministic sort theo UTC timestamp/source row khôi phục sequence; gap và stale-age vẫn còn sau sort. |

Sensitivity ở 90/120 giây làm tăng paired coverage rõ rệt cho Yangze, nhưng đó chỉ là chẩn đoán nguyên nhân; không thay đổi ngưỡng G11/temporal contract.

## Readiness và dữ liệu còn thiếu

| Vụ | Phân loại | Khuyến nghị |
|---|---|---|
| Yangze 7 / Miss Peggy | `CONDITIONAL_READY` cho isolated snapshot/replay data review; **NOT_READY cho collision-warning evaluation tại sự cố** | Có thể dùng 7 anchor history xa sự cố để review pipeline/G11 sau khi Trung duyệt. Để kiểm chứng cảnh báo 15 phút cần feed có cadence đủ dày sát event; hiện không có anchor strict nào trong T−15…T. Xác minh MMSI Miss Peggy và water mask trước trusted runtime. |
| Patrick J Studdert / Clara B | `INSUFFICIENT_RAW_AIS_FREQUENCY` | Loại khỏi replay kiểm chứng cảnh báo theo contract hiện tại. Archive 29/12 cần có nếu bắt buộc phủ trọn 120 phút, nhưng bổ sung phần đầu không sửa được độ thưa của Patrick sát sự cố. |

Không có vụ nào đủ tiêu chuẩn làm independent blind benchmark. Audit discovery trước đó đã làm lộ metadata hậu sự kiện của Yangze/Miss Peggy; nếu dùng sau này, phải ghi là retrospective/unblinded case study hoặc có evaluator độc lập.

### Bổ sung dữ liệu cần thiết

1. AIS feed/receiver có khoảng cách bản tin đủ để tạo ít nhất một paired 10-step anchor với age ≤60s trong 15 phút trước event; không nội suy hoặc padding.
2. MMSI ↔ vessel crosswalk độc lập, nhất là Miss Peggy `366935050` và Patrick `367534690`.
3. Water/shoreline mask QC cho các điểm được chọn.
4. Ground-truth future observations để đánh giá trajectory sau khi input/anchor được khóa; phần này chưa được đọc trong task.
5. Archive ngày 29/12/2024 nếu cần đủ 120 phút pre-event cho Patrick; chưa tìm hoặc tải archive này trong task.

`ADDITIONAL_DATA_REQUIRED=YES` nếu mục tiêu là collision-warning evaluation theo 15-minute horizon. Chưa cần tải dữ liệu trong task này; archive hiện có đã chứng minh giới hạn cadence ở các anchor gần event.

## Khuyến nghị bước kế tiếp

1. Trung review report và quyết định có tiếp tục với Yangze/Miss Peggy như candidate isolated data replay, với caveat không dùng làm hiệu năng cảnh báo tại sự cố.
2. Nếu tiếp tục, xác minh crosswalk MMSI và water location trước khi snapshot vào trusted runtime; giữ source raw read-only, pin archive SHA và áp dụng sort/duplicate policy deterministic.
3. Chỉ sau phê duyệt riêng mới chuẩn bị evaluator/ground truth hoặc chạy M5a + CC-DRI V4. Không chỉnh threshold, temporal contract hay Model Lock.
4. Không dùng Patrick/Clara cho mục tiêu này nếu chưa tìm được AIS source có tần suất cao hơn.

## Giới hạn và trạng thái

- Đã kiểm tra hai raw archive theo stream và chỉ so sánh 30-minute member được nêu trong từng audit package; không mở full-day CSV hoặc QA JSON.
- Record sau event chỉ được loại theo timestamp cutoff; các trường còn lại không được đưa vào thống kê/selection. Không giải nén raw archive ra đĩa.
- Không đọc Test labels/future/displacement artifacts; không chạy training, calibration, model inference, T15 benchmark hay test suite.
- Không sửa DATASET_FINAL, Model Lock, Risk V4, thresholds, Contract V1, backend/frontend hoặc raw AIS. Các thay đổi S5 chưa commit được giữ nguyên.
- Không tạo commit, push hoặc merge.

**Tóm tắt:** `YANGZE_MISS_PEGGY_RAW_RECORDS=211`; `PATRICK_CLARA_RAW_RECORDS=93`; `AUDIT_EXTRACT_MISSING_RECORDS=0`; `PAIRED_VALID_ANCHORS_30M=0/0`; `PAIRED_VALID_ANCHORS_60M=0/0`; `PAIRED_VALID_ANCHORS_120M=7/0`; `G11=PASS` cho hai snapshot Yangze/Miss Peggy ở T−60; `READY_CASES=CONDITIONAL_YANGZE_MISS_PEGGY_ONLY`; `REJECTED_CASES=PATRICK_CLARA_INSUFFICIENT_RAW_AIS_FREQUENCY`.
