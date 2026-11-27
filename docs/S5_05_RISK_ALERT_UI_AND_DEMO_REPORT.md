# S5-05 — Dashboard rủi ro, cảnh báo và demo

Ngày cập nhật: 2026-11-26
Branch: s5-integration-final
Worktree: C:\Users\MSI\Documents\Codex\2026-11-20\files-pasted-by-the-user-sprint-2\work\s5-integration-final
Baseline HEAD: 8f252c522914aa30ba05bd28368ec60cab71c5a6

## Trạng thái

- S5_05_STATUS=PASS_WITH_LIMITATIONS.
- DEMO_READY=PASS_WITHIN_SYNTHETIC_FIXTURE_SCOPE.
- Session recovery sau reload được xác minh hai lần trên cùng active session; không tạo session mới.
- Frontend suite gần nhất: 62 passed. Frontend production build: PASS.
- Backend regression tập trung cho session discovery/recovery và snapshot hết hạn: 2 passed. Q1 guard counters đều bằng 0.
- Model Lock, Risk Engine V4, thresholds và Contract V1 semantics không thay đổi.
- Dữ liệu Real AIS chưa được xác minh; demo chỉ dùng synthetic fixture.
- Không chạy full Python regression, training, calibration hoặc benchmark T15. Không commit, push hoặc merge.

## Blocker reload: nguyên nhân và khắc phục

Lỗi HTTP 409 ban đầu xảy ra vì ReplayAuthority chỉ hỗ trợ một active S5 fixture session trên mỗi backend process. Khi frontend tải lại, UI không còn session reference và cố tạo session thứ hai; backend từ chối đúng theo giới hạn hiện có.

Frontend hiện gọi endpoint bổ sung GET /api/v1/runtime/active-session khi vào chế độ S5. Nếu có phiên đang hoạt động, UI nhận session ID, version và clock có thẩm quyền rồi nạp lại tracks, candidates và alerts qua các API hiện có. Luồng này không dùng localStorage làm nguồn sự thật, không reset phiên và không lặp thử tạo session vô hạn. Sau reload, giao diện trở về chế độ Mock; cần chọn lại S5 nhiều tàu để discovery/restore chạy.

Kiểm tra browser cho thấy cùng session ID 11eae67b-3cad-4228-bace-253a609613c5 và clock 00:00:14Z được khôi phục hai lần. GET session, candidates và tracks trả 200; không có POST tạo session mới trong các lần reload đó.

Trong quá trình xác minh còn phát hiện snapshot đã hết TTL nhưng vẫn được giữ trong cache process-local. Khi một snapshot đã pin trả 404 hoặc 410, RuntimeState hiện xóa đúng cache snapshot/candidates/coverage tương ứng và pin lại snapshot tại clock có thẩm quyền hiện tại. Không thay đổi session, clock, contract hay thuật toán rủi ro. Snapshot ID cũ không được chấp nhận sau khi repin.

Kiểm thử backend test_active_s5_recovery_repins_expired_snapshot xác nhận session vẫn hoạt động, snapshot mới được cấp, tracks trả 200 và yêu cầu dùng snapshot ID cũ trả 409. Test discovery/replacement hiện có cũng PASS. Endpoint active-session là bổ sung transport/runtime; Contract V1 không đổi.

Ảnh lịch sử 06_full_dashboard_http409.png được giữ nguyên và vẫn thể hiện lần lỗi trước khi khắc phục. Ảnh 06_full_dashboard.png là dashboard sau recovery, không thay thế ảnh lịch sử.

## Kết quả demo trên synthetic fixture

| Demo | Anchor / cặp | Kết quả quan sát |
| --- | --- | --- |
| A | 00:09 / A–B | Risk 0.8832455466 (hiển thị 0.883246), threshold 0.420, ALERT; predicted DCPA 0.058816 NM; CPA sau 8 phút. |
| B | 00:15 / A–B | Risk 0.9638132257 (hiển thị 0.963813), threshold 0.420, ALERT; predicted DCPA 0.029867 NM; CPA sau 2 phút. |
| C | 00:09 / A–C | Risk 0.200000, threshold 0.420, NO ALERT. |
| D | 00:09 / A–E | Insufficient data; không tạo forecast/risk giả. |
| E | 00:09 / tất cả cặp | 1 alert, 5 no-alert, 4 unavailable. |
| E | 00:15 / tất cả cặp | 1 alert, 9 no-alert; 10/10 cặp đã xử lý. |
| F | risk components | Hiển thị predicted CPA 0.854146, current CPA 0.853551, rule proxy 1.000000 và THRESHOLD_APPLIED; current CPA AVAILABLE. |

