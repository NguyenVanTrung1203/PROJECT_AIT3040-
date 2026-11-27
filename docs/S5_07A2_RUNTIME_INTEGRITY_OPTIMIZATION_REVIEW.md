# AIT3040 — S5-07A2: Review tối ưu xác minh integrity runtime

## Trạng thái và phạm vi

- Branch: `s5-integration-final`
- HEAD kiểm tra: `8f252c522914aa30ba05bd28368ec60cab71c5a6`
- Chỉ review và feasibility probe trên synthetic fixture S5-01 tại anchor `00:09` và `00:15`.
- Không sửa runtime, Model Lock, Risk V4, threshold, Contract V1 hay model package. Không chạy unit test, full regression, T15, training, calibration hoặc Real AIS.
- Các phép tampering chỉ dùng bản sao tạm trong thư mục temporary; package và pin gốc không bị sửa.

## Kết luận

Nút thắt là mỗi candidate đủ điều kiện xác minh lặp lại toàn bộ package và threshold authority nhiều lần. M5a model/scalers đã nằm trong RAM sau khi khởi tạo, nhưng runtime vẫn băm lại nội dung package trên đĩa trước và sau mỗi forecast; resolver cũng xác minh lại cùng package trước quyết định và trước commit alert.

Batch-scoped verification (phương án C) khả thi trong probe synthetic: 7,110 giây tại `00:09` và 6,366 giây tại `00:15`, bao gồm xác minh đầy đủ ở đầu và cuối batch. Kết quả sau khi loại định danh ngẫu nhiên khớp chính xác với phương án B. Đây là số đo của probe không-production, không phải SLA hoặc bằng chứng sẵn sàng triển khai.

Không nên dùng phương án B một mình: xác minh một lần lúc khởi động không phát hiện pin, manifest, checkpoint hoặc scaler bị sửa sau đó; verifier hiện tại cũng không phát hiện sửa đổi trọng số đang nằm trong RAM. Khuyến nghị xem xét phương án C sau khi Trung phê duyệt thời gian hiệu lực trust context, cách nạp cùng byte đã verify, snapshot lease, và commit kết quả theo batch.

## 1. Call graph và công việc lặp

| Đường gọi | Công việc mỗi lần | Phạm vi |
|---|---|---|
| `M5aRuntime.__init__` → `_verify_integrity` | Đọc external pin; `verify_active`; đọc lại `package_payload.json`; so sánh 11 source trong worktree với snapshot đã pin; gọi `verify_artifacts` | Khởi tạo runtime |
| `M5aRuntime.predict` → `_verify_integrity` | Chạy lại cùng xác minh trước forecast và sau forecast | 2 lần mỗi forecast |
| `FixtureRiskHarness._evaluate` → `resolve_threshold` | Đọc external pin và chạy `verify_active` trước quyết định | 1 lần mỗi response có active model |
| Atomic commit trong `FixtureRiskHarness._evaluate` → `resolve_threshold` | Xác minh lại authority trước alert/cache commit | Thêm 1 lần mỗi response có active model |
| `M5aInference.__init__` | `verify_artifacts` lần nữa, băm model/projection config, sau đó đọc manifest/config/checkpoint và hai scaler từ đĩa | Khởi tạo model; load count vẫn là 1 |

Mỗi candidate đủ điều kiện hiện thực hiện khoảng **374 lần gọi hash được tính trong probe instrumentation**: hai lần `_verify_integrity` (mỗi lần 87 hash của `verify_active` và 13 hash của `verify_artifacts`) cùng hai lần `resolve_threshold` (mỗi lần 87 hash). `_verify_integrity` còn có 11 phép SHA-256 inline cho source snapshot và đọc/so sánh 11 source worktree/package; các phép inline này không nằm trong bộ đếm `digest` nói trên.

### Nội dung và chi phí mỗi lượt

`verify_active` hash 87 file, tổng **1.211.890 byte** theo nhóm package:

| Nhóm | Số file | Byte |
|---|---:|---:|
| Artifacts | 13 | 841.782 |
| Contracts | 16 | 62.145 |
| Evidence docs | 7 | 89.448 |
| Other snapshot | 9 | 35.929 |
| Package root | 4 | 24.672 |
| Snapshot source | 25 | 67.176 |
| Verification evidence | 13 | 90.738 |

