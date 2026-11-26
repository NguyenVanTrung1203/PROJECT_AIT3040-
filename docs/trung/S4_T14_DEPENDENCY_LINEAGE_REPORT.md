# S4 T14 C03 — Audit dependency lineage Validation

## Nguồn và phương pháp

Audit metadata-only `scripts/audit_s4_t14_lineage.py`; không mở Test tensors/labels/predictions, không load Validation trajectory tensor để suy luận. Dataset lock version `final_dataset_1.0`/READY_AND_LOCKED; checksum manifest SHA `21f6bde168631928e98b6273aaab4e168bfb6eb755599a1fbc1cb8c364611441`. Xác thực hash các file dùng: `manifests/dependency_groups.parquet`, encounter index và encounter metadata Validation, parent mapping và source windows Validation. Không khẳng định đã hash toàn bộ dataset ở lượt này.

Dependency manifest SHA `f0702ca49f289ec2a2ec9169e1b5632dcaf330fc634b027a7b11cf89d60ce2ea`: 835 encounter, 260 group, largest 556, còn lại 279; không trùng encounter, không thiếu group, tập ID khớp index. Source windows 1.190 dòng = 590 Real + 600 synthetic-parent. Dataset constructor `dataset_dependencies.py` dùng connected components theo MMSI vật lý trong split, Yang tách episode; tái dựng graph từ source windows cho ra mapping chính xác từng ID và partition, bao gồm group lớn nhất. Không tự sửa manifest, thêm singleton hay loại encounter.

## Parent, source và MMSI

`validation_parent_mapping.csv` có 300 final synthetic ID khác nhau, 300 original synthetic ID và 300 parent source-local ID khác nhau. Join với 600 synthetic source-window rows: **600/600** khớp final encounter → original synthetic → parent ID, parent source group; mỗi encounter có hai window. Parent IDs `KAT_*` thuộc namespace nguồn, không phải `VAL_*` final ID; 0/300 khớp trực tiếp final ID không phải lỗi. 150 parent `selected_295` map 1:1 tới original ID của 150 final Real; 150 `unselected_candidates` không nằm trong 295 final Real, vẫn có source windows upstream. Không nối hai namespace chỉ bằng chuỗi gần giống.

300/300 parent và nhóm nguồn khớp `AIS_SYNTHETIC_VALIDATION_V2/data/encounter_metadata.csv`, SHA `bd1622643fc36a73a21b3cc986814bbcd44a13a71b5c2232f699538505e75b06`, khớp run manifest upstream. 600/600 window khớp các trường parent ID/MMSI/track và thời gian với upstream `validation_parent_windows_v2.csv`, SHA quan sát `4220ea18363b4f4016e7efaac56a9dd6134bcd194d203fc70f442cb858e59cac`; 600/600 cặp MMSI/track cũng khớp metadata synthetic có hash. Mọi MMSI source-window là 9 chữ số ASCII; 1.190/1.190 dòng khớp `physical_mmsi:<MMSI>` trong vessel index. 480 vessel Yang Lei dùng namespace legacy `simulated_mmsi`, không mặc định hợp lệ G11 production. Đây là tính nhất quán nội bộ/provenance metadata, không chứng minh quyền sở hữu MMSI ngoài đời.

Upstream synthetic window file hiện có source identity và nội dung khớp bản source windows đã khóa của dataset, nhưng chưa tìm thấy hash độc lập của chính file đó trong run manifest. Cần bằng chứng nguồn/manifest gốc hoặc xác nhận phạm vi chấp nhận để khép provenance của file upstream; không mặc định nó đã được khóa trước khi so sánh. Quan hệ parent ngoài 295 final có thể hợp lệ theo namespace nguồn, nhưng chưa xác minh toàn bộ source record gốc độc lập. Không có mismatch membership đã quan sát.

## P5-M01–M10

| ID | Kết quả và evidence |
| --- | --- |
| M01–M05 | PASS: 835, group không rỗng, uniqueness và ID/index khớp; manifest được kiểm hash |
| M06 | PASS trên fixture assignment; assignment thực để kiểm group isolation thuộc STEP_03 |
| M07 | PARTIAL: 600/600 parent mapping/windows khớp; cần nguồn hash độc lập cho upstream windows và provenance record ngoài 295 |
| M08 | PARTIAL: 1.190 MMSI đúng định dạng, 600/600 synthetic MMSI/track khớp metadata; ownership/source thực không được xác thực |
| M09 | PASS trong phạm vi tái dựng group từ locked source-window MMSI: partition và label group khớp; completeness nguồn phụ thuộc M07/M08 |
| M10 | PASS: dataset version/READY_AND_LOCKED, manifest SHA và checksummed metadata |

`DEPENDENCY_LINEAGE_PARTIAL`: parent-reference **600 matched về mapping nội bộ**, **0 unmatched trong phép join**; 600 vẫn nằm trong phạm vi cần xác nhận provenance source độc lập, không được gọi là 600 mismatch. Không tự phê duyệt ngoại lệ cho D3/D4 hoặc lock.

## Addendum Q2 — acceptance không thay đổi evidence

Trung chấp nhận dependency grouping **có điều kiện cho D3/D4 exploratory offline**. Internal consistency và partition reproduction PASS trên bằng chứng đã audit; independent upstream provenance vẫn PARTIAL, real-world MMSI ownership NOT_VERIFIED, production provenance NO. Q2 không miễn hash/identity/duplicate/group integrity check hoặc mismatch mới; không thay nhóm/dataset. Quan sát upstream hash không được gọi là historical locked hash.
