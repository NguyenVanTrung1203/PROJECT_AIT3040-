# S4 Final Integration and Acceptance

## Trạng thái tổng thể

- AUTOMATED_ACCEPTANCE=PASS_WITH_APPROVED_SCOPE_LIMITATION: full regression 674 passed/6 skipped; năm original V4 parity tests đã PASS bổ sung; real AIS replay chuyển Sprint 5.
- BROWSER_UI_SMOKE=PASS; core fixture được xác minh bằng browser/API/automated; matrix 43 PASS, 2 NOT_VERIFIED (Console/Network trực tiếp); BUG-01 đã sửa.
- S4_CLOSURE_DECISION=APPROVED_WITH_LIMITATIONS; S4_TECHNICAL_READY=COMPLETED_WITH_LIMITATIONS.
- S4_DEMO_READY=SMOKE_ONLY_WITH_LIMITATIONS.
- MERGE_TO_MAIN_READINESS=APPROVED_SUBJECT_TO_GIT_PREFLIGHT; Console/Network trực tiếp NOT_VERIFIED, giới hạn evidence được Trung chấp nhận theo S4-D03.
- Không tạo commit cuối, không push, không merge vào main.

## A. Tóm tắt

Phần S4 của Trung và Toàn đã hợp nhất trên nhánh integration riêng. Hai lỗi Replay đã được xử lý: ReplayAPI nạp observation theo simulation clock để giữ đúng history; TrackBuffer không suy diễn original parent timestamp từ selected timestamp. Targeted Python, frontend tests và production build đạt theo các lần chạy đã ghi nhận. Full regression đã hoàn tất 674 passed, 6 skipped; năm parity tests đã PASS bổ sung. Trung đã quan sát UI smoke PASS; functional acceptance còn INCOMPLETE_WITH_KNOWN_ISSUES.

## B. Git integration

- Repository: PROJECT_AIT3040-.
- Main base: 04f411ee6c356d872fef63615c28970e6bc3547c.
- Toàn source: 2213ddad9e1b00be871cd5e8e70b13736ec0667f.
- Trung S4 commit 378c5fe83d642b773963582c97e7640015d262a2 đã nằm trong main.
- Integration branch: s4-integration-final.
- Merge commit: 3b3f9f17d67d1c0941c84c2928985711cd5dd5fc; parents là main base và Toàn source.
- Merge conflicts: none.
- Sửa đổi cuối ở trạng thái unstaged để Trung review. Không stage, commit, push, tạo PR hoặc merge vào main.

## C. Sprint 4 deliverables

| Deliverable | Trạng thái | Ghi chú |
|---|---|---|
| Trung — T14 Model Lock | COMPLETED_VERIFIED (historical) | Bằng chứng nghiệm thu trước đó được giữ nguyên; không chạy lại calibration hoặc xác minh package. |
| Trung — T15 technical acceptance | COMPLETED_VERIFIED (historical) | Kết quả trước đó được giữ nguyên; không chạy lại benchmark. |
| Trung — T15 benchmark | COMPLETED_WITH_LIMITATIONS | BENCHMARK_FAIL đã được chấp nhận trong prototype scope; không đổi thành PASS. |
| Toàn — T04 Mock API | COMPLETED_VERIFIED (historical) | Mock scope. |
| Toàn — T12 Replay fixture | COMPLETED_VERIFIED (historical + targeted checks) | Fixture scope; không khẳng định replay trên AIS thật. |
| Toàn — T16 audit | COMPLETED_VERIFIED (historical) | Không chạy lại audit lịch sử. |
| Toàn — T17 UI | COMPLETED_WITH_LIMITATIONS | UI smoke PASS theo Trung; functional acceptance incomplete, có lỗi chưa phân loại. |
| Tích hợp chung | COMPLETED_WITH_LIMITATIONS | Trung duyệt đóng có giới hạn; merge main chờ review severity lỗi browser. |

Các kết quả historical không được tính là test mới.

## D. Sửa lỗi tích hợp

### B05 — Replay retention và as-of

Root cause là ReplayAPI nạp toàn bộ source events khi tạo session trong khi TrackBuffer giữ retention 900 giây. Với source dài, history đầu replay có thể bị loại bỏ trước khi clock đến đó.

