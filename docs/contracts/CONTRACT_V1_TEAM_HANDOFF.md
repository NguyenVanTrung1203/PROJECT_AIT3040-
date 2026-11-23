# Bàn giao Contract V1 cho nhóm

## 1. Tổng quan

Contract V1 quy định giao diện dữ liệu và hành vi giữa nguồn AIS, Track/Replay, Encounter, Model/Forecast, Risk, Alert và giao diện bản đồ. Trung đã duyệt 14 quyết định thiết kế và P0-01 đến P0-06; đặc tả đã khóa trong phạm vi kiểm chứng. Validator tham khảo và mock hiện có đã được test. Runtime production, tích hợp nguồn và kiểm thử đầu cuối chưa hoàn thành; khóa đặc tả không có nghĩa hệ thống đã production-ready. Chưa có bằng chứng Toàn đã phê duyệt toàn bộ contract.

## 2. Thông tin Git

- Repository: `NguyenVanTrung1203/PROJECT_AIT3040-`.
- Source baseline: `origin/main` tại `a8583a72b5fee9a302bbb17ce3834385b32c5bbf`.
- Branch bàn giao: `trung-contract-v1-freeze`; commit bàn giao là HEAD của branch khi được push và xác minh, xem `git log -1`.
- Version schema đối tượng: `1.0.0`. Một số companion JSON còn `1.0.0-draft`; kiểm tra compatibility/versioning trước tích hợp production.
- Không merge trong lượt bàn giao này.

## 3. Quyết định đã duyệt

| Quyết định | Nội dung |
|---|---|
| D-01 | History 10 mốc; as-of không tương lai, age 0–60 giây; schema_version và mmsi phải có key; current state bằng history cuối. |
| D-02 | QC/model dùng selected source timestamp; original timestamp là provenance. |
| D-03 | Không đoán UTC; duplicate giống nhau giữ stable-first, xung đột loại toàn nhóm; source ordering cần bằng chứng. |
| D-04 | Giữ enum chất lượng; phân biệt chất lượng, inference, calibration và quyết định alert. |
| D-05 | Identity physical/simulated có namespace; is_simulated mô tả trajectory; không giả MMSI. |
| D-06 | Pair/Encounter hash canonical; A/B online theo UTF-8, offline giữ tensor mapping. |
| D-07 | Common EN đơn vị nm, origin tàu A tại t0−9; địa lý `[latitude, longitude]`. |
| D-08 | Model input `[2,10,4]` float32; Rule input `[2,10,2]` float64 SOG/COG, chỉ dùng history. |
| D-09 | Session isolation; RESET/SEEK tạo session mới; ma trận 25 state/action và idempotency. |
| D-10 | Năm path REST Replay và polling; UUID canonical, pagination snapshot TTL năm phút. |
| D-11 | Không fallback khi input sai; CV fallback chỉ cho lỗi kỹ thuật đủ điều kiện; chưa calibration thì decision null. |
| D-12 | Forecast 15 phút; quy ước CPA near-zero và trọng số theo contract; không tự thay thuật toán. |
| D-13 | Tối đa một alert chưa RESOLVED mỗi session/pair; xử lý idempotency, thứ tự và atomicity. |
| D-14 | Design approved bởi Trung; thay đổi phải có compatibility, version và bằng chứng review. |

P0-01–P0-06 đã duyệt; chi tiết và giới hạn tại [biên bản quyết định](CONTRACT_V1_DECISION_RECORD.md) và [danh sách gap](CONTRACT_V1_SPECIFICATION_GAPS.md). G11 quy định validation hai tầng; P0-05 xác định `is_simulated` theo trajectory và P0-06 xác định đủ 25 chuyển trạng thái.

## 4. Contract inventory

Đường dẫn dưới đây tính từ repository root; consumer phải áp dụng cả invariant semantic tại [integration contract](../../contracts/integration_contract.md).

