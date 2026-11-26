# REAL AIS Source Readiness — Final

**Audit date:** 2026-11-25

**Project branch:** `Trinh_Toan` · **HEAD:** `6b2de9a6c63fa64b2afda9094acf54b0086a061c`

**AIS source path:** `maritime-ais-system/data/processed/ais_cleaned/` (30 daily Parquet partitions present)

**AIS source repository status:** directory exists but has no `.git`; source commit/version could not be established.

## Status

| Check | Result | Basis |
|---|---|---|
| `TIMEZONE_STATUS` | **CONDITIONAL** | Raw `base_date_time` is timezone-naive; cleaner assigns UTC with `utc=True`; no source-owner timezone evidence found. |
| `PROVENANCE_STATUS` | **CONDITIONAL** | One raw row matched cleaned row and bounded T08 events retained file/row provenance; release digest is not embedded in Parquet manifest and full-row reconciliation was not done. |
| `DUPLICATE_POLICY_STATUS` | **CONDITIONAL** | T08 fixtures pass, but equality fields remain provisional; selected sample had no duplicates and cannot settle source policy. |
| `IDENTITY_STATUS` | **CONDITIONAL** | Nine-digit MMSI syntax and sampled partition continuity pass; no trusted vessel/MMSI registry or source attestation exists. |
| `G11_VALIDATION` | **PASS** for one controlled real-AIS snapshot | T09 output passed production structural + semantic G11 and temporal/history validation. |
| `REAL_AIS_T08_T09` | **PASS** for bounded controlled window | T08 emitted ten events and T09 produced one `VALID` ten-point snapshot at the selected anchor. This is not a production source approval. |
| `SOURCE_VALIDATION_PENDING` | **NOT_RESOLVED** | Timezone and D-03 source equality evidence still open. |
| `IDENTITY_SOURCE_VALIDATION_PENDING` | **NOT_RESOLVED** | No approved identity authority/registry or source-release trust policy. |
| `REAL_AIS_READY_FOR_REPLAY` | **NO** for production runtime | Contract V1 forbids assuming UTC without evidence; identity and duplicate policy are conditional. Bounded engineering smoke is reproducible under an explicitly temporary sample verifier. |

## Actual T08 → T09 smoke evidence

Scope: one day-01 Parquet partition, one MMSI, `[2024-11-01T00:00:00Z, 2024-11-01T00:10:01Z)`, anchor `2024-11-01T00:10:00Z`, batch size 1,024. No month-wide scan was run.

Equivalent T08 invocation:

```powershell
.venv\Scripts\python.exe -m src.data.replay_cli `
  --source-root ..\maritime-ais-system\data\processed\ais_cleaned `
  --start 2024-11-01T00:00:00Z `
  --end 2024-11-01T00:10:01Z `
  --mmsi 367457250 `
  --max-events 500 `
  --batch-size 1024
```

For the T09 portion, emitted events were ingested into a new in-memory session and the snapshot was requested at the fixed simulation anchor. An inline sample-only identity verifier checked source type, `is_simulated`, MMSI/ID equality, `source_file=ais-2024-11-01.tgz` and positive `source_row`; it did not assert ownership or trusted-source status.

| Measure | Observed |
|---|---:|
| Source rows read / row groups read | 1,188,705 / 12 of 79 |
| Events accepted/emitted | 10 / 10 |
| Rejected rows | 0 |
| Identical/conflicting duplicate groups | 0 / 0 |
| Missing partitions | 0 |
| TrackSnapshot `data_status` | `VALID` |
| History points | 10 |
| `current_state == history[-1]` | Yes |
| Selected source time `<=` each nominal time | Yes |
| Source age range | 19–51 seconds |
| G11 structural + semantic and temporal checks | Pass |

The selected-timestamp behavior was tested against the UTC values produced by the cleaner. Because upstream raw timezone meaning remains unknown, the word “UTC” here describes the stored/assumed representation, not independently verified source-clock semantics.

