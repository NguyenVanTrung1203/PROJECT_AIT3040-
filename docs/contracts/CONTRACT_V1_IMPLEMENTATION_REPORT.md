# Báo cáo triển khai phần Contract V1 đã được Trung duyệt

**Cập nhật G11:** Các trạng thái G11 và lock bên dưới ghi lại thời điểm trước quyết định hai tầng. G11 đã được chốt và kiểm chứng combined; xem `CONTRACT_V1_G11_SEMANTIC_VALIDATION_REPORT.md` và `CONTRACT_V1_FINAL_LOCK_READINESS.md` để biết kết luận hiện tại. Trung đã chốt semantics `is_simulated` theo trajectory và ma trận 25 state/action. Các giới hạn source và runtime vẫn có hiệu lực.

## Cập nhật quyết định cuối

Phần Replay schema/OpenAPI không còn là partial sau quyết định version, UUID, create/session response, pagination và idempotency. Có profile `encounter_v1`, `risk_request_v1`, `risk_response_v1`, `alert_v1` tách production khỏi fixture legacy; Risk/Alert OpenAPI dùng profile mới khi replay, phiên live null session giữ semantics T02. Hai query filter session trên các path T02 được siết UUID production, là thay đổi tương thích có chủ đích; mock legacy không được coi là production hoặc tự migrate. Các kết quả 205/5 bên dưới là lịch sử; xem `CONTRACT_V1_FINAL_LOCK_READINESS.md` cho lượt cuối.

G09/G10 đã được Trung giải quyết: `is_simulated` mô tả quỹ đạo; ma trận control gồm đủ 25 tổ hợp. Vẫn chưa báo lock do G11: structural JSON Schema không so sánh được physical ID với MMSI, trong khi Pydantic bắt buộc hai giá trị khớp. Hash/session equality, idempotency conditional header, snapshot pin và transaction cũng cần runtime semantic enforcement.

## Baseline và phạm vi

- Worktree `trung-contract-v1-freeze`, branch cùng tên, base `a8583a72b5fee9a302bbb17ce3834385b32c5bbf`. Giữ nguyên các thay đổi chưa commit từ hai lượt trước.
- 14 quyết định thiết kế vẫn được Trung phê duyệt. Phê duyệt bổ sung làm rõ NFC/UTF-8 sort, online A/B, Encounter ID, session states, idempotency, version và pagination.
- Không chỉnh dataset, CPA, calibration; không xây Replay Engine, Risk hoặc Alert runtime. Không có bằng chứng Toàn phê duyệt bản implementation.

## Các thay đổi

- `contracts/feature_contract.json`, `contracts/integration_contract.md` và decision record phản ánh quy tắc mới; A/B online theo canonical UTF-8 bytes, offline vẫn theo tensor mapping.
- Reference test `scripts/contract_identity_reference.py` minh họa NFC, sort bytes, compact JSON, SHA-256 pair và encounter. Registry namespace truyền vào chỉ là dữ liệu test, không xác minh MMSI vật lý hoặc tính ổn định nguồn. `scripts/verify_feature_contract.py` chuẩn hóa NFC và sort theo UTF-8 bytes, vẫn không là registry production.
- `contracts/replay.schema.json` và năm path OpenAPI thể hiện các field/status đã duyệt. Các operation đánh dấu `x-specification-gap`; expected_version và snapshot_id chưa được tự gán wire type. Conditional header/reset/seek và pagination pin còn phải được runtime kiểm tra.
- Sửa test helper unit/integration để kiểm tra A/B online mới; giữ offline mapping. Có test vectors Python/JavaScript, invalid/duplicate ID, anchor dưới giây, session/pair/anchor, schema, ví dụ OpenAPI và session oracle trong bộ nhớ.
- Mock T04 và các sáu endpoint Risk/Model/Alert cũ giữ nguyên; code Pydantic D-01 đã sửa từ lượt trước vẫn được kiểm tra.

## P0 và các điều kiện chưa khóa

Chi tiết trong `CONTRACT_V1_SPECIFICATION_GAPS.md`: create body và response session/control chưa được định nghĩa đầy đủ; type/initial value expected_version và phép tăng khi tạo session mới; snapshot_id wire type/default pagination; payload idempotency absent/null, encoding và thời điểm tính retention; namespace registry, UUID spelling và compatibility các fixture/mock schema cũ với UUID/enc:v1:. Không dùng schema partial để tuyên bố client/server có thể triển khai độc lập không mâu thuẫn.

`SOURCE_VALIDATION_PENDING` và `IDENTITY_SOURCE_VALIDATION_PENDING` còn hiệu lực. `DESIGN_FREEZE_APPROVED`; `CONTRACT_SPECIFICATION_LOCKED: NOT_READY`; `CONTRACT_IMPLEMENTATION_LOCKED: NOT_READY`. `FUTURE_RUNTIME_UNVERIFIED` áp dụng Replay, adapter, model/Risk/Alert và transaction/persistence. Không đồng nhất test oracle với test runtime.

## Kiểm thử và bàn giao

Pytest `tests/unit tests/integration backend/tests`: **207 passed, 0 failed, 0 xfailed**, với một cảnh báo deprecation Starlette/TestClient. Trong một lượt trung gian, test error example thất bại vì test chưa đăng ký reference `common.schema.json`; sau khi sửa registry của test, toàn bộ suite được chạy lại và đạt. Frontend **5 passed**, Vite build PASS. Tổng test riêng biệt trong bộ đầy đủ: **212 passed**. `CONTRACT_V1_PAIR_ID_TEST_VECTORS.md` có fixed vectors; test cross-language dùng Node và Python, gồm Unicode, escaping và UTF-8/UTF-16 ordering. OpenAPI validation chỉ xác nhận cấu trúc của tài liệu partial và ví dụ khớp partial schema; không phải chứng nhận wire complete. Chưa commit, push hoặc merge.
