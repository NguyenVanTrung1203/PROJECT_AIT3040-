# REAL AIS Duplicate QC Report

**DUPLICATE_POLICY_STATUS: CONDITIONAL**

**D-03 source rule:** group by MMSI plus selected source timestamp; identical duplicates keep stable-first; conflicting groups are excluded in full.

## Contract and implementation review

`contracts/temporal_contract.json` names the conflict group as all records for MMSI and timestamp and identical selection as stable-first. `docs/contracts/CONTRACT_V1_DECISION_RECORD.md` leaves source-specific equality fields unresolved pending source verification.

The T08 reader uses key `(timestamp, MMSI)`, stable order `source_file` UTF-8 ascending then `source_row` ascending, and currently compares `latitude`, `longitude`, `sog`, `cog` (`src/data/ais_replay.py:31,91-98,379-380`). It keeps the first matching payload and rejects all rows in a conflicting group. These equality fields are explicitly provisional: source/Contract V1 evidence does not settle whether heading, quality flags, or other source fields must participate.

The AIS trajectory reconstruction pipeline groups by `(mmsi, timestamp_utc)`, ranks rows by availability of SOG/COG/heading and then source file/row, and flags conflict only when latitude or longitude differs (`maritime-ais-system/data/scripts/05_reconstruct_trajectories.py:238-252`). It selects a winner even in a conflicting position group. That preprocessing policy is not compliant evidence for T08's exclude-the-whole-conflict rule.

## Observed counts

**Controlled T08/T09 window:** day-01 partition, selected MMSI `367457250`, `[2024-11-01T00:00:00Z, 2024-11-01T00:10:01Z)`, batch size 1,024.

| Measure | Result |
|---|---:|
| Row groups in partition / read | 79 / 12 |
| Rows read from selected row groups | 1,188,705 |
| Accepted ordered AIS events for selected MMSI | 10 |
| Rejected selected-MMSI rows | 0 |
| Identical duplicate groups / rows dropped | 0 / 0 |
| Conflicting duplicate groups / rows excluded | 0 / 0 |
| Missing partitions | 0 |

The bounded MMSI sample contained no duplicate group. This is not a month-wide duplicate estimate. The existing month trajectory validation reports 4,144 duplicate extra rows and 7 conflicting duplicate groups; its conflict definition is position-only and its pipeline retains one ranked winner, so those counts cannot be relabeled as T08/D-03 outcomes.

Fixtures in `tests/unit/test_ais_replay.py` cover identical stable-first and whole-group conflict exclusion. The full regression suite passed in this audit. The source statistics above do not resolve the equality-field question.

## Conclusion

The implemented T08 policy is deterministic and follows the contract's group handling using a provisional payload equality set. Keep `DUPLICATE_POLICY_STATUS: CONDITIONAL` until the Contract/source owner approves the complete equality fields for this source and a representative duplicate audit is run with that fixed definition. Do not use the trajectory builder's winner selection as a substitute.
