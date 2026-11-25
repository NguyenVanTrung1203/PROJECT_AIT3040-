# Đề xuất API Replay và Track V1

**APPROVED_DESIGN:** REST session resource + polling; năm method/path, UUID lowercase canonical, UTC Z, enum action/state, expected_version integer không âm, Idempotency-Key 1–128 ký tự cho RESET/SEEK, limit/offset, snapshot TTL 5 phút, HTTP 200/201/404/409/410/422/503. Không WebSocket/SSE; mock tách riêng. OpenAPI và Replay schema mô tả fields được duyệt; semantic liên field và runtime phải được kiểm chứng riêng.

| Method và path | Body / params minh họa | Response minh họa và session | Owner |
|---|---|---|---|
| `POST /api/v1/replay/sessions` | `{"source_id":"demo","start_time":"2025-10-01T12:00:00Z"}`; source_id bắt buộc, start_time tùy chọn | `{"session_id":"123e4567-e89b-12d3-a456-426614174000","source_id":"demo","simulation_time":"2025-10-01T12:00:00Z","status":"READY","version":0}`; 201 | Toàn |
| `GET /api/v1/replay/sessions/{session_id}` | Session path | Cùng các field session/time/status; đề xuất 200 | Toàn |
| `POST /api/v1/replay/sessions/{session_id}/control` | Header `Idempotency-Key: r1`; `{"action":"SEEK","target_time":"2025-10-01T12:10:00Z","expected_version":1}` | `{"session_id":"123e4567-e89b-12d3-a456-426614174001","source_id":"demo","simulation_time":"2025-10-01T12:10:00Z","status":"PAUSED","version":0}`; ID mới, 200 | Toàn |
| `GET /api/v1/replay/sessions/{session_id}/tracks` | `limit`, `offset`, `snapshot_id` | `{"items":[],"total":0,"limit":50,"offset":0,"snapshot_id":"123e4567-e89b-12d3-a456-426614174002","simulation_time":"2025-10-01T12:10:00Z"}`; 200 | Toàn |
| `GET /api/v1/replay/sessions/{session_id}/tracks/{vessel_id}` | Đề xuất `snapshot_id` | Một TrackSnapshot theo schema hiện có, không vượt clock của snapshot; đề xuất 200 | Toàn |

**Pagination đã duyệt:** stable order theo canonical vessel ID; limit mặc định 50, 1–100; offset mặc định 0; trang đầu trả UUID `snapshot_id`; trang sau phải gửi lại cùng ID, detail có thể dùng ID đó. Snapshot bất biến và TTL 5 phút, hết hạn trả 410; client refresh không reset session.

**Error/idempotency đã duyệt:** body `contracts/error.schema.json`; 404 thiếu resource, 422 input sai, 409 version/idempotency/control conflict, 410 session hoặc snapshot hết hạn, 503 nguồn replay không khả dụng. Retry control cùng `Idempotency-Key` và canonical payload trả cùng kết quả trước khi kiểm tra version; scope source session, key dài 1–128 ký tự, retention tối thiểu 24 giờ từ lúc kết quả lần đầu được ghi nhận.

**Acceptance:** create/status/control, retry/conflict, seek/reset tạo session một lần, session isolation, list/detail đồng bộ snapshot, nhiều trang không lặp/thiếu, token hết hạn, error/request ID và regression mock. Schema và OpenAPI không thay thế runtime kiểm tra conditional header, snapshot và transaction; chưa có runtime PASS.
