# Trung ↔ Toàn Interface Matrix

Ownership comes from `README.md` and `contracts/integration_contract.md`. Proposed defaults in this document are not approvals.

| Boundary | Toàn provides | Trung consumes / returns | Contract evidence | Owner | Must agree before |
|---|---|---|---|---|---|
| AIS source → replay loader | Raw/cleaned AIS record, source provenance, selected UTC fix, MMSI and source type | Uses valid history as inference data; no direct source-file dependency | `contracts/temporal_contract.json`; T03 `evaluation/data/T03_REPLAY_SOURCE_INVENTORY.md` | Toàn | Real AIS loader acceptance |
| Replay clock → as-of grid | Session clock, UTC anchor/grid, reset/seek lifecycle | Anchor and 10 history timestamps; consumes only source at/before grid | `contracts/temporal_contract.json`; `contracts/integration_contract.md` | Shared; Toàn runtime, Trung consumer | T08/T09 temporal integration |
| Runtime QC → TrackSnapshot | `vessel_id`, nullable MMSI, source type/simulation marker, anchor, current state, history timestamps/lat/lon/SOG/COG/age, status | Validates completeness/freshness before building Encounter; returns business status and suppresses inference when required | `contracts/track_snapshot.schema.json`; T04 `backend/app/mock_tracks.py` | Toàn produces; shared schema | T08 QC boundary |
| Track pair → Encounter | Candidate physical/simulated vessel identities and two snapshots at common anchor/session | `Encounter` with pair/encounter/session IDs, A/B snapshots, common EN origin/current distance/status | `contracts/encounter.schema.json`; `contracts/integration_contract.md` | Shared; documented owner: Trung builds Encounter, Toàn supplies track/candidate | T09 pair/Encounter integration |
| Geographic track → EN/features | WGS84/source geographic status and ordered history | Common EN, each own anchor, X `[2,10,4]` float32; separate observed SOG/COG `[2,10,2]` float64 for Rule | `contracts/coordinate_contract.md`, `feature_contract.json`, `rule_input_contract.json` | Shared conversion; Trung owns feature/rule definition | Before online inference adapter |
| Encounter → inference request | Track-derived Encounter only; no future/labels | `RiskRequest`: request/session/model + Encounter | `contracts/risk_request.schema.json`; API `POST /api/v1/risk/evaluate` | Trung | API integration; not part of current T04 routes |
| Inference → forecast/risk | No new input beyond the request | M5a/CV status; 15-step forecast; CPA/CC-DRI; calibrated decision only when eligible | `forecast.schema.json`, `risk_response.schema.json`, `model_status.schema.json`, model/risk configs | Trung | Risk response implementation |
| Evaluation → alert | Replay session/reset and monotonically advancing anchor events | Per-pair alert lifecycle, last-valid snapshot, idempotent/atomic update | `alert.schema.json`; `contracts/integration_contract.md` | Trung alert owner; Toàn supplies session events | Before alert side effects |
| API → map | Track/Replay endpoints, stable ordering, session query and documented errors | Client renders track state now; later forecast/risk/alert layers | `api_contract.yaml` excludes track endpoints; T04 `backend/app/main.py`, `frontend/src/App.jsx` | Toàn track routes; shared API review | Before shared client generation/integration |

## Compatibility path and constraints

The T04 TrackSnapshot has the raw observations needed to begin a feature adapter, but it is not itself the model feature tensor. Conversion must preserve history order, use the common origin at vessel A's first history point (`t0−9`), subtract each vessel's own anchor for position channels, and compute east/north velocity from observed SOG/COG in the feature-defined convention. The Rule adapter must retain observed COG when SOG is zero; it must not reconstruct COG from velocity.

Offline and replay identity must stay distinct. `DatasetLoader` preserves official tensor A/B indices; replay mapping is proposed using namespaced IDs and a deterministic pair hash. Do not reorder locked offline tensors using replay rules. `pair_id` names a pair; `encounter_id` names an anchor-specific evaluation; `replay_session_id` scopes state and reset.

`EncounterDataset` returns `model_input` and a separate `ground_truth` containing targets/labels. A live API must not accept or forward future data, labels, rule ground truth, thresholds, or client-computed features as authoritative inputs.

## Suggested parallel work

- Toàn can build the source reader, timestamp parser, replay-clock abstraction, QC and per-vessel buffer behind internal interfaces while the integration fields are reviewed.
- Trung can work independently on model/config/calibration and static contract validation. `src/models/` and `src/risk/` have no runtime implementation in this repository snapshot.
- Keep cross-boundary adapters behind explicit interfaces until the decisions in `CONTRACT_DECISION_CHECKLIST.md` are approved. This is a boundary constraint, not a requirement to block independent work.
