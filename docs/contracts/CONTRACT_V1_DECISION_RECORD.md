# Biên bản quyết định Contract V1

- **Phạm vi:** Contract V1 Design Freeze cho AIS, Replay, Model, Forecast, Risk và Alert.
- **Người phê duyệt thiết kế:** Trung; **ngày phê duyệt:** 2026-11-22, theo chỉ thị của Trung.
- **Trạng thái:** `DESIGN_FREEZE_APPROVED` cho 14 quyết định; G11 áp dụng validation hai tầng. Trạng thái khóa được đánh giá trong `CONTRACT_V1_FINAL_LOCK_READINESS.md`, không đồng nghĩa production-ready.
- Không có bằng chứng Toàn phê duyệt bản triển khai. Việc chấp thuận thiết kế không chứng minh runtime đã được triển khai, kiểm thử hoặc production-ready.
- Nền Git: T02 `0402747d54c9670d2ff8698824673a6c2a2dbe8e`; T03/T04 `a93c2db266c1d82109dc72037c7d2cd8dc33d7e4`; baseline `a8583a72b5fee9a302bbb17ce3834385b32c5bbf`.

## Quyết định đã chấp thuận về thiết kế

Tổ hợp D-03/D-04/D-05/D-09/D-10 là **A–A–A–B–B**. Mỗi dòng là phê duyệt nội dung thiết kế của Trung, không phải chứng nhận implementation.

| ID | Quy tắc thiết kế | Điều kiện hoặc giới hạn triển khai |
|---|---|---|
| D-01 | History 10 mốc; as-of không tương lai, age 0–60 giây inclusive; `schema_version` và `mmsi` phải có key, MMSI có thể null; current state bằng history cuối. | Pydantic T04 được sửa trong worktree và parity đạt trên các case liên quan; semantic validation nhiều quy tắc không do schema thuần bảo đảm. |
| D-02 | QC/model dùng selected source timestamp; original timestamp là provenance. Synthetic time-shift dùng timestamp mô phỏng, không để provenance tương lai rò vào inference. | Xác minh mapping timestamp từng nguồn trước loader thực. |
| D-03 | **A:** không đoán UTC khi thiếu căn cứ; identical duplicate giữ stable-first; conflicting duplicate loại toàn nhóm. Stable ordering phải có provenance kiểm chứng. Không giả MMSI để lập key. | `SOURCE_VALIDATION_PENDING`; xác định key, equality và ordering theo từng nguồn trước production. |
| D-04 | **A:** giữ enum hiện có, gồm `INVALID_DATA`; không thêm reason_code/quality_flags/QC object V1. Data quality, inference, calibration và alert decision riêng biệt. | Không nhầm unavailable với quyết định an toàn. |
| D-05 | **A / P0-05:** `is_simulated` phản ánh provenance quỹ đạo, không phải tàu; synthetic trajectory có thể giữ `physical_mmsi:<9 digits>` và MMSI tương ứng. Simulation ID `simulated:<dataset>:<stable-id>`, NFC; không gắn session hay giả ID. | `IDENTITY_SOURCE_VALIDATION_PENDING`. Kiểm semantic physical ID khớp MMSI sau JSON Schema; legacy mock tách profile. |
| D-06 | NFC; sort canonical IDs theo UTF-8 bytes; compact JSON UTF-8 không ASCII-escape Unicode, SHA-256 hex thường, prefix `pair:v1:`. Online A là ID nhỏ hơn; offline giữ tensor mapping. Encounter `enc:v1:` hash compact JSON `[session_id,pair_id,anchor_utc]`, UUID lowercase có gạch nối, anchor UTC đúng giây `Z`, từ chối dưới giây. | Semantic hash, source verification và runtime chưa triển khai. |
| D-07 | Common East–North, nm, origin tàu A tại t0−9; tọa độ địa lý `[latitude, longitude]`; nếu inverse không đáng tin thì geography unavailable/null theo schema. | Phép tính T02 không phải bảo đảm địa lý toàn cầu. |
| D-08 | Model input `[2,10,4]` float32; Rule `[2,10,2]` float64 SOG/COG; online chỉ dùng history. Toàn cung cấp source/QC, Trung sở hữu adapter. | Adapter production chưa triển khai. |
| D-09 | **B / P0-06:** bảng 25 state/action tại integration contract là bắt buộc. RESET/SEEK hợp lệ kết thúc source, source version +1 và tạo session mới READY/PAUSED version 0; retry cùng key/payload tra trước state/version. ENDED trả 409, EXPIRED trả 410; auto-end không resolve alert. | Transaction và isolation phải kiểm chứng khi có runtime. |
| D-10 | **B:** năm path REST session + polling; UUID lowercase session/snapshot, UTC Z, limit mặc định 50 từ 1–100, offset mặc định 0, snapshot pin TTL 5 phút; hết hạn 410; giữ mock riêng. Create body source_id bắt buộc, start_time tùy chọn; session response gồm session_id/source_id/simulation_time/status/version. | Production runtime chưa tồn tại; semantic pagination cần kiểm chứng khi triển khai. |
| D-11 | Input invalid/missing không inference hoặc CV fallback. CV chỉ fallback cho lỗi kỹ thuật khi input hợp lệ theo contract; chưa calibration thì alert decision null. | Runtime và calibration chưa triển khai. |
| D-12 | Forecast 15 phút; near-zero `v·v <= 1e-9 kn²`: TCPA API null theo status, DCPA/current score còn khả dụng; trọng số predicted/current/rule 0.68/0.12/0.20. | Không sửa công thức CPA hoặc calibration. |
| D-13 | Tối đa một alert chưa RESOLVED mỗi session/pair; idempotent evaluation; key lặp payload khác xử lý theo contract; evaluation cũ không đảo state mới; DATA_UNAVAILABLE khác RESOLVED; update atomic. | Chưa có Alert Manager hay test race runtime. |
| D-14 | Trung phê duyệt thiết kế ngày 2026-11-22; lưu changelog, compatibility và bằng chứng. Không suy ra Toàn đã phê duyệt. | Design freeze không đồng nghĩa implementation lock hay production ready. |

