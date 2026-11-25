# Real AIS Source Validation Gap Closure Plan

**Audit date:** 2026-11-25
**Repository branch:** `Trinh_Toan`
**Scope:** close or accurately disposition remaining NOAA AIS source validation gaps after the bounded T08 → T09 real-data run. This report is evidence and a plan; it does not change Contract V1, source AIS files, `DATASET_FINAL`, or runtime policy.

## Executive status

| Concern | Disposition | What is established | What remains open |
|---|---|---|---|
| Timezone | `VERIFIED_WITH_EVIDENCE` for the NOAA MarineCadastre 2024 product | NOAA says the complete AIS timestamp is added by a base station using its UTC clock; the 2024 InPort record identifies the product and links its CSV archive. | Exact byte-level binding of the local raw object to the NOAA object lacks a provider digest. Keep source release binding explicit in provenance. |
| Duplicate equality | `REQUIRES_TEAM_DECISION` | Contract D-03 defines stable-first for identical duplicates and drops a whole conflicting group; source reports show the existing trajectory rule is different. | Approve key, equality fields, null semantics, stable order, and scope before using the policy to accept production AIS. |
| Provenance | `VERIFIED_WITH_EVIDENCE` for the tested 2,000-row prefix; `BLOCKED` for provider-to-local byte identity and release-wide reconciliation | Raw SHA-256, cleaned SHA-256, manifest links and 2,000 raw rows reconcile to Parquet with file/row provenance. | Add immutable raw digest to a future processed manifest and reconcile the full partition or a declared representative sample. |
| Identity | `VERIFIED_WITH_EVIDENCE` for canonical syntax/mapping only; `REQUIRES_TEAM_DECISION` for source trust | Nine-digit MMSI maps deterministically to `physical_mmsi:<MMSI>`; three day partitions showed consistent mapping for one MMSI. | Decide an allowlist/trust policy. This does not authenticate the real vessel, owner, registration, or transmitter. |

**Overall source readiness remains CONDITIONAL for production acceptance.** This audit does not convert the T08/T09 bounded engineering run into a general source approval. Duplicate policy is unresolved, and local object release binding/trust registry work remains.

## 1. Timezone evidence and scope

The prior local audit correctly observed that raw `base_date_time` is timezone-naive and that the cleaner invokes `pandas.to_datetime(..., utc=True)`. That code proves the local transformation only; it cannot establish upstream clock semantics.

An authoritative NOAA MarineCadastre AIS FAQ states that the full timestamp is added by the base station using the reporting base station clock in Coordinated Universal Time (UTC). NOAA's InPort record identifies the product as “Nationwide Automatic Identification System 2024,” describes the data as collected from the U.S. Coast Guard national AIS receiver network, and links the NOAA 2024 daily CSV index. That index lists `ais-2024-11-01.csv.zst` at 214.0M. The local raw object is named `ais-2024-11-01.tgz`, is 224,380,502 bytes (about 214 MiB), and has Zstandard magic; its schema and daily date also match the NOAA CSV2 product.

This is sufficient evidence for the **NOAA product's timestamp semantics**, so timezone meaning is no longer blocked solely by the naive string or cleaner. It is not a cryptographic proof that the local bytes are identical to that NOAA object: the local extension differs and no provider SHA-256/ETag was found. Keep the local-to-provider object binding as a provenance sub-gap. The raw-to-cleaned conversion must continue to be interpreted as attaching UTC to the naive source timestamp; do not apply another timezone shift.

Evidence links:

- NOAA MarineCadastre AIS FAQ, timestamp question: <https://coast.noaa.gov/data/marinecadastre/ais/faq.pdf>
- NOAA InPort, Nationwide AIS 2024, metadata record: <https://www.fisheries.noaa.gov/inport/item/73064>
- NOAA OCM CSV2 2024 daily object index: <https://noaaocm.blob.core.windows.net/ais/csv2/csv2024/index.html>

## 2. Duplicate policy proposal (not approved)

Contract V1 Decision Record D-03 requires: identical duplicates keep stable-first; conflicting duplicate groups are excluded in full; key, equality and ordering must be verified per source before production. The decision record still marks source validation pending. The current T08 provisional equality set is `latitude`, `longitude`, `sog`, `cog`; this omits `heading` and QC flags. The existing source trajectory pipeline uses a different winner-ranking policy and must not be used as D-03 acceptance evidence.

**Proposal for team review, scoped only to NOAA MarineCadastre `csv2/csv2024` 17-column daily point files:**

1. Duplicate key: normalized nine-digit `mmsi` plus source `base_date_time` represented as the selected UTC instant, at the source's available timestamp precision.
2. Candidate replay-payload equality tuple: `latitude`, `longitude`, `sog`, `cog`, `heading`, plus the source QC/validity flags consumed by the loader (`flag_invalid_mmsi`, `flag_invalid_timestamp`, `flag_off_date`, `flag_invalid_position`, `flag_invalid_sog`, `flag_invalid_cog`, `flag_invalid_heading`, `flag_core_valid`, `flag_moving_1_to_50kn`). Compare normalized values with explicit missing-value semantics; do not coerce null motion values to zero.
3. `source_file` and `source_row` are provenance and deterministic tie-break metadata, not payload equality fields. Stable-first ordering should be lexicographic UTF-8 `source_file`, then positive integer `source_row`, after their stability is bound to an immutable source digest.
4. Static/descriptive fields (`vessel_name`, `imo`, `call_sign`, `vessel_type`, `status`, `length`, `width`, `draft`, `cargo`, `transceiver`) are excluded from the proposed *replay payload* equality tuple because they do not affect the current replay event/QC result. If D-03 intends row-level identity instead, require exact normalized equality across all 17 input columns; the team must choose explicitly.
5. Scope does not automatically extend to other AIS providers, years, schemas, or reprocessed products.

