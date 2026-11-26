# Sprint 4 — Bàn giao T14/T15

## 1. Executive Summary

T14 hoàn tất calibration và conditional technical model lock cho offline prototype. T15 hoàn tất về kỹ thuật với full access audit và tái lập chính xác R2. Kết quả chất lượng là **BENCHMARK_FAIL**; Trung đã chấp nhận giới hạn này cho prototype thử nghiệm. Đây là reused development benchmark, không phải external validation độc lập hay chứng nhận an toàn. Không có production hoặc runtime deployment approval.

## 2. Completed Deliverables

- T14 protocol, source/reference Risk V4, calibration primitives, lineage và conditional release verifier tại `configs/`, `src/protocol/`, `src/release/`, `src/risk/` và scripts T14.
- T15 authorization, trusted Test adapter, source mapping, provenance và full technical rerun với audit tại `src/evaluation/`, scripts T15 và protocol R1–R3.
- Tests unit/integration và các báo cáo T14/T15 trong `tests/` và `docs/trung/`. Draft evaluation-only replay bị thay thế bởi full technical rerun; draft không phải bằng chứng nghiệm thu.

## 3. Improvements from Sprint 3

So với T10/T11 offline, Sprint 4 bổ sung calibration cố định trên Validation, Model Lock có verifier và payload identity, trusted Test orchestration có source/provenance checks, authorization gate, benchmark và durable application-level access audit. Full technical rerun phân biệt memory map và actual value materialization; kết quả forecast, risk, decision và metric tái lập chính xác R2. Python audit không phải OS sandbox.

## 4. Final Model Configuration

M5a Residual-GRU, 15.390 tham số, checkpoint epoch 1; history 10 bước, forecast 15 bước, CV cộng residual, model float32 và projection float64. Risk dùng CC-DRI V4: `0.68 × Predicted-CPA + 0.12 × Current-CPA + 0.20 × Rule`. Operating points offline: M5a 0,420 và CV 0,435, comparator `>=`. Đây không phải quyền phát alert runtime; `risk_config.yaml` frozen vẫn chứa trạng thái not-calibrated lịch sử và cần review authority khi tích hợp.

## 5. Final Benchmark Results

| Metric | CV | M5a |
| --- | ---: | ---: |
| ROC-AUC | 0,944774 | 0,946398 |
| Recall | 0,954074 | 0,960000 |
| F1 | 0,893204 | 0,893793 |
| Real AIS FPR | 0,136667 | 0,126667 |
| Close-positive Recall | 0,977778 | 0,977778 |
| ADE, nm | 0,132429 | 0,144276 |
| FDE, nm | 0,284690 | 0,292495 |

Technical acceptance PASS; BENCHMARK_FAIL. Cả CV và M5a D1 FAIL do Real AIS FPR > 0,12. D2 FAIL vì M5a D1 FAIL và Real AIS ADE ratio 1,136158 > 1,10. Cả hai cùng bỏ sót `TEST_SYNTH_0105`. Không thay threshold hay model theo Test.

## 6. Verification Evidence

Evidence lịch sử đã nghiệm thu, **không phải test mới chạy trong handoff**: 129 targeted và 626 full regression PASS; full access audit PASS; exact R2 reproduction; dataset checksum 93/93; final run artifacts 41/41. Full run `s4_t15_full_20261125T161605Z_f54829ac`; chi tiết và giới hạn ở `S4_T15_FULL_TECHNICAL_RERUN_REPORT.md`. Source identity của 22 file pin trong run manifest đã được đối chiếu lại cho handoff.

## 7. External Model Package Handoff

Package nằm **ngoài Git**, chưa có bằng chứng đã chuyển cho Toàn. Cần chuyển riêng toàn bộ package `m5a-cc-dri-offline-v1.0-20261125T133930Z` cùng external manifest pin `m5a-cc-dri-offline-v1.0-20261125T133930Z.manifest_pin.json` qua kênh nhóm thống nhất. Package bao gồm snapshot source/config và 12 T10 model artifacts cùng checksum manifest; không gửi dataset, prediction hay scaler riêng rẽ thay cho package đã pin.

- Lock ID: `offline-t14-15980ed4f7255ddbdb943979`
- Manifest SHA-256: `257e77a3a5ae2b2175926145cc0d3c483ccacdaf80f3479d9c352d69f8f6dcdc`
- Payload identity: `15980ed4f7255ddbdb943979df7dda320ac4ae448e24feb357fa51f3dd38dd79`
- Môi trường tham chiếu: Python 3.12.3, torch 2.11.0+cu128, CUDA 12.8; dependency trực tiếp tại `requirements.txt`, closure quan sát tại `configs/s4_t14_observed_dependency_closure.yaml`. Snapshot không chứa đầy đủ G11 runtime closure hoặc requirements; cần phân phối các phụ thuộc riêng có provenance.

Trên máy nhận, đặt biến `AIT3040_MODEL_PACKAGE` tới thư mục package **trên máy đó**, cài dependencies trong môi trường riêng, nhận expected manifest hash qua kênh tin cậy và chạy:

```powershell
$env:AIT3040_MODEL_PACKAGE = '<duong-dan-package-tren-may-nhan>'
python -I -B -c "import os,sys; from pathlib import Path; p=Path(os.environ['AIT3040_MODEL_PACKAGE']).resolve(); sys.path.insert(0,str(p/'snapshot')); from src.release.offline_lock import verify_active; m=verify_active(p,'257e77a3a5ae2b2175926145cc0d3c483ccacdaf80f3479d9c352d69f8f6dcdc'); print(m['lock_id'],m['package_identity'])"
```

`-B` ngăn Python ghi `__pycache__` vào immutable snapshot; `-I` cô lập Python path, lệnh chèn đúng snapshot. Đối chiếu kết quả với hai identity ở trên và external pin. Hash không phải chữ ký số. `M5aInference.predict` và Risk adapter runtime vẫn từ chối runtime input cho đến khi T18/T19 được triển khai và nghiệm thu.

## 8. Integration Dependencies and Conflicts

Review readiness gần nhất chưa tìm thấy handoff/assignment T16/T17 tại nhánh Toàn đã kiểm tra. Cần phối hợp session/version binding, candidate-pair provider, synthetic original timestamp provenance, replay retention và early AIS marker. Runtime threshold authority phải được thống nhất vì offline lock và frozen risk config có phạm vi/trạng thái khác nhau. Không giải quyết các blocker Sprint 5 trong bàn giao này.

## 9. Next Steps

Toàn nhận source Sprint 4 và xác nhận package qua kênh riêng; hai bên thống nhất integration dependencies và ownership. Trung review, phê duyệt implementation plan T18/T19 trước khi phát triển; bắt đầu bằng fixtures rồi mới nghiệm thu tích hợp replay. Không suy diễn prototype readiness thành production approval.
