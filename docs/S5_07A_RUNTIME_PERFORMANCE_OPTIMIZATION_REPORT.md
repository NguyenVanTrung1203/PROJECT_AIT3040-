# S5-07A – Tối ưu hiệu năng runtime

## Phạm vi và môi trường

- Branch: `s5-integration-final`; baseline HEAD: `8f252c522914aa30ba05bd28368ec60cab71c5a6`.
- Python 3.12.3, PyTorch 2.11.0+cu128, CPU, 1 Torch thread; dùng model package và external pin S4-T14 hiện có.
- Chỉ dùng synthetic fixture S5-01, 5 tàu, các anchor 00:09 và 00:15. Không chạy T15, training, calibration, full regression hoặc GPU benchmark.
- Model Lock, Risk Engine V4, threshold, Contract V1, checkpoint, scaler và package không thay đổi.

Số liệu dưới đây là targeted runtime observations trên máy hiện tại, không phải SLA. Lượt đo A/B được thực hiện trong cùng process và cùng model instance: baseline mô phỏng đúng đường gọi trước chỉnh sửa bằng cách không truyền features đã có sẵn vào `M5aRuntime.predict`; optimized truyền object do provider phát hành. Baseline được đo trước optimized. I/O của việc kiểm tra package dao động mạnh giữa các lượt, nên chênh lệch batch wall time không đủ để khẳng định tăng hoặc giảm hiệu năng.

## Baseline và kết quả A/B

Mỗi batch gồm đủ 10 candidate pairs. 00:09 có 6 cặp đủ dữ liệu và 4 unavailable; 00:15 có 10 cặp đủ dữ liệu.

| Chỉ số | Baseline | Sau tối ưu | Số mẫu |
|---|---:|---:|---:|
| Model initialization | 2,212 s trong lượt A/B; các probe khác 0,847–5,313 s | Không thay đổi đường khởi tạo; không tải model thêm | 1 lần trong A/B; 3 probe cold-start tổng cộng |
| Cold initialization + lần đánh giá đủ dữ liệu đầu tiên | 10,09 s trong lượt A/B; 6,66–10,82 s qua 3 probe | Chưa đo lại như một process cold riêng; runtime init không đổi | 3 probe baseline |
| Cặp đủ dữ liệu, P50 / P95 | 7,203 / 9,172 s | 7,699 / 9,766 s | 16 request mỗi phía, gộp hai anchor |
| 10 cặp tại 00:09 | 35,683 s | 37,196 s | 1 batch mỗi phía |
| 10 cặp tại 00:15 | 73,848 s | 78,064 s | 1 batch mỗi phía |
| FastAPI JSON encoding / JSON render, median | 0,791 / 0,431 ms | JSON render 0,374 ms | 20 mẫu baseline; 40 mẫu render A/B |

Batch wall time được đo ở runtime harness, không gồm network round-trip. JSON encoding được đo riêng qua `jsonable_encoder` và `JSONResponse.render`. Vì vậy các số serialization mô tả chi phí encode response, không phải benchmark HTTP endpoint end-to-end.

Lượt A/B ghi nhận speed ratio baseline/optimized là **0,96× tại 00:09** và **0,95× tại 00:15**; đây không phải speedup có thể quy cho thay đổi. P50/P95 cũng không giảm. Trong khi đó thời gian package integrity check tăng từ 55,67 lên 61,59 giây tổng cộng ở cùng 32 lần gọi, một dấu hiệu rõ về biến động I/O. Một lượt baseline ban đầu đo 36,81/57,21 giây và một lượt optimized-only sau đó đo 16,40/29,90 giây; hai lượt này có trạng thái filesystem cache khác nhau nên **không dùng để tính speedup**.

## Bottleneck và công việc bị lặp

| Phase | Baseline A/B | Optimized A/B | Nhận xét |
|---|---:|---:|---|
| M5a package integrity | 55,671 s / 32 lần | 61,588 s / 32 lần | Chi phí lớn nhất. Mỗi inference giữ hai lần verify, trước và sau forecast. |
| Threshold authority verification | 52,320 s / 32 lần | 52,146 s / 32 lần | Chi phí lớn thứ hai; authority tiếp tục được xác minh trước và tại publish. |
| Snapshot acquisition | 1,353 s / 2 snapshot | 1,105 s / 2 snapshot | Một lần mỗi anchor, không lặp theo từng cặp. |
| Candidate enumeration | 0,009 s / 2 lần | 0,007 s / 2 lần | Không đáng kể so với inference/verification. |
| G11 validation | 0,178 s / 10 track checks | 0,329 s / 10 track checks | 5 track mỗi snapshot; không giảm hoặc bỏ bước này. |
| History extraction và feature construction | 0,193 s / 32 lần | 0,089 s / 16 lần | Trước đây cùng cặp dựng feature hai lần. |
| M5a forward | 0,091 s / 32 forward | 0,101 s / 32 forward | Hai forward, mỗi tàu một lần cho mỗi cặp đủ dữ liệu. Không reuse forecast giữa các cặp. |
| Residual inverse scaling | 0,012 s / 32 lần | 0,019 s / 32 lần | Đo riêng scaler inverse; giữ nguyên. |
| Kinematic projection | 0,680 s / 32 lần | 0,764 s / 32 lần | Tính theo từng tàu và cặp; không đổi projection. |
| QC | 0,034 s / 32 lần | 0,035 s / 32 lần | M5a/CV QC vẫn chạy. |
| Risk V4 calculation | 0,071 s / 16 cặp | 0,042 s / 16 cặp | Chênh lệch nhỏ; kết quả không đổi. |
| Risk reference verification | 0,064 s / 36 lần | 0,052 s / 36 lần | Giữ nguyên xác minh. |
| Alert lifecycle | 0,0006 s / 20 kết quả | 0,0008 s / 20 kết quả | Không phải bottleneck. |

