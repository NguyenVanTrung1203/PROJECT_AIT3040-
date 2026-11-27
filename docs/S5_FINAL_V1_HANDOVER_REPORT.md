# AIT3040 — Hoàn tất V1 và bàn giao

Ngày lập: 2026-11-27

Branch: `s5-integration-final`

HEAD trước bàn giao: `8f252c522914aa30ba05bd28368ec60cab71c5a6`

## 1. Phiên bản V1 được chọn

**V1_CONDITIONAL_ACCEPTANCE** — các kiểm tra kỹ thuật cốt lõi của synthetic demo đã đạt, gồm automatic evaluation 1×, manual evaluation khi PAUSED, Model M5a thật, Risk Engine V4 và trạng thái alert. Browser acceptance cho giao diện automatic monitoring hiện tại chưa được xác minh; S5-05 chỉ có browser evidence lịch sử cho fixture/manual demo. Không coi bằng chứng API là browser PASS.

Chế độ được chọn là automatic evaluation trong PLAYING, tại anchor UTC theo phút và playback 1×. Manual PAUSED evaluation vẫn dùng được làm phương án dự phòng. Chế độ này chỉ dành cho academic prototype, một backend process và một S5 session.

## 2. Phạm vi và trạng thái runtime

- Runtime context xác minh Model Package, external manifest pin, package inventory, các source/config binding và threshold authority. Checkpoint/scaler/config được nạp từ đúng byte đã verify.
- Mỗi automatic batch có xác minh đầy đủ ở đầu và cuối, token ràng buộc session/generation/snapshot/anchor/deadline, và stage riêng cho kết quả, cache, idempotency cùng alert state. Chỉ publish sau khi batch kết thúc hợp lệ; lỗi hoặc stale generation thì discard.
- Session-generation lease cho phép replay clock tiến trong lúc xử lý anchor. SEEK, RESET và generation/session thay đổi làm snapshot cũ hết hiệu lực.
- Scheduler backend dùng một worker, tối đa một batch đang chạy và một anchor pending mới nhất. Client chỉ đọc trạng thái; UI không tự chạy evaluator khi PLAYING.
- `PAUSED` giữ manual pair/all-pairs evaluation. Runtime trả `official_alerts=false`; không có thẩm quyền cảnh báo hàng hải chính thức.
- Trust boundary tin process và RAM cục bộ trong thời gian batch; không tuyên bố bảo vệ RAM/process tampering.

## 3. Nghiệm thu chức năng cốt lõi

### Replay và session

HTTP/API smoke trên server khởi chạy từ script đã xác nhận tạo session, PLAY, PAUSE, SEEK và RESET. Clock tiến đúng 3 giây trong 3,2 giây wall time. RESET trả session mới ở `READY` và clock `00:00:00Z`. SEEK tạo session mới; kết quả scheduler cũ không được trả như kết quả của session mới.

S5-05 trước đó đã có browser evidence cho hiển thị fixture, map, PLAY/PAUSE, forecast và reset. Giao diện automatic mới chưa được thao tác trực tiếp vì Computer Use không thể xác định URL browser đủ chắc chắn. Do đó hiển thị bản đồ và các panel hiện tại ở browser vẫn `NOT_VERIFIED` trong lần bàn giao này.

### M5a và Risk Engine

Automatic API results cho biết model thực tế `M5A`, forecast `AVAILABLE` với 15 bước dự báo, CPA status khả dụng ở cặp đủ dữ liệu, và runtime `READY`. Model load count là 1 cho toàn phiên kiểm tra. Kết quả sử dụng CC-DRI V4 và operating point M5a `0.420` đã khóa cho prototype; không thay Risk Engine, threshold hay Model Lock.

### Synthetic demo scenarios

