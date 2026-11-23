# G11: kiểm chứng semantic Contract V1

## Quy tắc và phạm vi

Production bắt buộc thỏa `STRUCTURAL_VALID AND SEMANTIC_VALID`. JSON Schema Draft 2020-12 kiểm tra shape, type, required, pattern, enum, version và nested schema, nhưng không có phép chuẩn để đối chiếu động hai giá trị field. Ví dụ `physical_mmsi:123456789` cùng `mmsi: 987654321` qua structural riêng lẻ nhưng bị semantic và combined từ chối. Không sửa hay tự tạo MMSI để làm dữ liệu hợp lệ.

`src/data/track_semantics.py` cung cấp `validate_track_semantics` theo `PRODUCTION_V1` và `LEGACY_MOCK`. Physical ID phải có MMSI chín chữ số trùng hậu tố; `is_simulated` mô tả quỹ đạo, do đó synthetic trajectory có thể dùng physical ID khớp. Simulated identity không được gán physical MMSI khi chưa có quy tắc provenance; REAL_AIS yêu cầu physical identity. Kiểm tra tính nhất quán không xác minh quyền sở hữu hay nguồn MMSI thực.

`validate_production_track_g11` kết hợp schema production và semantic G11. Đây không phải validator đầy đủ mọi quy tắc Contract V1: temporal/history, session, hash, pagination và các invariant khác vẫn cần được consumer tương ứng thực thi. `backend/app/mock_tracks.py` gọi cùng semantic rule theo profile legacy và giữ các validator temporal sẵn có. Legacy mock không tự động hợp lệ trong production.

## Vector và consumer

`contracts/validation_vectors/g11_track_v1.json` phiên bản 1.0 gồm 13 payload, kỳ vọng structural, semantic, combined và Pydantic, cùng giải thích. Python kiểm thử tất cả; JavaScript kiểm thử semantic trên cùng vector. Pydantic là consumer legacy nên có thể chấp nhận `mock-*` hoặc namespace legacy khác mà production từ chối. Trên các case production dùng chung, combined và Pydantic thống nhất; không yêu cầu structural-only từ chối lỗi chỉ thuộc semantic.

| Tình huống | Structural | Semantic | Combined | Pydantic legacy |
|---|---|---|---|---|
| Synthetic + physical ID/MMSI khớp | PASS | PASS | PASS | PASS |
| Physical ID/MMSI không khớp | PASS | FAIL | FAIL | FAIL |
| Physical thiếu hoặc null MMSI | FAIL | FAIL | FAIL | FAIL |
| Simulated ID, MMSI null | PASS | PASS | PASS | PASS |
| Simulated ID có MMSI | FAIL | FAIL | FAIL | FAIL |
| Mock trong profile legacy | PASS | PASS | PASS | PASS |
| Mock trong profile production | FAIL | FAIL | FAIL | PASS |
| REAL_AIS + physical khớp | PASS | PASS | PASS | PASS |
| REAL_AIS + simulated ID | FAIL | FAIL | FAIL | FAIL |

Các phép gọi schema-only trong test hiện hữu là test cấu trúc, không chứng minh validation production hoàn chỉnh. Backend hiện hữu là mock; chưa phát hiện consumer production runtime hiện hữu chỉ dùng schema. Khi triển khai producer/adapter, Replay Engine, hoặc các endpoint Encounter/Risk/Alert, phải áp dụng cả hai tầng cho mỗi track, kể cả nested track, cùng các quy tắc temporal và session liên quan. Identity reference kiểm canonical ID/hash, không thay thế validator TrackSnapshot.

## Hồi quy và quyết định

277 pytest và 5 frontend tests PASS; build frontend PASS; schema/ref và OpenAPI được bao phủ; pair/encounter Python–JavaScript và ma trận replay contract model 25/25 PASS. Browser smoke trên mock có bốn tàu và chọn STALE hiển thị 10 mốc. Có một cảnh báo deprecation Starlette/TestClient.

`CONTRACT_SPECIFICATION_LOCKED: YES` theo phạm vi đặc tả được duyệt, không còn P0 được xác định. `CONTRACT_IMPLEMENTATION_LOCKED: CONDITIONAL`: reference G11 và mock được kiểm chứng, production runtime chưa tích hợp và chưa được xác minh. `FUTURE_RUNTIME_UNVERIFIED` gồm Replay, adapter, model/Risk/Alert, persistence, concurrency. `SOURCE_VALIDATION_PENDING` và `IDENTITY_SOURCE_VALIDATION_PENDING` vẫn còn do raw AIS, timezone, duplicate và stable source identity chưa có bằng chứng.