## Integrity and regression

| Artifact | SHA-256 | Size |
|---|---|---:|
| Raw day-01 compressed CSV | `b93ed80f31f69f0a504a12a5e65105854f013199ec3e0786d3acfebfcaac932b` | 224,380,502 bytes |
| Cleaned day-01 Parquet | `3f42bd1a5b594d346de209914f982784bc2dd49c103a61e3009e564b1ff0302d` | 259,690,923 bytes |
| Processed day-01 manifest | `60a2b251f7e90c947208c08104a19bbd9efb526a9ef4f2f2d5dcae61829c76b3` | 520 bytes |

The raw and cleaned SHA-256 values matched the values captured during the initial row comparison after the smoke and tests. `DATASET_FINAL` verification passed **93/93** locked files; checksum manifest SHA-256 `21f6bde168631928e98b6273aaab4e168bfb6eb755599a1fbc1cb8c364611441`; lock status `READY_AND_LOCKED`. No command in this audit wrote to the source AIS tree or `DATASET_FINAL`.

Regression command:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit tests/integration backend/tests -q -p no:cacheprovider
```

Result: **317 passed, 1 existing Pytest/AnyIO deprecation warning**. This includes T08 duplicate/QC fixtures, T09 as-of/G11/session tests, T08→T09 fixture integration and T12/T04 backend regressions. T12 frontend regression: **6 passed** (`npm test`); production build passed (`npm run build`, Vite 7.3.8/esbuild). No project production code, Contract V1 or dataset file was modified.

## Blockers and next actions

1. Obtain authoritative source-owner documentation for the timezone semantics of raw `base_date_time` and whether any upstream conversion occurred.
2. Agree the full D-03 identical-payload equality field set and its scope for this source; then measure duplicate outcomes using that fixed definition on a declared bounded sample.
3. Include the raw object digest/release identifier in the processed manifest or another immutable provenance binding; verify broader raw-row-to-Parquet reconciliation before claiming release-wide provenance.
4. Establish a source trust/identity policy or approved registry for physical MMSI IDs. Do not treat nine-digit format or matching `physical_mmsi:` text as vessel authentication.
5. Reconcile the repository's Contract V1 status artifacts: the Decision Record/Final Lock Readiness describe the design as locked, while `contracts/temporal_contract.json` still says `proposed_pending_team_review`. No contract artifact was changed in this audit.

## Audit environment and Git safety

The project worktree was already dirty before this audit, with staged Contract V1 material and untracked T08–T13 work. Branch remained `Trinh_Toan`; HEAD remained `6b2de9a6c63fa64b2afda9094acf54b0086a061c` (local branch was one commit ahead of `origin/Trinh_Toan`). The separate AIS source directory has no Git metadata. Only these five audit reports were added to the project repository. No source, Contract V1, `DATASET_FINAL`, model, or production code was changed; no commit, push, merge or branch operation was performed.

## Supplemental evidence update — 2026-11-25

See [`REAL_AIS_EVIDENCE_MATRIX.md`](REAL_AIS_EVIDENCE_MATRIX.md) and [`REAL_AIS_GAP_CLOSURE_PLAN.md`](REAL_AIS_GAP_CLOSURE_PLAN.md) for additional read-only evidence obtained after this readiness snapshot. NOAA MarineCadastre documentation supports UTC semantics for the NOAA AIS product, and a 2,000-row raw-to-cleaned prefix comparison found zero mismatches across MMSI, timestamp, position, motion, source file and source row. This does not establish byte-identical local-to-provider object binding or release-wide reconciliation. Duplicate equality/scope still requires team decision; source trust and real-world vessel identity remain unverified. The classifications in this supplemental evidence do not change the historical observations above or promote overall production readiness: keep `REAL_AIS_READY_FOR_REPLAY: NO` for production and source acceptance CONDITIONAL.
