# Hợp đồng tọa độ — bản đề xuất 1.0.0

Trạng thái: chờ Trung và Toàn review; chưa phải API production. Nguồn trực tiếp: `DATASET_FINAL/schemas/coordinate_conventions.md`, `scripts/verify_dataset_final.py` và `scripts/prepare_dataset_splits.py`. Dữ liệu Real AIS được gắn `geographical_WGS84`; Yang Lei dùng LAT/LON mô phỏng và Synthetic AIS có tọa độ tổng hợp. Không coi tọa độ mô phỏng là vị trí tàu thật.

## Bốn biểu diễn

Với `(lat0, lon0)` là vị trí **tàu A tại mốc history đầu t0−9** của encounter, theo độ; `(lat, lon)` cũng theo thứ tự latitude, longitude:

```text
E_nm = (lon − lon0) × 60 × cos(lat0 × π / 180)
N_nm = (lat − lat0) × 60
lat = lat0 + N_nm / 60
lon = lon0 + E_nm / (60 × cos(lat0 × π / 180))
```

Đây là phép xấp xỉ phẳng theo độ có hệ số cos cố định tại vĩ độ tham chiếu, không phải UTM, phép chiếu ENU ellipsoid hay khoảng cách haversine. Source tensor không dùng bán kính Trái Đất hoặc bước đổi mét; `60` là hệ số nm/độ. Khi cần đổi đơn vị, 1 nm = 1.852 m. Quy trình tạo Synthetic AIS và các phép tính khoảng cách geodesic khác không đồng nghĩa với phép biểu diễn tensor này.

Common EN có gốc chung theo encounter; trục theo thứ tự `[East, North]`, đơn vị nm. Với từng tàu, `own_relative = common_EN − own_anchor` và `common_EN = own_relative + own_anchor`. Future displacement `Y(k) = future_common_EN(k) − own_anchor` là vị trí tương đối anchor, không phải sai phân từng phút. M5a cộng residual với CV trong đơn vị vật lý, cộng anchor riêng một lần, rồi áp dụng phép chiếu động học trên common EN.

## Chuyển ngược và giới hạn

Để xuất LAT/LON cần `(lat0,lon0)`, loại nguồn/tọa độ, đơn vị và anchor riêng A/B. Output cặp tọa độ theo thứ tự `[latitude, longitude]`; không dựa vào frontend để suy diễn thứ tự. Chỉ dùng nghịch đảo khi gốc và ánh xạ địa lý đã được xác minh, giá trị hữu hạn, không gần cực (`abs(cos(lat0)) > 1e-12`) và miền kinh độ không vắt qua antimeridian theo quy ước chưa xử lý wrap. Thiếu thông tin hoặc phép nghịch đảo không ổn định thì `forecast_lat_lon=null` kèm trạng thái không khả dụng. Tọa độ mô phỏng chỉ trả như tọa độ mô phỏng nếu có ánh xạ hợp lệ, không đánh dấu là AIS thực. Dataset này không chứng minh độ chính xác địa lý toàn cầu của phép xấp xỉ.

## Kiểm chứng

Dung sai định trước cho phép tính float64: round-trip LAT/LON `1e-10 độ`, so sánh anchor gốc `1e-10 nm`, và so sánh X float32 với phép dựng lại `1e-6 nm`; so sánh vận tốc float32 `1e-5 kn`. Các dung sai kiểm tra số học tại miền dữ liệu, không phải sai số địa lý thật. Test dùng dữ liệu giả độc lập và toàn bộ history Train/Validation, không ghi tensor mới. Kết quả đo được lưu trong `results/s1_t02/feature_contract_verification.json`.

## Thông tin cần phối hợp

Đề nghị Toàn review và cung cấp vessel ID/MMSI, anchor UTC, timestamp lưới, timestamp bản tin nguồn, LAT/LON, SOG/COG, chất lượng history và trạng thái stale/missing. Trung dự kiến cung cấp pair ID, vai trò A/B, forecast timestamps, LAT/LON khi có ánh xạ hợp lệ, availability, active model và data status. Pair ID và encounter ID là hai định danh khác nhau; quy tắc replay chỉ là đề xuất và chưa được Toàn chấp nhận.
