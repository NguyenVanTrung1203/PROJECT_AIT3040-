# S4 Browser Functional Test Report

## 1. Executive Summary

Chrome localhost, commit 238b4f40a7737c35c3b667403f29d6e0105234d9. Baseline trước sửa: 23 PASS, 3 FAIL, 19 NOT_VERIFIED. Retest sau sửa: 29 PASS, 0 FAIL, 16 NOT_VERIFIED. Kiểm tra closure: 39 PASS có phân biệt evidence, 0 FAIL, 6 NOT_VERIFIED, 0 BLOCKED. BUG-01 đã sửa và xác nhận bằng test cùng Chrome. Functional acceptance INCOMPLETE vì invariant cốt lõi chưa đủ bằng chứng.

## 2. Tested Environment

Windows, Chrome, backend FastAPI 127.0.0.1:8000, frontend Vite 127.0.0.1:5173, synthetic fixture. Health trả status ok. Branch s4-integration-final. Risk V4 đã hiện M từ trước; source không sửa. Hai server đã dừng.

## 3. Functional Test Matrix

| Test ID | Chức năng | Expected | Actual | Status | Evidence |
|---|---|---|---|---|---|
| A01 | Tải trang | Trang hiển thị | Mock tải | PASS | A01 |
| A02 | Bản đồ | Tile hiển thị | Kattegat hiển thị | PASS | A01 |
| A03 | Danh sách tàu | Có danh sách | 4 tàu mock | PASS | A01 |
| A04 | Zoom | Phóng to/thu nhỏ | Cả hai thay đổi bản đồ | PASS | Chrome |
| A05 | Chọn marker | Chọn tàu | mock-vessel-001 chọn được | PASS | Chrome |
| A06 | Chi tiết tàu | Hiển thị snapshot | Chi tiết xuất hiện | PASS | Chrome |
| A07 | Refresh | Tải lại track | READY và tàu vẫn hiện | PASS | Chrome |
| A08 | Chuyển mode | Mock/Replay | Chuyển hai chiều | PASS | Chrome |
| B01 | Tạo session | READY | READY và session ID | PASS | Chrome |
| B02 | Start time | 00:00 UTC | 00:00 UTC | PASS | C01 |
| B03 | Play | Clock tiến | PLAYING, clock tiến | PASS | Chrome |
| B04 | Pause | Clock dừng | Giữ 00:00:07 qua 3,5 giây | PASS | Chrome retest |
| B05 | Resume | Clock tiếp tục | PLAYING và clock tiến 00:00:07 đến 00:00:09 | PASS | Chrome retest |
| B06 | Reset | Về 00:00 | READY tại 00:00 | PASS | Chrome |
| B07 | Seek tiến | Đến mốc chọn | Giữ 00:09 qua 4 giây rồi seek đúng | PASS | BUG01_after_poll, B07_retest_0009 |
| B08 | Seek lùi | Đến mốc chọn | Giữ 00:02 qua 3,5 giây rồi seek đúng | PASS | B08_retest_0002 |
| B09 | Đồng bộ UTC | Clock và track đồng bộ | 00:00, 00:02, 00:09 và reset khớp API | PASS | API fixture |
| B10 | Session status | Status hợp lệ | READY, PLAYING, PAUSED | PASS | Chrome |
| B11 | Session isolation | Không lẫn dữ liệu cũ | ID/snapshot riêng; cross-session 404; delayed track không ghi đè | PASS | API + automated |
| C01 | Early marker | Marker 00:00 | Marker hiển thị | PASS | C01 |
| C02 | History 1/10 | 1/10 | 1/10 sau reset tại 00:00 | PASS | C02_retest_0000, UI |
| C03 | History 3/10 | 3/10 tại 00:02 | Chi tiết 3/10 | PASS | C03, UI |
| C04 | History 10/10 | 10/10 tại 00:09 | Chi tiết 10/10 | PASS | D04, UI |
| C05 | Thiếu history | INSUFFICIENT_DATA | 00:00 và 00:02 đúng | PASS | C01, C03 |
| C06 | Đủ history | VALID | 00:09 VALID | PASS | D04 |
| C07 | Vị trí tàu | Cập nhật theo clock | 00:00:59 giữ vị trí đầu; 00:01:00 chuyển điểm tiếp theo | PASS | API clock mô phỏng + frontend automated |
| C08 | Quỹ đạo history | Khớp dữ liệu | 10 điểm tại 00:09, 3 điểm sau seek lùi đúng thứ tự fixture | PASS | API + frontend automated |
| C09 | Future leakage | Không observation tương lai | Các điểm source ≤ nominal ≤ anchor tại ba mốc | PASS | API fixture |
| C10 | History sau seek/reset | Không giữ nhầm | Seek lùi 3 điểm; reset 1 điểm từ fixture | PASS | API fixture |
| D01 | Forecast thiếu history | Disabled | Disabled 00:00/00:02 | PASS | C01, C03 |
| D02 | Forecast đủ điều kiện | Bật tại VALID | Checkbox bật ở 00:09 | PASS | D04 |
| D03 | Đường forecast | Hiển thị đường | Đường forecast hiển thị khi bật | PASS | Browser |
| D04 | Nhãn MOCK | Nhãn rõ | MOCK FORECAST — NOT MODEL OUTPUT | PASS | D04 |
| D05 | Bật/tắt layer | Thay đổi layer | Bật có nhãn/đường; tắt nhãn biến mất | PASS | Browser |
| D06 | Forecast sau reset | Không còn cũ | Reset từ forecast bật về READY, checkbox disabled, nhãn biến mất | PASS | Browser |
| D07 | Forecast sau seek lùi | Không còn cũ | Checkbox disabled, nhãn biến mất | PASS | C03 |
| D08 | Phân biệt model | Không ghi output M5a | Nhãn NOT MODEL OUTPUT | PASS | D04 |
| E01 | Play/Pause nhiều lần | Ổn định | Hai vòng PLAY/PAUSE đúng trạng thái | PASS | Browser |
| E02 | Seek nhiều lần | Giữ mốc chọn | Seek tiến 00:09, lùi 00:02; draft giữ qua polling | PASS | Chrome retest |
| E03 | Reset nhiều lần | Ổn định | Reset hai lần về READY | PASS | Browser |
| E04 | Chuyển mode nhiều lần | Ổn định | Hai vòng Mock/Replay | PASS | Browser |
| E05 | Loading/error | Hiển thị phù hợp | Pending promise hiển thị loading rồi empty; error/retry test PASS | PASS | Automated |
| E06 | Stale responses | Không có response cũ | Delayed session GET và track sau SEEK/RESET/mode không ghi đè | PASS | Automated |
| E07 | Console | Không lỗi nghiêm trọng | Chưa kiểm tra DevTools | NOT_VERIFIED | — |
| E08 | Network | Không lỗi API | Backend log có response thành công; chưa kiểm tra đầy đủ | NOT_VERIFIED | — |

