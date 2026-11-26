# S4 T14 — Conditional Technical Model Lock Review

## 1–3. Tóm tắt, state và approval

`MODEL_LOCK_REVIEW_PASS`; `STEP04_MODEL_LOCK_REVIEW_ACCEPTANCE=PASS`; `READY_FOR_FINAL_LOCK_APPROVAL=YES`; `READY_FOR_CONDITIONAL_TECHNICAL_LOCK=YES_PENDING_FINAL_APPROVAL` trong phạm vi prototype offline. Đây chỉ là review/preparation. `FINAL_MODEL_LOCK_APPROVAL=NOT_GRANTED`, current config state `CANDIDATE`, `MODEL_LOCK=NO`, `TEST_BENCHMARK_AUTHORIZED=NO`, `PRODUCTION_APPROVED=NO`. Không có active lock manifest hoặc locked package được tạo.

D1–D7 7/7, P1–P7 7/7, Q1–Q4 4/4 và R1–R5 5/5 được Trung phê duyệt; tổng 23/23. R1 giữ M5a epoch 1/CV/V4/projection và thresholds; R2 chấp nhận D3 infeasible; R3 chấp nhận D4 evidence limited; R4 loại V1 khỏi primary T14/T15 do compatibility chưa đủ; R5 chỉ cho phép review/preparation, không duyệt lock cuối. Decision register lưu scope và approvals, không sửa semantic protocol snapshot.

## 4. Evidence chain và Git

Worktree `trung-contract-v1-freeze`, branch `s3-t10-trung-full-training`, HEAD và remote `4457fc2d4f485d2da832b039e8edc1cdf5837551`. Contract V1 `99bdb2649f5aec39d67a6f64645bce4f7fc49a3d` là ancestor; Contract và `configs/risk_config.yaml` không đổi. Thay đổi S4 chưa commit được giữ lại.

| Evidence | Kiểm chứng thực tế | Kết quả |
| --- | --- | --- |
| Dataset | `final_dataset_1.0`, checksum manifest `21f6bde168631928e98b6273aaab4e168bfb6eb755599a1fbc1cb8c364611441` | 93/93 PASS |
| Dataset lock | SHA `036d9c0e3652e526613238b91151002cbca35615552eba687b588da01b0fe764` | PASS |
| Dependency manifest | SHA `f0702ca49f289ec2a2ec9169e1b5632dcaf330fc634b027a7b11cf89d60ce2ea` | PASS; Q2 CONDITIONAL |
| T10 model artifacts | Manifest SHA `5f0af2eb5a4e418026b775fa412e2fc8bbc803c7438123038a1c519e5a082eb2` | 12/12 PASS |
| Batch 01/02/03 | SHA parent links, output checksums, effective source/config | 8/8, 9/9, 15/15 PASS; 8/8 Batch 03 source hashes PASS |
| D5 CPU/CUDA references | Cả hai device manifests và outputs, linkage, identity | CPU 8/8, CUDA 8/8; referenced D5 1/1 PASS |
| Protocol | Semantic SHA `23d427ea6416104efbc9e988aaaa6c774118a517aea528b1ecb0c8350de4bf0b`; raw file SHA trong inventory | PASS; semantic và raw hash phân biệt |
| Risk V4 | Original/package SHA `8e33effb06d7f2e1fe855b1cb067fb2d27eb3aba9498e2af30be1b387534be7e` | Byte-identical; full Validation exact parity 122745/122745 |

D5 được đối chiếu lại với forecast device và Batch 01 CUDA reference đã lưu; không rerun inference/bootstrap. Test bytes chỉ hash Q1; không deserialize Test, không Test inference. Guard giám sát process/call path, không bảo đảm mọi native/subprocess I/O.

## 5–6. D1/D2 acceptance

| Metric | CV | M5a | Requirement |
| --- | ---: | ---: | --- |
| Threshold (grid index) | 0.435 (87) | 0.420 (84) | `k/200`; comparator `>=` |
| Recall | 403/425 | 406/425 | ≥0.90 |
| Real AIS FPR | 31/295 | 30/295 | ≤0.12 |
| Synthetic recall | 281/300 | 283/300 | ≥0.90 |
| Close-positive recall | 58/60 | 58/60 | ≥0.95 |
| F1 | 0.911765 | 0.917514 | Exact Fraction tie-break |
| Severe QC | 0 | 0 | 0 |