backend/app/replay_api.py hiện:
- Khởi tạo session từ indexed lookback 10 phút quanh anchor.
- Nạp event tiếp theo chỉ đến simulation clock hiện tại.
- Cập nhật event cursor theo clock; seek/reset lấy history theo anchor tương ứng.
- Không đưa observation tương lai vào snapshot.

Regression fixture dài 30 phút trong backend/tests/test_replay_api.py kiểm tra đầu/giữa source, seek tiến/lùi, reset, history và as-of semantics.

### B04 — Synthetic timestamp provenance

src/data/track_buffer.py giữ original_source_timestamp=null khi nguồn không cung cấp giá trị đó; selected timestamp không còn được dùng làm parent provenance. Timestamp gốc không hợp lệ bị từ chối; với REAL_AIS, original timestamp có sẵn nhưng không khớp vẫn bị từ chối.

Regression cases ở tests/unit/test_track_buffer.py. Dataset và Contract V1 không đổi.

## E. T17 browser acceptance

Bằng chứng ban đầu (lịch sử): Trung trực tiếp xác nhận frontend tải, backend/frontend giao tiếp trong fixture, tạo Replay Session, xuất hiện early marker, hiển thị Simulation UTC và trạng thái PLAYING: BROWSER_UI_SMOKE=PASS. Một số chức năng còn lỗi chưa có danh sách hoặc bằng chứng B01–B12 đầy đủ: BROWSER_FUNCTIONAL_ACCEPTANCE=INCOMPLETE_WITH_KNOWN_ISSUES; severity=NOT_VERIFIED. Không suy đoán chức năng cụ thể hay đánh dấu checklist PASS.

### Khởi chạy cục bộ

Mở hai terminal PowerShell riêng.

Terminal 1 — backend. Working directory: integration worktree root.

    Set-Location -LiteralPath 'C:\Users\MSI\Documents\Codex\2026-11-20\files-pasted-by-the-user-sprint-2\work\s4-integration-final'
    & 'C:\Users\MSI\Desktop\PROJECT_AIT3040\.venv\Scripts\python.exe' -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000

Health endpoint: http://127.0.0.1:8000/health
Kết quả mong đợi: {"status":"ok","service":"mock-track-api"}.

Terminal 2 — frontend. Working directory: frontend bên trong integration worktree. Dependencies có sẵn; không chạy npm ci hoặc cài package.

    Set-Location -LiteralPath 'C:\Users\MSI\Documents\Codex\2026-11-20\files-pasted-by-the-user-sprint-2\work\s4-integration-final\frontend'
    $env:VITE_API_BASE_URL = 'http://127.0.0.1:8000'
    & 'C:\Program Files\nodejs\npm.cmd' run dev -- --host 127.0.0.1 --port 5173 --strictPort

Mở http://127.0.0.1:5173/. Chọn nút Replay fixture, rồi Bắt đầu replay fixture. API tạo source fixture-denmark-10m-v1: fixture tổng hợp 10 phút từ 2024-11-01T00:00:00Z, một tàu và observation mỗi phút đến 00:09:00Z.

### Checklist cho Trung

Ghi PASS/FAIL cho mỗi mục. Chụp ảnh tối thiểu tại B04 và B10.

