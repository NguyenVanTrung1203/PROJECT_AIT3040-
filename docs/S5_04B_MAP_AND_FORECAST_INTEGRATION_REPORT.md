# S5-04B — Map and real forecast integration

## Phạm vi và kết quả

**S5_04B_STATUS: PASS_WITHIN_SYNTHETIC_FIXTURE_SCOPE.** Giao diện React/Leaflet kết nối runtime HTTP S5-04A với nguồn `s5-01-synthetic-denmark-v1`. Đây là prototype học thuật dùng dữ liệu tổng hợp, không phải AIS thật hay hệ thống cảnh báo hàng hải chính thức. Không kết luận continuous playback inference hoặc full G4 E2E PASS.

- Ba chế độ Mock, S4 Replay fixture và S5 nhiều tàu; bản đồ hiển thị marker, vị trí, hướng và history as-of, danh tính, tình trạng và số mốc history ở phần chi tiết tàu.
- Danh sách candidate giữ cả các cặp không đủ dữ liệu và hiển thị Expected, Evaluated, Eligible, Unavailable. Người dùng chọn một cặp, dừng replay và yêu cầu đánh giá; không tự chạy cả 10 cặp mỗi lần polling.
- Forecast lấy từ forecast nhúng trong risk response của HTTP runtime, không gọi model lần hai; đường lịch sử liền và forecast nét đứt, phân biệt hai tàu, anchor và 15 mốc tương lai. Nhãn phân biệt M5a và CV fallback. Khi không có mapping địa lý hợp lệ, không tự sinh tọa độ; cặp thiếu history hiển thị lý do và không vẽ dự báo.
- Các route replay hiện hữu, runtime status, candidates và evaluate được sử dụng. Alert dashboard và việc trình bày danh sách alerts thuộc S5-05; không tuyên bố đã tích hợp panel này.

## Freshness và xử lý lỗi

Forecast được ràng buộc với session ID, version, snapshot, anchor, pair và encounter identity; kiểm tra thứ tự tàu, thời gian và tọa độ trước khi hiển thị. Generation guard loại response đến muộn sau thay đổi trạng thái. PLAY, SEEK, RESET, đổi mode, session, cặp hoặc anchor làm mất hiệu lực forecast cũ. HTTP 409 được thể hiện là xung đột/stale và 503 là runtime unavailable; không tự retry liên tục hoặc coi unavailable là an toàn. Khi PLAYING có thể xem replay, nhưng cần PAUSE để yêu cầu forecast.

## Kiểm thử

- Frontend: `npm test -- --run` — **44 passed, 3 files**; bao gồm 13 kiểm thử S5 và các kiểm thử S4 hiện có. Kiểm thử S5 bao gồm hiển thị năm tàu và coverage, chọn cặp, geometry, loading, thiếu dữ liệu, 409/503, delayed response sau điều khiển/đổi cặp/đổi mode và từ chối binding không khớp.
- Production build: `npm run build` — **PASS**, Vite 7.3.8, 74 modules.
- `git diff --check` — PASS cho thay đổi được Git theo dõi. Không chạy lại Python full regression: không sửa backend trong S5-04B.
- Model Lock, Risk V4, thresholds và Contract V1 không được sửa trong công việc S5-04B. Các thay đổi S5-00–04A có sẵn được giữ lại.

## Chrome demo: bằng chứng thực tế

Chrome truy cập `http://127.0.0.1:5173/`, backend localhost chạy CPU với external Model Package. Network/backend log ghi nhận POST evaluate HTTP 200; giao diện nhận `M5a · ACTUAL MODEL` và anchor tương ứng.