## 4. Passed Functions

Trang, map, zoom, marker và chi tiết mock, tạo session, PLAY, RESET, seek nhanh, early marker, history 3/10 và 10/10, trạng thái track, bật Forecast Mock và nhãn mock đã quan sát trực tiếp.

## 5. Failed Functions

Không còn FAIL được quan sát; BUG-01 đã được sửa. Hai scenario còn NOT_VERIFIED: Console và Network trực tiếp.

## 6. Bug Register

### BUG-01 — Mốc seek bị ghi đè khi đang chọn

- Severity: HIGH, vì ảnh hưởng điều khiển Replay cốt lõi và có thể đưa người dùng tới mốc khác mong muốn.
- Preconditions: Replay fixture READY hoặc PAUSED; simulation UTC hiện tại 00:02.
- Steps: đặt slider tới 00:09; chờ một chu kỳ cập nhật trước khi nhấn SEEK; quan sát nhãn và slider.
- Expected: mốc 00:09 giữ nguyên đến khi nhấn SEEK hoặc người dùng đổi.
- Actual: mốc tự về 00:02; nếu nhấn sau đó session ở mốc cũ. Đã quan sát hai lần tại các mốc khác nhau.
- Evidence: BUG01_seek_reverted.jpg cho trạng thái sau khi trả về; UI trước đó hiển thị slider 540 và sau polling 120. Ảnh đơn lẻ không thể hiện toàn bộ chuyển đổi.
- Suspected module: frontend/src/App.jsx; polling cập nhật seekOffset theo simulation_time. Đây là giả thuyết có cơ sở từ source và hành vi, cần kiểm chứng khi sửa.
- Proposed fix: giữ riêng giá trị slider đang chỉnh khỏi cập nhật polling cho tới khi SEEK hoàn tất hoặc người dùng hủy; bổ sung test race.
- Owner đề xuất: Toàn (PROPOSED).
- Cần sửa trước merge main: YES.

