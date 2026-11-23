# Báo cáo Contract V1 Design Freeze

**Lưu ý lịch sử:** báo cáo freeze dưới đây phản ánh thời điểm trước quyết định khóa cuối. Các nhận định về Replay partial, vector simulated và số test được thay thế bởi `CONTRACT_V1_FINAL_LOCK_READINESS.md` và `CONTRACT_V1_DECISION_RECORD.md` hiện hành.

## Baseline và trạng thái

- Nguồn `origin/main` tại `a8583a72b5fee9a302bbb17ce3834385b32c5bbf` chứa T02 `0402747d54c9670d2ff8698824673a6c2a2dbe8e` và T03/T04 `a93c2db266c1d82109dc72037c7d2cd8dc33d7e4`. Contract của main giống T02 tại baseline.
- Branch làm việc `trung-contract-v1-freeze`, worktree tách riêng; không thay branch nguồn. Worktree sửa D-01 có thay đổi chưa commit được giữ riêng, không merge.
- Trung phê duyệt 14 quyết định thiết kế ngày 2026-11-22; không có bằng chứng Toàn phê duyệt. `DESIGN_FREEZE_APPROVED`; `CONTRACT_IMPLEMENTATION_LOCKED: NOT_READY`.
- `CONTRACT_V1_DECISION_RECORD.md` là biên bản quyết định; `CONTRACT_V1_SPECIFICATION_GAPS.md` liệt kê các điều kiện khóa triển khai. Không có runtime Replay, Model, Risk hoặc Alert mới trong thay đổi này.

## Kiểm kê contract

Nguồn tất cả các file contract trong bảng là T02 commit `0402747` và giống baseline `a8583a7` trước các thay đổi trong worktree này. Schema đối tượng ghi `schema_version=1.0.0`; `common.schema.json` là thư viện defs không có trường version ở root; các companion JSON ghi `1.0.0-draft`. OpenAPI là 3.1/version 1.0.0. Dấu `mock` nghĩa là fixture/test, không phải runtime production.

| File | Đối tượng / consumer; implementation và test hiện có | D liên quan / khác biệt |
|---|---|---|
| `track_snapshot.schema.json` | Track producer, Replay/Encounter; T04 Pydantic + mock API, backend/schema tests | D-01–05; Pydantic nhận thiếu hai key bắt buộc; semantic cần runtime. |
| `common.schema.json` | Shared types, status, identity và coordinate; schema ref tests | D-04–07; không tự bảo đảm canonical ID/runtime. |
| `encounter.schema.json` | Encounter/Risk; mock fixtures + semantic tests | D-06–09; A/B replay và ID còn gap. |
| `risk_request.schema.json` | Risk API tương lai; mock/negative fixture tests | D-08,11; runtime chưa triển khai. |
| `risk_response.schema.json` | Risk/UI; mock/semantic tests | D-11–13; score/finite/decision cần runtime validation. |
| `alert.schema.json` | Alert/UI; mock lifecycle tests | D-09,13; transaction và idempotency chưa có runtime. |
| `model_status.schema.json` | Model/Risk/UI; mock/status tests | D-04,11–12; không chứng minh model ready. |
| `forecast.schema.json` | Forecast/Risk/Map; mock/schema tests | D-07,08,12; online adapter/inverse chưa xác minh. |
| `error.schema.json` | API client/server; T04 mock error và schema tests | D-10,11; lỗi production Replay chưa được đặc tả. |
| `api_contract.yaml` | Sáu path model/risk/alert và năm path Replay partial; OpenAPI/ref tests | D-09–14; Replay thiếu wire details, các operation đánh dấu gap. |
| `temporal_contract.json` | Loader, Track, adapter; feature tests | D-01–03,09; source validation và duplicate ordering pending. |
| `feature_contract.json` | Model/Encounter; feature tests | D-05–08; online A/B theo NFC/UTF-8 byte sort, offline giữ mapping tensor. |
| `coordinate_contract.md` | Feature/Forecast/Map; feature reconstruction tests | D-07–08; độ chính xác ngoài miền và geographic availability cần kiểm chứng. |
| `rule_input_contract.json` | Rule adapter; feature tests | D-08,11; online adapter chưa tồn tại. |
| `forecast_contract.json` | Forecast/Risk; feature và schema tests | D-07,08,11,12; companion vẫn draft, cần đối chiếu schema/runtime. |
| `integration_contract.md` | Giao diện các nhóm; API/mock tests | D-01–14; cập nhật seek, A/B và approval; runtime chưa có. |
| `model_design.md`, `model_config_provenance.md` | Model owner; model config tests | D-08,11,12; historical provenance không chứng minh model mới đã train. |
| `contracts/mock/manifest.json`, `contracts/mock/README.md`, fixtures | Dev và integration tests; 46 fixture static | D-01–14; giá trị là mock, không chứng minh runtime/threshold chính thức. |

## Compatibility và implementation

- T04 `/health`, `/api/v1/mock/tracks` và detail tiếp tục hoạt động theo test backend; frontend vẫn gọi mock paths không bị đổi. Frontend test/build và browser mock được kiểm tra ở lượt finalization; không kết luận frontend production tương thích.
- JSON Schema Track yêu cầu hai key; bản sửa Pydantic cần thiết đã được áp dụng trực tiếp trong worktree này sau khi review diff worktree riêng. Các case parity liên quan PASS; chưa chứng minh parity trên mọi input.
- Phê duyệt mới quy định A/B online theo thứ tự canonical ID NFC/UTF-8; các helper unit/integration được cập nhật theo quy tắc mới, offline vẫn giữ A/B. Registry namespace và ID thực còn cần kiểm chứng.
- Schema kiểm tra một số shape, range và required; equality current/history, source age tính theo timestamp, session isolation, finite numbers, pair/hash cross-language, idempotency và atomicity cần semantic/runtime checks bổ sung.
- Source raw AIS và canonical ID nguồn chưa được xác minh: `SOURCE_VALIDATION_PENDING`, `IDENTITY_SOURCE_VALIDATION_PENDING`. Test không biến các điều kiện này thành PASS.

## Test và phạm vi

Lượt freeze trước ghi 161 passed, 2 xfailed. Lượt finalization chạy `.venv` hiện có với `PYTHONDONTWRITEBYTECODE=1`, tắt pytest cache và đọc dataset khóa: **182 passed, 0 failed, 0 xfailed** trên bộ `tests/unit`, `tests/integration`, `backend/tests`. Có một cảnh báo Starlette TestClient về httpx. Bộ test bao gồm schema, OpenAPI/refs, 46 fixture và API mock; ví dụ session là mô hình trong bộ nhớ, không chứng minh runtime. Frontend cài từ lockfile, không chạy install scripts: **5 tests PASS, build PASS**; browser mở map mock có bốn tàu, chọn tàu STALE và thấy 10 mốc, tuổi 180 giây. Không có kiểm chứng Replay/Risk production.

## Thay đổi, version và khuyến nghị

Thay đổi gồm integration/feature contract, OpenAPI, schema Replay partial, backend D-01, identity test reference, tests và tài liệu. Model và dataset không đổi. OpenAPI/Replay schema chỉ ghi các phần được duyệt; wire detail còn thiếu không được xem là khóa.

Kiểm tra `git diff --check` trước bàn giao. Chưa commit/push/merge. Sẵn sàng cho Trung review; chưa sẵn sàng tuyên bố implementation locked. Cần thống nhất các gap về wire, identity và source trước khi khóa.
