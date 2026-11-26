# Real AIS Evidence Matrix

**Audit date:** 2026-11-25
**Source scope:** local NOAA MarineCadastre / NOAA OCM AIS daily CSV2 release, 2024-11-01.
**Rule:** a good sample does not by itself promote a conditional source-wide policy to PASS.

## Issue dispositions

| Issue | Classification | Evidence verified in this audit | Remaining gap / acceptance limit |
|---|---|---|---|
| NOAA product timestamp semantics | `VERIFIED_WITH_EVIDENCE` | NOAA MarineCadastre FAQ says the complete timestamp is added by the receiving base station using its UTC clock. NOAA InPort identifies Nationwide AIS 2024, its USCG receiver-network source, and links the NOAA CSV2 2024 index. | This evidence establishes the named NOAA product's field semantics. It does not alone prove that the local file bytes are an unmodified copy of the listed NOAA object. |
| Local raw object's exact NOAA release binding | `BLOCKED` | Local file basename/date/schema/compressed format and approximately 214 MiB size align with NOAA index entry `ais-2024-11-01.csv.zst` (214.0M). Local SHA-256 is recorded. | No provider-published content digest/ETag or acquisition receipt was found to bind local bytes cryptographically. Local suffix `.tgz` differs from NOAA `.csv.zst`. |
| Cleaner timestamp behavior | `VERIFIED_WITH_EVIDENCE` (transformation only) | Raw `base_date_time` is naive; cleaner parses using `utc=True`; Parquet uses `timestamp[ns, tz=UTC]`; first 2,000 raw timestamps parse to the same instants as cleaned rows. No second shift was observed in reviewed cleaner/T08 path. | This cannot establish timezone by itself; source-level UTC is supported by NOAA product docs above. Do not interpret `utc=True` as timezone conversion from an unknown zone. |
| D-03 duplicate semantics | `REQUIRES_TEAM_DECISION` | Decision Record D-03 states stable-first for identical groups and excludes conflicting groups in full; it explicitly leaves source-specific key/equality/order to source validation. Existing source trajectory logic is different. | Approve key, equality fields, null equivalence, stable ordering and scope before acceptance. This audit does not approve the proposal in the companion plan. |
| Raw/cleaned provenance sample | `VERIFIED_WITH_EVIDENCE` (2,000-row prefix only) | Compared 2,000 raw day-01 rows to cleaned Parquet by 1-based `source_row`: MMSI, timestamp, lat/lon, SOG/COG, source_file and row all matched 2,000/2,000; zero mismatches. | Not full 7.9M-row partition reconciliation; a deterministic prefix does not prove all-row integrity or stability across regeneration. |
| Raw/cleaned local integrity | `VERIFIED_WITH_EVIDENCE` (captured artifacts) | Raw SHA-256 `b93ed80f31f69f0a504a12a5e65105854f013199ec3e0786d3acfebfcaac932b`; Parquet SHA-256 `3f42bd1a5b594d346de209914f982784bc2dd49c103a61e3009e564b1ff0302d`; manifest has matching basename/size and output row count. | Processed manifest omits raw digest; hashes prove current local bytes only, not provider-origin authenticity. |
| Manifest/release binding | `BLOCKED` for provider-verified full release provenance | Current processed manifest links source basename/size to output and rows have `source_file`/`source_row`. | Add exact raw digest, provider object URI/release, schema fingerprint, transform revision and reconciliation result in a future upstream change. No source file was changed here. |
| Canonical ID syntax/mapping | `VERIFIED_WITH_EVIDENCE` (operational mapping) | T08 maps a valid nine-digit MMSI to `physical_mmsi:<same digits>`; G11 checks semantic consistency. MMSI `367457250` yielded the same key in day 01/02/30 (prior audit). | This is not vessel authentication. Provenance coordinates do not establish physical identity. |
| Production source trust / vessel identity | `REQUIRES_TEAM_DECISION` | No repository trust registry or approved source acceptance policy was found. NOAA FAQ says NOAA does not maintain vessel ownership. | Agree source/provider trust registry and verifier behavior. Real-world ownership, registration or transmitter authenticity needs separate authoritative evidence and is not claimed here. |

## Reconciliation run evidence

Read-only Python invocation from repository root, using installed project environment:

```powershell
@'
import pandas as pd
import pyarrow.dataset as ds
raw_path=r'..\maritime-ais-system\data\raw\ais\2024\11\ais-2024-11-01.tgz'
parquet_path=r'..\maritime-ais-system\data\processed\ais_cleaned\year=2024\month=11\day=01\part-00000.parquet'
raw=pd.read_csv(raw_path, compression='zstd', nrows=2000).reset_index(drop=True)
clean=ds.dataset(parquet_path, format='parquet').to_table(
    filter=ds.field('source_row') <= 2000
).to_pandas().sort_values('source_row').reset_index(drop=True)
# Compare mmsi, UTC-parsed base_date_time, latitude, longitude, sog, cog,
# source_file == ais-2024-11-01.tgz and source_row == 1..2000.
'@ | .\.venv\Scripts\python.exe -
```

Observed: `raw_rows=2000`, `clean_rows=2000`; eight compared fields passed with zero mismatches. The command did not write to either source directory.

## Primary external evidence

- NOAA MarineCadastre AIS FAQ, timestamp semantics and ownership limitation: <https://coast.noaa.gov/data/marinecadastre/ais/faq.pdf> (Q26 states base station UTC; Q21 says NOAA does not maintain vessel ownership).
- NOAA InPort metadata for Nationwide AIS 2024: <https://www.fisheries.noaa.gov/inport/item/73064> (product/source and CSV2 download index).
- NOAA OCM daily CSV2 listing: <https://noaaocm.blob.core.windows.net/ais/csv2/csv2024/index.html> (2024-11-01 object name and rounded size).

## Contract and prior engineering evidence

- `docs/contracts/CONTRACT_V1_DECISION_RECORD.md`: D-02 (selected vs original timestamp), D-03 (duplicate rule and pending source verification), D-05 (identity semantics), G11 note (ID/MMSI consistency does not prove identity).
- `evaluation/s2_t08/T08_SOURCE_VALIDATION.md`, `T08_IDENTITY_VALIDATION.md`, `evaluation/s2_t09/T08_T09_INTEGRATION_REPORT.md`, and the prior four `REAL_AIS_*_VERIFICATION` reports.
- Prior controlled T08→T09 run: one selected MMSI and ten accepted events in a 10-minute bounded window, zero duplicates observed, production-format TrackSnapshot VALID. This remains bounded engineering evidence only.

## Status summary

- `TIMEZONE_PRODUCT_SEMANTICS: VERIFIED_WITH_EVIDENCE`
- `LOCAL_PROVIDER_OBJECT_BINDING: BLOCKED`
- `DUPLICATE_POLICY: REQUIRES_TEAM_DECISION`
- `PROVENANCE_SAMPLE: VERIFIED_WITH_EVIDENCE`
- `PROVENANCE_RELEASE_WIDE: BLOCKED`
- `CANONICAL_MMSI_MAPPING: VERIFIED_WITH_EVIDENCE`
- `PRODUCTION_SOURCE_TRUST: REQUIRES_TEAM_DECISION`
- `REAL_AIS_PRODUCTION_READY: NO (overall remains CONDITIONAL)`