CV/M5a D1 PASS; 201 candidates mỗi model, 23/25 feasible. Selected candidates được kiểm lại từ saved grids bằng Fraction và tie-break F1 tối đa, Real FPR tối thiểu, recall tối đa, threshold tối thiểu; không recalibrate. D2 PASS: recall Δ +0.007059, Real FPR Δ −0.003390, F1 Δ +0.005749, overall ADE ratio 1.084467, Real ADE ratio 1.053204, 0 new close misses. Cùng miss `VAL_SYN_0171`, `VAL_SYN_0270`. Đây là in-sample engineering acceptance, không phải statistical non-inferiority hoặc independent evaluation.

## 7–10. D3/D4/D5 và V1

D3 `GROUPED_CV_INFEASIBLE`: 260 groups, largest 556/835 chứa 56/60 close; complement 4 < P3 minimum 10; 32 attempts mỗi K 5,4,3,2; OOF 0/835. R2 chấp nhận limitation offline, không đổi evidence thành PASS.

D4 `D4_EVIDENCE_LIMITED`: L1/L2 mỗi phần 5000 attempts, seed 20261124, cùng paired plan, 0 errors. L1 Real FPR 3370 và close recall 3152 valid-support <4750, qualified CI unavailable. L2 both feasible 3137; D2 pass/fail/blocked/conditional 1565/1572/1863/0; 1397 repetitions có new close miss failure; median CV/M5a 0.435/0.420. S2 279 có 23 Real negatives và 4 close; AUC/AP delta đổi dấu S2/S3. R3 chấp nhận scope offline, không claim superiority hay absolute stability.

D5 PASS trên 835 Validation encounters: max coordinate 3.300808803252675e−5 nm ≤5e−5; aggregate ADE/FDE differences 8.064425682796639e−9 / 1.0513774906240059e−7 nm ≤1e−6; max Risk Score difference 1.493624194515153e−5 ≤5e−5; decisions 835/835, 0 vessels vượt, severe 0, semantic exact. Fresh CUDA forecast/score/decision exact với Batch 01; CV dùng deterministic CPU path. D5 không bảo đảm parity với mọi future runtime input.

V1 `V1_BASELINE_REVIEW_REQUIRED`; R4 chấp nhận không dùng V1 trong primary T14/T15. Không chạy V1, không claim M5a vượt V1, không trộn historical metrics với current protocol.

## 11–13. Proposed package và môi trường

Tên đề xuất `m5a-cc-dri-offline-candidate-v1.0`; inventory là `PROPOSED_NOT_LOCKED`, activation false. Model: Residual-GRU 1 layer, input 4, hidden 48, head 48→96→30, 15390 trainable parameters, `[B,10,4]` → residual `[B,15,2]`, final CV plus residual và projection, epoch 1, training seed 20261110. Model float32, projection float64.

Checkpoint SHA `e01a19e913d14a068c6c82a1c2a52a8be2aadd2f44e3ad5d8770d7f69a1fc7bc`; X scaler `a538be921104ed1bb2fa495c0c3f527c0385fd6c737aa69afda81ba1962d452a`; residual scaler `96b062fab9a5d4e27c9b1cc32a649e44e98d29648c7dcc3b7f482eba3d50358f`. Risk score `0.68 × Predicted-CPA + 0.12 × Current-CPA + 0.20 × Rule`; rule là proxy, không chứng nhận tuân thủ đầy đủ COLREGs; CC-DRI không phải calibrated collision probability.