| Demo | Kết quả quan sát |
| --- | --- |
| 01 | PASS: năm marker, danh sách cặp và replay controls; nguồn được ghi synthetic. |
| 02 | PASS: SEEK 00:09, chọn A–B, forecast M5a +1…+15 phút và history/forecast hiển thị. |
| 03 | PASS: SEEK 00:15 xóa forecast trước, sau đó tạo forecast mới tại anchor 00:15. |
| 04 | PASS: tại 00:09 chọn A–E, hiển thị `INSUFFICIENT_DATA · INSUFFICIENT_OR_INVALID_HISTORY`, nút dự báo disabled và không còn forecast cũ. |
| 05 | PASS cho thao tác đổi cặp và SEEK đã quan sát; automated tests bổ sung response đến muộn sau PLAY/SEEK/RESET/đổi cặp/đổi mode. |

Ảnh Chrome gốc được lưu ngoài Git tại `C:\Users\MSI\Documents\Codex\2026-11-20\files-pasted-by-the-user-sprint-2\s5_demo_evidence`:

1. `01_system_overview.png`
2. `02_multivessel_replay.png`
3. `03_m5a_forecast_0009.png`
4. `04_m5a_forecast_0015.png`
5. `05_insufficient_data.png`

## Chạy demo trong môi trường hiện có

Backend, PowerShell, thư mục làm việc là worktree S5:

```powershell
Set-Location 'C:\Users\MSI\Documents\Codex\2026-11-20\files-pasted-by-the-user-sprint-2\work\s5-integration-final'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:DATASET_ROOT = 'C:\Users\MSI\Desktop\PROJECT_AIT3040\DATASET_FINAL'
$env:AIT3040_MODEL_PACKAGE = 'C:\Users\MSI\Documents\Codex\2026-11-20\files-pasted-by-the-user-sprint-2\s4_t14_model_packages\m5a-cc-dri-offline-v1.0-20261125T133930Z'
$env:AIT3040_MODEL_MANIFEST_PIN = 'C:\Users\MSI\Documents\Codex\2026-11-20\files-pasted-by-the-user-sprint-2\s4_t14_model_packages\m5a-cc-dri-offline-v1.0-20261125T133930Z.manifest_pin.json'
$env:AIT3040_RUNTIME_DEVICE = 'cpu'
$env:AIT3040_RUNTIME_AUTHORITY = 'S5-D10-TRUNG-ACADEMIC-PROTOTYPE'
$env:AIT3040_DEMO_MAX_VESSELS = '5'
$env:AIT3040_MAX_CONCURRENCY = '1'
& 'C:\Users\MSI\Desktop\PROJECT_AIT3040\.venv\Scripts\python.exe' -B -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Frontend, terminal PowerShell thứ hai:

```powershell
Set-Location 'C:\Users\MSI\Documents\Codex\2026-11-20\files-pasted-by-the-user-sprint-2\work\s5-integration-final\frontend'
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Mở `http://127.0.0.1:5173/`, chọn **S5 nhiều tàu**, tạo phiên, SEEK đến 00:09 hoặc 00:15, chọn A–B và bấm **Dự báo cặp tàu** khi PAUSED. Frontend trong worktree dùng junction `node_modules` trỏ tới dependencies có sẵn của worktree S4; không cài dependency mới. Hai tiến trình demo đã được khởi chạy trong phiên làm việc hiện tại.

## Giới hạn và bước tiếp theo

- Một active S5 session mỗi backend process, CPU là thiết bị nghiệm thu, evaluation tại PAUSED anchor và supplemental transport DTO là phương án hiện tại; trạng thái phê duyệt của các giới hạn này không được giả định. Reload trang có thể làm mất tham chiếu phiên đang hoạt động ở frontend trong khi backend vẫn giữ phiên đó; khởi động lại backend nếu cần phiên sạch.
- Team interface approval của Toàn: **PENDING**. Real AIS chưa được kiểm chứng tại bước này. Forecast liên tục khi PLAYING và risk/alert panel đầy đủ thuộc phạm vi tiếp theo.
- S5-05 có nền tảng kỹ thuật để tiếp tục trong phạm vi prototype, còn phụ thuộc quyết định/phối hợp về interface của Toàn; không đồng nghĩa toàn bộ sản phẩm đã được nghiệm thu.
- Không training, calibration, benchmark T15, commit, push hay merge.
