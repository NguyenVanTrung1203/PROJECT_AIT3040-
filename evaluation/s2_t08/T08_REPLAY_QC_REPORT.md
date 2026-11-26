# S2_T08 Replay Loader and Runtime QC Report

**Date:** 2026-11-23
**Branch:** `Trinh_Toan`
**Scope:** bounded cleaned-AIS Parquet reader, UTC/QC, deterministic ordering, duplicate policy, JSONL CLI, and the TrackSnapshot adapter boundary.

## Result

`T08_STATUS: CONDITIONAL`. The loader and CLI are implemented and tested. Contract V1 structural plus G11 semantic validation is invoked when the production TrackSnapshot adapter emits a snapshot. Production readiness remains conditional on the source timezone and duplicate-equality decisions documented in the companion reports.

| Check | Result | Evidence |
|---|---|---|
| Contract V1 sync | PASS | Reads the repository schemas and `src/data/track_semantics.py`; production snapshots run `validate_production_track_g11` plus temporal checks. |
| Replay loader | PASS | Streaming Parquet batches, row-group pruning, external merge sort, bounded event cap, filters, provenance, and half-open UTC window. |
| UTC QC | PASS for stored Parquet and runtime input | Stored Arrow timestamps must have `tz=UTC`; CLI timestamps require an explicit known zero offset; naive, nonzero offset, and unknown `-00:00` are rejected. Raw-feed timezone evidence remains pending. |
| Duplicate policy | CONDITIONAL | Stable-first ordering uses source file and source row. Payload equality uses latitude/longitude/SOG/COG provisionally because Contract V1 leaves the equality set unresolved. Conflicting groups are excluded in full. |
| G11 boundary | PASS for this adapter | Snapshot adapter enforces identity/source semantics through G11 and additionally validates ten anchor-grid history points and as-of age 0–60 seconds. |
| Full regression | PASS | `290 passed, 0 failed`, one existing AnyIO/Pytest deprecation warning. Command: `.venv\Scripts\python.exe -m pytest tests/unit tests/integration backend/tests -q -p no:cacheprovider`. |
| Real-source CLI smoke | PASS | 15-second window, MMSI `338443451`, batch 1,024; 388,705 rows read from 4/79 row groups (75 pruned), one valid event emitted, zero rejected rows, complete partition coverage. |

## CLI

Run from the repository root. Use an explicit source path or set `AIS_REPLAY_ROOT`:

```powershell
$env:AIS_REPLAY_ROOT = "D:\path\to\ais_cleaned"
python -m src.data.replay_cli `
  --start 2024-11-01T00:00:00Z `
  --end 2024-11-02T00:00:00Z `
  --mmsi 338443451 `
  --batch-size 8192 `
  --max-events 10000 `
  --output .\replay-events.jsonl `
  --summary-file .\replay-qc.json
```

The end time is exclusive. `--mmsi` can be repeated. Output and temporary sort paths are rejected if they fall inside the source tree or `DATASET_FINAL`; existing output files are not overwritten. `max-events` caps emitted events, while the selected window is fully scanned so ordering and QC totals remain complete. Temporary sort files are deleted after completion.

### Observed smoke event

```json
{"cog_deg":14.7,"is_simulated":false,"latitude":41.69467,"longitude":-71.39008,"mmsi":"338443451","provenance":{"source_file":"ais-2024-11-01.tgz","source_row":1},"sog_kn":0.0,"source_type":"REAL_AIS","timestamp_utc":"2024-11-01T00:00:01Z","vessel_id":"physical_mmsi:338443451"}
```

QC summary for that run: accepted 1, written 1, rejected 0, conflicting duplicate groups 0, identical duplicate groups 0, missing partitions 0. The replay event is raw cleaned-AIS replay input and is separate from `DATASET_FINAL` training/validation/test encounters.

## Safety and limits

- AIS source partitions are only read; the CLI prevents writes to the source tree and `DATASET_FINAL`.
- No MODEL, Risk, Alert, or replay-session lifecycle was added. T09 owns persistent buffering/session controls.
- Null SOG/COG are rejected and never converted to zero. No interpolation is performed. `is_simulated=false` describes real AIS trajectory provenance.
- T08 does not add wire QC fields. QC details live in the CLI summary.
- `DATASET_FINAL` was not used as replay input. Its lock manifest SHA-256 and a sampled source partition SHA-256 are recorded in `T08_SOURCE_VALIDATION.md`.

## Changed files

- `src/data/ais_replay.py`
- `src/data/replay_cli.py`
- `tests/unit/test_ais_replay.py`
- `tests/integration/test_ais_replay_cli.py`
- `evaluation/s2_t08/T08_REPLAY_QC_REPORT.md`
- `evaluation/s2_t08/T08_SOURCE_VALIDATION.md`
- `evaluation/s2_t08/T08_IDENTITY_VALIDATION.md`

No Contract V1 or Trung-owned mock/model/risk code was modified by T08. Existing staged Contract V1 changes in the worktree were left untouched; no staging, commit, push, merge, or branch operation was performed.