Ba bottleneck chính là M5a package integrity, threshold authority verification và phần snapshot/G11. Trong inference core, projection mất khoảng 0,68–0,76 giây cộng dồn; model forward chỉ khoảng 0,09–0,10 giây. Các phase lồng nhau nên không cộng thời lượng của pipeline tổng với các phase con.

Scaling đầu vào mất 0,013/0,015 giây cộng dồn; residual inverse scaling 0,012/0,019 giây. Geographic conversion được thực hiện trong `M5aRuntime.predict` và không có timer riêng cho phép tính vector hóa; output read-only copy (gồm chuyển NumPy) mất 0,0021/0,0023 giây trong 64 lần gọi. Toàn bộ phần này nằm trong `M5a predict total` (56,77/62,72 giây cộng dồn), phần lớn là integrity checks trước/sau inference.

Throughput quan sát được: baseline xử lý lần lượt 0,280 và 0,135 candidate pairs/giây tại 00:09/00:15; optimized là 0,269 và 0,128 pairs/giây. Đây là throughput của batch tuần tự trên synthetic fixture, không phải throughput triển khai.

Provider `encounter` được xác minh nhiều lần để giữ authoritative binding; số call giảm từ 104 xuống 88 nhờ không dựng lại encounter bên trong lần feature extraction thứ hai. Freshness checks hiện hành trước/sau inference và trước commit alert vẫn chạy.

Có 9 lần lặp lại chính xác một số feature rows giữa các candidate pairs trong fixture. Không cache forecast theo tàu giữa các cặp: forecast trong common EN frame, anchor, QC/fallback và cặp phải được ràng buộc đầy đủ; cache liên cặp cần một thiết kế identity riêng và bằng chứng tương đương cho các trường hợp đó.

## Tối ưu đã triển khai

Risk harness truyền object `Features` bất biến mà provider vừa phát hành sang M5a runtime, thay vì để M5a runtime dựng lại cùng feature lần thứ hai. Provider chỉ chấp nhận đúng object đã cấp cho cùng session, version, snapshot, anchor, source, fixture digest, candidate object, pair, vessel set và encounter. Cache object bị xóa khi tạo session, đổi replay state, tạo snapshot hoặc candidate set mới. Model/config vẫn thuộc instance M5a hiện hành; không cache forecast output hay integrity result.

Tối ưu giảm feature construction từ 32 xuống 16 lần cho 16 cặp đủ dữ liệu; issued-feature binding được kiểm tra 16 lần. Feature construction mất 0,193 giây trước và 0,089 giây sau; binding check thêm 0,022 giây. Mức tiết kiệm ròng đo được khoảng 0,082 giây, dưới 0,1% tổng batch. **Không có speedup wall-time đo được.**

Không thay đổi số lần kiểm tra integrity: 32 M5a checks mỗi phía cho 16 inference, cộng một lần khi khởi tạo instance. Threshold checks giữ 32; Risk V4 reference checks giữ 36. Model load count là 1. Không thêm dependency.

## Numerical parity và alert parity

Các response A/B của cả 20 candidate records tại hai anchor khớp chính xác sau khi loại ba định danh được sinh ngẫu nhiên (`request_id`, `encounter_id`, `replay_session_id`). Kiểm thử dựng feature hai lần từ cùng encounter cũng xác nhận `history`, `anchors_en` và origin giống hệt nhau. So sánh response bao gồm forecast/coordinates trả về, QC/model status, CPA, risk score, decision và unavailable reason.

- 00:09: **1 alert, 5 no-alert, 4 unavailable** ở cả hai phía.
- 00:15: **1 alert, 9 no-alert, 0 unavailable** ở cả hai phía.
- Alert lifecycle, retry/idempotency, missing data và stale result tests đều PASS trong targeted suite.

## Kiểm thử mục tiêu

