# Đề xuất đặc tả Replay Session V1

**APPROVED_DESIGN:** play/pause/resume giữ session; reset và mọi seek tạo session mới; các session và alert cô lập; kết thúc không tự RESOLVED. Clock có thẩm quyền là simulation time/anchor. Đây không phải Replay Engine.

**APPROVED_DESIGN:** enum `READY`, `PLAYING`, `PAUSED`, `ENDED`, `EXPIRED`; SEEK đưa session mới về PAUSED. Session mới version 0; control thay đổi trạng thái cùng session tăng version thêm 1.

| State | PLAY | PAUSE | RESUME | RESET | SEEK |
|---|---|---|---|---|---|
| READY | PLAYING | 409 | 409 | READY mới | PAUSED mới |
| PLAYING | 409 | PAUSED | 409 | READY mới | PAUSED mới |
| PAUSED | PLAYING | 409 | PLAYING | READY mới | PAUSED mới |
| ENDED | 409 | 409 | 409 | 409 | 409 |
| EXPIRED | 410 | 410 | 410 | 410 | 410 |

PLAY/PAUSE/RESUME hợp lệ giữ session, clock và tăng version một lần. RESET/SEEK hợp lệ từ READY/PLAYING/PAUSED kiểm tra input, state và expected_version; sau đó trong một transaction kết thúc source (`ENDED`, source version +1), tạo session mới version 0, và ghi kết quả idempotency. RESET trả session READY tại source start; SEEK trả session PAUSED tại target hợp lệ trong miền nguồn, không replay ngầm khoảng bỏ qua. Target thiếu hoặc ngoài miền trả 422. Response trả session ID mới có hiệu lực; source không điều khiển timeline hiện hành. Client muốn phát lại sau ENDED phải POST create session. Auto-end PLAYING→ENDED không tạo RESOLVED alert.

`Idempotency-Key` dài 1–128 ký tự, bắt buộc với RESET/SEEK, scope source session và giữ tối thiểu 24 giờ từ lúc kết quả lần đầu được ghi; retry cùng payload được tra trước state/version, trả đúng kết quả cũ, payload khác 409. Canonical payload gồm `action`, `target_time` chỉ khi SEEK, `expected_version`, JSON compact UTF-8 thứ tự key cố định; non-SEEK cấm target_time kể cả null. Mọi control cần expected_version integer không âm; mismatch 409. Evaluation cũ không cập nhật alert session mới. Session expired trả 410. Concurrent requests cùng expected_version chỉ tối đa một thay đổi thành công; tính nguyên tử và race cần runtime test.

Các ví dụ ở `tests/unit/test_replay_session_proposal.py` và `test_contract_v1_final_lock.py` là mô hình trong bộ nhớ, không chứng minh API, idempotency bền vững, tính nguyên tử hoặc runtime đã hoạt động.