Trong 87 hash, `verify_active` kiểm tra manifest, `package_payload.json` và 85 đường dẫn được liệt kê chính xác trong payload index; detached checksum được đọc và so với manifest digest. 13 hash artifacts là `checksums.sha256` cùng 12 file trong `snapshot/artifacts/checkpoints/s3_t10_20261124_seed20261110_run01/`. `verify_artifacts` hash thêm 13 file, **841.782 byte**. Toàn bộ nhóm này đã nằm trong payload mà `verify_active` hash, nên 13 lượt đó là trùng. Một lượt `_verify_integrity` được đo gồm 100 hash API, **2.053.672 byte**, chưa kể các SHA inline/source-byte comparison. `resolve_threshold` riêng chạy lại 87 hash trên cùng package. Thời gian thực đo dao động theo trạng thái filesystem: các probe đơn lẻ ghi nhận khoảng 1,3–2,4 giây cho một lượt verifier; không dùng thời gian đó làm SLA.

11 file `_BOUND_SOURCES` được đọc từ worktree và từ snapshot package rồi so sánh là: `src/inference/m5a_wrapper.py`, `src/models/m5a.py`, `src/models/scalers.py`, `src/models/pipeline.py`, `src/models/kinematics.py`, `src/training/engine.py`, `src/training/loss.py`, `src/models/__init__.py`, `src/release/offline_lock.py`, `configs/model_config.yaml` và `configs/projection_config.yaml`. Đây không phải toàn bộ S5 runtime closure; dependency binding vẫn ghi `runtime_integration_closure=NOT_VERIFIED`.

M5a model, input scaler và residual scaler được load một lần vào RAM tại khởi tạo. `M5aRuntime._run_vessel` dùng các object này trong inference; không deserialize checkpoint/scaler mỗi candidate. Các lượt hash sau đó vẫn đọc package trên đĩa, dù không thay thế các object đã load. `resolve_threshold` cũng đọc external pin và package trên đĩa ở mỗi lần gọi.

## 2. Trust boundary và rủi ro

| Trường hợp | A — Hiện tại | B — Verify lúc khởi động | C — Verify theo batch |
|---|---|---|---|
| Checkpoint/scaler trên đĩa bị sửa | Thường phát hiện ở lần verify tiếp theo; có race giữa hash và lần mở file | Không phát hiện trong process sau startup | Phát hiện nếu nội dung sai còn tồn tại tại lần verify cuối batch |
| Manifest/external pin bị sửa | Thường phát hiện ở lần verify/resolve kế tiếp | Không phát hiện đến khi restart hoặc invalidation ngoài chưa có | Phát hiện tại boundary kế tiếp nếu thay đổi còn tồn tại |
| Threshold authority bị thu hồi/đổi | Resolve lại trước decision và commit; vẫn có race sau check | Context cũ tiếp tục được dùng; không có invalidation đã chứng minh | Resolve lại ở đầu/cuối batch; cửa sổ phát hiện tối đa một batch |
| Sửa model weights/scalers trong RAM | Disk verifier không phát hiện | Disk verifier không phát hiện | Disk verifier không phát hiện |
| Thay file giữa verify và load/use | Có TOCTOU; không có atomic verified-byte load | Startup TOCTOU vẫn còn | Boundary TOCTOU vẫn còn; C không tự giải quyết race ở khâu load hoặc sau verify cuối |
| Sửa rồi khôi phục file giữa hai boundary | Lần kiểm tra có thể không thấy | Không thấy | Có thể không thấy nếu thay đổi đã được khôi phục trước boundary |
| Stale result / SEEK / RESET | Provider kiểm tra snapshot/session ngay trước commit; clock phải đúng anchor | Cần giữ nguyên guard; context startup không thay stale guard | Cần lease theo session generation; recheck cuối và loại kết quả stale |
| Alert commit an toàn | Recheck threshold và provider ngay trước commit từng pair | Có thể commit bằng authority đã cũ | Chỉ an toàn nếu response, alert, idempotency/cache được stage và publish sau kiểm tra cuối batch |
| Contract V1 | Được giữ nguyên | Có thể giữ schema, nhưng temporal authority semantics thay đổi | Có thể giữ schema, nhưng anchor/`as-of` semantics và publication timing cần duyệt |
| Trust model | Per-pair disk revalidation, nhưng không atomic | Tin process memory và package bất biến suốt vòng đời; hiện chưa có bằng chứng invalidation | Tin context trong batch; giảm cửa sổ phát hiện thay đổi xuống boundary; cần atomic batch publication |

