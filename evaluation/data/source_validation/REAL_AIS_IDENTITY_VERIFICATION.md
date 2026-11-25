# REAL AIS Identity Verification

**IDENTITY_STATUS: CONDITIONAL**

## Format and mapping

Cleaned `mmsi` is stored as text and the T08 loader accepts exactly nine ASCII digits. The event adapter derives `vessel_id=physical_mmsi:<mmsi>`, labels the trajectory `REAL_AIS`, and sets `is_simulated=false`; it does not use filename or row number as vessel identity (`src/data/ais_replay.py:326`; `src/data/track_semantics.py:31-44`). The G11 semantic validator checks physical ID/MMSI consistency and source/provenance semantics.

The source full-month cleaner report records 237,960,745 records and zero invalid-MMSI rows, but this is a syntactic source-QC result, not an independent vessel registry or authenticity check.

## Partition continuity sample

MMSI `367457250` was queried in day-01, day-02 and day-30 Parquet partitions:

| Partition | Rows with this MMSI | Core + SOG/COG valid | Derived canonical ID |
|---|---:|---:|---|
| 2024-11-01 | 1,180 | 1,180 | `physical_mmsi:367457250` |
| 2024-11-02 | 1,221 | 1,221 | `physical_mmsi:367457250` |
| 2024-11-30 | 1,050 | 1,050 | `physical_mmsi:367457250` |

This confirms the source stores the same nine-digit value in these sampled partitions and that the canonical ID function is stable for that value. It does not prove that the MMSI is authentic, uniquely assigned to the same real vessel, or controlled by the claimed owner. It also does not establish stability across every day or source release.

## T08/T09 production-boundary check

The controlled 10-minute smoke used T08 events and T09 `ReplaySessionCore`/`TrackBuffer`. A temporary, sample-scoped verifier checked only `REAL_AIS`, `is_simulated=false`, MMSI-to-ID equality, expected source basename and positive row number. It was not an approved trust registry. The emitted TrackSnapshot passed G11 and temporal validation; see `REAL_AIS_FINAL_READINESS.md`.

## Conclusion

Canonical mapping and semantic validation work for the sampled records. There is no approved source authority, vessel identity registry, MMSI lifecycle rule, or certification of the feed in the repository. Regex and self-consistency do not prove real-world identity. Keep `IDENTITY_SOURCE_VALIDATION_PENDING` unresolved and `IDENTITY_STATUS: CONDITIONAL`.
