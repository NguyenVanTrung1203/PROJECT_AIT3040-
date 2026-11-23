# Đánh giá sẵn sàng khóa Contract V1

## Quyết định và phạm vi

Trung đã phê duyệt 14 quyết định thiết kế D-01 đến D-14 và P0-01 đến P0-06. G11 được chốt theo `PRODUCTION_VALID = STRUCTURAL_VALID AND SEMANTIC_VALID`. Không còn gap đặc tả P0 được xác định. Thiết kế và đặc tả được đánh giá đã khóa; thay đổi tại branch `trung-contract-v1-freeze`, base `a8583a72b5fee9a302bbb17ce3834385b32c5bbf`, vẫn chờ Trung review và chưa commit, push hoặc merge. Không suy ra sự phê duyệt của Toàn.

## G11 và tính tương thích

JSON Schema Draft 2020-12 kiểm tra cấu trúc nhưng không so sánh động `physical_mmsi:<digits>` với `mmsi`. Semantic validator dùng chung bắt buộc kiểm tra hai giá trị khớp cùng source và provenance; parity được đánh giá với kết quả kết hợp, không phải schema đơn lẻ. Pydantic mock gọi cùng quy tắc trong profile legacy. `mock-*` có thể hợp lệ với legacy nhưng không vì vậy trở thành production-valid.

`validate_production_track_g11` thực hiện schema production và semantic G11; hàm này không thay thế các kiểm tra temporal/history, session, hash và semantic khác của toàn hợp đồng. Consumer nhận nested TrackSnapshot trong Encounter/Risk cũng cần áp dụng semantic cho từng track. Chưa có production runtime để kiểm chứng tích hợp đầu cuối; không tuyên bố mọi consumer tương lai đã được kiểm thử. Xem `CONTRACT_V1_G11_SEMANTIC_VALIDATION_REPORT.md` và `contracts/integration_contract.md`.

## Kiểm thử

Đợt G11: **277 pytest PASS, 0 failed, 0 xfailed**, gồm schema/ref, OpenAPI, Pydantic, vector Python/JavaScript, ma trận replay 25/25, session/idempotency, pagination và backend mock; **5 frontend tests PASS**, build PASS. Một cảnh báo deprecation Starlette/TestClient. Browser smoke mock hiển thị bốn tàu, chọn tàu STALE hiển thị 10 mốc và tuổi 180 giây. Ma trận là contract model trong bộ nhớ, không chứng minh runtime.

## Kết luận và giới hạn

- `DESIGN_FREEZE_APPROVED: YES`; `CONTRACT_SPECIFICATION_LOCKED: YES` trong phạm vi đặc tả và contract test đã kiểm tra.
- `CONTRACT_IMPLEMENTATION_LOCKED: CONDITIONAL`: reference G11 và mock hiện có đã kiểm thử; các semantic khác và sự tích hợp trong production runtime chưa được kiểm chứng đầu cuối.
- `SOURCE_VALIDATION_PENDING`: raw AIS, timezone, duplicate và provenance chưa được xác minh; `IDENTITY_SOURCE_VALIDATION_PENDING`: tính ổn định source ID và MMSI ngoài đời chưa được chứng minh. Khớp chuỗi không chứng minh MMSI thuộc tàu thực.
- `FUTURE_RUNTIME_UNVERIFIED`: Replay Engine, adapter, model/Risk/Alert, persistence và concurrency. Không đồng nhất test oracle với runtime test. Các ngưỡng mock không phải ngưỡng chính thức.
