# S1_T04 — Mock Data API và bản đồ AIS

**Ngày:** 2026-11-22
**Branch:** `Trinh_Toan`
**Trạng thái nghiệm thu:** **PASS** trong phạm vi S1_T04. Người dùng đã xác nhận kiểm tra thủ công trên Chrome tại `localhost:5173`; các test tự động backend/frontend, build, esbuild và dependency audit cũng đạt. Browser automation của agent không khả dụng trong phiên này.

## Đã triển khai

- Backend FastAPI tạo bốn TrackSnapshot deterministic quanh Kattegat. Ba tàu có trạng thái `VALID`, một tàu `STALE` với source age 180 giây. Mỗi tàu dùng `source_type=SYNTHETIC_AIS`, `is_simulated=true`, MMSI `null` và ID `mock-vessel-*`; không tạo MMSI thật, risk score, nhãn an toàn, hoặc forecast.
- Mỗi history có 10 mốc nominal từ anchor −9 phút đến anchor. Tọa độ được tạo từ tốc độ/hướng hằng định theo phút bằng chuyển động cục bộ East/North; source time không muộn hơn nominal time, không có bản tin tương lai.
- API đọc-only có filter theo source/data status, detail theo vessel ID, health, response rỗng và error body theo `error.schema.json`.
- Frontend React/Leaflet dùng OSM tiles; marker, polyline history, chi tiết khi click, UTC/SOG/COG, status, nhãn MOCK, loading/error/empty/retry. Tọa độ Leaflet được truyền theo thứ tự `[latitude, longitude]`.
- Không có pairing, CPA, risk panel, alerts, replay controls/clock, WebSocket hoặc M5a.

## API

| Method | Endpoint | Kết quả |
|---|---|---|
| GET | `/health` | `{"status":"ok","service":"mock-track-api"}` |
| GET | `/api/v1/mock/tracks` | `{"items":[TrackSnapshot,...],"total":4}` |
| GET | `/api/v1/mock/tracks?source_type=SYNTHETIC_AIS&data_status=VALID` | Filtered TrackSnapshots |
| GET | `/api/v1/mock/tracks/{vessel_id}` | Một TrackSnapshot gồm current state và history |

Không tìm thấy vessel trả 404 theo `error.schema.json`, `error_code=VESSEL_NOT_FOUND`. Query không hợp lệ trả 422 `INVALID_REQUEST`. Filter `source_type=REAL_AIS` hiện cho danh sách rỗng `{ "items": [], "total": 0 }`.

Mẫu response đầy đủ cho `mock-vessel-001` được lưu tại [`mock_track_snapshot.json`](mock_track_snapshot.json) và validate bằng `contracts/track_snapshot.schema.json`.

Response list có dạng:

```json
{
  "items": [
    {"vessel_id": "mock-vessel-001", "source_type": "SYNTHETIC_AIS", "data_status": "VALID"}
  ],
  "total": 4
}
```

`items` trong response thật chứa đầy đủ TrackSnapshot theo schema, không phải các object rút gọn ở ví dụ list.

## Chạy local

Từ thư mục repo:

```powershell
# Backend: cài requirements-dev.txt trong .venv theo README nếu chưa có
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Terminal thứ hai:

```powershell
cd frontend
npm install
npm run dev
```

Mở `http://127.0.0.1:5173/`. API mặc định `http://127.0.0.1:8000`; có thể thay bằng `VITE_API_BASE_URL` dựa trên `frontend/.env.example`. Bản đồ cần truy cập OpenStreetMap tiles để tải nền.

## Kiểm thử và kết quả

