# T17 Forecast Map Report

## Result

Added a client-side mock Forecast V1 adapter and a dashed Leaflet forecast layer for a selected Replay track. The UI labels the layer **MOCK FORECAST — NOT MODEL OUTPUT** and states that it carries no risk score, CPA, threshold, or alert.

The adapter only creates output for a `VALID` track with `source_type=SYNTHETIC_AIS`, `is_simulated=true`, a valid UTC anchor, and valid anchor geography. It generates 15 one-minute UTC timestamps and two synthetic EN/lat-lon paths. The coordinate metadata is marked `geographic_availability=SIMULATED` and `geographic_mapping_status=VERIFIED_SIMULATED`. It returns no forecast for a real AIS track or invalid/stale track.

The validator checks exact Forecast V1 fields, array shapes `[2,15,2]` and `[2,2]`, finite values, timestamp progression, EN composition, geographic bounds, and the unavailable-geography/null rule. `contracts/forecast.schema.json` and other Contract V1 artifacts were not changed.

## Boundaries

- This is deterministic synthetic visualization for the fixture only; it is not model inference or a forecast-quality claim.
- No Model, Risk, CPA, threshold, Alert, or ground-truth/future-label logic was added.
- Production AIS forecast coordinates remain unsupported here. The mock layer is disabled until a track is selected and the user enables it.

## Evidence

- Forecast adapter tests: 5 cases included in the 15 passing frontend tests.
- Generated a synthetic sample from `buildMockForecastV1` and validated it against the checked-in Forecast V1 JSON Schema with the common-schema references: **PASS**.
- Production Vite build: **PASS**.
- Browser rendering evidence: **PENDING_MANUAL**; no Chrome visual result is asserted.

