# S5 synthetic demo geographic relocation

- Task: `AIT3040_S5_DEMO_GEOGRAPHIC_FIX`; base `312107855374943b8dcf9c195a73c969580de57a`; branch `s5-demo-geographic-fix`.
- Synthetic simulation only: vessel reports are generated, not real AIS. No model training, benchmark, calibration, threshold, G11, Contract V1 or scheduler change.

## Cause and method

The original source `s5-01-synthetic-denmark-v1` generated coordinates around 55.70° N, 12.50° E, near Copenhagen. Natural Earth identifies 93/100 source observations and 89/95 unique history segments as intersecting mapped land. Both M5a and CV predictions also intersected mapped land. Inspection of the projection, inverse projection, forecast outputs and frontend coordinate use found no evidence that latitude/longitude order or frontend rendering caused this: the underlying synthetic coordinates were on land. This is a bounded finding for the inspected fixture, not a proof about other inputs.

The new source `s5-01-synthetic-denmark-water-v2` is centred on 55.70° N, 15.30° E, in the Baltic east/northeast of Bornholm. It translates every longitude by +2.80° at the same latitude: the existing local EN frame, velocities, histories, ordering, and 15-minute horizons are preserved. `_events_legacy()` retains the original exact event generator for regression; the old source is not registered as a second live replay source. A and B begin at (55.70, 12.45) and (55.70, 12.55), heading 90° and 270°; C at (55.75, 12.50), heading 0°; D at (55.65, 12.50), heading 180°; E at (55.72, 12.50), heading 0°. All speeds are 6 kn. A–D appear at minute 0, E at minute 5; events end at minute 20, with the source end at 00:21 exclusive. New longitudes are +2.80° for every vessel. The 95 adjacent history segments cover all history windows because each window is made of these same consecutive segments.

## Geographic QC

Primary land polygons: Natural Earth 1:10m physical land v5.1.1, cartographic scale **1:10,000,000**, SHA-256 `e547d749445eaa0964aba76738090ec88f5e63c4585122170f98c67a7ea922dc`; https://www.naturalearthdata.com/downloads/10m-physical-vectors/10m-land/ . Distance computed in WGS84 / UTM 33N (EPSG:32633). Supplement: OpenStreetMap map API bounding box 15.10–15.50 E, 55.50–55.90 N, SHA-256 `c897f202d789021864853da577f341c6c306abe72a4db8829b75aff8b727e851`; OpenStreetMap contributors, ODbL. Returned objects contained no tagged coastline, land, island or islet; all demo points lie inside that box.

| Item | Checked | On/intersect mapped land |
|---|---:|---:|
| Source/history points | 100 | 0 |
| Unique consecutive history segments | 95 | 0 |
| M5a forecast points | 3,000 | 0 |
| M5a forecast segments including anchor-to-first-point | 3,000 | 0 |
| CV forecast points | 3,000 | 0 |
| CV forecast segments including anchor-to-first-point | 3,000 | 0 |
| M5a CPA markers | 200 | 0 |

Forecast QC covers every eligible pair at each minute 00:09–00:20: 100 pair–anchors. Earlier minutes lack the minimum history, while 00:21 is outside the source interval. Minimum distance of the entire tested line footprint to **mapped** Natural Earth land is approximately 30.70 km. No fallback occurred. Geographic bounds are 55.59167–55.80833 N, 15.24649–15.35352 E.

**Limitations:** Natural Earth is generalized cartography; “10m” refers to map scale, not 10-metre positional accuracy. The OSM API may miss a way crossing the query box with no node inside and OSM itself can be incomplete. Thus the QC passes against the listed datasets, but does not prove that every small island or navigational hazard is absent; nautical-chart-grade geographic verification remains incomplete. No forecast points were hidden, snapped or altered.

## Frozen runtime parity

All 120 candidate pair–anchors (100 eligible, 20 insufficient) preserved decision/status and model/fallback. Maximum measured absolute difference for event EN, history EN, forecast EN, pair distance, risk, current DCPA/TCPA, predicted DCPA/time is 0 in the saved comparisons. No relocation tolerance was assumed.