This is a recommendation only. Until the contract/source owner approves the exact equality and null semantics, keep `DUPLICATE_POLICY_STATUS: CONDITIONAL`; do not label a source acceptance run PASS by selecting whichever definition produces fewer conflicts. After approval, rerun a declared representative duplicate audit and the production loader under the approved rule.

## 3. Provenance findings and proposed manifest

Observed day-01 artifacts:

| Artifact | Size | SHA-256 |
|---|---:|---|
| Raw `ais-2024-11-01.tgz` | 224,380,502 bytes | `b93ed80f31f69f0a504a12a5e65105854f013199ec3e0786d3acfebfcaac932b` |
| Cleaned `day=01/part-00000.parquet` | 259,690,923 bytes | `3f42bd1a5b594d346de209914f982784bc2dd49c103a61e3009e564b1ff0302d` |

The source inventory records the raw digest and compressed-CSV format. The processed manifest records the matching raw basename/size, cleaned output path, completion and row count, but not the raw digest. Parquet rows retain `source_file` and 1-based `source_row`.

**New bounded reconciliation performed for this report:** decoded the first 2,000 records of the immutable raw day-01 Zstandard CSV; selected cleaned Parquet rows with `source_row <= 2000`, sorted by `source_row`; compared all 2,000 positions. MMSI, parsed timestamp instant, latitude, longitude, SOG, COG, source basename, and source row each matched 2,000/2,000 with zero mismatches. This is a deterministic prefix sample, not full-partition reconciliation or an independent provider checksum match.

**Manifest proposal for a future source-pipeline change (not applied here):**

```json
{
  "provider": "NOAA OCM / MarineCadastre",
  "product": "Nationwide AIS 2024 CSV2",
  "source_object_uri": "https://noaaocm.blob.core.windows.net/ais/csv2/csv2024/ais-2024-11-01.csv.zst",
  "source_object_name": "ais-2024-11-01.csv.zst",
  "source_object_sha256": "<computed from acquired immutable source bytes>",
  "source_object_bytes": "<exact byte count>",
  "source_schema_fingerprint": "<ordered 17-column schema digest>",
  "timestamp_semantics": "base_date_time UTC per NOAA MarineCadastre AIS FAQ",
  "source_row_ordinal": "1-based data-record ordinal after CSV header",
  "transform_code_revision": "<immutable commit or release digest>",
  "duplicate_policy_revision": "<approved D-03 policy ID>",
  "output_object": "<relative Parquet path>",
  "output_sha256": "<cleaned Parquet SHA-256>",
  "output_row_count": "<integer>",
  "source_row_reconciliation": {"method": "<full or declared sample>", "checked": "<integer>", "mismatches": "<integer>"}
}
```

Use an exact provider digest when NOAA publishes one; otherwise compute and preserve the digest immediately on acquisition and explicitly mark it as an acquisition digest, not a provider-attested digest. Do not retrofit a claimed provider checksum from the local file alone.

## 4. Identity and source trust

The source stores MMSI as a string and the cleaner validates nine decimal digits. The T08 adapter derives `physical_mmsi:<9 digits>` from that value; the sample identity report observed `367457250` in day 01, 02 and 30 and produced the same canonical ID. G11 semantic validation checks structural consistency between the ID and MMSI. These are operational identity-key checks only.

NOAA's AIS FAQ explicitly says it does not maintain vessel ownership in its AIS data, and notes that data may need joins to other sources to derive ownership. Consequently this audit makes no claim about vessel ownership, registration, transmitter authenticity, MMSI exclusivity, or real-world identity. `source_file`/`source_row` establish record provenance within an acquired file, not vessel identity.

**Trust policy proposal for team approval:** maintain a versioned source registry keyed by provider/product/schema/release, recording allowed URI pattern, required timezone evidence, checksum strength, provenance requirements, quality behavior, duplicate policy ID and effective period. The runtime identity verifier should fail closed if the source is absent from this registry or MMSI/source provenance does not match. A trusted archive source must not be described as proof that the transmitting vessel is authentic.

Status: canonical mapping is evidenced; production source-trust acceptance requires a team decision. External vessel/owner authentication is out of scope unless the project explicitly requires it, in which case an authoritative registry/source and matching policy must be supplied.

## 5. Demo 26/11/2026 and deferred work

**Can be shown before demo, using the validated scope:**

- A bounded replay from the local NOAA 2024 day partition with explicit source object digest, UTC evidence citation and provenance displayed in the run record.
- The already demonstrated T08 → T09 10-point TrackSnapshot for MMSI `367457250`, labeled as a bounded NOAA-source engineering sample with duplicate outcome `0` observed in that window.
- Raw-to-cleaned prefix reconciliation result (2,000 rows, zero field/source-row mismatches), without presenting it as a whole-file guarantee.
- Existing synthetic Replay Fixture browser workflow remains the appropriate deterministic UI demo; clearly distinguish it from raw AIS evidence.

**Must remain conditional or move beyond the demo:**

- Team approval of D-03 equality fields, null semantics, tie-break ordering and scope; then representative/month-wide duplicate re-audit.
- Exact NOAA object-to-local-byte binding using provider checksum/ETag or an acquisition record tied to immutable URI and local SHA-256.
- Full day partition reconciliation (or a team-approved statistically/stratified sample); raw digest in the processed manifest; transform revision pinning.
- Versioned production source trust registry and identity verifier. No vessel-owner/authenticity claim.
- Any extension to providers, release years, alternate schemas or production SLAs.

No tests were run as part of this report-only evidence update. The existing regression evidence remains as cited in the prior T08/T09/T12-T13 reports; this audit's new verification is the read-only 2,000-row reconciliation described above.