| Mã | Thao tác | Kết quả mong đợi |
|---|---|---|
| B01 | Mở frontend sau khi hai server chạy. | Trang Track Map tải xong; không có overlay lỗi Replay/Mock API. |
| B02 | Chọn Replay fixture rồi Bắt đầu replay fixture. | Session READY, có session ID, simulation time 2024-11-01T00:00:00Z. |
| B03 | Quan sát tàu ở thời điểm bắt đầu. | Tàu synthetic xuất hiện tại observation đầu, khoảng lat 55.680/lon 12.560. |
| B04 | Chọn tàu và xem badge/lịch sử tại 00:00Z. | INSUFFICIENT_DATA, history 1/10; marker dùng observation hợp lệ, current_state=null; Forecast Mock disabled. |
| B05 | Nhấn PLAY; quan sát 2–3 giây. | Status PLAYING và Simulation UTC tiến lên. |
| B06 | Nhấn PAUSE. | Status PAUSED; Simulation UTC dừng tăng khi quan sát thêm vài giây. |
| B07 | Nhấn RESUME. | Status PLAYING; Simulation UTC tiếp tục tăng. |
| B08 | Dừng playback nếu cần; seek đến 00:09:00Z rồi 00:02:00Z. | 00:09 có history 10/10 và đủ điều kiện; 00:02 có history 3/10, INSUFFICIENT_DATA và không có forecast state. |
| B09 | Nhấn RESET. | Session READY mới ở 00:00:00Z; history trở về observation đầu và forecast layer bị xóa. |
| B10 | Seek 00:09Z; chọn tàu VALID có history 10/10; bật Bật lớp Forecast Mock. | Xuất hiện MOCK FORECAST — NOT MODEL OUTPUT và legend FORECAST MOCK. Không có risk score, CPA, threshold hoặc alert. |
| B11 | Khi forecast bật, seek lùi 00:02Z rồi thử RESET. | Forecast cũ biến mất, lớp bị tắt, không dùng kết quả từ anchor/session cũ. |
| B12 | Mở DevTools Console/Network và lặp lại B02–B11. | Không có exception JavaScript hoặc API /api/v1/ lỗi nghiêm trọng; session/control/tracks trả thành công. Ghi riêng lỗi tile OpenStreetMap nếu mạng ngoài chặn tile. |

## F. Test results

### Targeted Python — đã chạy trước full regression

- tests/unit/test_track_buffer.py + backend/tests/test_replay_api.py: 32 passed.
- tests/unit/test_replay_session_core.py + tests/integration/test_ais_replay_cli.py + tests/integration/test_t08_t09_replay_integration.py: 10 passed, 1 skipped.
- Tổng: 42 passed, 1 skipped. Q1 guard counters trong targeted runs bằng 0.
- Warning: StarletteDeprecationWarning từ starlette.testclient/httpx.

### Skip cụ thể

- Test: tests/integration/test_t08_t09_replay_integration.py::test_controlled_real_ais_slice_reaches_t09_without_future_leakage.
- Nguyên nhân: AIS_REPLAY_ROOT chưa đặt và default maritime-ais-system/data/processed/ais_cleaned không tồn tại; test skip với lý do cleaned AIS source is not present in this environment.
- Skip gate đã có trong Toàn source commit 9c6b1d80, trước các sửa đổi tích hợp hiện tại; không phát sinh từ retention/provenance fix.
- Tác động: replay trên AIS source thật là NOT_VERIFIED; skip này không làm hỏng kiểm thử synthetic fixture. Không xóa test hoặc ép skip thành PASS.

### Full Python regression — lần chạy trước khi sửa LF (lịch sử)

Đã chạy từ integration worktree bằng Python environment có sẵn, thêm -rs để in lý do skip:

    $env:DATASET_ROOT = 'C:\Users\MSI\Desktop\PROJECT_AIT3040\DATASET_FINAL'
    $env:PYTHONDONTWRITEBYTECODE = '1'
    & 'C:\Users\MSI\Desktop\PROJECT_AIT3040\.venv\Scripts\python.exe' -m pytest -p scripts.q1_test_access_guard tests/unit tests/integration backend/tests -q -rs

- Collected: không được báo cáo do collection bị ngắt.
- Passed: 0 test được thực thi.
- Failed assertions: 0.
- Errors: 7 lỗi collection.
- Skipped/deselected: không được báo cáo do collection bị ngắt.
- Warnings: 1 StarletteDeprecationWarning.
- Thời gian: 57.51 giây.
- Q1 guard: hash_opens=0, blocked_deserialization=0, blocked_other_opens=0.

Bảy module không import được đều đi qua src.risk.adapter; adapter dừng ở kiểm tra SHA-256 của src/risk/reference_v4/risk_pipeline.py. Root cause khoanh vùng mà không sửa Risk Engine: Git core.autocrlf=true, thuộc tính eol không khai báo cho file này. Git blob có LF và khớp hash pin 8e33effb06d7f2e1fe855b1cb067fb2d27eb3aba9498e2af30be1b387534be7e; Windows worktree có CRLF và SHA-256 72d716721bf1ce3084ff83c7d78755e7e174ff143adc85132d593b00f3c9039a. Do file Risk Engine/lock nằm ngoài phạm vi được phép sửa, chưa chuẩn hóa line ending hoặc thay hash. Cần quyết định cách cấu hình checkout giữ byte LF canonical rồi chạy lại full regression.

