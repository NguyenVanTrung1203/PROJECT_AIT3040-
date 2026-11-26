# T16 Index Integrity Report

**Date:** 2026-11-25
**Dataset:** `DATASET_FINAL/final_dataset_1.0`
**Result:** `PASS` for locked artifact integrity, declared split/index mappings, tensor metadata and cross-split key checks. No dataset file was modified.

## Lock, checksums and counts

Read-only T13 integrity/index verification was rerun as part of `scripts/t13_data_benchmark.py`. Output: [`t13_benchmark_rerun.json`](t13_benchmark_rerun.json).

| Check | Result |
|---|---|
| Lock status | `READY_AND_LOCKED` |
| Checksum entries | 93/93 PASS |
| Checksum manifest SHA-256 | `21f6bde168631928e98b6273aaab4e168bfb6eb755599a1fbc1cb8c364611441` |
| Train / Validation / Test | 1,440 / 835 / 1,320 encounters |
| Total | 3,595 encounters, 179,750 vessel rows, 7,190 vessel instances |

| Split | Encounter count | Official A/B rows | Tensor rows | Source mapping as recorded |
|---|---:|---:|---:|---|
| Train | 1,440 | 2,880 | 72,000 | `yang_lei`: 1,440 |
| Validation | 835 | 1,670 | 41,750 | `yanglei`: 240; `real_ais_kattegat_v3`: 295; `augmented_real_ais_kattegat_v3`: 300 |
| Test | 1,320 | 2,640 | 66,000 | `yang_lei`: 720; `real_ais_denmark_oct2025`: 300; `synthetic_ais_denmark_oct2025`: 300 |

The official validation source alias is retained as written in the manifest. T03 source normalization identifies its 300 `augmented_real_ais_kattegak_v3` encounters as the synthetic/augmented group; this audit did not rewrite source labels.

## Index, A/B, X_row, labels and shapes

The loader and T13 audit passed unique encounter IDs, split-manifest membership, label agreement, global index membership, and exactly one official A and B vessel row per encounter. Each official A/B `X_row` resolves to a vessel row with the same encounter ID; there was no resort by online canonical identity. Offline tensor A/B remains authoritative.

| Split | `X` storage shape / dtype | `displacement` | `common` | `anchors` | labels |
|---|---|---|---|---|---|
| Train | `[2880,10,4]` / float32 | `[2880,15,2]` float32 | `[1440,2,15,2]` float32 | `[1440,2,2]` float64 | 1,440 int8 |
| Validation | `[1670,10,4]` / float32 | `[1670,15,2]` float32 | `[835,2,15,2]` float32 | `[835,2,2]` float64 | 835 int8 |
| Test | `[2640,10,4]` / float32 | `[2640,15,2]` float32 | `[1320,2,15,2]` float32 | `[1320,2,2]` float64 | 1,320 int8 |

Encounter materialization uses the official pair rows to produce model history `[2,10,4]` float32; anchors remain float64. The separate Rule contract describes observed SOG/COG history as `[2,10,2]` float64. No offline index or A/B tensor was reordered.

## Temporal alignment and leakage checks

The current integrity verifier passed Train/Validation UTC, history-grid, anchor, finite-value and reconstruction checks. Test was not used for model scoring; a read-only direct timestamp-grid check was also run over `DATASET_FINAL/test/data/test_1320.parquet`:

- 66,000 rows, UTC timestamps; timestamp minus anchor exactly equals `relative_minute` for every row.
- Every one of 2,640 encounter/vessel groups has 25 unique offsets from −9 through +15 minutes.
- Each encounter has one anchor; `is_history` agrees with offsets ≤0 and `is_future` with offsets >0.
- Across train/validation/test, overlap was zero for encounter IDs, `dependency_group_id`, `vessel_id`, `simulated_vessel_id`, `source_track_id`, and `source_id`. `(data_source, original_encounter_id)` also did not cross splits.
- Parent references in validation/test dependency maps did not resolve into a different split. In Test, 100 of 300 referenced final encounter IDs matched a Test parent; all remained inside Test. The locked manifest intentionally records parent/child dependencies within Test. This is no observed *cross-split* leakage on audited keys; it does not imply all Test encounters are statistically independent.

The locked dataset's proxy labels, source/domain confounding, and within-Test parent dependencies remain known limitations. No label, split, tensor, source mapping, parent mapping, or scaler was changed or recalibrated.

## Verdict

- `DATASET_LOCK`: `PASS`
- `CHECKSUMS`: `PASS` (93/93)
- `INDEX_AND_A_B`: `PASS`
- `SOURCE/LABEL/SPLIT_MAPPING`: `PASS` for stored mapping consistency
- `CROSS_SPLIT_LEAKAGE`: `NOT_OBSERVED` on the listed ID/dependency keys; same-split Test parent/child relations are disclosed above
- `TEST_QUALITY_OR_CALIBRATION`: `NOT_RUN`
