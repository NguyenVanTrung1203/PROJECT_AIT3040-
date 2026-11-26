# T16 Benchmark Review

**Date:** 2026-11-25
**Branch:** `Trinh_Toan`
**Status:** `PASS` for the reproducible data/API fixture harness; `NOT_IMPLEMENTED` for model inference performance.

## Run configuration and evidence

Command from repository root:

```powershell
.venv\Scripts\python.exe scripts/t13_data_benchmark.py --iterations 30 --warmups 3 --output evaluation/s4_t16/t13_benchmark_rerun.json
```

The harness performs 3 unreported warm-up requests, then 30 measured calls for each operation. It builds the in-memory Replay Fixture API, uses 10 fixture events and returns one track with 10 history points. It measures `GET /api/v1/replay/sessions/{id}/tracks` and the corresponding track detail call using in-process FastAPI `TestClient`; there is no socket/network, real AIS scan, model invocation, or GPU work. Any non-success response fails the run. Full machine-readable output is in [`t13_benchmark_rerun.json`](t13_benchmark_rerun.json).

| Environment / metric | Observed |
|---|---|
| OS reported by Python | `Windows-10-10.0.19045-SP0` |
| Python | 3.13.7 |
| Hardware model / RAM | Not captured; CIM query returned Access Denied |
| API timing unit | milliseconds per TestClient request |
| List tracks | median 11.713 ms; p95 13.292 ms |
| Track detail | median 7.220 ms; p95 7.903 ms |
| Errors / failed API calls | 0; run status `PASS` |
| Full integrity + mapping + benchmark run | 5.241 s |

The harness computes median with `statistics.median`. Its p95 is the sorted observation at index `int((n-1)*0.95)` (index 27 of 30), without interpolation; retain this implementation detail when comparing runs.

## Comparison with committed T13 run

The previously recorded T13 run used the same 30 iterations/3 warm-ups and fixture. The latest single rerun is in the same latency range:

| Operation | Previous median / p95 (ms) | T16 rerun median / p95 (ms) | Median change |
|---|---:|---:|---:|
| List tracks | 12.148 / 13.981 | 11.713 / 13.292 | −3.6% |
| Track detail | 7.448 / 9.319 | 7.220 / 7.903 | −3.1% |

One repeat is not enough to characterize run-to-run variance or establish a service-level benchmark. The observed p95, especially detail, varies more than its median. These are fixture-only API-handler timings and **not** production throughput, network latency, AIS ingest throughput, or model inference latency. No model-quality comparison, M5a/CV evaluation, threshold tuning, or Test calibration was performed.

## T16 assessment

- `BENCHMARK_HARNESS`: `PASS` for deterministic fixture setup, bounded repetitions, API success checks and JSON evidence.
- `DATASET_INDEX_AUDIT`: `PASS`; 93/93 locked artifacts and index mapping were revalidated by the same command.
- `MODEL_INFERENCE_BENCHMARK`: `NOT_IMPLEMENTED`; there is no model inference call in this repository path, and no approved common protocol/results from Trung were available.
- `PRODUCTION_THROUGHPUT_CLAIM`: `BLOCKED` by scope; this harness intentionally does not measure a production deployment.