- Python: `.venv\Scripts\python.exe -m pytest tests/unit tests/integration backend/tests -q` — **151 passed**, 1 warning dependency `anyio`/pytest deprecation.
- Backend riêng: 8 test API mới đạt, gồm JSON Schema snapshot/example, UTC, lat/lon bounds, history không vượt anchor, cấm source timestamp tương lai, detail/404, empty filter, 422 và health.
- Frontend: `npm test` — **5 passed** (React/jsdom); marker và polyline, đúng lat/lon order, chọn tàu/10 điểm history, empty/error/retry, Refresh và trạng thái `STALE`/age 180s của `mock-vessel-004`.
- Frontend build: `npm run build` — **PASS**, Vite 7.3.8 tạo production bundle; `npm exec -- esbuild --version` trả `0.28.2`.
- Dependencies: `npm ls --depth=0` — các dependency top-level đã resolve; `npm audit --audit-level=high` — **0 vulnerabilities** sau khi nâng Vite/Vitest theo advisory từ registry.
- Live HTTP smoke: `/health`, list (4 tàu), detail (10 mốc), empty filter, 404 và Vite HTML đều trả kết quả mong đợi.
- Browser thật: người dùng xác nhận đã thấy Leaflet/OSM, marker, chọn `mock-vessel-001`, TrackSnapshot, MMSI mock, UTC, LAT/LON, SOG/COG, history 10 mốc và track line trên Chrome. Agent không có phiên browser automation khả dụng để kiểm tra lại độc lập.
- `git diff --check` PASS trong lượt nghiệm thu cuối.

## Contract compatibility và quyết định cần review

- TrackSnapshot JSON được validate với `track_snapshot.schema.json`; error body tái dùng `error.schema.json`. Không sửa `contracts/api_contract.yaml` hoặc schema chung.
- `api_contract.yaml` hiện chỉ liệt kê model/risk/encounter/alert paths, không có Track API hay `/health`. Routes mới được đặt riêng dưới `/api/v1/mock/tracks` để tránh xung đột; collection envelope `{items,total}` và route naming là đề xuất bổ sung cho contract chung.
- Schema có `data_status` (`VALID`, `INSUFFICIENT_DATA`, `STALE`, `INVALID_DATA`) nhưng không có `quality_status`/`quality_flags` riêng. T04 dùng `data_status` làm QC summary; nếu tầng map cần cờ QC chi tiết, đề nghị bổ sung contract sau khi Trung và Toàn review.
- CORS hiện cho `localhost:5173` và `127.0.0.1:5173` phục vụ dev local.

## Phối hợp và phần tiếp theo

- **Cần Trung review:** API path/envelope trong `api_contract.yaml`; semantics nguồn synthetic và QC status; contract ownership trước khi risk/integration dùng TrackSnapshot.
- **Chưa làm trong T04:** replay clock/session, ingest raw AIS, track management/freshness thực, pair candidate/A-B, CPA, inference/risk/alerts, WebSocket và frontend map layers ngoài demo mock. Các phần này thuộc T08–T09 hoặc sprint sau.
- Người dùng đã kiểm tra Leaflet/OSM runtime trên Chrome. Trung và Toàn cần thống nhất route/envelope trước khi nhóm coi Track API là shared integration contract.

## Trạng thái bàn giao

- `T04_STATUS: PASS`
- `MOCK_DATA_STATUS: PASS`
- `DATA_API_STATUS: PASS`
- `LEAFLET_MAP_STATUS: PASS` — người dùng xác nhận thủ công trên Chrome; React tests và build cũng đạt.
- `CONTRACT_COMPATIBILITY: PASS_WITH_ROUTE_PROPOSAL` — payload/error schema tương thích; route/envelope được cô lập, cần review trước khi thêm vào OpenAPI chung.
- `BACKEND_TEST_RESULTS: PASS` — 151 project/backend tests.
- `FRONTEND_TEST_RESULTS: PASS` — 5 jsdom tests + Vite build; người dùng xác nhận browser test.
- `REFRESH: PASS` — React test xác nhận reload danh sách.
- `STALE_STATUS: PASS` — API/React test xác nhận `mock-vessel-004` hiển thị STALE và age 180s.
- `HISTORY_CAUSALITY: PASS` — tests xác nhận 10 mốc tăng dần, không vượt anchor và source timestamps không vượt nominal time.
- `READY_FOR_T08_T09: YES` — T04 mock map/API có thể dùng cho tích hợp; route/envelope shared cần được review với Trung.
- `READY_TO_COMMIT: YES` — test/build/audit/diff checks đạt; không commit/push/merge trong lượt này.