Replay PLAY làm clock tiến lên; PAUSE dừng tại 00:00:14Z trong phiên kiểm tra. Risk evaluation được chấp nhận tại anchor PAUSED. Continuous playback inference không được xác nhận là chế độ hỗ trợ. Reset xóa forecast/risk/alert cũ. Sau SEEK, có thể cần bấm Refresh replay data để nạp snapshot/candidates ở anchor mới trước khi đánh giá.

## Bằng chứng browser, API và automated test

Bằng chứng browser:

- Hai lần reload rồi chọn lại S5 nhiều tàu: cùng session ID và clock được khôi phục; giao diện hiển thị tracks/candidates.
- PLAY tiến clock; PAUSE dừng clock.
- A–F được thao tác trên synthetic fixture. Các ảnh dưới đây là ảnh chụp Chrome thực tế.
- 06_full_dashboard_http409.png là bằng chứng lịch sử lỗi, không được tính là demo PASS.

Bằng chứng API:

- Health endpoint trả {"status":"ok"}.
- Các GET session, candidates và tracks của phiên mới trả 200 sau reload. Network panel của phiên hiện tại cũng cho thấy các request này trả 200.
- Log lịch sử có GET tracks trả 410 cho snapshot đã hết hạn trước bản sửa. Sau bản sửa, cache snapshot hết hạn được repin; kiểm thử backend xác nhận hành vi stale ID.
- Network panel tích lũy 393 request từ nhiều thao tác/lượt kiểm tra; vì vậy chỉ các request hiện tại được xác nhận 200, không tuyên bố toàn bộ lịch sử network không có lỗi.

Console:

- Không thấy exception từ ứng dụng React trong lượt cuối.
- Console có một unchecked runtime.lastError “Could not establish connection. Receiving end does not exist.”, có vẻ liên quan extension nhưng nguồn chưa được chứng minh. Đây là NOT_VERIFIED về nguồn gốc, không được gán là lỗi ứng dụng.
- Lượt cũ có favicon 404 và lỗi 410 của snapshot hết hạn; những lỗi lịch sử này được ghi nhận riêng, không bị xóa khỏi evidence.

Automated tests:

- Frontend: 62 passed; frontend production build: PASS. Bộ test bao gồm session recovery sau reload, generation/stale-response protection, batch evaluation, pair/mode/control changes và các trạng thái unavailable.
- Backend targeted: 2 passed trong 10.49 giây; gồm active session discovery/replacement và repin snapshot hết hạn.
- Q1 access guard: hash_opens=0, blocked_deserialization=0, blocked_other_opens=0.
- Lần pytest đầu bị treo trước khi bắt đầu thu thập test do Windows asyncio Proactor socketpair startup. Lượt targeted cuối chạy trong môi trường hiện có và PASS.
- Không chạy full Python regression theo giới hạn task.

## Ảnh demo

Thư mục: C:\Users\MSI\Documents\Codex\2026-11-20\files-pasted-by-the-user-sprint-2\s5_demo_evidence

- 01_system_overview.png — tổng quan hệ thống; giữ nguyên.
- 02_multivessel_replay.png — replay nhiều tàu; giữ nguyên.
- 03_m5a_forecast_0009.png — forecast M5a tại 00:09; giữ nguyên.
- 04_m5a_forecast_0015.png — forecast M5a tại 00:15; giữ nguyên.
- 05_insufficient_data.png — trạng thái thiếu dữ liệu; giữ nguyên.
- 06_full_dashboard.png — dashboard S5 sau recovery.
- 06_full_dashboard_http409.png — ảnh lỗi HTTP 409 lịch sử, giữ nguyên.
- 07_collision_alert_0009.png — A–B, alert tại 00:09.
- 08_collision_alert_0015.png — A–B, alert tại 00:15.
- 09_no_alert.png — A–C, no-alert.
- 10_insufficient_data.png — A–E, insufficient data.
- 11_all_pairs_evaluation.png — đánh giá tất cả cặp tại 00:15.
- 12_risk_components.png — các thành phần risk/CPA.
- 12_reset_cleared_forecast.png — ảnh phụ xác nhận reset xóa forecast cũ.

