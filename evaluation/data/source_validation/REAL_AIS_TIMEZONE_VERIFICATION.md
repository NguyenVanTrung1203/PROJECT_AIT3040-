# REAL AIS Timezone Verification

**TIMEZONE_STATUS: CONDITIONAL**

**Inspection date:** 2026-11-25 · **Source window sampled:** 2024-11-01

## Evidence reviewed

- Raw input: `maritime-ais-system/data/raw/ais/2024/11/ais-2024-11-01.tgz` (224,380,502 bytes; SHA-256 `b93ed80f31f69f0a504a12a5e65105854f013199ec3e0786d3acfebfcaac932b`). The extension is misleading: the file begins with Zstandard magic `28 b5 2f fd` and is a compressed CSV stream, not a tar archive.
- The raw CSV has 17 columns. Its event-time column is `base_date_time`; a directly read first data row contains `2024-11-01 00:00:01` with no offset or timezone marker.
- Cleaner: `maritime-ais-system/data/scripts/03_clean_to_parquet.py:63-68,92-95,192-197`. It decodes the Zstandard CSV, then calls `pandas.to_datetime(..., format="%Y-%m-%d %H:%M:%S", utc=True, errors="coerce")` on the naive string.
- Raw inventory: `data/metadata/raw_inventory.csv` records the archive SHA-256, `zstd-csv`, 17 columns, and a 2,000-row structural sample. It contains no timezone statement or source-release provenance document.
- Day manifest: `data/metadata/processed_manifest/2024-11-01.json` says COMPLETE, identifies the raw basename and size, output Parquet path and 7,888,705 rows. It does not record a raw-file checksum.

## Raw-to-cleaned timestamp comparison

The first raw CSV record was compared to Parquet row `source_file=ais-2024-11-01.tgz, source_row=1`:

| Field | Raw CSV | Cleaned Parquet |
|---|---|---|
| MMSI | `338443451` | `338443451` |
| Event time | `2024-11-01 00:00:01` | `2024-11-01 00:00:01+00:00` |
| Latitude / longitude | `41.69467 / -71.39008` | `41.69467 / -71.39008` |
| SOG / COG | `0.0 / 14.7` | `0.0 / 14.7` |
| Core/QC | — | core-valid; MMSI/time/position/SOG/COG flags false |

This proves the exact transformation for this row. It does not prove that the unzoned source clock was UTC. `utc=True` assigns UTC semantics to the naive value; it cannot convert from a source timezone that was not specified. No separate ingestion/receive timestamp is present in the raw 17-column schema. `base_date_time` is treated as event time; `source_file`/`source_row` are provenance coordinates, not ingestion time.

The T08 reader requires Arrow `timestamp[ns, tz=UTC]` and reads its epoch value directly for ordering; it does not infer a timezone from the host clock. That validates the stored Parquet representation, not the upstream timestamp meaning. The local pipeline has no second explicit timezone shift in the reviewed raw-to-Parquet cleaner. A timezone misassignment at the initial `utc=True` step remains possible until the source owner confirms semantics.

## Conclusion

The raw timestamp is timezone-naive, and local source documentation does not establish its timezone. Therefore UTC cannot be asserted from the field name, Parquet type, or this row match. No credible evidence of a double conversion was found in the reviewed cleaner/T08 path, but absence of a second conversion does not resolve the initial timezone assumption.

**Required evidence:** source-provider or source-owner documentation that `base_date_time` in these files is UTC (including any export conversion rule). Until supplied, reject production UTC certification and keep `SOURCE_VALIDATION_PENDING` unresolved.