### Frontend

- Frontend tests: 20 passed trên 2 files (kết quả đã có; không chạy lại).
- Production build: PASS (kết quả đã có; không chạy lại).
- Browser UI smoke: PASS theo Trung; BUG-01 đã sửa; kết quả closure mới nhất tại mục Q.

## G. Bảo toàn Model Lock và bằng chứng lịch sử

Không có Git diff cho Model Lock, model/config/risk files, Contract V1, dataset, T14/T15 protocol hoặc historical evidence. Checkpoint/scalers/package không được chép vào Git. Model architecture, selected epoch, thresholds 0.420/0.435, comparator >= và trạng thái benchmark BENCHMARK_FAIL được giữ nguyên.

Blocker CRLF đã được xử lý; import src.risk.adapter và adapter.verify_reference() PASS. Năm test V4 original skip trong full regression đã PASS bổ sung theo mục M.

## H. Giới hạn và bàn giao Sprint 5

- Thiếu session/version envelope cho consumer model/risk, online candidate-pair provider, encounter builder và trusted runtime model adapter.
- Runtime inference T18, runtime Risk Engine T19, runtime threshold authorization và live forecast/risk/alert integration chưa được implement.
- T20/T21 cần xác nhận assignment.
- Model package nằm ngoài Git, cần chuyển/kiểm tra riêng trong phạm vi được duyệt.
- S4-D01 APPROVED: replay scope SYNTHETIC_FIXTURE_ONLY; real AIS replay NOT_VERIFIED, test SKIPPED do thiếu cleaned source và DEFERRED_TO_SPRINT_5. Dataset nghiên cứu Train/Validation/Test không đổi.
- Session/snapshot/idempotency state ở memory của một backend process; chưa có persistence, multi-worker consistency hoặc restart recovery.
- Không tuyên bố Sprint 5 ready, production ready hoặc model superiority.

## I. Merge readiness

| Phạm vi | Trạng thái |
|---|---|
| Merge S4 code vào integration branch | PASS |
| Replay retention/provenance targeted fixes | PASS |
| Targeted Python + frontend automated checks | PASS |
| Full Python regression | PASS WITH SKIPS — 674 passed, 6 skipped, Q1 guard hoạt động |
| S4 fixture/demo | Core PASS trong synthetic fixture qua browser/API/automated; Console/Network trực tiếp NOT_VERIFIED |
| S4 technical completion | COMPLETED_WITH_LIMITATIONS theo quyết định của Trung; quy trình đóng chờ main merge |
| Merge vào main | APPROVED_SUBJECT_TO_GIT_PREFLIGHT — Console/Network trực tiếp NOT_VERIFIED, S4-D03 approved |
| T18/T19 integration readiness | NO |
| Production readiness | NO |

## J. Demo evidence và bước tiếp theo

T11 và backend targeted checks đã đạt; năm original V4 parity tests đã PASS bổ sung. Trung cần hoàn thành browser checklist B01–B12 trước khi xem xét nghiệm thu và merge main.

## K. LF remediation and post-fix regression

### Khôi phục byte canonical

