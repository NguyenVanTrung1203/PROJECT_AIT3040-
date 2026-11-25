# T08 AIS Source Validation

**Source inspected:** external cleaned-AIS partitions at `maritime-ais-system/data/processed/ais_cleaned` (repository-relative sibling path; no personal machine path embedded).
**Result:** `SOURCE_VALIDATION: CONDITIONAL`.

## Inventory evidence

- 30 daily Parquet files cover 2024-11-01 through 2024-11-30.
- All 30 files have the same Arrow schema; total row count is **237,960,745** across **2,394** row groups. The source-side full-month validation report records all 30 partitions as PASS with no issues and COMPLETE manifest status.
- Source-side cleaning summary: 237,960,745 records; 237,960,745 marked `flag_core_valid`; zero invalid MMSI, invalid timestamp, off-date, or invalid-position rows. It also reports 493,364 invalid SOG, 40,712,302 invalid COG, and 120,139,582 invalid heading flags. These are source pipeline summary counts; a row may carry more than one flag.
- The month’s trajectory manifest reports COMPLETE, 19,659,725 points and 217,203 trajectories. It records 4,144 duplicate extra rows and 7 conflicting duplicate groups. Its trajectory de-duplication is not reused as T08 policy because it keeps a canonical row for a conflict rather than excluding the full group.
- Spatial processing metadata lists bbox `[-96.5, 28.5, -94.0, 30.5]`; this indicates a Houston-area AIS collection. It is not used as identity evidence.

## Schema and mapping

Every partition inspected has `mmsi` string; `timestamp_utc` Arrow `timestamp[ns, tz=UTC]`; `latitude`, `longitude`, `sog`, `cog` nullable doubles; boolean QC flags; `source_file` string; and `source_row` int64. Additional columns include heading, vessel dimensions/type, and other flags. The T08 loader requires MMSI/time/position/motion, the applicable quality flags, and source provenance. It rejects timestamps that are not explicitly stored as Arrow UTC.

The source cleaner maps `base_date_time` using `pandas.to_datetime(..., format="%Y-%m-%d %H:%M:%S", utc=True, errors="coerce")`. The input is parsed with no timezone marker and `utc=True` assigns UTC. This proves the transformation performed by the pipeline, but the inspected source documentation does not independently establish the original feed’s timezone. Therefore this dataset cannot yet be asserted to represent known UTC solely from the Parquet type. Contract V1 forbids assuming UTC without that evidence.

`source_file` and 1-based `source_row` are retained by the cleaner for audit back to raw CSV. The source manifest/cleaning inventory associates daily files and sizes; stable ordering is derived as `source_file` ascending UTF-8 bytes, then `source_row` ascending. This is deterministic for the present cleaned source layout. It does not establish that basenames/row numbers are durable identities across regenerated source releases.

The source validation script describes its duplicate count as repeated MMSI/timestamp rows, not necessarily identical payloads. The trajectory reconstruction ranks records using availability of SOG/COG/heading and then source file/row; it flags conflict based on differing latitude/longitude and retains a canonical record. Contract V1 instead requires identical duplicates stable-first and conflicting groups excluded. The loader follows the V1 outcome, but equality fields latitude/longitude/SOG/COG remain provisional pending source-owner/contract confirmation. This is why source/duplicate status stays CONDITIONAL.

## Runtime smoke and integrity

Actual command (relative source path):

```powershell
python -m src.data.replay_cli --source-root ..\maritime-ais-system\data\processed\ais_cleaned --start 2024-11-01T00:00:00Z --end 2024-11-01T00:00:15Z --mmsi 338443451 --max-events 5 --batch-size 1024
```

Observed: exit code 0; 388,705 rows read from 4 row groups, 75 of 79 row groups pruned; one event accepted/emitted; zero QC rejections, duplicates, or missing partitions. Event timestamp was `2024-11-01T00:00:01Z`, with source file `ais-2024-11-01.tgz` and source row 1. The window was `[00:00:00Z, 00:00:15Z)`.

Read-only integrity evidence:

| File | SHA-256 | Size |
|---|---|---:|
| Day 01 cleaned Parquet sample | `3f42bd1a5b594d346de209914f982784bc2dd49c103a61e3009e564b1ff0302d` | 259,690,923 bytes |
| `DATASET_FINAL/DATASET_LOCK_MANIFEST.json` | `036d9c0e3652e526613238b91151002cbca35615552eba687b588da01b0fe764` | 5,518 bytes |

The CLI and regression run did not write to either protected tree. SHA-256 hashes of both listed files were identical immediately before and after the actual-source smoke and regression run. The selected source hash is a sample integrity check, not a full-month re-hash.

## Required follow-up evidence

1. Source owner documentation confirming the timezone semantics of raw `base_date_time` before treating it as known UTC.
2. Contract/source-owner decision naming the complete duplicate equality field set and whether it applies to the entire AIS source.
3. Stable source-release/provenance rules if identity or ordering must survive re-export or source regeneration.

No data source or `DATASET_FINAL` file was modified. `DATASET_FINAL` is not used as a replay substitute.
