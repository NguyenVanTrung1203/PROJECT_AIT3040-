# Kiểm chứng P0-05 và P0-06

**Cập nhật G11:** Các kết luận G11 và trạng thái conditional bên dưới ghi lại thời điểm trước quyết định hai tầng. G11 đã được chốt và kiểm chứng combined; xem `CONTRACT_V1_G11_SEMANTIC_VALIDATION_REPORT.md` và `CONTRACT_V1_FINAL_LOCK_READINESS.md` để biết kết luận hiện tại. Giới hạn source và runtime vẫn có hiệu lực.

Trung đã phê duyệt P0-05/P0-06. Baseline `a8583a72b5fee9a302bbb17ce3834385b32c5bbf`, worktree `trung-contract-v1-freeze`. Không có bằng chứng Toàn phê duyệt hoặc production runtime đã hoạt động.

## P0-05: quỹ đạo và identity

`is_simulated` là provenance quỹ đạo; `source_type=SYNTHETIC_AIS`, `is_simulated=true`, `vessel_id=physical_mmsi:123456789`, `mmsi=123456789` được chấp nhận. JSON Schema và Pydantic đồng ý trên các case REAL_AIS/physical, synthetic/physical, synthetic/simulated, Yang Lei/null MMSI, MMSI sai và source/flag sai. Mock T04 tiếp tục dùng legacy profile; production yêu cầu canonical namespace, REAL_AIS có physical ID và physical ID có MMSI.

**Giới hạn parity bắt buộc:** khi `vessel_id=physical_mmsi:123456789` nhưng `mmsi=987654321`, Pydantic từ chối và semantic contract cấm; JSON Schema Draft 2020-12 structural vẫn chấp nhận vì không so sánh trực tiếp hai field. Test minh bạch xác nhận sự khác biệt này. Không được xem structural validation đơn lẻ là đủ. Vì acceptance yêu cầu hai validator đồng nhất trên case mismatch, `P005_STATUS=CONDITIONAL`, chưa PASS theo nghĩa literal; G11 cần một cơ chế semantic bắt buộc/interoperable cho mọi consumer, không bỏ kiểm tra để ép parity.

## P0-06: 25 tổ hợp

| State | PLAY | PAUSE | RESUME | RESET | SEEK |
|---|---|---|---|---|---|
| READY | PLAYING | 409 | 409 | READY mới | PAUSED mới |
| PLAYING | 409 | PAUSED | 409 | READY mới | PAUSED mới |
| PAUSED | PLAYING | 409 | PLAYING | READY mới | PAUSED mới |
| ENDED | 409 | 409 | 409 | 409 | 409 |
| EXPIRED | 410 | 410 | 410 | 410 | 410 |

Schema chứa `x-control-transition-matrix`; OpenAPI và integration contract quy định conditional Idempotency-Key, expected_version, source ENDED/version +1, session mới version 0, retry trước state/version, range của SEEK, transaction và isolation. `tests/unit/test_p005_p006.py` kiểm tra 25 tổ hợp và ví dụ retry/conflict/concurrency/auto-end bằng mô hình trong bộ nhớ. **CONTRACT_MODEL_TEST PASS**, không phải Replay runtime hoặc kiểm thử DB/concurrency thật.

## Compatibility và giới hạn

Risk/Alert OpenAPI dùng production replay profile có UUID/enc:v1:; session null/live vẫn theo profile T02. Fixture `mock-*` được giữ và test theo legacy, không tự migrate hay coi là production. Đây là thay đổi compatibility có chủ đích; không sửa CPA, dataset hoặc offline A/B. Schema không thể tự chứng minh NFC, hash, equality, nguồn MMSI, clock hay tính nguyên tử; runtime phải kiểm semantic.

`SOURCE_VALIDATION_PENDING` và `IDENTITY_SOURCE_VALIDATION_PENDING`: raw AIS, timezone, duplicate và tính ổn định ID thực chưa được xác minh. Replay, adapter, Risk/Alert và persistence là `FUTURE_RUNTIME_UNVERIFIED`. Lượt cuối **262 pytest PASS, 0 failed, 0 xfailed**; frontend **5 PASS**, build PASS; browser smoke mock có bốn tàu, chi tiết STALE 10 mốc/180 giây. Một cảnh báo Starlette/TestClient. `git diff --check` được kiểm tra trước bàn giao.