| File | Công dụng và consumer / điều kiện |
|---|---|
| `contracts/common.schema.json`, `track_snapshot.schema.json` | Kiểu chung và TrackSnapshot cho loader/Replay/Encounter; không tự kiểm tất cả quan hệ thời gian. |
| `contracts/replay.schema.json`, `encounter_v1.schema.json` | Replay và Encounter production; UUID và identity production, cộng semantic validation. |
| `contracts/risk_request_v1.schema.json`, `risk_response_v1.schema.json`, `alert_v1.schema.json` | Risk/Alert profile replay; consumer kiểm semantic, session, hash và lifecycle. |
| `contracts/encounter.schema.json`, `risk_request.schema.json`, `risk_response.schema.json`, `alert.schema.json` | Schema legacy/live tương ứng; mock không tự hợp lệ production replay. |
| `contracts/forecast.schema.json`, `model_status.schema.json`, `error.schema.json` | Forecast, trạng thái model và lỗi API; consumer không suy ra model sẵn sàng từ schema. |
| `contracts/api_contract.yaml`, `integration_contract.md` | OpenAPI và quy ước tích hợp cho client/server; runtime phải thực thi các điều kiện cross-field. |
| `contracts/feature_contract.json`, `coordinate_contract.md`, `rule_input_contract.json`, `temporal_contract.json` | Mapping, hệ tọa độ, input và thời gian cho adapter; kiểm chứng source và frame trước vận hành. |
| `contracts/validation_vectors/g11_track_v1.json`, `docs/contracts/CONTRACT_V1_PAIR_ID_TEST_VECTORS.md` | Vector G11 và identity cho Python/consumer ngôn ngữ khác; chỉ là dữ liệu kiểm thử. |
| `scripts/contract_identity_reference.py`, `src/data/track_semantics.py` | Reference identity và G11; không thay runtime hoặc xác minh identity thật. |
| `tests/unit/`, `tests/integration/`, `backend/tests/` | Contract, compatibility và mock regression; test model không chứng minh runtime. |

## 5. Giao diện chung

TrackSnapshot chứa identity, source, provenance, anchor, current state và history. Timestamp nguồn được chọn không vượt grid; history không vượt simulation clock. Physical ID là `physical_mmsi:<9digits>` và phải khớp MMSI; simulated là `simulated:<dataset>:<stable-id>`, NFC. Dataset/stable ID và MMSI thực cần xác minh nguồn; không dùng filename/row index làm ID nếu chưa chứng minh ổn định.

Pair ID là `pair:v1:` + SHA-256 của compact JSON UTF-8 gồm hai canonical ID phân biệt đã sort theo bytes. Online A là ID nhỏ hơn; offline giữ mapping tensor. Encounter ID là `enc:v1:` + SHA-256 compact JSON `[session_id,pair_id,anchor_utc]`; session UUID lowercase canonical, anchor UTC `Z` đúng giây. Feature/Rule adapter phải giữ mapping và frame Common EN; địa lý trả LAT/LON. Forecast, Risk và Alert phân biệt input invalid, inference, calibration và decision; `NOT_CALIBRATED`/decision null không phải không có rủi ro.

Replay giữ session cho play/pause/resume; mọi reset/seek hợp lệ tạo session mới và kết thúc source. Version và idempotency bảo vệ control; không suy ra atomicity từ contract tests. Nguồn và model/risk/alert runtime chưa được triển khai đầy đủ trong phạm vi này.

## 6. Yêu cầu validation

`PRODUCTION_VALID = STRUCTURAL_VALID AND SEMANTIC_VALID`. JSON Schema Draft 2020-12 kiểm shape/type/required/pattern/version, không tự đối chiếu physical ID với MMSI. Consumer production phải thực thi schema production **và** semantic G11 cho từng track, kể cả track lồng trong Encounter/Risk, cùng các invariant temporal, history, session, hash và nguồn. `validate_production_track_g11` chỉ bao phủ structural production và semantic G11, không thay thế toàn bộ kiểm tra runtime.

Legacy/mock dùng schema và `LEGACY_MOCK` riêng; mock ID không phải UUID hay identity production. Cross-language cần chạy vector Pair/Encounter và G11; dùng byte sort UTF-8, không dựa vào sort mặc định UTF-16. Mỗi session/snapshot có UUID opaque lowercase; không trộn phiên hay snapshot, và phải giữ schema version phù hợp.

## 7. API bàn giao

Các path và schema dưới đây mô tả contract, chưa chứng nhận server production tồn tại. Chi tiết lỗi dùng `contracts/error.schema.json`; status cụ thể theo `contracts/api_contract.yaml`.

| Method và path | Request | Response thành công |
|---|---|---|
| `POST /api/v1/replay/sessions` | `replay.schema.json#/$defs/create_request` | 201 `session_response` |
| `GET /api/v1/replay/sessions/{session_id}` | UUID path | 200 `session_response` |
| `POST /api/v1/replay/sessions/{session_id}/control` | `control_request`; Idempotency-Key bắt buộc RESET/SEEK | 200 `session_response` |
| `GET /api/v1/replay/sessions/{session_id}/tracks` | limit, offset, snapshot_id | 200 `track_list` |
| `GET /api/v1/replay/sessions/{session_id}/tracks/{vessel_id}` | UUID, vessel ID, snapshot_id tùy chọn | 200 `production_track` |