Q1-guarded targeted run: **19 passed in 203,19 s**. Hai lượt supplementary focused tests: session/cache isolation **1 passed in 50,12 s**; feature tensor/binding equality **1 passed in 15,45 s**. Tổng cộng **21 pass executions, 20 unique targeted cases, 268,76 s**, không chạy full regression.

Các kiểm tra bao gồm CPU M5a/reference parity, intermediate parity (scaled input, residual, CV có max absolute difference bằng 0), exact issued-feature identity, feature corruption fail-closed, pin tampering fail-closed, stale SEEK/RESET, Risk V4 parity, cache/idempotency conflict, session isolation trong runtime, unavailable/mixed-model semantics, duplicate retry/alert và stale alert commit.

Q1 guard: `hash_opens=0`, `blocked_deserialization=0`, `blocked_other_opens=0` trong cả ba lần pytest hoàn tất.

Kiểm thử HTTP `test_controls_snapshot_invalidation_and_session_isolation` **NOT_VERIFIED**. Lượt chạy bị treo trước khi test body bắt đầu tại `asyncio.run()`; faulthandler chỉ ra Windows Proactor loop bị chặn trong `socket.socketpair()`/`accept`. Retry với Windows Selector policy cũng không hoàn thành trong giới hạn chờ. Đây là giới hạn khởi tạo event loop của test harness trên môi trường hiện tại, không phải bằng chứng lỗi API. Runtime-level session/cache isolation đã PASS; không tuyên bố HTTP test này PASS.

`git diff --check` PASS. Model Lock / immutable package, Risk V4, threshold config, Contract V1 và frontend không bị sửa trong task này. Không chạy frontend tests/build vì frontend không đổi.

## Đề xuất automatic evaluation khi PLAYING

Đây là proposal, chưa triển khai:

1. Chỉ tạo một evaluation anchor trên mỗi mốc minute-grid; không khởi chạy inference theo từng frame render. Replay clock tiếp tục chạy độc lập. Mỗi job phải mang session ID, version, snapshot ID và evaluation anchor riêng.
2. Giữ nguyên giới hạn một inference worker hiện tại trong lần đầu. Đưa một snapshot batch đang chạy và tối đa một batch mới nhất đang chờ vào queue; nếu có anchor mới hơn, thay batch đang chờ cũ và ghi nhận anchor bị bỏ qua. Không tạo queue không giới hạn.
3. Đặt deadline theo playback rate: một phút mô phỏng có ngân sách `60 / playback_rate` giây wall time. Batch 10 cặp đo được 73,85–78,06 giây; vì vậy ở 1× không thể đảm bảo hoàn tất tất cả cặp trước anchor phút kế tiếp. Số đo hiện tại chưa đủ để đặt SLA hoặc playback rate chính thức.
4. Khi anchor mới đến, hủy công việc chưa bắt đầu; inference đang chạy có thể không hủy giữa forward, nhưng kiểm tra generation/snapshot giữa các cặp và trước publish. Kết quả cũ sau deadline bị loại, không ghi alert và không hiển thị như forecast hiện tại.
5. Giữ freshness recheck trong provider/harness ngay trước alert commit. UI chỉ hiển thị forecast khi session/version/snapshot/anchor khớp replay state; nếu giữ một alert hợp lệ cũ thì phải ghi rõ `as-of` anchor của alert.
6. Exact-current-anchor hiện gây stale/409 khi replay clock đổi trong inference. Chuyển sang discrete evaluation anchor là thay đổi temporal semantics và cần Trung phê duyệt riêng; không đóng băng clock để bù latency.

## Quyết định cần duyệt và S5-07B readiness

- Chọn exact-current-anchor hay discrete minute-grid evaluation anchors khi PLAYING.
- Chọn playback rate/deadline và cách xử lý anchor bị bỏ qua khi batch chậm hơn cadence.
- Duyệt policy queue một in-flight + một latest pending, cancellation giữa các cặp và stale display/alert commit.
- Nếu muốn giảm mạnh latency, cần review riêng trust model cho integrity/authority verification. Không triển khai integrity cache hoặc giảm tần suất verify trong S5-07A.

**S5-07B readiness: CONDITIONAL_PENDING_USER_DECISIONS.** Feature reuse an toàn đã có numerical parity và targeted tests PASS; tuy nhiên nó không cải thiện wall time đáng kể. Với batch 10 cặp mất khoảng 74–78 giây và API HTTP session-isolation test chưa xác minh được trong môi trường hiện tại, chưa nên tuyên bố automatic all-pairs evaluation trong PLAYING sẵn sàng. Chờ Trung duyệt temporal anchors, deadline/queue policy và hướng xử lý trust-boundary bottleneck trước S5-07B.

Không sửa frontend, Model Lock, Risk V4, thresholds, Contract V1, dataset, checkpoint hoặc scalers. Không commit, push hay merge.
