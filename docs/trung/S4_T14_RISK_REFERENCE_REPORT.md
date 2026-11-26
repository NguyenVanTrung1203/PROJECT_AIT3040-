# S4 T14 — Risk reference V4 packaging audit

## Provenance và quyền

Reference `MODEL_CANDIDATE_PACKAGE/inference/risk_pipeline.py` có SHA-256 `8e33effb06d7f2e1fe855b1cb067fb2d27eb3aba9498e2af30be1b387534be7e`, khớp T10/S3 reference. Không tìm thấy giấy phép trong package; Trung trực tiếp xác nhận quyền sử dụng và phân phối source vào repository trong lượt làm việc này. File được sao chép byte-identical tại `src/risk/reference_v4/risk_pipeline.py`, packaged SHA giống original, không có import adaptation hay sửa thuật toán. Scan tên secret/path thông dụng không có kết quả; không coi scan là chứng nhận an ninh đầy đủ.

## Dependency và boundary

Source top-level imports: stdlib pathlib/json, numpy, pandas, joblib, torch; các hàm score/CPA/rule dùng numpy; offline adapter dùng DatasetLoader, T11, T06 projection/QC. Versions quan sát: Python 3.12.3, NumPy 2.4.4, pandas 3.0.3, PyTorch 2.11.0+cu128, joblib 1.5.3, scikit-learn 1.8.0. Manifest `configs/risk_reference_manifest.yaml` ghi version quan sát, không phải lockfile đầy đủ của toàn bộ transitive environment; cần khóa và kiểm chứng dependency closure trước coi là deployment package.

Raw V4 file có helper `history_features` hỗ trợ cả Test và không phải trusted boundary. Không gọi helper đó trong STEP_02; không dùng raw reference làm production API. `src/risk/adapter.py` có runtime fail-closed; `evaluate_validation` dự kiến tự dùng loader/validator và M5a T11, CV T06, gọi cùng reference cho cả hai, trả score diagnostic không decision. Hàm full Validation này chưa được chạy trong STEP_02 theo yêu cầu; cần audit input provenance, failure/QC, exact parity toàn Validation tại STEP_03 trước calibration. Python cùng tiến trình không là security sandbox.

## Parity và portability

Fixture tests đối chiếu original và packaged cùng environment cho CPA, roles, rule, các component và score bằng `array_equal`, so sánh quyết định tại các threshold fixture, kiểm tra near-zero và malformed input. Portable subprocess import chỉ dùng repository/installed dependencies, bỏ biến reference path, không di chuyển/xóa original. Đây là fixture evidence, không chứng minh hết mọi case invalid/NaN/QC, và chưa có full Validation packaging parity. Test access và production approval không được suy ra từ việc import được raw reference.

## Trạng thái

`RISK_REFERENCE_PACKAGED=YES`; source hash PASS, permission confirmed. Fixture parity có phạm vi nêu trên; `RISK_REFERENCE_READY_FOR_STEP03=NO` cho đến khi hoàn tất kiểm chứng dependency closure, adapter failure/QC và fixture coverage yêu cầu P6. Full Validation parity luôn là first gate của STEP_03, không phải bằng chứng đã thực hiện ở bước này. Không thay CC-DRI, CPA, threshold comparator hay Contract V1.

## Addendum C04

Source integrity/rights giữ nguyên. Xem `S4_T14_RISK_ADAPTER_VERIFICATION_REPORT.md` và dependency manifest observed environment. Đã bổ sung synthetic adapter failure/QC, scoring từ cwd độc lập và kiểm tra hash trước import; clean environment và full Validation parity chưa được xác minh. Trạng thái fixture evidence cụ thể được ghi theo test, không tự nâng lên production certification.

## Addendum Q4 — acceptance offline

Q4 do Trung duyệt cho phép đánh giá P6 trong môi trường offline đã kiểm chứng; 25 installed distributions khớp manifest hiện tại, Python 3.12.3, torch 2.11.0+cu128/CUDA 12.8 khả dụng, `pip check` PASS. Clean-environment installation vẫn NOT_VERIFIED và phải làm trước integration handoff. Raw V4 byte-identical không được gọi như public trusted API, đặc biệt helper `history_features` có nhánh Test; Python cùng process không là sandbox.

Synthetic tests so CPA/role/rule/components/score/decision exact và adapter reject invalid; full T11 trusted-boundary regression theo Q1 bổ sung evidence thực. Full original/package Validation Risk parity, forecast/score completeness và severe QC là first gate STEP_03; không coi kết quả regression T11 là đã chạy các gate đó. Offline acceptance không phê duyệt T18/T19 hoặc production.