## 7. Screenshot Evidence

Ảnh Chrome thực tế ngoài Git tại thư mục s4_browser_evidence: A01_overview.jpg, C01_replay_0000.jpg, C03_seek_0002.jpg, D04_forecast_0009.jpg, BUG01_seek_reverted.jpg. Ảnh C03 và D04 thể hiện vị trí và controls; số history được đọc từ accessibility state.

## 8. Contract V1 Concerns

API và automated tests xác minh temporal, future leakage và session isolation trong synthetic fixture scope; không phát hiện Contract V1 violation. Không suy rộng sang AIS thật.

## 9. Required Fixes Before Merge

BUG-01 đã sửa và retest; các kiểm tra core fixture đã đạt. Không còn fix HIGH/CRITICAL đã xác nhận trước merge. Console/Network trực tiếp vẫn NOT_VERIFIED; Trung chấp nhận giới hạn theo S4-D03.

## 10. Deferred Fixes for Sprint 5

Model/risk/alert runtime và AIS thật thuộc backlog S5 trong báo cáo S4. Các scenario NOT_VERIFIED cần được phân công xác minh, không coi là bug đã xác nhận.

## 11. Merge Readiness Recommendation

Trung phê duyệt merge theo S4-D04 nếu Git preflight đạt. Core synthetic fixture có browser/API/automated evidence; Console/Network trực tiếp NOT_VERIFIED được chấp nhận theo S4-D03. Không coi đó là browser PASS. Đối chiếu B01–B12 trong báo cáo S4: session, early marker, play, reset và nhãn mock có bằng chứng; pause/resume timing, future leakage, stale, console/network và các mốc chưa xác nhận đầy đủ vẫn NOT_VERIFIED. Không kết luận toàn bộ checklist PASS.

## 12. BUG-01 remediation và retest (lịch sử)

Root cause: polling ghi setSeekOffset theo simulation time mỗi chu kỳ. frontend/src/App.jsx giữ cờ seekEditingRef để draft không bị polling ghi đè; SEEK/RESET thành công, session mới và chuyển mode xóa draft; request failure giữ draft để retry. Guard generation/session hiện có tiếp tục xử lý response cũ.

Regression test bổ sung đã FAIL trước sửa (slider 540 trở về 120), PASS sau sửa. Frontend suite 22 passed, production build PASS. Test mới bao phủ polling, SEEK failure, reset khi đang chỉnh và mode/session mới; test cũ bao phủ seek. Chưa có test riêng đầy đủ cho mọi chuỗi seek và stale polling.

Chrome: mốc 00:09 giữ qua 4 giây, seek đúng; mốc 00:02 giữ qua 3,5 giây, seek đúng; reset trong lúc chỉnh trả về 00:00; pause 3,5 giây giữ clock 00:00:07; resume clock tiến đến 00:00:09; early marker history 1/10. Ảnh BUG01_after_poll.jpg, B07_retest_0009.jpg, B08_retest_0002.jpg, reset_draft.jpg, C02_retest_0000.jpg ở thư mục evidence.

BUG-01 FIXED theo targeted test và Chrome; không có bug CRITICAL/HIGH mới được xác nhận. Temporal correctness, future leakage, session isolation, stale response, Contract V1 compatibility và console/network coverage toàn diện còn NOT_VERIFIED; không kết luận không có lỗi. Merge readiness NOT_READY.
## 13. P0/P1 closure evidence (lịch sử)