## D-10: năm path production

- `POST /api/v1/replay/sessions`
- `GET /api/v1/replay/sessions/{session_id}`
- `POST /api/v1/replay/sessions/{session_id}/control`
- `GET /api/v1/replay/sessions/{session_id}/tracks`
- `GET /api/v1/replay/sessions/{session_id}/tracks/{vessel_id}`

Simulation clock là thời gian replay; history không vượt clock; reset/seek trả session ID mới; pagination không trộn snapshot. OpenAPI và `replay.schema.json` ghi các trường được duyệt. `/api/v1/mock/...` vẫn là API phát triển riêng. Profile production replay/risk/alert tách với fixture legacy trong các schema `*_v1`.

## Versioning và changelog

- Quyết định khóa cuối: `expected_version` integer không âm; session mới version 0; session source đổi state thì tăng 1; retry idempotent được tra trước version. Key `Idempotency-Key` 1–128 ký tự, scope source session, retention tối thiểu 24 giờ kể từ khi ghi kết quả đầu tiên. Payload compact UTF-8 thứ tự key `action`, `target_time` nếu SEEK, `expected_version`; non-SEEK không có target_time, kể cả null.
- G11: `PRODUCTION_VALID = STRUCTURAL_VALID AND SEMANTIC_VALID`. JSON Schema chỉ kiểm cấu trúc; `src.data.track_semantics` kiểm identity/provenance và được Pydantic mock dùng lại. Consumer production phải thực hiện cả hai tầng và các invariant temporal/session khác; `LEGACY_MOCK` là profile riêng. Simulated ID mang MMSI physical không có provenance binding được duyệt bị từ chối. Sự khớp ID/MMSI không xác minh danh tính thật.
- P0-05/P0-06: Trung chốt `is_simulated` theo quỹ đạo và đầy đủ ma trận 25 state/action; source session kết thúc sau RESET/SEEK, không tự RESOLVED alert.
- Snapshot UUID lowercase canonical, TTL 5 phút; limit mặc định 50, từ 1–100, offset mặc định 0; trang tiếp theo dùng ID snapshot trang đầu. Create yêu cầu `source_id`, `start_time` tùy chọn; thiếu start dùng đầu nguồn thay vì wall-clock.
- Production simulated ID có cú pháp `simulated:<dataset>:<stable-id>`: dataset không rỗng và không chứa dấu phân cách `:`, stable-id không rỗng; text được chuẩn hóa NFC, Unicode và JSON escaping theo D-06. Không khẳng định mọi ký tự hoặc ID này có nguồn hợp lệ: sự ổn định và whitelist theo từng source phải được xác minh (`IDENTITY_SOURCE_VALIDATION_PENDING`).

- Đặc tả Contract V1 đã khóa trong phạm vi được kiểm chứng; implementation vẫn CONDITIONAL. Schema hiện mang `schema_version=1.0.0`; một số companion JSON vẫn mang `1.0.0-draft`, cần được xem xét tương thích và versioning trước tích hợp production; không tự đồng nhất số version.
- 2026-11-22: Trung phê duyệt V1 design; mọi seek tạo session mới, D-06 tách sort pair khỏi vai trò A/B, REST session + polling được chọn về kiến trúc. Các chi tiết chưa đủ căn cứ được đánh dấu specification gap.
- Phê duyệt bổ sung: online A/B sort theo canonical ID NFC bằng bytes UTF-8, offline mapping giữ nguyên; bổ sung encounter hash, trạng thái session, idempotency và pagination. Consumer mock và schema cũ dùng ID ví dụ không phải UUID/enc:v1: phải được review compatibility; không tuyên bố tương thích production.
- Mọi thay đổi wire breaking cần review compatibility, changelog và version bump phù hợp trước khi khóa implementation; thay đổi additive cũng phải xét `additionalProperties: false` và client cũ.
