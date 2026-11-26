# S3 T11 — M5a inference và xác minh đầu vào ngoại tuyến

## Phạm vi và baseline

Worktree `trung-contract-v1-freeze`, branch `s3-t10-trung-full-training`, HEAD `f3096fd2d44471ce7bbf455932cd7c3d5634f692`. Các thay đổi T10 và diagnostic trước đó được giữ nguyên. Contract V1 không thay đổi; không commit, push hoặc merge.

M5a epoch 1 là ứng viên kỹ thuật, không phải model production đã phê duyệt. Không huấn luyện lại, thay checkpoint hoặc fit scaler. Model 15.390 tham số; checkpoint SHA-256 `e01a19e913d14a068c6c82a1c2a52a8be2aadd2f44e3ad5d8770d7f69a1fc7bc`; input scaler `a538be921104ed1bb2fa495c0c3f527c0385fd6c737aa69afda81ba1962d452a`; residual scaler `96b062fab9a5d4e27c9b1cc32a649e44e98d29648c7dcc3b7f482eba3d50358f`. Manifest T10 được ghim và 12/12 artifact kiểm tra trước khi nạp; model/projection config và checkpoint được đối chiếu.

## Trusted input boundary

`M5aInference.predict_validation(dataset_root, batch_size=128)` tự mở DatasetLoader, xác minh dataset version và SHA-256 manifest đã khóa `21f6bde168631928e98b6273aaab4e168bfb6eb755599a1fbc1cb8c364611441`, kiểm tra 93/93 checksum rồi tự đọc Validation. Hàm không nhận tensor, đối tượng Verified, provenance boolean hoặc kết quả validator từ caller. `predict` từ chối mọi runtime object cho đến khi T18 có adapter đã kiểm chứng.

Adapter đối chiếu 835 encounter/1.670 vessel với index, hai vai trò A/B, identity, source, anchor và 16.700 dòng history. Nó kiểm tra đúng 10 phút UTC t−9…t0, không có future, số hữu hạn, SOG/COG, source, frame và thứ tự feature. History EN và velocity được tái tạo từ LAT/LON/SOG/COG history rồi đối chiếu X/anchor. Xếp cặp theo index ngoại tuyến, không sort lại identity.

Real AIS: 5.900 dòng history có original source timestamp và source track, tuổi nguồn từ 0 đến 60 giây. Synthetic AIS: 6.000 dòng có simulated source timestamp và original provenance; as-of dùng simulated source timestamp, không so timestamp original chưa time-shift với replay clock. Yang Lei: 4.800 dòng dùng timestamp mô phỏng; không có và không tạo AIS source timestamp. Không có ingest timestamp trong các trường dataset này. Identity được xác minh về tính nhất quán với index và dữ liệu đã khóa, không chứng minh quyền sở hữu MMSI ngoài đời. Một số ID Yang Lei là legacy offline và không mặc định hợp lệ G11 production.

Không dùng label hoặc future target để dựng batch hay xác minh history. DatasetLoader hiện memory-map các tensor target/label khi mở Validation, nhưng adapter không đọc giá trị đó vào model; mutation test xác minh validator không phụ thuộc target/label. Hash toàn vẹn có đọc byte các file Test, không load hoặc benchmark Test tensors. Kiểm tra source gắn với bản ghi đã khóa, không chứng minh độc lập sự tồn tại của bản tin gốc ngoài tập dữ liệu.

Ranh giới tin cậy là code adapter, manifest ghim và filesystem được kiểm soát trong cùng tiến trình; đây không phải sandbox chống caller có quyền thực thi Python tùy ý, monkeypatch code hoặc sửa đồng thời filesystem. Không dùng boolean/class/private field làm chứng cứ provenance. `_predict_test_only` là đường fixture riêng, trả `TEST_ONLY_UNVERIFIED`; nó không phải API production. Tensor core nội bộ cũng không tự gắn trạng thái VALID. Không dùng kết quả test-only để quyết định alert hoặc coi là nguồn đã xác minh.

## Pipeline, fallback và thiết bị

`auto` ưu tiên CUDA hoạt động; `cpu` dùng CPU; `cuda` bắt buộc CUDA. Pipeline tái sử dụng model/scaler/CV/projection T06, model float32, tọa độ/projection float64; eval và inference mode. Output gồm common EN, displacement, thời gian +1…+15, mapping A/B, QC và metadata; không tự sinh LAT/LON hay alert.

Mọi lỗi manifest, identity, timestamp, source, frame hoặc feature dừng trước model và không fallback. Chỉ sau khi adapter ngoại tuyến xác minh thành công, lỗi kỹ thuật model/nonfinite/severe QC mới xét CV; CV cũng qua projection và QC. Artifact lỗi fail-closed. Fallback theo batch và được đánh dấu rõ, không chọn threshold hay tạo quyết định risk/alert.

## Replay Validation và CPU/GPU

Chạy cùng checkpoint/scaler/config, batch 128 encounter (256 vessel), PyTorch 2.11.0+cu128, CUDA 12.8, RTX 4050. Đã xử lý đủ 835/835 encounter, không loại mẫu; 1.670 lượt tàu; QC severe CPU/GPU đều 0. Dự báo CUDA khớp chính xác prediction T10: max diff `0` nm.

| Chênh lệch CPU/GPU | Giá trị |
| --- | ---: |
| Max absolute position | 3.300808803252675e-5 nm |
| Mean / P95 / P99 | 2.143955438867671e-6 / 7.197260856628418e-6 / 1.163043081760408e-5 nm |
| Số vessel vượt 5e-5 nm | 0 |
| ADE / FDE | 8.06442548850761e-9 / 1.0513768750053387e-7 nm |

Các ngưỡng 5e-5 vị trí và 1e-6 ADE/FDE là **ứng viên**, chưa được Trung phê duyệt. Semantic mapping và QC khớp trên dữ liệu và fixture đã chạy; không khẳng định cho mọi input.

## Tests và regression

Tests T11 bao gồm boolean/Verified giả, manifest sai, source/identity/A-B sai, timestamp tương lai/stale/thiếu, thiếu metadata, frame sai, target/label mutation và fallback chỉ sau validation; kiểm tra hash artifact và CPU/GPU. Regression `tests/unit tests/integration` đạt 338 test ở lần chạy trước các case T11 bổ sung cuối; tập T11 chạy lại sau thay đổi cuối đạt 36/36; hai tập có phần giao nhau. Backend 8/8, có một cảnh báo deprecation từ Starlette. `git diff --check` PASS; file mới untracked được kiểm tra trailing whitespace riêng.

## Handoff và nghiệm thu

T18 cần TrackSnapshot + G11, replay/session/version, canonical identity và pair hash, source/ingest timestamp khi có yêu cầu, as-of/stale, history coverage, chuyển đổi EN/anchor và causal provenance. Không có runtime adapter hợp lệ trong T11 này. Xem tài liệu bàn giao cùng thư mục.

MODEL_STATUS = CANDIDATE
MODEL_LOCK = NO
PRODUCTION_ALERT = NO
T10_RETRAINED = NO
T11_PARITY_APPROVED_BY_TRUNG = NO
T11_OFFLINE_INFERENCE_READY = YES, trong phạm vi dataset cố định và trust boundary nêu trên.
T11_CODE_COMPLETE = YES, trong phạm vi T11 offline được yêu cầu.
T11_READY_FOR_RUNTIME_INTEGRATION = DEPENDENT_ON_T18.