| UTC | Pair | Risk old = new | Current DCPA NM | Current TCPA min | Predicted DCPA NM | Predicted CPA min | Decision |
|---|---|---:|---:|---:|---:|---:|---|
| 00:09 | A–B | 0.8832455466 | ~0 | 7.9057814681 | 0.0588161852 | 8 | ALERT |
| 00:09 | A–C | 0.2000000001 | 3.9793232850 | -15.5471092659 | 4.0560958110 | 1 | NO ALERT |
| 00:09 | A–E | unavailable | — | — | — | — | INSUFFICIENT_DATA |
| 00:15 | A–B | 0.9638132257 | ~0 | 1.9057814681 | 0.0298667820 | 2 | ALERT |

All pairs: 00:09 = 1 ALERT / 5 NO ALERT / 4 UNAVAILABLE; 00:15 = 1 / 9 / 0. The 20-row comparison and QC summary are committed in `results/s5_demo_geographic_fix/`. The large full-sweep JSON and downloaded geographic datasets are retained separately as local evidence and are not distributed in this branch. To rerun `scripts/demo_geographic_qc.py`, provide the two source datasets at the paths in that script and regenerate or supply `baseline.json` and `relocated.json`; the source URLs and SHA-256 values are recorded above.

## Tests and operation

- Targeted backend pytest: 26 passed, including fixture, relocation, temporal/source guard, locked M5a inference and actual 00:09/00:15 risk coverage; no full project regression or T15.
- Geographic QC script asserts point/segment checks and decision parity; full output in `results/s5_demo_geographic_fix/geographic_qc.json`.
- Frontend: 65 tests passed across 4 files; production build passed. `FitTracks` logic was unchanged; viewport behavior is covered by automated tests. Trung separately confirmed that the demo works in Chrome; that confirmation is user-reported browser evidence, distinct from the automated test results.
- The backend startup script failed under Windows PowerShell because its Python `-c` probe loses nested quote characters. The same backend was started directly with the configured environment and Uvicorn; frontend is started separately. The source startup script was not changed.
- Manual PAUSED evaluation and automatic scheduler DISABLED are retained. API checks and service status are recorded in the delivery message. Original V1 checkout remains clean; S6 status matches its pre-task snapshot.

## Manual Chrome retest

1. Open http://127.0.0.1:5173/ and select the S5 synthetic mode. Start the synthetic session; E only appears after minute 5.
2. Check PLAY and PAUSE, then SEEK to 00:09 and evaluate A–B and all pairs; expect 1/5/4. SEEK to 00:15 and evaluate all; expect 1/9/0.
3. Inspect vessel arrows, history, M5a/CV forecast and CPA markers over the Baltic. Zoom and pan manually, wait through several polls and confirm the view remains fixed.
4. Check RESET and that automatic monitoring is DISABLED. Confirm browser network requests do not return HTTP 503. Trung has confirmed the demo works in Chrome; the automated checks above are reported separately.

## Direct backend startup workaround

From the repository root in PowerShell, load the same local `.env` configuration and run Uvicorn directly. Set `$python` to the Python environment that has the project dependencies; the external model package and pin must be configured in `.env`.

```powershell
foreach ($raw in Get-Content -LiteralPath .env) {
    $line = $raw.Trim()
    if (-not $line -or $line.StartsWith('#')) { continue }
    if ($line -match '^(?<key>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?<value>.*)$') {
        $value = $Matches.value.Trim().Trim('"').Trim("'")
        [Environment]::SetEnvironmentVariable($Matches.key, $value, 'Process')
    }
}
$env:PYTHONDONTWRITEBYTECODE = '1'
$python = 'C:\Users\MSI\Desktop\PROJECT_AIT3040\.venv\Scripts\python.exe'
& $python -B -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --log-level info
```

The existing startup script's quoting issue has not been changed in this release.