Model Lock hiện có tự ghi rõ checksum không phải chữ ký số; manifest đặt `runtime_integration_approved=false` và `production_approved=false`. S5 authority là academic prototype riêng. `configs/s5_runtime_dependency_binding.json` vẫn có trạng thái `OBSERVED_ENVIRONMENT_NOT_DEPLOYMENT_LOCK`, `runtime_integration_closure=NOT_VERIFIED`. Những giới hạn này không thay đổi trong review.

## 3. Feasibility probe A/B/C

Probe chạy trong một process, CPU, một Torch thread, model và fixture hiện có. Không có response nào được gửi qua HTTP. A là số đo baseline feature-reuse gần nhất trong báo cáo S5-07A; B/C được đo riêng trong lượt probe này. I/O có biến động giữa lượt, vì vậy phần trăm so với A chỉ là tham khảo.

| Phương án | `00:09` — 10 cặp (6 đủ dữ liệu) | `00:15` — 10 cặp (10 đủ dữ liệu) | Full verification trong batch |
|---|---:|---:|---|
| A — hiện tại, historical optimized run | 37,196 s | 78,064 s | Theo từng pair; mỗi pair đủ dữ liệu có 374 hash API calls |
| B — context verify một lần, batch time | 0,358 s | 0,513 s | 0 trong batch; chỉ in-memory binding checks |
| C — full check đầu/cuối batch | 7,110 s | 6,366 s | 2 integrity + 2 authority checks/batch, tương đương 374 hash API calls |

B cần thêm **1,355 giây integrity + 1,579 giây authority** để tạo context ở đầu probe, ngoài constructor model **1,931 giây**. Hai thời gian kiểm tra khởi tạo không nằm trong batch time của B; `00:15` tái sử dụng context từ `00:09`. Nếu package/threshold bị sửa sau đó, B không kiểm tra lại.

Chi tiết C:

| Anchor | Integrity đầu/cuối | Authority đầu/cuối | Tổng batch |
|---|---:|---:|---:|
| `00:09` | 1,828 / 1,723 s | 1,696 / 1,555 s | 7,110 s |
| `00:15` | 1,751 / 1,598 s | 1,589 / 1,049 s | 6,366 s |

So với historical A, số đo C thấp hơn khoảng **80,9% tại `00:09`** và **91,8% tại `00:15`**; B batch-only thấp hơn khoảng 99%. So sánh B loại trừ startup và không có disk invalidation, nên không phải so sánh công bằng về trust hoặc end-to-end startup. C vẫn lặp toàn bộ package traversal riêng cho integrity và threshold tại mỗi boundary; nếu được duyệt, một boundary context có thể kiểm tra package/external pin một lần rồi cung cấp cùng verified identity cho threshold resolver.

B và C cho **response parity chính xác** tại cả hai anchor sau khi bỏ `request_id`, `encounter_id` và `replay_session_id`. Trong C, cả 10 thao tác áp dụng alert được giữ tạm và chỉ flush sau boundary cuối. Probe chỉ stage alert application; `_cache` và `_requests` của harness vẫn được cập nhật nội bộ trong từng lần evaluate, còn response chỉ được giữ trong biến cục bộ của probe và harness bị bỏ sau batch. Vì vậy production C phải stage hoặc rollback cả response, cache/idempotency và alert state trước publish. Probe không đo HTTP/network và không xác lập SLA. Báo cáo S5-07A trước đó ghi nhận kết quả `00:09`: 1 alert, 5 no-alert, 4 unavailable; `00:15`: 1 alert, 9 no-alert.

### Số lần xác minh theo số cặp

