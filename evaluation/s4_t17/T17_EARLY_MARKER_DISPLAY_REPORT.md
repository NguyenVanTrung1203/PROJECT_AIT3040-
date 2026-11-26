# T17 Early AIS Marker Display Review

## Kết luận

- **ROOT_CAUSE:** Backend giữ `current_state=null` cho TrackSnapshot chưa `VALID`, trong khi frontend trước đây chỉ render marker nếu `track.current_state` truthy. Vì vậy những TrackSnapshot `INSUFFICIENT_DATA` có history một phần không có marker.
- **BACKEND_PARTIAL_HISTORY:** Có. `/api/v1/replay/sessions/{id}/tracks` trả `history` một phần cho các mốc đầu nguồn; `track_list` dùng production TrackSnapshot schema cho phép `history` từ rỗng đến tối đa 10 điểm. `TrackBuffer.snapshot()` tạo các điểm as-of thực có và không điền dữ liệu thiếu.
- **FRONTEND_FILTER:** Trước thay đổi, `FitTracks` và `<Marker>` đều lọc qua `current_state`; history partial không được xét. Sau thay đổi, chỉ nhánh hiển thị `INSUFFICIENT_DATA` có thể lấy điểm history tại đúng anchor.
- **CONTRACT_COMPATIBILITY:** Tương thích. Schema cho phép `current_state` là null và history ngắn ở trạng thái chưa `VALID`; `VALID` vẫn yêu cầu đủ 10 điểm và `current_state` là object. Runtime tiếp tục giữ invariant `current_state=null` cho non-VALID. Không thêm field/wire schema, không nội suy và không dùng timestamp future.
- **EARLY_MARKER_DISPLAY:** PASS trong phạm vi synthetic Replay fixture. Marker `INSUFFICIENT_DATA` dùng màu xanh lam nhạt/opacity riêng, có legend, timestamp fix và số history `N/10`. Marker chỉ dùng history point tại anchor có tọa độ trong giới hạn, source timestamp UTC `Z` không sau anchor, age 0–60 giây và khớp `source_age_seconds`.
- **MODEL_RISK_SAFETY:** PASS. Forecast checkbox bị khóa nếu track không `VALID` hoặc không có đủ 10 history point; Forecast adapter vẫn yêu cầu `VALID`. Không có Model/Risk/Alert inference hay output mới.

## Nguyên nhân và dữ liệu fixture

`src/data/track_buffer.py` chọn message mới nhất không sau từng nominal grid point, bỏ điểm không đạt freshness 0–60 giây, và giữ history thực có. Khi số điểm dưới 10, status là `INSUFFICIENT_DATA` và `current_state` được đặt null. Khi đủ 10 điểm, status mới là `VALID` và current state bằng history cuối.

Fixture tại `backend/app/fixtures/t12_replay_events.json` có một synthetic AIS event mỗi phút từ 00:00 đến 00:09 UTC. Kết quả API đã kiểm tra:

| Simulation anchor UTC | Số history point | Status | Điểm quan sát tại anchor |
|---|---:|---|---|
| 00:00 | 1 | INSUFFICIENT_DATA | 00:00, age 0s |
| 00:01 | 2 | INSUFFICIENT_DATA | 00:01, age 0s |
| 00:05 | 6 | INSUFFICIENT_DATA | 00:05, age 0s |
| 00:08 | 9 | INSUFFICIENT_DATA | 00:08, age 0s |
| 00:09 | 10 | VALID | 00:09, age 0s |
| 00:10 | 10 | VALID | 00:09, age 60s |

Mốc 00:10 là end-exclusive của source. Session kết thúc tại thời điểm đó, nhưng event 00:09 nằm đúng biên freshness 60 giây nên history vẫn đủ 10 điểm và status vẫn `VALID`.

Các fixture này là dữ liệu synthetic có kiểm soát, không phải bằng chứng rằng nguồn AIS production có cùng coverage.

## Thay đổi UI

- Marker, map fit và danh sách tàu dùng điểm `INSUFFICIENT_DATA` chỉ khi có history point `nominal_timestamp == anchor_timestamp`, timestamp nguồn là UTC `Z` không sau anchor, age 0–60 giây, age metadata khớp và lat/lon hợp lệ.
- Replay history lines/details bỏ các point có nominal/source time sau anchor, age ngoài 0–60 giây, metadata age không khớp, timestamp không UTC `Z`, hoặc tọa độ ngoài miền. Mock mode giữ nguyên cách hiển thị history T04.
- Marker thiếu history có màu/opacity và nhãn legend khác `VALID`; tooltip nêu status và thời gian của selected fix.
- Chi tiết snapshot hiển thị vị trí quan sát as-of, AIS fix UTC, `current_state` không bị thay đổi, và history count theo dạng `N/10`.
- Điểm future, quá tuổi hoặc tọa độ ngoài miền không tạo marker/history point trên Replay map. `STALE`/`INVALID_DATA` không đi qua nhánh partial-history và không tạo marker trong Replay mode.
- T04 Mock API mode tiếp tục dùng `current_state` hiện hữu; không thay đổi endpoint hoặc Mock data.
- RESET/session replacement xóa snapshot/selection cũ trước khi tải snapshot mới; kiểm thử xác nhận vị trí mới đến từ session mới.

## Kiểm thử thực tế

- Backend API anchor matrix, including partial history, counts, state, as-of bounds and 00:10 source end: **6 parameter cases PASS**.
- Full Python regression (`tests/unit`, `tests/integration`, `backend/tests`): **325 passed**; one upstream AnyIO pytest deprecation warning.
- Frontend Vitest: **17 passed** across 2 files. Includes eligible partial point, rejected future/age-mismatch points, incomplete forecast gate, reset marker replacement, and existing Mock mode coverage.
- Frontend production build: **PASS**, Vite transformed 74 modules.
- `git diff --check`: **PASS**.

## Files changed this turn

- `backend/tests/test_replay_api.py` — exact Replay anchor matrix and count/status/as-of assertions.
- `frontend/src/App.jsx` — as-of partial marker selection, explicit marker status, fix UTC/history completeness, and Forecast eligibility gate.
- `frontend/src/App.test.jsx` — partial/future/stale guard and reset-session marker tests; existing T04 tests retained.
- `frontend/src/styles.css` — distinct incomplete-marker and legend styling.
- `evaluation/s4_t17/T17_EARLY_MARKER_DISPLAY_REPORT.md` — this review.

No Contract V1, DATASET_FINAL, AIS source, `current_state` semantics, Model/Risk/Alert module, or wire field was modified. Pre-existing T17/T16 working changes were preserved. No branch, commit, push, or merge operation was performed.

## Remaining limitations

- Early marker evidence is limited to the synthetic T12 Replay fixture; production AIS source trust/timezone and real source completeness remain outside this test.
- When history has no valid fix at the anchor (including stale-only or invalid data), no marker is drawn. Contract status and `current_state` are not relaxed to force a position onto the map.
- A partial-history position is display-only and remains `INSUFFICIENT_DATA`; it is not an input for Model/Risk evaluation.