- Trước khi sửa: worktree SHA-256 72d716721bf1ce3084ff83c7d78755e7e174ff143adc85132d593b00f3c9039a; 38 CRLF, không có LF-only.
- Trước khi thêm thuộc tính, .gitattributes không tồn tại và core.autocrlf=true được đọc từ C:/Program Files/Git/etc/gitconfig; đây là nguyên nhân checkout CRLF. Không đổi Git config toàn hệ thống. Git blob SHA-256 8e33effb06d7f2e1fe855b1cb067fb2d27eb3aba9498e2af30be1b387534be7e khớp expected hash; blob có 38 LF-only, không có CRLF.
- Chuẩn hóa CRLF của worktree trước sửa sang LF cho kết quả byte-for-byte bằng Git blob; không có khác biệt nội dung.
- Thêm duy nhất rule .gitattributes: src/risk/reference_v4/risk_pipeline.py text eol=lf. Git check-attr xác nhận text=set, eol=lf.
- Khôi phục bằng Path.write_bytes từ output binary của git show HEAD:path, không dùng text redirection/encoding. Sau sửa, worktree SHA-256 là 8e33effb06d7f2e1fe855b1cb067fb2d27eb3aba9498e2af30be1b387534be7e và bytes bằng Git blob.
- Hash pin, adapter, reference logic và các Model Lock files không đổi. Git diff không có nội dung diff cho src/risk/reference_v4/risk_pipeline.py hoặc src/risk/adapter.py. Worktree status vẫn báo M cho risk_pipeline.py sau sửa line ending; nội dung byte hiện tại khớp chính xác Git blob. Không stage/commit.
- Các pin source trong configs/risk_reference_manifest.yaml, configs/s4_calibration_protocol.yaml và T15 protocol files đều trỏ tới cùng src/risk/reference_v4/risk_pipeline.py. Không tìm thấy source .py hash pin thứ hai trong các manifest/list này. Không renormalize repository.

### Import và hash guard

Với Python 3.12.3 hiện có, PYTHONDONTWRITEBYTECODE=1 và -B:
- Import src.risk.adapter: PASS.
- adapter.verify_reference(): PASS.
- Hash guard mismatch test hiển thị PASSED trong partial pytest output; verifier không bị bypass.

### Regression sau sửa LF

- Lượt sau sửa với -q -rs đã đến khoảng 95%, không phát ra summary sau thời gian dài và bị ngắt; không có pytest/Q1 footer.
- Lượt verbose tiếp theo thu thập 680 items. Partial output có lỗi/failure trong tests/unit/test_s3_t11_inference.py (trong đó test_real_artifacts_and_cpu_inference ERROR, test_auto_and_invalid_device FAILED và test_manifest_and_scaler_corruption FAILED); không có traceback tổng kết để xác định đầy đủ nguyên nhân.
- Lượt verbose dừng ở 96% khi tests/integration/test_t08_t09_replay_integration.py::test_controlled_real_ais_slice_reaches_t09_without_future_leakage được báo SKIPPED, rồi backend/tests/test_mock_api.py::test_list_tracks_matches_snapshot_schema_and_has_valid_positions không trả kết quả hơn năm phút. Lượt này được ngắt; không có pytest summary.
- Tổng collected: 680. Passed/failed/errors/skipped/deselected, warnings, elapsed tổng và Q1 guard counters: NOT_REPORTED do run bị ngắt trước summary/session hook.
- Partial output xác nhận real AIS skip đã biết; lý do và tác động được ghi tại mục F. Các skip khác xuất hiện trong partial output nhưng tổng số và đầy đủ lý do chưa được báo cáo.
- Tại thời điểm lượt chạy bị ngắt, automated acceptance BLOCKED. Kết quả lần chạy tiếp theo được ghi tại mục L.

### Acceptance split

- Synthetic fixture: targeted replay/retention and provenance checks passed; frontend 20 tests/build passed. Full suite sau đó hoàn tất như mục L.
- Real AIS replay: NOT_VERIFIED; the cleaned AIS source was unavailable and the integration test skipped.
- Scope acceptance: S4-D01 APPROVED; synthetic fixture-only replay. Real AIS replay test remains SKIPPED and NOT_VERIFIED, deferred to Sprint 5.

## L. Targeted regression debug và full regression hoàn tất