Inventory xác định 31 source/config references (bao gồm transitive imports), 16 Contract references, 13 T10 artifact references (12 files + checksum manifest), cùng SHA/purpose/scope/Git status/dependencies. `M5aInference.verify_artifacts` hiện yêu cầu **tất cả 12 file** trong manifest hiện diện và hợp lệ trước model load; inventory chỉ tham chiếu, không copy dataset/checkpoint/predictions. Nếu package tương lai không cung cấp đủ references cần thay đổi verifier bằng phê duyệt và kiểm thử riêng, tạo identity mới; không sửa verifier trong review này. Source closure đã kiểm static imports/path và import thành công trong môi trường hiện tại; relocation và clean-environment build chưa được verify. Runtime T18/T19 không có trong closure được chứng nhận offline.

Observed Python 3.12.3, NumPy 2.4.4, PyTorch 2.11.0+cu128/CUDA 12.8, pandas 3.0.3, joblib 1.5.3, scikit-learn 1.8.0, pyarrow 26.0.1, NVIDIA GeForce RTX 4050 Laptop GPU; 25 observed distributions khớp và `pip check` PASS. Auto ưu tiên CUDA hoạt động rồi CPU; explicit CUDA thiếu thiết bị thì error. Clean environment `NOT_VERIFIED`, bắt buộc trước integration handoff; wheel hashes chưa thu, manifest không là production lockfile.

## 14–15. Limitations và D6 checklist

Bảng 12 limitations, tác động, phê duyệt và blocking theo phase nằm tại `S4_T14_APPROVED_LIMITATIONS.md`. Q2 grouping là CONDITIONAL, provenance PARTIAL, MMSI ownership NOT_VERIFIED; Q4 chỉ áp dụng observed offline environment. Validation reuse, D3 infeasibility, D4 support/stability, trajectory ADE/FDE cao hơn CV, V1, clean environment, runtime integration, reused Test và production safety đều còn hiệu lực.

D6: (1) integrity PASS; (2) D1 CV/M5a PASS; (3) D2 PASS; (4) D3 limitation accepted R2; (5) D4 limitation accepted R3; (6) D5 PASS; (7) V1 limitation accepted R4; (8) P6 PASS; (9) Q2 conditional retained; (10) Q4 scope retained; (11) D7 policy approved; (12) regression evidence reused; (13) Contract unchanged; (14) risk config unchanged; (15) identities/thresholds verified; (16) review-only inventory complete within observed offline scope; (17) no unresolved correctness/integrity blocker in review scope; **(18) final lock approval NOT_GRANTED**. Điều kiện 18 vẫn cần Trung quyết định riêng, và mọi hashes cần verify lại ngay trước lock.

## 16–17. D7 plan và regression

`S4_T15_BENCHMARK_PLAN.md` đã chuẩn bị, chưa authorize. Expected Test scope theo metadata: 1320 encounters (Yang 720, Real 300, Synthetic 300); `REUSED_DEVELOPMENT_BENCHMARK`, không phải independent external validation. Chỉ sau lock thực tế được duyệt và protocol T15 cố định mới cân nhắc authorize Test; không recalibration/model selection trên Test. Production cần independent dataset, reliable real positive/negative labels, expert/runtime/safety review.

Full regression evidence **được reuse**, không rerun: Batch 03 report ghi 511 passed, 0 failed/skipped/deselected, một StarletteDeprecationWarning, 74.54 giây, Q1 guard. Bằng chứng là report và source hashes verified; không có machine-readable pytest log trong Batch 03 run artifacts, nên không tuyên bố có log riêng. STEP_04 chỉ tạo/sửa documentation và review-only JSON, không đổi executable source. Test Q1 guard khi verify lại: 14 Test file opens cho checksum, 0 blocked deserialization/other opens. `pip check` và offline imports PASS.

## 18–20. Blockers và bước tiếp

Actual correctness/integrity blockers: không phát hiện trong phạm vi offline review. R2/R3/R4/Q2/Q4 là approved limitations, không phải evidence PASS hoặc production waiver. Các nguồn worktree còn uncommitted; Git HEAD, actual source hashes, future commit và proposed package identity là các khái niệm riêng. Inventory hashes phản ánh trạng thái hiện tại, không phải chữ ký số hoặc proof of immutability.

**Pending:** final lock approval của Trung. Chỉ sau phê duyệt riêng và revalidation mới có thể thực hiện bước lock sau này; không tự promote model, tạo active lock manifest, authorize T15, commit hoặc push.
