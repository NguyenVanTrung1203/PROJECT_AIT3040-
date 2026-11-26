# S4 T14 — Final Conditional Technical Model Lock

## 1–3. Kết quả và phê duyệt

`CONDITIONAL_TECHNICAL_MODEL_LOCK=PASS`, `MODEL_LOCK=YES`, `T14_FINAL_ACCEPTANCE=PASS`, `T14_COMPLETED=YES` trong phạm vi `OFFLINE_PROTOTYPE`. F1–F4 được Trung phê duyệt riêng trong yêu cầu task; tổng D1–D7/P1–P7/Q1–Q4/R1–R5/F1–F4 là 27/27. Approval provenance là cuộc trao đổi và hash request, không phải chữ ký số. F1 lock offline, F2 giữ đủ 12 T10 artifacts và T11 verifier, F3 giữ model/protocol/Contract, F4 hoàn tất T14 và dừng; Test/T15 và production không được authorize.

## 4. Pre-lock evidence

Trước update approval docs: proposed inventory 65/65 references khớp; raw protocol `e2d33ffbce7920f893779dddd7652fd79760808e85e63e0a4c24b0ccf5f24901`, semantic protocol `23d427ea6416104efbc9e988aaaa6c774118a517aea528b1ecb0c8350de4bf0b`, risk config `7da5db07fd634afe698efc95cb226b37eb7b93d9df27047230b85a0b16f00535`. Dataset 93/93, T10 artifacts 12/12, Batch 01/02/03 8/8, 9/9, 15/15, D5 CPU/CUDA 8/8 mỗi bên, parent/source/config linkage PASS. Contract V1 ancestor `99bdb2649f5aec39d67a6f64645bce4f7fc49a3d`, Contract/risk_config unchanged. HEAD và remote `4457fc2d4f485d2da832b039e8edc1cdf5837551`.

Review references đã được copy byte-identical vào snapshot trước khi ghi F1–F4; proposed inventory vẫn `PROPOSED_NOT_LOCKED`. `verification/review_reference_provenance.json` ghi trước và pre-activation; file `.review_doc_provenance.json` cạnh package ghi hashes sau completion. Parent experiment artifacts và protocol snapshot không sửa.

## 5–8. Model và package

M5a Residual-GRU, GRU 1 layer, input 4, hidden 48, head 48→96→30, 15390 parameters, input `[B,10,4]`, residual `[B,15,2]`, CV plus residual với projection; epoch 1, seed 20261110, model float32/projection float64. Checkpoint `e01a19e913d14a068c6c82a1c2a52a8be2aadd2f44e3ad5d8770d7f69a1fc7bc`, X scaler `a538be921104ed1bb2fa495c0c3f527c0385fd6c737aa69afda81ba1962d452a`, residual scaler `96b062fab9a5d4e27c9b1cc32a649e44e98d29648c7dcc3b7f482eba3d50358f`; T10 manifest `5f0af2eb5a4e418026b775fa412e2fc8bbc803c7438123038a1c519e5a082eb2`.

Package `m5a-cc-dri-offline-v1.0` nằm ngoài Git trong `C:\Users\MSI\Documents\Codex\2026-11-20\files-pasted-by-the-user-sprint-2\s4_t14_model_packages\m5a-cc-dri-offline-v1.0-20261125T133930Z`. `snapshot/` gồm source/config/Contract closure và đủ 12 T10 files: best_model.pt, x_scaler.json, residual_scaler.json, run_config.yaml, run_start.json, training_manifest.json, training_history.csv, training_history.jsonl, validation_metrics.json, validation_predictions.npz, environment.json, artifact_verification.json; cộng checksums.sha256. Không bundle raw dataset hay Test predictions.

Source và 13 artifact files snapshot byte-identical với inventory/source trước cập nhật. T11 `verify_artifacts` giữ nguyên, verified 12/12 từ package; `M5aInference` load checkpoint/scalers, eval mode và architecture 15390 PASS. Risk V4 original/package SHA `8e33effb06d7f2e1fe855b1cb067fb2d27eb3aba9498e2af30be1b387534be7e`, công thức 0.68 predicted CPA + 0.12 current CPA + 0.20 rule proxy; không claim calibrated probability hoặc COLREGs certification.

## 9–12. Package verification và operating points

Payload có 85 files, checksum identity `15980ed4f7255ddbdb943979df7dda320ac4ae448e24feb357fa51f3dd38dd79`. Verifier kiểm đúng tập file, hash và symlink, không chỉ tên folder. Package không self-contained: locked dataset và reference evidence ở bên ngoài, cùng observed dependencies; phải kiểm identity khi reuse. Từ cwd ngoài worktree, module `__file__` cho T11/offline validator/Risk adapter/release verifier/feature verifier đều trong snapshot; CPU model load 12/12 PASS. CUDA trusted Validation package smoke trên 835 encounters/1670 vessels, `allow_fallback=False`: forecast, current/predicted CPA, risk components, scores và fixed-threshold decisions exact với Batch 01; severe QC 0, fallback false. Đây là post-package verification, không recalibration/model selection.

Smoke phát `UserWarning` PyTorch vì anchor NumPy memory-map không writable khi tạo tensor; call path QC đã quan sát chỉ đọc, không sửa model/adapter. Cảnh báo và giới hạn cần được xét trong integration review; clean-environment build chưa verified.

CV threshold 0.435/k=87, M5a 0.420/k=84, comparator `>=`, không epsilon/rounding/override; nguồn Batch 02. `risk_config.yaml` và semantic protocol không được sửa.