| Anchor / cặp | Kết quả kiểm chứng |
| --- | --- |
| 00:09 / A–B | `ALERT`; risk `0.883245546568247` (xấp xỉ `0.8832455466`); forecast và CPA khả dụng. |
| 00:09 / A–C | `NO ALERT`; risk `0.200000000128382` (xấp xỉ `0.2`). |
| 00:09 / A–E | `INSUFFICIENT_DATA`; không sinh risk/forecast giả. |
| 00:09 / tất cả cặp | 10/10 đã xử lý: 1 alert, 5 no-alert, 4 unavailable. |
| 00:15 / A–B | `ALERT`; risk `0.963813225705582` (xấp xỉ `0.9638132257`). |
| 00:15 / tất cả cặp | 10/10 đã xử lý: 1 alert, 9 no-alert, 0 unavailable. |

Đây là kết quả được tính từ fixture và model, không hardcode vào demo. Fixture có provenance synthetic, mang tính sơ đồ và không đại diện tuyến hàng hải thật.

### Manual PAUSED evaluation và stale-result handling

Manual PAUSED evaluation trả quyết định hợp lệ tại 00:09 và 00:15. Đã kiểm tra trường hợp manual evaluation tại 00:15 rồi PLAY trên cùng anchor: batch automatic tính lại dưới snapshot/generation mới, kết quả AB khớp `0.963813225705582`, và batch hoàn tất thay vì tái sử dụng response có binding cũ. SEEK/RESET chuyển sang session mới; endpoint scheduler lọc latest batch theo session nên không trả batch cũ cho session mới.

## 4. Các sửa lỗi trong phạm vi cuối

1. Phát hiện `ENCOUNTER_SNAPSHOT_CONFLICT` nếu manual PAUSED và automatic PLAY đánh giá cùng encounter/anchor qua hai generation khác nhau. Runtime giờ loại bỏ cache/idempotency binding cũ cho đúng session+anchor khi snapshot/generation khác, rồi tính lại dưới lease mới. Không bỏ identity guard, không tái gắn response cũ.
2. P95 bị tính bằng index làm tròn xuống, khiến hai mẫu hiển thị P95 bằng giá trị nhỏ nhất. Percentile đổi sang nearest-rank; unit test xác nhận với hai mẫu 2,361 s và 3,009 s, P50=2,361 s và P95=3,009 s.

Trong lúc kiểm tra startup script, một lỗi cú pháp PowerShell ở chuỗi báo lỗi `.env` cũng được sửa trước khi xác nhận script khởi chạy thành công.

## 5. Hiệu năng automatic evaluation

Đo bằng backend/API thực tế, CPU, batch đủ 10 cặp, playback 1×:

| Anchor | Batch latency | Đủ dữ liệu | Boundary verification |
| --- | ---: | ---: | ---: |
| 00:09 | 3,009 s | 6 eligible, 4 unavailable | Đầu và cuối batch |
| 00:15 | 2,361 s | 10 eligible, 0 unavailable | Đầu và cuối batch |

Với hai batch mẫu, nearest-rank P50=`2,361 s`, P95=`3,009 s`. Đây là hai quan sát của một máy, không phải SLA hoặc ước lượng hiệu năng production. Model được load 1 lần; trong lượt API acceptance `failed=0`, `skipped=0`, `missed_deadlines=0`. Targeted queue test xác nhận tối đa một active batch và một latest pending anchor. Automatic mode chỉ được kiểm chứng ở 1×.

## 6. Kiểm thử cuối

