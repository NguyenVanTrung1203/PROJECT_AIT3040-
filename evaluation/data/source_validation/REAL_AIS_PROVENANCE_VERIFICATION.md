# REAL AIS Provenance Verification

**PROVENANCE_STATUS: CONDITIONAL**

**Scope:** code path review, one raw-to-cleaned row comparison, and a bounded 10-minute T08/T09 run.

## Fields and transformation path

Raw CSV has no `source_file`, `source_row`, `source_object`, or ingestion timestamp fields. The cleaner adds `source_file` as the archive basename and `source_row` as a 1-based data-row ordinal (`data/scripts/03_clean_to_parquet.py:127-128,192-197`). It retains records rather than dropping rows; invalid measurements become null with flags. The daily manifest records source basename, byte size, output path, status and row count.

The raw inventory ties the day-01 archive to SHA-256 `b93ed80f31f69f0a504a12a5e65105854f013199ec3e0786d3acfebfcaac932b`. The processed manifest links the same basename and size (224,380,502 bytes) to the day-01 Parquet partition but does not embed that checksum. The independent inventory and processed manifest together support a release-specific join, but the Parquet row itself carries only basename/ordinal, not the raw archive digest.

## Direct comparison and replay evidence

- Raw row 1 and cleaned row `(ais-2024-11-01.tgz, 1)` matched on MMSI, event timestamp string/value, latitude, longitude, SOG and COG. The cleaned timestamp acquired UTC metadata through the cleaner; timezone semantics remain conditional in the companion report.
- The selected T08 events retained `provenance.source_file` and positive `provenance.source_row`; sample provenance began at rows 4048 and 10364.
- The T08 reader orders by selected UTC epoch, MMSI, UTF-8 `source_file`, then `source_row`. This is deterministic for the present archive ordering.
- The `source_row` counter increments in input CSV order, including through chunked reads. This supports repeatability for an identical raw archive. The pipeline was not rerun because its normal path writes/replaces cleaned Parquet and manifests.

## Limits

The exact raw-to-cleaned field match was checked for one row, not every source row. A source basename and row ordinal do not remain durable if the provider republishes/reorders a file under the same basename. The current processed manifest lacks the raw SHA-256, and the AIS source directory is not a Git repository (`.git` absent), so no source-code commit/release identity could be verified there. No unmatched-row count was computed across the full 7.9-million-row partition.

**Conclusion:** traceability is demonstrated for the sampled row and for emitted T08 event provenance, with deterministic ordering within the observed immutable raw release. Release-wide provenance and stability across regenerated source files remain unverified; keep status CONDITIONAL.
