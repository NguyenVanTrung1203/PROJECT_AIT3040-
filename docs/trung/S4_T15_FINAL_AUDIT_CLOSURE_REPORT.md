# T15 final audit closure — bị chặn

## Kết luận

`T15_EXECUTION_ACCEPTANCE=BLOCKED`, `T15_COMPLETED=NO`. Ngoài sự kiện đọc future bị thiếu observed trong R2, audit lịch sử còn ghi `SEMANTIC_ACCESS_OBSERVED` cho tensor đầu vào ngay sau thao tác tạo memory map. Theo yêu cầu hiện tại, thao tác đó không chứng minh trực tiếp các giá trị đã được đọc. Evaluation-only replay không thể tạo lại observed event lịch sử cho inference, và yêu cầu không cho chạy lại inference hoặc hạ yêu cầu audit lịch sử.

## Bằng chứng R2

Run `s4_t15_r2_20261125T152141Z_2cd800cd` có manifest SHA-256 `8ba0913490dd8f56fc5f445e43e16dbb7a254a9dd4818861db1d0ecdbf160a15`. Kiểm tra lại 29/29 checksum của run và 5/5 checksum supplement thành công. Forecast CV/M5a có shape `[1320,2,15,2]`, đủ 1.320 encounter mỗi model; score có 1.320 record mỗi model. Đã đối chiếu identity, timestamp, frame, A/B, source, QC, score và threshold. Evidence R2 được bảo toàn.

`DatasetLoader.load_split` dùng `np.load(..., mmap_mode='r')`. Wrapper trong `t15_trusted_test.py` ghi observed ngay khi `np.load` trả về. Ví dụ event của `test/tensors/X_unscaled.npy` lúc `2026-11-25T15:25:16.013672+00:00` chứng minh memory map được tạo, không phải timestamp trực tiếp của semantic value access. Event của `anchor_positions_EN_nm.npy` có cùng giới hạn. Validator sau đó thực hiện kiểm tra giá trị và inference/scoring đã tạo artifact; đây là evidence về call path và kết quả, không phải observed event trực tiếp cho lần đọc memory-mapped values.

R2 future read cũng chỉ có event trước read; direct observed timestamp lịch sử không có. Không sửa log hoặc status lịch sử, không suy ra observed timestamp từ output hay file modification time.

## Phạm vi đã thực hiện

Active model lock verifier PASS với package identity `15980ed4f7255ddbdb943979df7dda320ac4ae448e24feb357fa51f3dd38dd79`. Kiểm tra dataset raw-byte 93/93 PASS; guard ghi 14 hash opens, không Test deserialization. R2 protocol SHA-256 không đổi `606bf33104c88bb0feac4ce24ef0b95f1efc7966fa5d479d3ec5cd7296c8a735`.

Đã tạo implementation dự thảo cho evaluation-only replay và kiểm thử synthetic ban đầu: 17 passed. Implementation chưa được nghiệm thu, chưa có full regression cho source mới và không được dùng làm evidence closure. Chưa tạo authorization replay hoặc đọc thêm labels/future thật. Không chạy lại CV/M5a inference hoặc Risk Engine. Forecast và score R2 có thể đọc về mặt cấu trúc và checksum, nhưng chưa đủ điều kiện chứng nhận composite audit theo yêu cầu.

## Trạng thái và bước tiếp theo

`EVALUATION_ONLY_REPLAY_FEASIBLE=NO` cho mục tiêu đóng audit theo các ràng buộc hiện tại; `COMPOSITE_EVIDENCE_ACCEPTANCE=BLOCKED`. Kết quả lịch sử `BENCHMARK_FAIL` không đổi, model lock vẫn giữ; không có production hoặc runtime approval. Không commit/push.

Trung cần quyết định cách xử lý yêu cầu observed trực tiếp cho memory-mapped inference input. Evaluation-only replay có thể xử lý observed event của future cho một lần đọc mới, nhưng tự nó không khắc phục event lịch sử của inference. Không tự chạy lại toàn bộ benchmark hoặc sửa lịch sử.