- Python trước hai cập nhật mục tiêu cuối: 11 targeted tests passed; Q1 guard counters đều 0.
- Sau cập nhật cache/generation: 6 targeted batch/API tests passed.
- Lượt targeted cuối sau sửa percentile: 4 passed trong 35,85 giây, gồm nearest-rank, queue bound, manual-to-automatic same-anchor và parity tại 00:09/00:15. Q1: `hash_opens=0`, `blocked_deserialization=0`, `blocked_other_opens=0`.
- Frontend: 64 tests passed. Frontend production build: PASS; frontend source không đổi kể từ lượt build đó.
- Startup scripts: backend preflight báo Python 3.12.3, PyTorch 2.11.0+cu128 trên CPU; Uvicorn chạy thành công. Frontend Vite 7.3.8 khởi chạy thành công. Health backend HTTP 200 và trang frontend HTTP 200.
- Model Lock và Contract V1: không có diff hoặc worktree change trong các đường dẫn đã khóa. Full Python regression, T15, training và calibration không chạy theo phạm vi.
- `git diff --check`: PASS; Git chỉ phát cảnh báo chuyển line ending chuẩn của `README.md` khi checkout trên Windows.
- Browser acceptance và ảnh automatic mới: `NOT_VERIFIED`; không tạo hoặc khai là có ảnh browser mới.

## 7. Khởi chạy và demo

### Cấu hình trên máy nhận

1. Cài Python 3.12, dependencies trong `requirements-dev.txt`, Node.js/npm; chạy `npm ci` trong `frontend/`.
2. Sao chép `.env.example` thành `.env`. Điền đường dẫn tuyệt đối tới thư mục Model Package và detached external manifest pin đã được nhóm chuyển riêng. Pin phải ở ngoài thư mục package. Có thể đặt `AIT3040_PYTHON` tới Python environment riêng; mặc định là `.venv\Scripts\python.exe`.
3. `DATASET_ROOT` không bắt buộc cho synthetic demo; chỉ điền nếu cần dataset tools hoặc Q1 tests. Không chép dataset, checkpoint, scaler hay package vào Git.
4. Terminal 1 tại repository root: `.\scripts\start_backend.ps1`.
5. Terminal 2 tại repository root: `.\scripts\start_frontend.ps1`.
6. Mở `http://127.0.0.1:5173/`; backend health là `http://127.0.0.1:8000/health`.

### Kịch bản thuyết trình 5–10 phút

1. Chọn `S5 nhiều tàu`, giới thiệu nhãn synthetic fixture và các tàu trên map.
2. SEEK đến 00:09 rồi PLAY; xem panel Automatic Monitoring, coverage 10 cặp, AB alert, AC no-alert và các cặp insufficient data.
3. PAUSE, chọn AB và chạy manual evaluation để trình bày score, CPA, threshold và forecast 15 bước.
4. SEEK đến 00:15 rồi PLAY để xem đủ 10 cặp eligible và alert AB được tính lại tự động. Có thể dùng SEEK thay vì chờ sáu phút replay thật.
5. Thử SEEK/RESET và chỉ lại clock/session mới; kết quả forecast cũ không được xem như kết quả hiện hành.
6. Kết thúc bằng giới hạn: dữ liệu synthetic, academic prototype, 1×, process-local, không có official alert.

## 8. Model Package và khả năng tái lập

Model Package cần bàn giao ngoài Git cùng external pin:

- Package directory identity: `m5a-cc-dri-offline-v1.0-20261125T133930Z`.
- Lock ID: `offline-t14-15980ed4f7255ddbdb943979`.
- Manifest SHA-256: `257e77a3a5ae2b2175926145cc0d3c483ccacdaf80f3479d9c352d69f8f6dcdc`.
- Payload SHA-256: `15980ed4f7255ddbdb943979df7dda320ac4ae448e24feb357fa51f3dd38dd79`.
- External pin filename convention: `<package-directory>.manifest_pin.json`.

Máy nhận phải có đúng Model Package, external pin và Python dependencies; verifier sẽ fail closed nếu identity/hash sai. Package cùng checkpoint/scalers, dataset, raw AIS và file `.env` không thuộc commit. Synthetic fixture source nằm trong repository. Baseline dependency binding vẫn là quan sát môi trường, chưa phải deployment lock.

## 9. Giới hạn và phần hoãn