Ở C, mỗi batch có 374 hash API calls tại bốn boundary checks, bất kể batch có 6 hay 10 eligible pairs. So với A, số lượt này giảm 6 lần tại `00:09` và 10 lần tại `00:15`. B giảm thêm các lượt trong batch, nhưng đánh đổi khả năng phát hiện invalidation giữa các lần khởi động.

## 4. Tampering và fail-closed evidence

Các thao tác sau được thực hiện trên bản sao tạm của package; bản gốc không bị ghi:

- `verify_active` từ chối khi manifest bị thêm byte.
- `verify_active` và `verify_artifacts` từ chối khi một byte checkpoint bị đổi.
- `resolve_threshold` trả về `RELEASE_UNAVAILABLE` khi external manifest pin sai.
- Probe TOCTOU thay `x_scaler.json` sau khi `verify_artifacts` đã chạy nhưng trước khi `TrainOnlyScaler.load` mở file. Constructor hoàn tất và nạp giá trị scaler đã đổi. Lượt `verify_active` tiếp theo từ chối package đã đổi. Đây là bằng chứng cụ thể rằng hash file rồi mở lại theo path không đảm bảo deserialize đúng các byte đã verify.
- Probe sửa một trọng số model trong RAM; `verify_active` trên package không đổi vẫn PASS. Integrity verifier hiện xác thực disk package, không xác thực in-memory tensor.

Kết luận: fail-closed hiện có hoạt động khi tampering còn hiện diện tại thời điểm verifier chạy. Nó không chứng minh atomicity giữa verify/load, không phát hiện thay đổi RAM, và không phát hiện chắc chắn thay đổi rồi khôi phục trước lượt hash kế tiếp. Phương án C thu hẹp khoảng phát hiện thay đổi persistent xuống tối đa một batch, nhưng chỉ khi mọi response và alert được stage đến khi boundary cuối đạt.

## 5. Thiết kế `VerifiedRuntimeContext` đề xuất

Đây là thiết kế để xem xét, chưa triển khai:

1. Tại startup, đọc external pin và package; kiểm tra exact inventory, manifest, payload, source binding, artifact checksums và threshold authority. Hash byte buffer rồi deserialize chính buffer đó (checkpoint/scaler/config), không hash một path rồi mở lại path khác. Lưu model/scaler/config immutable theo process context.
2. Context giữ tối thiểu: manifest SHA, payload identity, external pin identity, lock ID, source/config identity, operating points, model instance generation, device, và thời điểm khởi tạo. Mọi mismatch/error đều unavailable; `mtime` và file size không phải bằng chứng integrity.
3. Với C, tại mỗi batch boundary kiểm tra pin và package đầy đủ một lần, xác thực context/authority, rồi tạo context token có scope đúng một batch. Trong batch, các lần gọi nội bộ chỉ kiểm tra token, model/config identity và snapshot lease; token tự hết hạn sau batch hoặc deadline.
4. Kết quả response, cache/idempotency writes và alert transitions được stage cục bộ. Chỉ flush đồng thời sau khi integrity, authority, snapshot generation và deadline đều còn hợp lệ. Nếu một bước fail, bỏ toàn batch.
5. Không tuyên bố bảo vệ khỏi process memory tampering. Việc tin process/runtime code và RAM phải được Trung chấp thuận hoặc được xử lý bằng sandbox/attestation khác trong một phạm vi riêng. Model Lock hiện tại không cung cấp cơ chế này.

Nạp từ cùng byte buffer giải quyết race cụ thể giữa hash và deserialize ở startup. Boundary start/end thu hẹp thời điểm phát hiện thay đổi sau startup. Hai điều này không thay thế nhau và chưa được implement ở task này.

## 6. Thiết kế automatic evaluation khi PLAYING

