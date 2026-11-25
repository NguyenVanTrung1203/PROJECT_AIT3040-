# T08 Identity Source Validation

**Result:** `IDENTITY_VALIDATION: CONDITIONAL`.

## Evidence and implemented rule

The cleaned Parquet schema stores MMSI as text and the source cleaner validates it against exactly nine decimal digits. For rows that pass `flag_invalid_mmsi=false`, `flag_core_valid=true`, timestamp/position QC, and motion/provenance QC, T08 emits `vessel_id = physical_mmsi:<MMSI>` and `source_type = REAL_AIS`, `is_simulated = false`. The production TrackSnapshot adapter requires the ID suffix to match the same nine-digit MMSI and calls `validate_production_track_g11`, which performs both production structural schema validation and shared G11 semantic validation.

The actual-source smoke emitted `physical_mmsi:338443451` from MMSI `338443451`, source file `ais-2024-11-01.tgz`, row 1. Unit coverage includes accepted physical IDs and G11 snapshot validation. `is_simulated` represents trajectory provenance, never vessel class/type.

## Limits

The MMSI regex and ID/MMSI equality prove only syntactic consistency. They do not independently verify vessel ownership, registration, source authority, or that the MMSI is stable and authentic. The source inventory has no separate vessel identity registry or source certification establishing that binding. The source cleaner’s file/row provenance supports audit of a specific observed row, but is not a durable vessel identity. Therefore an ID can be derived for replay and validated structurally/semantically, while source identity validation remains CONDITIONAL for production.

No filename, row index, vessel name, vessel type, or DATASET_FINAL encounter ID is used as a persistent identity. No identity is synthesized when MMSI is missing or invalid. Future work needs an approved source-trust/identity evidence policy; do not interpret this report as real-world identity verification.