Negative tests trên disposable copies từ chối missing T10 file, checkpoint/scaler/T10 manifest bị sửa, Risk source/model source/config bị sửa, draft inventory và package chưa activate. Sau activation, verifier từ chối bản sao có manifest/checkpoint/scaler/Risk/config bị sửa, file thừa, manifest pin sai; synthetic Test deserialization bị Q1 guard từ chối. Không sửa package gốc để test.

## 13–14. D1–D6 gates

D1 CV/M5a PASS; D2 PASS. CV recall 403/425, Real FPR 31/295, synthetic recall 281/300, close 58/60; M5a 406/425, 30/295, 283/300, 58/60; severe QC 0. D2 recall/FPR/F1 Δ +0.007059/−0.003390/+0.005749, overall/Real ADE ratio 1.084467/1.053204, 0 new close misses.

D3 `GROUPED_CV_INFEASIBLE`: largest 556/835 giữ 56/60 close, ngoài chỉ 4 <10; OOF 0/835; R2 accepted. D4 `D4_EVIDENCE_LIMITED`: L1/L2 5000; Real FPR qualified 3370, close recall 3152; L2 both feasible 3137, D2 pass/fail/blocked 1565/1572/1863 và 1397 new-close-miss failures; R3 accepted. D5 PASS: coordinate max 3.300808803e−5 nm, ADE/FDE diff 8.064425683e−9/1.051377491e−7 nm, score max 1.493624195e−5, 835/835 decisions, 0 severe, semantic exact. V1 `V1_BASELINE_REVIEW_REQUIRED`, R4 accepted.

D6 24 checks: dataset/model/parent/device integrity PASS; CV/M5a D1 and D2 PASS; D3/D4 limitations accepted R2/R3; D5 PASS; V1 accepted R4; P6 exact parity PASS; Q2/Q4 and D7 scope retained; Contract/risk_config unchanged; full regression PASS; 12-artifact package, source/config identity, loading and exact smoke PASS; Test metadata boundary retained with executable T15 gate NOT_IMPLEMENTED; F1–F4 granted. Approved limitations remain and do not become evidence PASS.

## 15–17. Active manifest, release state và Test boundary

Actual `model_lock_manifest.json` được công bố sau staging, package validation, negative tests và regression. Manifest SHA `257e77a3a5ae2b2175926145cc0d3c483ccacdaf80f3479d9c352d69f8f6dcdc`; lock ID `offline-t14-15980ed4f7255ddbdb943979`. `package_payload.json` hash là package identity; detached checksum và external pin không là chữ ký số. `verify_active` yêu cầu external expected manifest SHA, kiểm state/approval, exact thresholds, payload inventory và toàn bộ file hashes; sau publish đã verify độc lập từ snapshot. Nếu thiếu/đổi/thêm file hoặc đổi pin, lock validation fail closed.

Release lifecycle ghi `CANDIDATE → CALIBRATED_CANDIDATE → CONDITIONAL_TECHNICAL_LOCK` trong release-specific manifest; runtime ModelStatus/Contract schema không bị đổi. Frozen protocol snapshot vẫn là historical CANDIDATE, semantic/raw hashes giữ nguyên. Manifest `model_lock=true`, `lock_scope=OFFLINE_PROTOTYPE`, `test_benchmark_authorized=false`, `production_approved=false`, runtime integration false.

Không có active T15 runner/authorization validator được triển khai trong task này: `T15_EXECUTABLE_AUTHORIZATION_ENFORCEMENT=NOT_IMPLEMENTED`. Lock verifier không là sandbox cho raw V4 helper hoặc T11 API. Phải implement/verify explicit T15 authorization gate trước Test content access. T15 không được authorize, không Test inference/benchmark, không production.

## 18–20. Regression, limitations và T14

Targeted integrity/T11 tests 41/41 PASS. Full regression 531 passed, 0 failed/skipped/deselected, một StarletteDeprecationWarning, 72.52 giây; console log và JUnit XML nằm dưới package `verification/`. Chạy ngoài sandbox do backend TestClient từng treo trong sandbox; Q1 guard: 42 Test raw-byte hash opens, 0 blocked deserialization/other opens. Standalone pre-lock/activation guard cũng chỉ hash Test; guard không bảo đảm mọi native/subprocess I/O.

Giữ 12 limitations trong `S4_T14_APPROVED_LIMITATIONS.md`: Validation reuse, group imbalance/D3, D4 limited support/stability, M5a ADE/FDE cao hơn CV, provenance/MMSI chưa độc lập, V1, clean environment, T18/T19, reused Test và production safety. 25 observed dependency versions khớp, pip check PASS; clean environment NOT_VERIFIED, bắt buộc trước integration handoff. Không claim statistical superiority, independent evaluation hoặc maritime safety.

## 21–24. T15, handoff và Git

`T15_READY_FOR_AUTHORIZATION_REVIEW=YES`, `T15_AUTHORIZED=NO`, `TEST_BENCHMARK_AUTHORIZED=NO`, `TEST_BENCHMARK_PERFORMED=NO`. Test metadata dự kiến 1320 encounters chỉ từ documentation; không mở Test để đánh giá. Integration handoff cần clean-environment rebuild, trusted runtime adapter và T18/T19 verification; production cần dữ liệu độc lập và expert/operational review.

Files mới: release verifier `src/release/`, targeted tests, package và sidecar pins/evidence ngoài Git, guide và báo cáo này. Cập nhật decision register, acceptance matrix, traceability và T15 plan; review snapshots trước F được giữ. Các thay đổi S4 vẫn chưa commit; không push, merge, rebase, reset hoặc tag. Evidence Git HEAD là historical source anchor, không phải commit mới hay chữ ký package.