- Tạo job tại các anchor phút rời rạc; replay clock tiếp tục chạy độc lập. Job chứa `session_id`, session generation/version, snapshot ID, source/fixture digest, anchor, candidate IDs và deadline.
- Đóng băng history đúng tại evaluation anchor. Chạy G11/source-age theo chính anchor đó; không thêm observation sau anchor và không tính tuổi nguồn dựa trên clock tương lai trong lúc worker chạy. Gắn kết quả với `as-of anchor`.
- Duy trì một batch đang chạy và tối đa một batch mới nhất đang chờ. Batch pending cũ bị thay bằng anchor mới hơn; queue không tăng vô hạn. Hủy job chưa bắt đầu và kiểm tra cancellation giữa các cặp. Inference đang chạy có thể chỉ dừng sau khi pair hiện tại hoàn tất.
- Deadline cho một phút mô phỏng là `60 / playback_rate` giây wall time. Nếu hết hạn hoặc trễ cadence, không commit alert/result như trạng thái hiện tại; bỏ hoặc thay anchor theo policy đã duyệt.
- SEEK, RESET, đổi mode hoặc session mới làm tăng generation và hủy lease cũ. Chỉ clock progression bình thường mới không làm mất lease; đây là khác với `_check(snapshot)` hiện tại, vốn đòi simulation clock bằng đúng anchor và sẽ đánh dấu snapshot stale khi clock tiến.
- Manual PAUSED tiếp tục dùng đường đánh giá hiện tại với exact anchor. Chế độ PLAYING cần lease riêng cho anchor rời rạc; không sửa `TrackBuffer` history hoặc frozen source-age rules để thích nghi với độ trễ.
- Trước flush, kiểm tra generation/session, deadline, authority boundary và snapshot lease. Quyết định có hiển thị kết quả `as-of` cũ hay chỉ latest completed anchor cần được duyệt.

Số đo C thấp hơn 60 giây trên synthetic fixture tại hai anchor, nhưng chưa chứng minh deadline ở mọi playback rate, môi trường, concurrency hoặc HTTP load.

## 7. Quyết định cần Trung phê duyệt

1. Chọn C làm policy: xác minh package/authority ở đầu và cuối batch; chấp nhận thời gian phát hiện persistent tampering tối đa một batch hay yêu cầu cửa sổ ngắn hơn.
2. Cho phép một full package verification dùng chung cho integrity và threshold tại boundary; xác định external pin/threshold authority được bind vào context theo cách nào.
3. Chấp nhận process/RAM là trusted trong thời gian batch hay yêu cầu biện pháp bảo vệ in-memory mutation. Hash trên đĩa hiện không phát hiện trường hợp này.
4. Chấp thuận load checkpoint/scalers/config từ chính byte buffer đã verify, và policy khi filesystem/pin đổi sau startup.
5. Chấp thuận stage/atomic commit toàn bộ response, alert, cache và idempotency của batch; mọi lỗi boundary sẽ bỏ toàn batch.
6. Duyệt discrete minute-grid anchors khi PLAYING, history/source-age `as-of anchor`, session-generation lease, stale-display rule, deadline, playback-rate support và chính sách bỏ anchor.
7. Giữ scope synthetic academic prototype. Model Lock hiện không phê duyệt runtime integration hoặc production.

## 8. Kế hoạch S5-07B tối thiểu sau phê duyệt

1. Implement context và byte-buffer loading trong runtime module riêng; giữ nguyên hash pin, threshold và Contract V1 semantics.
2. Implement boundary verifier dùng chung package identity/threshold, token chỉ sống một batch, và atomic staging trước publish.
3. Thêm kiểm tra mục tiêu cho manifest/pin/checkpoint/scaler tamper, verify-to-load race trên temporary copies, stale SEEK/RESET, deadline/cancellation, response parity và alert commit rollback.
4. Đo lại hai synthetic anchors và so sánh với số liệu này; sau đó xin duyệt riêng trước khi chạy regression phạm vi rộng hoặc tích hợp Real AIS.

**S5-07B readiness: `CONDITIONAL_PENDING_USER_APPROVAL`.** Feasibility C đã được chứng minh ở synthetic probe; còn pending các quyết định trust boundary, atomic batch publication, RAM threat model và temporal semantics. Không thay đổi production/runtime path trong review này.

## 9. Tính toàn vẹn phạm vi

- Model Lock: không đổi.
- Risk Engine V4 và thresholds: không đổi.
- Contract V1: không đổi.
- Checkpoint, scalers, package và external pin gốc: không đổi.
- Unit tests/full regression/T15/training/calibration/Real AIS: không chạy.
- Source/runtime: không sửa.
- Chỉ file được tạo bởi review: `docs/S5_07A2_RUNTIME_INTEGRITY_OPTIMIZATION_REVIEW.md`.
