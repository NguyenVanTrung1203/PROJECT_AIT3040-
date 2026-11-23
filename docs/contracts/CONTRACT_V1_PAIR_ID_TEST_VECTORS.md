# Pair ID: bằng chứng và vector tham khảo

**APPROVED_DESIGN:** NFC; sort UTF-8 bytes; compact JSON UTF-8, không ASCII-escape Unicode thông thường, escape JSON chuẩn; SHA-256 hex thường, prefix `pair:v1:`. Pair không phụ thuộc thứ tự truyền. Online A là canonical ID nhỏ hơn theo bytes, B là ID còn lại; origin EN lấy tàu A tại t0−9. Offline A/B giữ index tensor đã khóa.

**IMPLEMENTED_REFERENCE:** `scripts/contract_identity_reference.py` và `scripts/verify_feature_contract.py::proposed_pair_id` là helper kiểm chứng, không phải registry identity hoặc Encounter runtime. Bộ reference chấp nhận registry namespace được truyền vào để test; registry production, xác minh MMSI và độ ổn định source chưa có. Tests Python/JavaScript dùng UTF-8 byte sort và đối chiếu vector.

| Hai ID (đảo input cho cùng kết quả) | Compact JSON | Pair ID |
|---|---|---|
| `physical_mmsi:000000001`, `physical_mmsi:000000002` | `["physical_mmsi:000000001","physical_mmsi:000000002"]` | `pair:v1:5edcd44d2d37a0ada2de37283483f76bbddc8bb9c5bb22b8992b7f7297cf5c18` |
| `simulated:demo:a`, `simulated:demo:b` | `["simulated:demo:a","simulated:demo:b"]` | `pair:v1:4ca3f457062383c8d067fb89c9f86a50786bd3fe71dfb9447a25616ee0edc7ff` |

Các vector bổ sung: `simulated:demo:e\u0301` và `simulated:demo:z` sau NFC cho pair `pair:v1:f57e47b39cc80588b6c15944c4b7984a6ef771e7e69f55557a5f95c4125e7062`; ID chứa dấu nháy, backslash, newline `simulated:demo:quote"\\\n` và `simulated:demo:x` cho `pair:v1:0f72689d24c015c483ca890c7225b93204c1b132ac977445da2bbaac02da61f3`. Đây chỉ là fixture test, không khẳng định identity có thật hay ổn định ngoài dữ liệu test. Vector cũ `simulated:a`/`simulated:b` là legacy, không hợp lệ theo profile production V1.

Encounter vector: session `123e4567-e89b-12d3-a456-426614174000`, pair đầu bảng và anchor `2025-10-01T12:00:00Z` cho `enc:v1:044186cd64489fb72600d1aeb385509204ee6bee4d3a5b7b5c660d845d868529`. Từ chối anchor có phần giây lẻ. UUID production phải lowercase canonical; wire anchor `Z` đúng precision giây. Reference cũng chuẩn hóa input `+00:00` sang `Z` trước hash, nhưng schema wire yêu cầu `Z`. Không tạo ID từ filename/row nếu chưa chứng minh ổn định.

Vector kiểm tra khác biệt sort UTF-16/UTF-8: `simulated:demo:\uE000` và `simulated:demo:\U00010000` cho `pair:v1:a4526e482e99b25de4d79d8bf925f6307f62f8102b33fed845be21b164b2bbb2`; JavaScript reference dùng `Buffer.compare`, không dùng default `.sort()` trên chuỗi.