- T11 root cause: integration worktree không có thư mục artifacts/checkpoints/s3_t10_20261124_seed20261110_run01 mà test tham chiếu tương đối. Lượt đầu: 3 failed, 18 errors; traceback báo thiếu checksums.sha256.
- Artifact T10 hiện có trong worktree trung-contract-v1-freeze đã qua verify_artifacts, bao gồm checkpoint e01a19e913d14a068c6c82a1c2a52a8be2aadd2f44e3ad5d8770d7f69a1fc7bc, X scaler a538be921104ed1bb2fa495c0c3f527c0385fd6c737aa69afda81ba1962d452a và residual scaler 96b062fab9a5d4e27c9b1cc32a649e44e98d29648c7dcc3b7f482eba3d50358f. Một bản sao ignored được đặt đúng đường dẫn test; không đổi artifact gốc hoặc verifier.
- T11 inference và trusted boundary: 37 passed trong 31.98s; Q1 counters hash_opens=28, blocked_deserialization=0, blocked_other_opens=0.
- Backend hang: faulthandler cho thấy Windows event loop chờ socket.accept trong socketpair khi TestClient khởi tạo AnyIO portal bên trong sandbox. Cùng test ngoài sandbox với Q1 guard: 1 passed; toàn bộ backend/tests: 22 passed, 1 warning. Đây là bằng chứng khác biệt môi trường, chưa chứng minh cơ chế sandbox cụ thể; không sửa backend.
- Full regression với Q1 guard ngoài sandbox: 680 collected (theo số test chạy), 674 passed, 0 failed, 0 errors, 6 skipped, 0 deselected, 1 StarletteDeprecationWarning, 118.94s. Q1 counters hash_opens=42, blocked_deserialization=0, blocked_other_opens=0. Log: s4_targeted_full_regression.log ở thư mục task Codex.
- Trong lượt full regression, năm test original V4 parity skip vì V4_REFERENCE_RISK_PATH chưa đặt; năm test này đã PASS bổ sung tại mục M. Một skip là controlled real AIS slice vì AIS_REPLAY_ROOT/default cleaned source không tồn tại.
- Synthetic fixture: targeted tests và full suite đạt trong phạm vi đã chạy. Real AIS replay: NOT_VERIFIED và DEFERRED_TO_SPRINT_5 theo S4-D01 APPROVED. Browser UI smoke PASS theo Trung; functional acceptance INCOMPLETE_WITH_KNOWN_ISSUES, severity NOT_VERIFIED.
## M. S4-D01 và original V4 parity bổ sung (lịch sử)

- S4-D01: APPROVED; S4 replay scope SYNTHETIC_FIXTURE_ONLY. Real AIS replay NOT_VERIFIED; integration test SKIPPED vì không có cleaned source; verification DEFERRED_TO_SPRINT_5. Không thay đổi dataset nghiên cứu Train/Validation/Test.
- S4-D02: original reference tại C:\Users\MSI\Desktop\Môn học Dự án\MODEL_FINAL_VERIFICATION_V4\MODEL_CANDIDATE_PACKAGE\inference\risk_pipeline.py. Báo cáo T14 xác định nguồn này và FINAL_MODEL_LOCK_MANIFEST.json của package pin inference/risk_pipeline.py. Original và packaged là hai file riêng; mỗi file có SHA-256 8e33effb06d7f2e1fe855b1cb067fb2d27eb3aba9498e2af30be1b387534be7e.
- Supplemental tests: 5 passed, 0 failed, 0 skipped trong 22.71s; Q1 hash_opens=0, blocked_deserialization=0, blocked_other_opens=0. Đúng năm node skip trước đó: test_exact_components_and_score_parity, test_near_zero_cpa_and_score_boundary_parity, test_malformed_input_errors_match (tests/unit/test_risk_reference_v4.py); test_v4_reference_cpa_near_zero_and_score và test_reference_score_ignores_future_and_label (tests/unit/test_s3_post_t10_risk_comparison.py).
- Historical full regression: 674 passed, 6 skipped, 0 failed, 0 errors; 118.94s. Supplemental parity là lượt riêng 5 passed. Combined coverage: 679/680 nodes PASS qua hai lượt; node còn lại là real AIS test đã được phê duyệt giới hạn scope. Không trình bày combined coverage như kết quả một lượt full regression.
- Artifact T10 đã được sao chép vào ignored directory để chạy test; không đưa vào Git. Executable source không thay đổi sau full regression; Model Lock và Risk Engine giữ nguyên.
- AUTOMATED_ACCEPTANCE=PASS_WITH_APPROVED_SCOPE_LIMITATION; BROWSER_UI_SMOKE=PASS; BROWSER_FUNCTIONAL_ACCEPTANCE=INCOMPLETE_WITH_KNOWN_ISSUES; S4_CLOSURE_DECISION=APPROVED_WITH_LIMITATIONS; MERGE_TO_MAIN_READINESS=MERGE_PENDING_USER_REVIEW. Quy trình đóng S4 chờ merge main.
## N. Quyết định đóng và bàn giao Sprint 5 (lịch sử)

