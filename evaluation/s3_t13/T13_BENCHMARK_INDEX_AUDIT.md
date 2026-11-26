# T13 Benchmark Harness & Index Audit

**Status: PASS for locked-data mapping audit and fixture runtime harness.**
No model training, inference, tuning, Test quality scoring, or calibration was performed.

## DATASET_FINAL v1.0 index evidence

The read-only run of `scripts/t13_data_benchmark.py` invoked `src.data.tensor_verification.verify()` and a second mapping audit. The lock says `READY_AND_LOCKED`; the checksum manifest SHA-256 was `21f6bde168631928e98b6273aaab4e168bfb6eb755599a1fbc1cb8c364611441`, and all **93/93** listed artifacts matched.

| Split | Encounters | Official A/B vessel rows | Data rows | Source mapping as stored in official manifest |
|---|---:|---:|---:|---|
| Train | 1,440 | 2,880 | 72,000 | `yang_lei`: 1,440 |
| Validation | 835 | 1,670 | 41,750 | `yanglei`: 240; `real_ais_kattegat_v3`: 295; `augmented_real_ais_kattegat_v3`: 300 |
| Test | 1,320 | 2,640 | 66,000 | `yang_lei`: 720; `real_ais_denmark_oct2025`: 300; `synthetic_ais_denmark_oct2025`: 300 |
| **Total** | **3,595** | **7,190** | **179,750** | |

For each split, loader validation and the T13 audit passed: unique encounter index, complete and unique `X_row`, exactly one tensor row for official vessel A and B, each pair linked to its encounter, label agreement across tensor/index/metadata/split manifest, split IDs matching manifest, and global encounter-index rows matching labels and split. Source names are preserved exactly as stored. The prior T03 audited lock maps the validation `augmented_real_ais_kattegat_v3` alias to the normalized `synthetic_ais` source count; no source field or split was changed.

Checksums, dtypes/shapes, UTC grids and finite/reconstruction checks for Train/Validation also passed through the existing verifier. Test received only integrity, shape, dtype and index checks. The verifier did not perform model evaluation or fit scalers.

## Reproducible data/runtime benchmark

Command:

```powershell
.venv\Scripts\python.exe scripts/t13_data_benchmark.py --iterations 30 --warmups 3
```

Recorded environment: Python 3.13.7, Windows 10. Output is in [`t13_benchmark_results.json`](t13_benchmark_results.json). The script reports timings and index counts, uses the deterministic ten-event synthetic Replay fixture, and does not load a model.

| Fixture API operation | Median | p95 | Iterations |
|---|---:|---:|---:|
| List tracks | 12.148 ms | 13.981 ms | 30 (after 3 warmups) |
| Get TrackSnapshot | 7.448 ms | 9.319 ms | 30 (after 3 warmups) |

These are in-process FastAPI TestClient measurements on one fixture vessel, not production/network or real-AIS throughput benchmarks. Model metrics and Test calibration are `NOT_RUN`.

## Integrity

The script opens source files read-only, uses NumPy memory maps for tensor arrays, and emits only a JSON report. The locked checksum audit passed. DATASET_FINAL split, labels, tensors, source mapping and parent mapping were not edited.
