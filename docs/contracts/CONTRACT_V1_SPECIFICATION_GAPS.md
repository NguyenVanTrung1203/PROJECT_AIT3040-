# Các khoảng trống đặc tả Contract V1

Trung đã chấp thuận thiết kế; các mục dưới đây ngăn `CONTRACT_IMPLEMENTATION_LOCKED`. Không suy ra Toàn đã phê duyệt, không tự chọn wire format thay cho quyết định còn thiếu.

| ID | Khoảng trống / mismatch | Interface phụ thuộc và việc cần làm |
|---|---|---|
| G01 D-01 | **ĐÃ SỬA TRONG WORKTREE:** Pydantic yêu cầu `schema_version` và `mmsi`; parity các case liên quan PASS. JSON Schema không tự kiểm chứng mọi semantic như current state/history cuối, thứ tự grid hoặc tuổi source thực. | Duy trì test semantic/runtime cho 0/60 giây, future, grid và current equality. Không tuyên bố toàn bộ không gian đầu vào Pydantic và Schema tương đương. |
| G02 D-03 | `SOURCE_VALIDATION_PENDING`: timezone raw chưa xác nhận; chưa chốt tập trường dùng so sánh identical, key cho nguồn không MMSI, stable-order provenance và phạm vi áp dụng theo nguồn. | Replay Loader/TrackSnapshot. Xác minh metadata và mẫu raw; test identical/conflict, không tự suy UTC hoặc tạo MMSI. |
| G03 D-05/06 | **P1 source:** `IDENTITY_SOURCE_VALIDATION_PENDING`: `simulated:<dataset>:<stable-id>` và `physical_mmsi:<9 digits>` đã được duyệt, song tính ổn định/source thật và nội dung MMSI chưa được chứng minh. NFC và trùng ID phải kiểm tra semantic, không thể suy từ regex. | Replay, pair persistence và alert: xác minh nguồn trước production. |
| G04 D-06 | NFC, UTF-8 byte sort, UUID lowercase canonical, JSON compact, A/B online và `enc:v1:` có vector Python/JS. Profile production `encounter_v1` và `*_v1` tách fixture legacy; không migrate ID cũ. | Schema kiểm tra format; runtime cần kiểm hash, session equality, current source MMSI và origin. Fixtures cũ không hợp lệ theo production profile một cách có chủ đích. |
| G05 D-09 | Enum, version integer, version 0, retry trước version, key length/scope, payload key order và retention được duyệt. | Transaction/concurrency/persistence là `FUTURE_RUNTIME_UNVERIFIED`; test oracle chỉ minh họa. |
| G06 D-10 | Năm Replay paths có create/session/control response và list/detail schema; UUID, defaults và statuses được duyệt. Schema không biểu diễn trực tiếp điều kiện header RESET/SEEK, snapshot pin/expiry hay stable order. | Các quy tắc semantic được đặc tả trong integration contract; runtime tests cần bổ sung khi có server. |
| G07 D-12/13 | JSON Schema và fixture không bảo đảm mọi giá trị finite, toán học score, idempotency và transaction atomicity; ngưỡng calibration chính thức chưa tồn tại. | Risk/Alert runtime. Kiểm tra semantic và concurrency khi có implementation; không xem fixture pass là runtime pass. |
| G08 D-07/08 | Khả dụng địa lý ở antimeridian/gần cực cần xử lý theo contract; adapter online và đường đi data QC chưa triển khai. | Feature/Rule và Forecast. Kiểm thử origin A t0−9, dtype, history-only và geographic unavailable. |
| G09 D-05 — ĐÃ CHỐT | Trung xác nhận `is_simulated` mô tả quỹ đạo, không phải tàu; synthetic trajectory có thể có physical MMSI khớp. Schema và Pydantic giữ `SYNTHETIC_AIS` + true và cho phép physical identity; source stability còn P1. | Xem test provenance/profile; semantic equality cần G11. |
| G10 D-09 — ĐÃ CHỐT | Trung đã duyệt ma trận 25 state/action, RESET/SEEK source ENDED/version +1, new session version 0, retry trước state/version. | Test model đủ 25 tổ hợp; runtime atomicity vẫn chưa kiểm chứng. |
| G11 D-05 — ĐÃ CHỐT | Trung duyệt `PRODUCTION_VALID = STRUCTURAL_VALID AND SEMANTIC_VALID`. JSON Schema structural vẫn không so sánh trực tiếp hai field; validator dùng chung `src.data.track_semantics` thực hiện equality, source và trajectory provenance. | `validate_production_track_g11` chạy đúng structural production + semantic G11; Pydantic T04 gọi cùng semantic rule ở legacy profile. Vector phiên bản dùng chung kiểm structural, semantic, combined, Pydantic và JavaScript. Consumer tương lai phải tích hợp, không suy ra runtime đã pass. |

## Các quyết định cần Trung tiếp tục chốt

- **P0 specification:** Không còn sau quyết định G11; consumer tương lai phải tích hợp hai tầng và test temporal/session đầy đủ trước runtime production.
- **P1 D-06:** xử lý client legacy không có mapping ID; giữ mock tách biệt, không tự migrate lịch sử.
- **Nguồn:** xác nhận timezone/provenance raw, duplicate ordering và tính ổn định identity trước production. Các giới hạn này không phủ nhận việc Trung đã phê duyệt thiết kế ngày 2026-11-22.