Trung phê duyệt S4_CLOSURE_DECISION=APPROVED_WITH_LIMITATIONS. AUTOMATED_ACCEPTANCE=PASS_WITH_APPROVED_SCOPE_LIMITATION. BROWSER_UI_SMOKE=PASS; BROWSER_FUNCTIONAL_ACCEPTANCE=INCOMPLETE_WITH_KNOWN_ISSUES. Chưa có danh sách lỗi và bằng chứng đủ để đánh giá severity; BROWSER_ISSUE_SEVERITY=NOT_VERIFIED. REAL_AIS_REPLAY=NOT_VERIFIED. S5_INTEGRATION_READY=NO; PRODUCTION_READY=NO. Quy trình đóng S4 vẫn S4_CLOSURE_PENDING_MAIN_MERGE; không tự kết luận main merge an toàn.

| Backlog | Công việc | Owner đề xuất | Dependencies | Trạng thái |
|---|---|---|---|---|
| S5-B01 | Xác định và sửa lỗi Replay chức năng trên browser | Toàn, Trung phối hợp | Danh sách lỗi và tái hiện | PROPOSED |
| S5-B02 | Session/version binding | Toàn, Trung phối hợp | Contract và consumer agreement | PROPOSED |
| S5-B03 | Candidate-pair provider | Toàn | Track snapshots, identity | PROPOSED |
| S5-B04 | Encounter builder | Toàn, Trung phối hợp | S5-B02, S5-B03 | PROPOSED |
| S5-B05 | T18 Runtime Model Inference | Trung | S5-B02, S5-B04, trusted adapter | PROPOSED |
| S5-B06 | T19 Runtime Risk Engine | Trung | S5-B04, S5-B05, risk contract | PROPOSED |
| S5-B07 | Runtime threshold authority | Trung, Toàn | Phê duyệt ngưỡng và policy | PROPOSED |
| S5-B08 | Real AIS replay verification | Toàn, Trung phối hợp | Cleaned source, provenance và scope approval | PROPOSED |
| S5-B09 | Forecast/Risk/Alert UI integration | Toàn, Trung phối hợp | S5-B05, S5-B06, S5-B07 | PROPOSED |
| S5-B10 | Final end-to-end acceptance | Trung, Toàn | S5-B01–B09 | PROPOSED |
| S5-B11 | External model package handoff | Trung, Toàn phối hợp | Package identity, transfer và verification | PROPOSED |

## Files

Năm tệp S4 đang sửa được giữ nguyên: README.md, backend/app/replay_api.py, backend/tests/test_replay_api.py, src/data/track_buffer.py, tests/unit/test_track_buffer.py. .gitattributes là tệp mới với rule LF duyệt ở mục K. src/risk/reference_v4/risk_pipeline.py có bytes đúng bằng Git blob và không có Git content diff; status có thể hiện M do checkout line ending. Báo cáo này là tệp mới. Không stage/commit, push hoặc merge vào main.


## O. BUG-01 fix và browser retest (lịch sử)

BUG-01 root cause: polling ghi đè seekOffset bằng clock. Frontend giữ draft seek trong khi chỉnh, giải phóng khi SEEK/RESET thành công hoặc đổi session/mode; lỗi request giữ draft. Regression test tái hiện FAIL trước sửa, frontend suite 22 passed sau sửa, build PASS. Chrome xác nhận giữ mốc 00:09 qua 4 giây và 00:02 qua 3,5 giây rồi seek đúng; reset khi chỉnh về 00:00, pause/resume và history 1/10 đã quan sát.

Browser matrix cập nhật: 29 PASS, 0 FAIL, 16 NOT_VERIFIED; baseline 23/3/19 được giữ trong browser report. Temporal payload, future leakage, session isolation, stale responses và Contract V1 end-to-end chưa xác minh đầy đủ. BUG01_FIXED=YES; BROWSER_FUNCTIONAL_ACCEPTANCE=INCOMPLETE; MERGE_TO_MAIN_READINESS=NOT_READY. Không chạy lại Python full regression; backend/Python source không đổi. Chi tiết và screenshots trong S4_BROWSER_FUNCTIONAL_TEST_REPORT.md.
## P. Kiểm chứng fixture và stale responses (lịch sử)