404 là không tìm thấy, 409 là conflict được mô tả, 410 là session/snapshot hết hạn, 422 là input không hợp lệ, 503 là nguồn không khả dụng. Limit mặc định 50, tối đa 100; trang tiếp dùng snapshot ID, snapshot TTL năm phút. Risk/Alert T02 dùng profile V1 khi replay; live `session_id=null` theo profile live/legacy tương ứng.

## 8. Phân công

| Người | Trách nhiệm thực hiện tiếp |
|---|---|
| Trung | Feature adapter, Model/Forecast, Risk, Alert, calibration và kiểm thử các phần này. |
| Toàn | Xác minh nguồn, AIS loader, Replay Engine, session/persistence, map và tích hợp frontend. |

Đây là phân công triển khai, không xác nhận Toàn đã duyệt các thay đổi.

## 9. Hoàn thành và còn lại

Đã hoàn thành đặc tả trong phạm vi kiểm chứng, reference validators, contract tests và tương thích mock. Chưa hoàn thành xác minh raw AIS, Replay runtime, online adapter, Model/Risk/Alert production runtime, persistence/concurrency và end-to-end tests. Không có threshold production được chứng minh chỉ bằng fixture mock.

## 10. Bằng chứng kiểm thử

Trên worktree branch bàn giao, base commit nêu ở mục 2, dùng `.venv` hiện có, Node và npm hiện có:

- `python -m pytest tests/unit tests/integration backend/tests -q -p no:cacheprovider`: **277 passed, 0 failed, 0 xfailed**; `DATASET_ROOT` trỏ dataset hiện có, tắt ghi bytecode. Bao gồm schema/ref, OpenAPI, Pydantic, G11, Pair/Encounter Python–JavaScript, 25 transition contract model, session, pagination và backend mock.
- Trong `frontend`: `npm test`: **5 passed**; `npm run build`: **PASS**.
- `git diff --check`: kiểm tra trước stage; kiểm tra staged diff tiếp tục trước commit.
- Browser smoke: **BROWSER_NOT_RERUN** trong lượt này. Một cảnh báo deprecation Starlette/TestClient; không cài dependency mới.

Ma trận replay và idempotency là model/ví dụ kiểm thử, không chứng minh persistence, race, API thực hoặc production runtime. Kết quả thuộc nội dung worktree trước commit bàn giao; commit được xác định qua HEAD branch, không dự đoán SHA.

## 11. Checklist tích hợp

- [ ] Kiểm schema version và compatibility của companion draft.
- [ ] Chạy structural **và** semantic production cho mọi track.
- [ ] Kiểm UUID và namespace, xác minh identity tại nguồn.
- [ ] Giữ A/B online/offline đúng mapping và EN origin.
- [ ] Thực thi session lifecycle, isolation và version.
- [ ] Kiểm idempotency, transaction và concurrency.
- [ ] Pin snapshot, kiểm pagination và expiry.
- [ ] Kiểm no-future leakage theo source clock.
- [ ] Phân biệt NOT_CALIBRATED/decision null với no alert.
- [ ] Chạy contract tests, cross-language vectors và end-to-end tests khi runtime tồn tại.

## 12. Thay đổi tương thích và giới hạn

Các path Model/Risk/Alert T02 giữ tên nhưng refs cho replay chuyển sang profile V1; filter session yêu cầu UUID production. Legacy mock/session/encounter ID không tự tương thích replay production; client phải chuyển profile có kiểm soát. `schema_version` và `mmsi` là key bắt buộc trong Pydantic. Online A/B được canonical hóa, offline không đổi tensor mapping. Không thay đổi CPA, trọng số hoặc ngưỡng bằng việc bàn giao contract.

Raw AIS, timezone, duplicates và stable source identity vẫn `SOURCE_VALIDATION_PENDING`; kiểm tra ID khớp MMSI không chứng minh tàu ngoài đời. Replay, adapter, Model/Risk/Alert, persistence và concurrency là `FUTURE_RUNTIME_UNVERIFIED`.

## 13. Quyết định bàn giao

`DESIGN_FREEZE_APPROVED` bởi Trung; `CONTRACT_SPECIFICATION_LOCKED: YES` trong phạm vi bằng chứng; `CONTRACT_IMPLEMENTATION_LOCKED: CONDITIONAL`. Chưa merge, sẵn sàng cho nhóm review sau khi branch được push và xác minh. Không suy ra Toàn đã phê duyệt.
