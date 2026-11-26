# S4 T15 — Benchmark plan, review only

**T15_PLAN_PREPARED=YES; T15_AUTHORIZED=NO; TEST_BENCHMARK_AUTHORIZED=NO; TEST_BENCHMARK_PERFORMED=NO.** Đây là kế hoạch, không phải execution authorization hoặc lock manifest.

Theo dataset documentation và locked manifest, scope dự kiến gồm 1.320 encounters: Yang Lei 720, Real AIS 300, Synthetic AIS 300. Đây là metadata dự kiến, chưa được xác nhận bằng cách deserialize Test. Classification: `REUSED_DEVELOPMENT_BENCHMARK`; Test đã được dùng trong development trước, không phải independent external validation.

Chỉ sau conditional technical lock có phê duyệt cuối riêng của Trung, xác minh active lock manifest và version, fixed checkpoint/scalers/source/thresholds, dataset lock và protocol T15 cố định trước khi mở Test. Khi được authorize, chạy CV và M5a với Risk V4, projection/QC, mapping và comparator đã khóa; giữ M5a threshold 0.420 và CV 0.435. Báo confusion counts, recall/FPR/F1/precision, ROC-AUC, average precision, ADE/FDE, source/subgroup support, close-positive missed IDs, severe QC, CPU/GPU latency và technical failures; thiếu metric bắt buộc ghi NA/PARTIAL/INCONCLUSIVE theo D7. Áp fixed D1/D2 và taxonomy benchmark được duyệt.

Không recalibrate thresholds, retrain, chọn checkpoint/model, thay weights/gates hoặc chọn rerun theo Test. V1 không là primary comparison theo R4. Kết quả T15 không tự authorize production.

Trước production cần independent dataset mới không overlap encounter, parent hoặc dependency groups với development; khác thời gian hoặc vùng phù hợp; có Real AIS positive/negative đáng tin cậy; expert review, false-alarm/missed-detection analysis, runtime integration verification và operational safety review. Không triển khai dataset mới trong review này.

## Sau T14 lock — vẫn chờ authorization

T14 đã có conditional offline technical lock `offline-t14-15980ed4f7255ddbdb943979`. `AWAITING_EXPLICIT_T15_AUTHORIZATION`: T15/test benchmark vẫn NOT_AUTHORIZED; executable T15 authorization gate chưa triển khai và phải được implement/verify trước bất kỳ Test content access nào. Lock không authorize production hoặc runtime deployment.