API fixture 00:00, 00:02, 00:09 và reset: anchor/session clock, 1/3/10 history, timestamps, source age, original và positions khớp fixture; G11 validator PASS, không quan sát future observation. Seek/reset tạo session/snapshot riêng; cross-session snapshot trả 404. Ba test frontend delayed track poll sau SEEK/RESET/mode PASS; không khẳng định test riêng session GET delay. Browser forecast bật/tắt, reset khi bật, hai vòng PLAY/PAUSE, reset và mode switching PASS. Frontend suite 25 passed; build PASS.

C07/C08 browser geometry/playback, E07 console và E08 Network chưa xác minh. Chrome DevTools không hiển thị panel có thể kiểm tra qua công cụ; backend logs không thay thế Network inspection. BUG-01 FIXED; MERGE_TO_MAIN_READINESS=NOT_READY do P0 chưa hoàn chỉnh. Real AIS deferred S5 và Model Lock không thay đổi.
## Q. S4 final targeted verification

CORE_FUNCTIONAL_ACCEPTANCE=PASS_WITHIN_SYNTHETIC_FIXTURE_SCOPE. C07: API clock mô phỏng 00:00:59/00:01:00 và frontend marker test khớp source fixture, không xuất hiện observation tương lai. C08: API và frontend polyline tests khớp 10 điểm 00:09, 3 điểm sau seek lùi 00:02, đúng thứ tự; browser không xác minh từng điểm. E06: delayed session GET và delayed track response sau SEEK/RESET/mode được kiểm thử tự động; clock, session, status, seek target, marker và forecast không bị response cũ ghi đè. E05 pending loading/empty và existing error/retry tests PASS.

Frontend suite 31 passed; build PASS. Browser Console/Network E07/E08 trực tiếp vẫn NOT_VERIFIED vì panel DevTools không hiển thị qua công cụ; log backend và test không được coi là browser PASS. Không phát hiện HIGH/CRITICAL mới. Model Lock unchanged; real AIS deferred S5. S4_TECHNICAL_READY=READY_WITH_APPROVED_LIMITATIONS; MERGE_TO_MAIN_READINESS=READY_PENDING_USER_APPROVAL. Trung đã phê duyệt giới hạn evidence và merge theo điều kiện Git preflight; trạng thái merge thực tế xác minh từ Git.
## Phê duyệt S4 final signoff

Trung phê duyệt S4-D01 synthetic fixture-only; S4-D02 original V4 parity; S4-D03 chấp nhận E07/E08 Console và Network trực tiếp còn NOT_VERIFIED do giới hạn công cụ; S4-D04 cho phép commit, push và merge khi Git preflight đạt.

- AUTOMATED_ACCEPTANCE=PASS_WITH_APPROVED_SCOPE_LIMITATION.
- CORE_FUNCTIONAL_ACCEPTANCE=PASS_WITHIN_SYNTHETIC_FIXTURE_SCOPE.
- FUNCTIONAL_VERIFICATION=43_OF_45 qua browser, API và automated tests; không gọi 43/45 là browser PASS.
- BROWSER_CONSOLE_DIRECT=NOT_VERIFIED; BROWSER_NETWORK_DIRECT=NOT_VERIFIED; E07_E08_SCOPE_LIMITATION=APPROVED.
- BUG01_FIXED=YES; REAL_AIS_REPLAY=NOT_VERIFIED_DEFERRED_TO_S5.
- S4_TECHNICAL_READY=READY_WITH_APPROVED_LIMITATIONS; S4_FINAL_SIGNOFF=APPROVED.
- T15 BENCHMARK_FAIL giữ nguyên; PRODUCTION_READY=NO; S5_INTEGRATION_READY=NO.
- Quy trình đóng S4 chỉ hoàn tất khi integration commit đã merge vào remote main và xác minh. Trạng thái Git thực tế cần kiểm tra trên remote.