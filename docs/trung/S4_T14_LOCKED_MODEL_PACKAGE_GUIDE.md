# S4 T14 — Hướng dẫn package offline đã khóa có điều kiện

Package: `C:\Users\MSI\Documents\Codex\2026-11-20\files-pasted-by-the-user-sprint-2\s4_t14_model_packages\m5a-cc-dri-offline-v1.0-20261125T133930Z`.

Lock ID `offline-t14-15980ed4f7255ddbdb943979`; manifest SHA-256 được pin `257e77a3a5ae2b2175926145cc0d3c483ccacdaf80f3479d9c352d69f8f6dcdc`; payload SHA-256 `15980ed4f7255ddbdb943979df7dda320ac4ae448e24feb357fa51f3dd38dd79`. Manifest là release lifecycle state riêng; `configs/s4_calibration_protocol.yaml` vẫn là snapshot CANDIDATE lịch sử và không được sửa để phản ánh active state.

Trước khi dùng, xác minh active lock bằng `src.release.offline_lock.verify_active(package_root, expected_manifest_sha256)` từ `snapshot/`, với SHA được cung cấp qua kênh pin độc lập. Verifier từ chối manifest/payload sai, file bị thêm hoặc thiếu, threshold/state không khớp và quyền Test/production không hợp lệ. Detached checksum hoặc external pin không phải chữ ký số. Bất kỳ chỉnh sửa trong package làm verification fail; đặt outputs bên ngoài package và đặt `PYTHONDONTWRITEBYTECODE=1`.

T10 artifacts nằm tại `snapshot/artifacts/checkpoints/s3_t10_20261124_seed20261110_run01/`; giữ đủ 12 file và `checksums.sha256`. Dùng T11 `M5aInference(artifact_path, device='cpu'|'cuda'|'auto')` và trusted `predict_validation(dataset_root, batch_size=128, allow_fallback=False)` cho offline Validation; không gắn VERIFIED cho tensor tùy ý. Dataset `final_dataset_1.0` là external reference bắt buộc, không nằm trong package. Auto ưu tiên CUDA hoạt động rồi CPU; explicit CUDA thiếu thiết bị phải báo lỗi.

Operating points: CV `0.435` (k=87), M5a `0.420` (k=84), comparator `score >= threshold`, không epsilon/rounding. CC-DRI là risk score, không phải calibrated collision probability; Rule là proxy, không phải chứng nhận COLREGs. Không override threshold hoặc bypass verifier.

Full Validation smoke đã tạo 835 encounters/1670 vessels và exact forecast/Risk/decision parity trên CUDA trong observed environment; `verification/package_smoke.log`, `verification/full_regression_final.log` và `.xml` là bằng chứng. Source imports sau relocation đã xác minh từ `snapshot/`; package vẫn cần locked dataset, reference artifacts và Python dependencies bên ngoài, nên không self-contained. Clean environment NOT_VERIFIED và bắt buộc trước integration handoff.

**T15 chưa được authorize.** Không có executable T15 authorization gate; phải implement và verify explicit gate trước Test content access. Release verifier không phải sandbox tổng quát cho raw V4 helper hay API. Không production approval, không runtime T18/T19 deployment; xem Approved Limitations Register và final report.
