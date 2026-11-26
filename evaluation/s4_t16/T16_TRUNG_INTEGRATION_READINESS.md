# T16 — Trung Integration Readiness

**Date:** 2026-11-25
**Scope:** evidence for Track/Replay-to-Model/Risk interfaces. This is a compatibility review, not an implementation of Trung's modules.

## Interface status

| Interface / requirement | Status | Evidence and limit | Owner / next action |
|---|---|---|---|
| T08/T09 TrackSnapshot with G11 | `READY` at the implemented TrackSnapshot boundary | T08/T09 regression and T12 Replay API tests pass; production structural + G11 semantic checks are invoked at tested TrackSnapshot boundaries. Does not prove nested Encounter/Risk consumers. | Toàn owns replay/track producer; Trung reviews consumer parity. |
| Replay session and anchor | `CONDITIONAL` | Simulation clock and UTC anchor/session are present in the T09 core and exercised through the fixture Replay API. Persistence, cross-process transaction, durable idempotency/TTL and production scheduling are not verified. | Toàn to supply durable API semantics before production integration. |
| TrackSnapshot → Encounter V1 | `NOT_IMPLEMENTED` | `encounter_v1.schema.json` and contract test vectors exist; no production builder/adapter constructs a V1 Encounter from live tracks. T08/T09 provides tracks, not pair discovery/Encounter integration. | Trung owns Encounter builder/consumer; Toàn provides canonical tracks and source/QC metadata. |
| Model input `[2,10,4]` float32 | `CONDITIONAL` | Offline `EncounterDataset` materializes the official two-vessel history without reordering and keeps labels/targets under `ground_truth`. Live geographic TrackSnapshot → common-EN feature adapter is absent. | Trung owns feature/model adapter; Toàn provides tracks, UTC grid, identity and geographic source status. |
| Rule input `[2,10,2]` float64 SOG/COG | `NOT_IMPLEMENTED` for production adapter | Contract defines observed SOG/COG and history-only rules; its `production_implementation` is false. T08 events carry observations, but no online Encounter/Rule tensor adapter exists. | Trung owns Rule interface; Toàn supplies observed history; retain observed COG at zero speed. |
| Offline A/B mapping | `READY` | T13 loader/index audit resolves official A/B through the locked pair and vessel index; no resort by canonical ID occurred. | Toàn preserves index mapping in all offline readers. |
| Online canonical A/B / pair identity | `CONDITIONAL` | Contract specifies NFC + UTF-8 canonical ordering and pair/encounter hash semantics; T12 can order track-list IDs, but no production pair discovery/Encounter V1 builder consumes that policy end-to-end. | Shared: Toàn implements source candidate pair boundary; Trung validates pair/Encounter consumer. |
| Common EN origin | `CONDITIONAL` offline, `NOT_IMPLEMENTED` live | Offline helper/tests and locked tensors use common origin at vessel A's first history point (t0−9); live TrackSnapshot carries lat/lon, not the complete common EN Encounter frame. | Shared; Toàn supplies coordinate provenance, Trung owns feature semantics and inverse availability. |
| Forecast at 15 timestamps | `NOT_IMPLEMENTED` | Contract defines +1…+15 outputs; no M5a/CV/Forecast production runtime or live adapter is present. | Trung owns Model/Forecast. No thresholds or forecast logic changed. |
| No future labels in online inference | `READY` for offline input separation; `CONDITIONAL` for online serving | `EncounterDataset` separates `model_input` from future `ground_truth`; tests check labels/targets are not in model input. There is no live inference endpoint to test end-to-end leakage. | Trung owns serving request construction; both teams verify no future labels cross boundary. |
| Contract metadata synchronization | `CONDITIONAL` | G11/Replay V1 schemas and tests are in repo, but `feature_contract.json`, `rule_input_contract.json`, and `temporal_contract.json` still report `1.0.0-draft` / `proposed_pending_team_review`; `coordinate_contract.md` still says review pending. These metadata conflict with the team-approved Contract V1 context and must be reconciled without changing locked wire semantics. | Trung + Toàn record whether these companion contracts are approved, superseded, or still pending. This review made no contract edits. |

## Integration conclusion

The data and offline index boundary is suitable as an input contract reference. The TrackSnapshot and synthetic Replay Fixture paths are structurally/semantically tested. A production Model/Risk integration is **not ready** until Encounter construction, live feature/Rule adapters, pair identity/A/B handling, common coordinate frame, and Model/Forecast runtime are implemented and tested against the approved Contract V1. Real AIS remains conditional for production because source trust and D-03 duplicate policy are unresolved; T16 did not change them.
