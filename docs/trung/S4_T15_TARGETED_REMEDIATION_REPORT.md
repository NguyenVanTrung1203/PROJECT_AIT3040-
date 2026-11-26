# T15 targeted remediation — trạng thái bị chặn

## Kết luận

`T15_REMEDIATION_ACCEPTANCE=BLOCKED`; `READY_FOR_TECHNICAL_RERUN=NO`. Bộ kiểm thử mục tiêu sau thay đổi có 40 passed và 2 failed. Theo điều kiện dừng của yêu cầu, không chạy full regression hoặc technical benchmark rerun, không đọc thêm semantic content của Test. Đây không phải kết quả chất lượng mô hình.

## Phê duyệt và lịch sử

Trung phê duyệt T15-R1–R5. Failed run `s4_t15_20261125T141930Z_d5db93d9`, protocol gốc SHA-256 `fc5fa50bcb797311c02506e08c0ff72af77404e918de576d438689744344c063` và authorization gốc được giữ nguyên. Test đã được đọc sau gate lần đầu lúc 2026-11-25T14:23:08.578213+00:00. Không hoàn tất inference, risk scoring hoặc benchmark trong run đó. Correction record độc lập ghi hash các bằng chứng lịch sử và sửa cách diễn giải trạng thái `NOT_YET`.

## Source mapping và provenance

Mã tích hợp Test và tài liệu schema xác nhận các raw ID `yang_lei`, `real_ais_denmark_oct2025`, `synthetic_ais_denmark_oct2025` tương ứng Yang Lei, Real AIS và Synthetic AIS. Registry mới sử dụng exact match và không đổi tên địa lý. Adapter đã bắt đầu sử dụng các nhánh Test riêng bên ngoài package; chưa được nghiệm thu do kiểm thử thất bại.

Yang Lei dùng simulation timeline; AIS source timestamp không áp dụng theo thiết kế. Mã tạo Real AIS sao chép timestamp bản tin nguồn và kiểm tra tuổi 0–60 giây. Mã Synthetic AIS phân biệt timestamp gốc của parent và timestamp sau time shift, với kiểm tra tuổi trên simulated timeline. Các nhận định này là evidence về thiết kế; **chưa kiểm tra toàn bộ metadata Test thực tế**, nên không kết luận provenance runtime đạt. Không có metadata-audit access mới.

## Access audit

Đã sửa orchestration để phân biệt attempt, observed và loader failure bằng sự kiện durable; kết quả kiểm thử tổng thể chưa PASS. Không ghi đè `run_status.json` lịch sử. Audit guard ở mức Python không phải OS sandbox.

## Kiểm thử và integrity

Lần chạy đầu của các test liên quan: 42 passed trước khi chỉnh adapter. Sau chỉnh adapter: 40 passed, 2 failed. Hai lỗi là `test_source_adaptation_changes_only_size_constants` còn kỳ vọng tên code cũ và `test_adapted_history_validates_synthetic_and_rejects_wrong_ab` có fixture dùng source Validation. Chưa xác nhận sửa lỗi và chưa chạy full regression mới. Evidence 563 passed trước Test của run cũ không thể dùng làm regression cho source đã thay đổi.

Active lock verifier chạy lại PASS, package identity `15980ed4f7255ddbdb943979df7dda320ac4ae448e24feb357fa51f3dd38dd79`. Dataset 93/93 là kết quả gate lịch sử, chưa xác minh lại trong remediation. Protocol revision và authorization mới chưa được tạo; chưa có gate mới, Test rerun, prediction, score hay metric. Threshold, locked package và dataset không được cố ý thay đổi. Không có commit hoặc push.

## Bước tiếp theo

Trung review hai lỗi test và phần adapter chưa hoàn tất. Sau khi xử lý theo chỉ đạo tiếp theo, cần kiểm tra provenance thực tế trong metadata-only authorization riêng, hoàn thiện protocol/authorization revision và chạy toàn bộ regression theo Q1 trước khi xét technical rerun. Không thay model, threshold, risk engine hoặc các acceptance gate.


## Bổ sung ngày 25-11-2026: tiếp tục remediation

Hai test thất bại đã được cập nhật: test adapter kiểm chứng T11 source SHA và mapping Test, thay kỳ vọng tên code cũ; fixture Synthetic AIS dùng raw source Test, timestamps parent/simulated riêng, đồng thời giữ kiểm tra A/B và bổ sung các trường hợp thiếu, future, stale và Validation alias. Targeted: 92 passed. Full Q1: 589 passed, 0 failed/skipped/deselected; 42 raw hash opens, không deserialize Test.

Metadata-only authorization riêng đã được gate trước đọc history: 26.400 rows, 1.320 encounter; Yang Lei 720, Real AIS 300, Synthetic AIS 300. Source age Real 0–55 s và Synthetic 0–60 s, không vi phạm; synthetic parent và simulated timeline khớp shift được ghi. Không dùng quyền metadata để dự báo.

Revision R1 sửa mapping; run R1 qua inference/scoring nhưng lỗi do nhóm difficulty chứa null. Đã giữ output, sửa riêng cách biểu diễn nhóm thiếu, tạo R2 và chạy lại các kiểm thử trước retry. Revision R2 SHA-256 `606bf33104c88bb0feac4ce24ef0b95f1efc7966fa5d479d3ec5cd7296c8a735`. Không đổi thresholds hoặc quality gates.

Run R2 hoàn thành dự báo/scoring. Audit loader ghi attempt/observed; tuy nhiên event đọc future ở evaluation được ghi trước lệnh đọc và không có state observed. Run hoàn tất và kết quả phụ thuộc future là bằng chứng suy luận read đã thành công, nhưng log không ghi timestamp observed trực tiếp. Vì vậy audit toàn bộ access chưa thể xác nhận đầy đủ; cần xử lý riêng trước khi tuyên bố execution acceptance PASS.