- API fixture: TestClient kiểm tra 00:00, 00:09, seek lùi 00:02, reset 00:00. Session IDs và snapshot IDs khác nhau; sử dụng snapshot session cũ ở session mới trả 404. Version các session mới là 0.
- Tại ba mốc history 1, 3, 10; status INSUFFICIENT_DATA, INSUFFICIENT_DATA, VALID; current_state null khi thiếu. G11 validator PASS. Mọi source timestamp ≤ nominal ≤ anchor; source age bằng nominal-source trong [0,60] giây. Tọa độ và original/source timestamps khớp fixture: 00:00 (55.68,12.56), 00:02 (55.6833,12.5638), 00:09 (55.6948,12.5771). Không phát hiện future observation trong các payload này.
- Automated: ba test delayed track poll sau SEEK, RESET, mode đều PASS; đây là track response race, không chứng minh riêng session GET response. Frontend suite 25 passed; build PASS.
- Browser: bật/tắt Forecast Mock, reset khi đang bật; play/pause hai vòng, reset lặp và chuyển mode hai vòng. DevTools phím tắt không hiển thị panel có thể kiểm tra qua công cụ; E07 console, E08 network NOT_VERIFIED. Log server chỉ là quan sát từng request, không thay Network inspection.
- C07 (vị trí cập nhật liên tục khi playback) và C08 (đối chiếu hình học toàn bộ history với fixture) vẫn NOT_VERIFIED; API positions tại các anchor và history source đã khớp fixture.
- Tổng matrix: 39 PASS với evidence riêng browser/API/automated, 0 FAIL, 6 NOT_VERIFIED. BUG-01 FIXED. Không có CRITICAL/HIGH mới được xác nhận. Không tuyên bố mọi invariant P0 hoàn chỉnh.
## 14. Kiểm tra tập trung C07/C08/E05/E06

- C07 API TestClient, clock mô phỏng: PLAY tại 00:00:59 giữ observation 00:00, tuổi 59 giây, vị trí (55.6800,12.5600); tại 00:01:00 dùng observation 00:01, vị trí (55.6816,12.5619). Frontend test với mock API và cùng source fixture kiểm tra marker và clock trước/sau boundary. Không coi automated test là browser PASS.
- C08 API: 00:09 history có đúng 10 tọa độ theo fixture; seek lùi 00:02 chỉ còn 3 tọa độ đầu, đúng thứ tự và không có điểm sau anchor. Frontend test với mock API kiểm tra polyline nhận chính xác 10 rồi 3 tọa độ, loại geometry cũ. Browser trước đó đã quan sát marker và seek; hình học từng điểm được xác minh qua API + automated, không phải browser.
- E06: ba test deterministic trì hoãn session GET cũ sau SEEK, RESET và đổi mode. Response cũ có status PLAYING/version 99 không thay clock, session, trạng thái, seek target, marker hoặc forecast của session mới; delayed track tests đã có cũng PASS.
- E05: pending promise test xác nhận loading hiển thị và biến mất khi empty response đến; existing empty/error/retry tests PASS.
- E07/E08: DevTools panel không hiển thị qua công cụ trong lần kiểm tra trước; theo giới hạn không lặp vô ích hoặc bypass. Console và Network trực tiếp NOT_VERIFIED. Backend request logs và frontend automated tests là evidence bổ sung, không phải browser PASS. Đây là giới hạn thu thập evidence; không có lỗi nghiêm trọng được xác nhận từ thông tin hiện có.
- Frontend suite: 31 passed, 2 files. Production build PASS. Không thay frontend executable source hoặc backend trong lượt kiểm tra này. Model Lock không đổi.
- CORE_FUNCTIONAL_ACCEPTANCE=PASS_WITHIN_SYNTHETIC_FIXTURE_SCOPE; S4_TECHNICAL_READY=READY_WITH_APPROVED_LIMITATIONS; MERGE_TO_MAIN_READINESS=READY_PENDING_USER_APPROVAL. Trung đã phê duyệt giới hạn E07/E08 và merge nếu Git preflight đạt.
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