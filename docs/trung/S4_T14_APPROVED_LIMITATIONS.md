# S4 T14 — Approved limitations

Phạm vi chấp nhận là prototype offline; các giới hạn không trở thành evidence PASS. `Review` nghĩa là phải có quyết định/verification phù hợp, không mặc định được miễn. Final Model Lock approval và production approval chưa được cấp.

| ID | Giới hạn và bằng chứng | Tác động | Approval / phạm vi | Giảm thiểu hoặc yêu cầu tiếp theo | Offline technical lock | Integration handoff | Production |
| --- | --- | --- | --- | --- | --- | --- | --- |
| L01 | Validation dùng chọn epoch và threshold; Batch 02 | D1/D2 in-sample, không độc lập | D3/R1, offline | Evaluation độc lập mới | Không riêng lẻ | Review | Chặn đến independent evaluation |
| L02 | 260 groups, lớn nhất 556/835; Batch 03 | Không coi encounters là độc lập | Q2/R2/R3 offline | Dataset/dependency độc lập | Không riêng lẻ | Review nếu phụ thuộc grouping | Chặn đến evidence phù hợp |
| L03 | 56/60 close trong group lớn, còn 4; D3 | OOF 0/835, GROUPED_CV_INFEASIBLE | R2 offline | Grouped evaluation trên dataset phù hợp | Không riêng lẻ | Ghi nhận | Chặn đến evidence phù hợp |
| L04 | L1 Real FPR 3370/5000 và close recall 3152/5000 valid; CI có thể chứa 0 | D4_EVIDENCE_LIMITED, không đủ qualified CI hai metric | R3 offline | Thêm dữ liệu/đánh giá độc lập | Không riêng lẻ | Ghi nhận | Chặn đến evidence phù hợp |
| L05 | L2 both feasible 3137; D2 pass/fail/blocked 1565/1572/1863; new close miss failures 1397 | Threshold stability không tuyệt đối | R3 offline | Review failure cases và thêm independent evidence | Không riêng lẻ | Review | Chặn đến evidence phù hợp |
| L06 | M5a overall ADE/FDE cao hơn CV, Batch 02 | D2 margin đạt, không chứng minh trajectory tốt hơn | R1/R3 offline | Theo dõi trajectory metrics, independent review | Không riêng lẻ | Ghi nhận | Review an toàn/hiệu năng |
| L07 | Independent dependency provenance PARTIAL; MMSI ownership NOT_VERIFIED | Quan hệ phụ thuộc chưa quan sát có thể tồn tại | Q2/R2/R3 offline | Xác thực provenance khi cần, không claim ownership | Không riêng lẻ | Review theo use case | Chặn đến provenance phù hợp |
| L08 | V1 provenance/compatibility chưa đủ; recovery report | Không so M5a vượt V1 | R4/P7 offline | Không dùng V1 primary T14/T15; review nếu có evidence mới | Không riêng lẻ | Ghi nhận | Review theo claim |
| L09 | Clean environment chưa rebuild; observed closure và pip check PASS | Chưa chứng minh tái lập trong môi trường sạch | Q4/R5 offline | Clean rebuild, import và execution verification | Không riêng lẻ | Chặn trước handoff | Chặn |
| L10 | Runtime T18/T19, trusted replay/session/TrackSnapshot chưa nghiệm thu | Offline boundary không chứng nhận runtime | Q4/R5 offline | Trusted runtime adapter và integration verification | Không riêng lẻ | Chặn tới nghiệm thu | Chặn |
| L11 | Test đã dùng trong development trước; T15 chưa thực hiện | Test là reused development benchmark | D7/R5 | Chỉ benchmark sau lock được duyệt và T15 protocol cố định | Không riêng lẻ | Review | Không thay independent evaluation |
| L12 | Chưa có independent real-world positive/negative evidence và expert/operational validation | Chưa có kết luận an toàn thực tế | R5 offline; production không duyệt | Independent dataset, expert và operational safety review | Không riêng lẻ | Giới hạn controlled preparation | Chặn |

Evidence: `S4_T14_STEP03_BATCH01_REPORT.md`, `S4_T14_STEP03_BATCH02_REPORT.md`, `S4_T14_STEP03_BATCH03_REPORT.md`, dependency lineage, V1 recovery và observed environment closure. Các chấp thuận không miễn final model lock approval hoặc yêu cầu kiểm tra integrity trước lock.