- Browser acceptance của giao diện automatic mới chưa xác minh. Chỉ lịch sử S5-05 có browser evidence cho synthetic/manual demo.
- Chỉ hỗ trợ một process, một active S5 session, một worker và playback 1×. Session/runtime/cache không bền qua restart.
- Prototype tin process/RAM trong batch và không chống RAM tampering. Không có production authority, không có official maritime alert.
- Fixture schematic có thể đặt một số marker gần/trên đất liền; không chỉnh tọa độ để làm đẹp kết quả.
- Real AIS provider và Real Collision Case Study được hoãn sau bàn giao V1; không tải dữ liệu mới.
- Benchmark T15 được giữ theo historical result, không chạy lại hoặc đổi kết luận.
- Interface review của Toàn còn `PENDING`; không tuyên bố Toàn đã nghiệm thu.

## 10. Git handover

Audit trước commit:

- Local branch: `s5-integration-final`; HEAD trước handover `8f252c522914aa30ba05bd28368ec60cab71c5a6`.
- 38 dirty paths của công việc S5 chưa commit được bảo toàn; báo cáo này là file thứ 39 trong tập handover.
- Frozen contracts, Model Lock, Risk Engine V4 reference, thresholds, dataset và external model package không nằm trong diff.
- Secret-pattern scan không phát hiện credential/key. Không có file candidate nào lớn hơn 5 MB; không có dataset/checkpoint/scaler hoặc generated frontend build trong danh sách commit.
- `origin` truy cập được. Remote có `main` và `s4-integration-final` tại baseline trên; không có remote branch `s5-integration-final`. Local commit sẽ không được push.
- Commit cục bộ được tạo theo ủy quyền hiện có với message `Finalize AIT3040 V1 academic prototype and demo handover`. SHA được trả trong final response.
- Push: không thực hiện. Merge: không thực hiện.

### Tập file được bàn giao trong commit

```text
.env.example
README.md
backend/app/main.py
backend/app/replay_api.py
backend/app/runtime_http.py
backend/tests/test_s5_04a_runtime_http.py
configs/s5_runtime_dependency_binding.json
docs/S5_00_DESIGN_FREEZE_AND_RUNTIME_FOUNDATION_REPORT.md
docs/S5_01_TRUSTED_PAIR_AND_ENCOUNTER_REPORT.md
docs/S5_02_RUNTIME_M5A_INFERENCE_REPORT.md
docs/S5_03_RUNTIME_RISK_AND_ALERT_REPORT.md
docs/S5_04A_RUNTIME_HTTP_INTEGRATION_REPORT.md
docs/S5_04B_MAP_AND_FORECAST_INTEGRATION_REPORT.md
docs/S5_05_RISK_ALERT_UI_AND_DEMO_REPORT.md
docs/S5_06A_REAL_AIS_SOURCE_READINESS_REPORT.md
docs/S5_06_REAL_COLLISION_AIS_DISCOVERY_REPORT.md
docs/S5_06_REAL_COLLISION_RAW_AIS_FEASIBILITY_REPORT.md
docs/S5_07A_RUNTIME_PERFORMANCE_OPTIMIZATION_REPORT.md
docs/S5_07A2_RUNTIME_INTEGRITY_OPTIMIZATION_REVIEW.md
docs/S5_FINAL_V1_HANDOVER_REPORT.md
frontend/src/App.jsx
frontend/src/App.s5.test.jsx
frontend/src/styles.css
scripts/start_backend.ps1
scripts/start_frontend.ps1
src/data/replay_session_core.py
src/runtime/__init__.py
src/runtime/batch_scheduler.py
src/runtime/config.py
src/runtime/m5a_service.py
src/runtime/risk_service.py
src/runtime/trusted_fixture.py
src/runtime/verified_context.py
tests/unit/test_s5_00_runtime_config.py
tests/unit/test_s5_01_trusted_fixture.py
tests/unit/test_s5_02_runtime_m5a.py
tests/unit/test_s5_03_runtime_risk.py
tests/unit/test_s5_07b_batch_runtime.py
tests/unit/test_s5_07b_http_surface.py
```