Các ảnh gốc có tên khác và ảnh 01–05 không bị ghi đè.

## Kiểm thử và thay đổi liên quan

- Frontend suite gần nhất: 62 passed; frontend build PASS. Frontend không đổi kể từ lượt xác minh đó.
- Backend targeted recovery tests: 2 passed trong 10.49 giây.
- Q1 guard counters: 0 lần hash open, 0 deserialization bị chặn, 0 lần open khác bị chặn.
- git diff --check sẽ được kiểm tra sau khi cập nhật báo cáo.
- Backend thay đổi chỉ xử lý cache snapshot đã hết hạn trong recovery. Test mới xác minh repin và từ chối stale snapshot ID.
- Không sửa Model Lock, Risk Engine V4, thresholds, dataset, checkpoint/scaler hay Contract V1.

## Chạy demo trong worktree

Backend — mở PowerShell tại worktree s5-integration-final:

    Set-Location 'C:\Users\MSI\Documents\Codex\2026-11-20\files-pasted-by-the-user-sprint-2\work\s5-integration-final'
    $env:PYTHONDONTWRITEBYTECODE = '1'
    $env:DATASET_ROOT = 'C:\Users\MSI\Desktop\PROJECT_AIT3040\DATASET_FINAL'
    $env:AIT3040_MODEL_PACKAGE = 'C:\Users\MSI\Documents\Codex\2026-11-20\files-pasted-by-the-user-sprint-2\s4_t14_model_packages\m5a-cc-dri-offline-v1.0-20261125T133930Z'
    $env:AIT3040_MODEL_MANIFEST_PIN = 'C:\Users\MSI\Documents\Codex\2026-11-20\files-pasted-by-the-user-sprint-2\s4_t14_model_packages\m5a-cc-dri-offline-v1.0-20261125T133930Z.manifest_pin.json'
    $env:AIT3040_RUNTIME_DEVICE = 'cpu'
    $env:AIT3040_RUNTIME_AUTHORITY = 'S5-D10-TRUNG-ACADEMIC-PROTOTYPE'
    $env:AIT3040_DEMO_MAX_VESSELS = '5'
    $env:AIT3040_MAX_CONCURRENCY = '1'
    & 'C:\Users\MSI\Desktop\PROJECT_AIT3040\.venv\Scripts\python.exe' -B -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000

Frontend — PowerShell thứ hai, working directory frontend:

    Set-Location 'C:\Users\MSI\Documents\Codex\2026-11-20\files-pasted-by-the-user-sprint-2\work\s5-integration-final\frontend'
    npm run dev -- --host 127.0.0.1 --port 5173 --strictPort

Mở http://127.0.0.1:5173/ và chọn S5 nhiều tàu. Health endpoint: http://127.0.0.1:8000/health.

## Giới hạn và readiness

- Một active S5 fixture session cho mỗi backend process; process restart làm mất session process-local. Frontend reload mặc định về Mock mode; chọn lại S5 để đọc active session.
- Synthetic fixture only. Real AIS validation chưa thực hiện và được để ngoài phạm vi này. Fixture có một số marker trên đất liền; không hiệu chỉnh tọa độ.
- Runtime risk evaluation được xác minh tại anchor PAUSED. Continuous PLAY evaluation chưa được chấp nhận. Sau SEEK có thể cần refresh dữ liệu replay.
- Một console runtime.lastError chưa xác minh được nguồn. Request network hiện tại liên quan phiên recovery trả 200; lịch sử Network tích lũy vẫn chứa các request của lượt trước.
- Interface review của Toàn vẫn PENDING. S5-06 chưa triển khai và cần review/điều phối giao diện với Toàn cùng quyết định tiếp theo của nhóm.
- S5-05 hoàn tất trong giới hạn synthetic fixture. Chưa tuyên bố product/production readiness hoặc khả năng phát cảnh báo hàng hải chính thức.

Commit/push/merge: không thực hiện.
