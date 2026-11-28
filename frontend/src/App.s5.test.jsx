import { webcrypto, createHash } from 'node:crypto'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import App from './App.jsx'

vi.mock('react-leaflet', () => ({
  MapContainer: ({ children }) => <div>{children}</div>, TileLayer: () => null,
  Polyline: ({ positions, pathOptions }) => <output data-testid={pathOptions.className} data-positions={JSON.stringify(positions)} />,
  CircleMarker: ({ children, center }) => <output data-testid="cpa-marker" data-center={JSON.stringify(center)}>{children}</output>,
  Marker: ({ children, eventHandlers }) => <button data-testid="marker" onClick={eventHandlers.click}>{children}</button>,
  Tooltip: ({ children }) => <span>{children}</span>, useMap: () => ({ setView: vi.fn(), fitBounds: vi.fn() }),
}))
vi.mock('leaflet', () => ({ default: { divIcon: (config) => config } }))

const anchor = '2024-11-01T00:09:00Z'
const sessionId = '123e4567-e89b-42d3-a456-426614174000'
const snapshotId = '123e4567-e89b-42d3-a456-426614174001'
const ids = ['a', 'b', 'c', 'd', 'e'].map((name) => `simulated:s5-01:${name}`)
const pairs = [[0,1],[0,2],[0,3],[0,4],[1,2],[1,3],[1,4],[2,3],[2,4],[3,4]].map(([a,b], index) => ({
  pair_id: `pair:v1:${String.fromCharCode(97 + index).repeat(64)}`,
  vessel_ids: [ids[a], ids[b]], unavailable_reason: a === 4 || b === 4 ? 'INSUFFICIENT_OR_INVALID_HISTORY' : null,
}))
const pairId = pairs[0].pair_id
const secondPair = pairs[1].pair_id
const unavailablePair = pairs[3].pair_id
const session = { session_id: sessionId, source_id: 's5-01-synthetic-denmark-water-v2', simulation_time: anchor, status: 'PAUSED', version: 0 }
const coverage = { session_id: sessionId, session_version: 0, snapshot_id: snapshotId, anchor_utc: anchor, expected: 10, evaluated: 10, eligible: 6, unavailable: 4, pairs }
const tracks = ids.map((id, index) => {
  const point = { nominal_timestamp: anchor, source_timestamp: anchor, original_source_timestamp: null, source_age_seconds: 0, latitude: 55.7 + index * 0.01, longitude: 12.5 + index * 0.01, sog_kn: 6, cog_deg: 90 }
  return { vessel_id: id, mmsi: null, source_type: 'SYNTHETIC_AIS', is_simulated: true, anchor_timestamp: anchor, current_state: index === 4 ? null : point, history: [point], data_status: index === 4 ? 'INSUFFICIENT_DATA' : 'VALID' }
})
const lines = [0, 1].map((vessel) => Array.from({ length: 15 }, (_, i) => [55.7 + vessel * 0.01 + i * 0.001, 12.5 + vessel * 0.01]))
const encId = 'enc:v1:' + createHash('sha256').update(JSON.stringify([sessionId, pairId, anchor])).digest('hex')
function result(overrides = {}, pair = pairs[0]) {
  const encounter = 'enc:v1:' + createHash('sha256').update(JSON.stringify([sessionId, pair.pair_id, anchor])).digest('hex')
  return { session_id: sessionId, session_version: 0, snapshot_id: snapshotId, anchor_utc: anchor,
    risk: { schema_version: '1.0.0', replay_session_id: sessionId, pair_id: pair.pair_id, anchor_timestamp: anchor, encounter_id: encounter, vessel_ids: pair.vessel_ids, alert_triggered: pair.unavailable_reason ? null : pair.pair_id === pairId, decision_status: pair.unavailable_reason ? 'INSUFFICIENT_DATA' : 'DECIDED', decision_reason: pair.unavailable_reason || 'THRESHOLD_APPLIED', risk_score: pair.unavailable_reason ? null : pair.pair_id === pairId ? 0.883246 : 0.2, threshold: 0.42, current_dcpa_nm: pair.unavailable_reason ? null : 0.01, current_tcpa_minutes: pair.unavailable_reason ? null : 8, predicted_min_distance_nm: pair.unavailable_reason ? null : 0.058816, predicted_closest_time_minutes: pair.unavailable_reason ? null : 8, predicted_closest_timestamp: pair.unavailable_reason ? null : new Date(Date.parse(anchor) + 8 * 60000).toISOString().replace('.000Z', 'Z'), current_cpa_status: pair.unavailable_reason ? 'UNAVAILABLE' : 'AVAILABLE', predicted_cpa_score: pair.unavailable_reason ? null : 0.85, current_cpa_score: pair.unavailable_reason ? null : 0.85, rule_score: pair.unavailable_reason ? null : 1, forecast_status: pair.unavailable_reason ? 'NOT_RUN' : 'AVAILABLE', model_status: { active_model: 'M5A', fallback_used: false }, forecast: pair.unavailable_reason ? null : { forecast_lat_lon: lines, geographic_availability: 'SIMULATED', forecast_timestamps: Array.from({ length: 15 }, (_, i) => new Date(Date.parse(anchor) + (i + 1) * 60000).toISOString()) }, ...(overrides.risk || {}) }, ...Object.fromEntries(Object.entries(overrides).filter(([key]) => key !== 'risk')) }
}
function alertItem(pair = pairs[0], status = 'ACTIVE') {
  const encounter = 'enc:v1:' + createHash('sha256').update(JSON.stringify([sessionId, pair.pair_id, anchor])).digest('hex')
  return { schema_version: '1.0.0', alert_id: `alert-${pair.pair_id.slice(-4)}-${status}`, replay_session_id: sessionId,
    pair_id: pair.pair_id, opened_encounter_id: encounter, latest_encounter_id: encounter, vessel_ids: pair.vessel_ids,
    opened_at: anchor, updated_at: anchor, closed_at: status === 'RESOLVED' ? anchor : null,
    latest_evaluation_timestamp: anchor, risk_score: 0.883246, threshold: 0.42, predicted_min_distance_nm: 0.058816,
    predicted_closest_time_minutes: 8, current_dcpa_nm: 0.01, current_tcpa_minutes: 8, active_model: 'M5A',
    alert_status: status, status_reason: status === 'ACTIVE' ? 'THRESHOLD_MET' : status,
    values_as_of: status === 'DATA_UNAVAILABLE' ? '2024-11-01T00:08:00Z' : anchor, values_are_last_valid: status === 'DATA_UNAVAILABLE' }
}
const ok = (data) => ({ ok: true, status: 200, json: async () => data })
let evaluation
let alertResponse
let sessionCreate
let activeSessionResponse
let schedulerResponse
let candidatesResponse
let sessionResponse

beforeEach(() => {
  vi.stubGlobal('crypto', webcrypto)
  evaluation = (_url, options = {}) => {
    const request = JSON.parse(options.body || '{}')
    const pair = pairs.find((candidate) => candidate.pair_id === request.pair_id) || pairs[0]
    return Promise.resolve(ok(result({}, pair)))
  }
  alertResponse = () => Promise.resolve(ok({ session_id: sessionId, session_version: 0, snapshot_id: snapshotId, anchor_utc: anchor, total: 0, items: [] }))
  sessionCreate = () => Promise.resolve(ok(session))
  sessionResponse = session
  schedulerResponse = () => ({ monitoring_status: sessionResponse.status === 'PLAYING' ? 'PLAYING' : sessionResponse.status,
    session_id: sessionResponse.session_id, session_generation: sessionResponse.version, running: false,
    active_anchor: null, pending_anchor: null, latest_completed_anchor: null, latest_batch: null,
    last_outcome: null, last_error: null, skipped_anchors: [], failed_anchors: [], missed_deadlines: 0,
    latency_sample_count: 0, latency_p50_seconds: null, latency_p95_seconds: null })
  candidatesResponse = () => Promise.resolve(ok({ ...coverage, session_version: sessionResponse.version, anchor_utc: sessionResponse.simulation_time }))
  activeSessionResponse = () => Promise.resolve(ok({ session: null }))
  vi.stubGlobal('fetch', vi.fn((url, options = {}) => {
    const path = String(url)
    if (path.includes('/mock/tracks')) return Promise.resolve(ok({ items: [] }))
    if (path.endsWith('/runtime/status')) return Promise.resolve(ok({ runtime_status: 'READY' }))
    if (path.includes('/runtime/scheduler')) return Promise.resolve(ok(schedulerResponse(path, options)))
    if (path.endsWith('/runtime/active-session')) return activeSessionResponse(path, options)
    if (path.endsWith('/replay/sessions') && options.method === 'POST') return sessionCreate(path, options)
    if (path.endsWith('/candidates')) return candidatesResponse(path, options)
    if (path.includes('/tracks?')) return Promise.resolve(ok({ items: tracks, snapshot_id: snapshotId, simulation_time: anchor }))
    if (path.includes('/alerts?')) return alertResponse(path, options)
    if (path.endsWith('/evaluate')) return evaluation(path, options)
    if (path.endsWith('/control')) {
      sessionResponse = { ...sessionResponse, status: options.body && JSON.parse(options.body).action === 'PAUSE' ? 'PAUSED' : 'PLAYING', version: sessionResponse.version + 1 }
      return Promise.resolve(ok(sessionResponse))
    }
    if (path.endsWith(sessionId)) return Promise.resolve(ok(sessionResponse))
    return Promise.resolve({ ok: false, status: 404, json: async () => ({ message: 'not found' }) })
  }))
})
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

it('keeps PLAYING replay free of candidate and scheduler requests', async () => {
  sessionCreate = () => {
    sessionResponse = { ...session, status: 'PLAYING', version: 1 }
    return Promise.resolve(ok(sessionResponse))
  }
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: 'S5 nhiều tàu' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Bắt đầu replay fixture' }))
  await screen.findAllByTestId('marker')
  expect(fetch.mock.calls.filter(([url]) => String(url).endsWith('/candidates'))).toHaveLength(0)
  expect(fetch.mock.calls.filter(([url]) => String(url).includes('/runtime/scheduler'))).toHaveLength(0)
  expect(screen.queryByRole('region', { name: 'Automatic monitoring' })).not.toBeInTheDocument()
})

async function openFixture() {
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: 'S5 nhiều tàu' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Bắt đầu replay fixture' }))
  await screen.findAllByText('A — B')
}

it('shows five markers, coverage, pair selection and actual forecast geometry', async () => {
  await openFixture()
  expect(screen.getAllByTestId('marker')).toHaveLength(5)
  expect(screen.getByText('Expected').parentElement).toHaveTextContent('10')
  fireEvent.click(screen.getByText('A — B'))
  fireEvent.click(screen.getByRole('button', { name: 'Dự báo cặp tàu' }))
  expect(await screen.findByText('M5a · ACTUAL MODEL')).toBeInTheDocument()
  const displayed = screen.getAllByTestId('forecast-real-path')
  expect(displayed).toHaveLength(2)
  expect(JSON.parse(displayed[0].dataset.positions)).toEqual(lines[0])
  expect(screen.getByText('Đường liền: history · Nét đứt: forecast')).toBeInTheDocument()
})

it('keeps unavailable pairs visible and reports DATA_UNAVAILABLE without fabricating forecast', async () => {
  await openFixture()
  fireEvent.click(screen.getByText('A — E'))
  expect(screen.getAllByText(/INSUFFICIENT_DATA/).length).toBeGreaterThan(0)
  fireEvent.click(screen.getByRole('button', { name: 'Dự báo cặp tàu' }))
  expect((await screen.findAllByText('UNAVAILABLE')).length).toBeGreaterThan(0)
  expect(screen.queryByTestId('forecast-real-path')).not.toBeInTheDocument()
  expect(fetch.mock.calls.filter(([url]) => String(url).endsWith('/evaluate'))).toHaveLength(1)
})

it.each([409, 503])('shows HTTP %s as unavailable without a forecast', async (status) => {
  evaluation = () => Promise.resolve({ ok: false, status, json: async () => ({ message: 'unavailable' }) })
  await openFixture()
  fireEvent.click(screen.getByText('A — B'))
  fireEvent.click(screen.getByRole('button', { name: 'Dự báo cặp tàu' }))
  expect(await screen.findByText(new RegExp(`HTTP ${status}`))).toBeInTheDocument()
  expect(screen.queryByTestId('forecast-real-path')).not.toBeInTheDocument()
})

it.each(['PLAY', 'SEEK tới mốc này', 'RESET', 'pair', 'mode'])('discards delayed evaluation after %s', async (action) => {
  let finish
  evaluation = () => new Promise((resolve) => { finish = resolve })
  await openFixture()
  fireEvent.click(screen.getByText('A — B'))
  fireEvent.click(screen.getByRole('button', { name: 'Dự báo cặp tàu' }))
  expect(screen.getByText('Đang đánh giá cặp tàu…')).toBeInTheDocument()
  if (action === 'pair') fireEvent.click(screen.getByText('A — C'))
  else if (action === 'mode') fireEvent.click(screen.getByRole('button', { name: 'Mock' }))
  else fireEvent.click(screen.getAllByRole('button', { name: action })[0])
  await act(async () => { finish(ok(result())); await Promise.resolve() })
  expect(screen.queryByTestId('forecast-real-path')).not.toBeInTheDocument()
  expect(screen.queryByText('M5a · ACTUAL MODEL')).not.toBeInTheDocument()
})

it.each(['session_id', 'session_version', 'snapshot_id', 'anchor_utc'])('rejects mismatched %s', async (field) => {
  evaluation = () => Promise.resolve(ok(result({ [field]: field === 'session_version' ? 8 : 'wrong' })))
  await openFixture()
  fireEvent.click(screen.getByText('A — B'))
  fireEvent.click(screen.getByRole('button', { name: 'Dự báo cặp tàu' }))
  await screen.findByText(/không khớp session/)
  expect(screen.queryByTestId('forecast-real-path')).not.toBeInTheDocument()
})

it('maps risk score and threshold as scores, and plots CPA from the matching forecast minute', async () => {
  await openFixture()
  fireEvent.click(screen.getByText('A — B'))
  fireEvent.click(screen.getByRole('button', { name: 'Dự báo cặp tàu' }))
  expect(await screen.findByText('0.883246')).toBeInTheDocument()
  expect(screen.getByText('Threshold 0.420 · M5A')).toBeInTheDocument()
  expect(screen.getByText(/KHÔNG PHẢI XÁC SUẤT/)).toBeInTheDocument()
  const cpa = screen.getAllByTestId('cpa-marker')
  expect(cpa).toHaveLength(2)
  expect(JSON.parse(cpa[0].dataset.center)).toEqual(lines[0][7])
  expect(JSON.parse(cpa[1].dataset.center)).toEqual(lines[1][7])
})

it('labels CV fallback and uses its response threshold and decision', async () => {
  evaluation = () => Promise.resolve(ok(result({ risk: { model_status: { active_model: 'CV', fallback_used: true }, threshold: 0.435, risk_score: 0.44, alert_triggered: true } })))
  await openFixture()
  fireEvent.click(screen.getByText('A — B'))
  fireEvent.click(screen.getByRole('button', { name: 'Dự báo cặp tàu' }))
  expect(await screen.findByText('CV FALLBACK')).toBeInTheDocument()
  expect(screen.getByText('Threshold 0.435 · CV · FALLBACK')).toBeInTheDocument()
  expect(screen.getByText('0.440000')).toBeInTheDocument()
})

it.each(['ACTIVE', 'DATA_UNAVAILABLE', 'RESOLVED'])('renders API alert lifecycle state %s without remapping it', async (status) => {
  alertResponse = () => Promise.resolve(ok({ session_id: sessionId, session_version: 0, snapshot_id: snapshotId, anchor_utc: anchor, total: 1, items: [alertItem(pairs[0], status)] }))
  await openFixture()
  fireEvent.click(screen.getByText('A — B'))
  fireEvent.click(screen.getByRole('button', { name: 'Dự báo cặp tàu' }))
  expect(await screen.findAllByText(status)).not.toHaveLength(0)
  if (status === 'DATA_UNAVAILABLE') expect(screen.getByText(/lần hợp lệ gần nhất/)).toBeInTheDocument()
})

it('evaluates every candidate once and reports alert, no-alert, and unavailable separately', async () => {
  alertResponse = () => Promise.resolve(ok({ session_id: sessionId, session_version: 0, snapshot_id: snapshotId, anchor_utc: anchor, total: 1, items: [alertItem()] }))
  await openFixture()
  fireEvent.click(screen.getByRole('button', { name: 'Đánh giá tất cả 10 cặp' }))
  expect(await screen.findByText('Batch hoàn tất')).toBeInTheDocument()
  const progress = screen.getByLabelText('Tiến độ đánh giá tất cả cặp')
  expect(progress).toHaveTextContent('Đã xử lý 10/10')
  expect(progress).toHaveTextContent('Alert 1')
  expect(progress).toHaveTextContent('No-alert 5')
  expect(progress).toHaveTextContent('Unavailable 4')
  expect(progress).toHaveTextContent('Failed 0')
  expect(progress).toHaveTextContent('Pending 0')
  expect(fetch.mock.calls.filter(([url]) => String(url).endsWith('/evaluate'))).toHaveLength(10)
  expect(screen.getAllByText('ACTIVE')).not.toHaveLength(0)
})

it('reuses a valid single-pair evaluation when the user runs evaluate-all', async () => {
  await openFixture()
  fireEvent.click(screen.getByText('A — B'))
  fireEvent.click(screen.getByRole('button', { name: 'Dự báo cặp tàu' }))
  await screen.findByText('M5a · ACTUAL MODEL')
  await waitFor(() => expect(fetch.mock.calls.some(([url]) => String(url).includes('/alerts?'))).toBe(true))
  fireEvent.click(screen.getByRole('button', { name: 'Đánh giá tất cả 10 cặp' }))
  expect(await screen.findByText('Batch hoàn tất')).toBeInTheDocument()
  expect(fetch.mock.calls.filter(([url]) => String(url).endsWith('/evaluate'))).toHaveLength(10)
})

it('continues a partial batch after one failed request and counts the failure', async () => {
  evaluation = (url, options = {}) => {
    const body = JSON.parse(options.body || '{}')
    if (body.pair_id === pairs[1].pair_id) return Promise.resolve({ ok: false, status: 500, json: async () => ({ message: 'temporary error' }) })
    const pair = pairs.find((candidate) => candidate.pair_id === body.pair_id)
    return Promise.resolve(ok(result({}, pair)))
  }
  await openFixture()
  fireEvent.click(screen.getByRole('button', { name: 'Đánh giá tất cả 10 cặp' }))
  expect(await screen.findByText('Batch hoàn tất')).toBeInTheDocument()
  const progress = screen.getByLabelText('Tiến độ đánh giá tất cả cặp')
  expect(progress).toHaveTextContent('Failed 1')
  expect(progress).toHaveTextContent('Pending 0')
  expect(fetch.mock.calls.filter(([url]) => String(url).endsWith('/evaluate'))).toHaveLength(10)
})

it('cancels a running batch and rejects its delayed response after pair change', async () => {
  let finish
  evaluation = () => new Promise((resolve) => { finish = resolve })
  await openFixture()
  fireEvent.click(screen.getByRole('button', { name: 'Đánh giá tất cả 10 cặp' }))
  await waitFor(() => expect(finish).toBeDefined())
  fireEvent.click(screen.getAllByText('A — C')[0])
  await act(async () => { finish(ok(result())); await Promise.resolve() })
  expect(await screen.findByText('Batch đã dừng')).toBeInTheDocument()
  expect(fetch.mock.calls.filter(([url]) => String(url).endsWith('/evaluate'))).toHaveLength(1)
  expect(screen.queryByTestId('forecast-real-path')).not.toBeInTheDocument()
})

it.each(['pair', 'SEEK', 'RESET', 'PLAY', 'mode'])('rejects a delayed alert response after %s changes the binding', async (action) => {
  let finishAlerts
  alertResponse = () => new Promise((resolve) => { finishAlerts = resolve })
  await openFixture()
  fireEvent.click(screen.getByText('A — B'))
  fireEvent.click(screen.getByRole('button', { name: 'Dự báo cặp tàu' }))
  expect(await screen.findByText('M5a · ACTUAL MODEL')).toBeInTheDocument()
  await waitFor(() => expect(finishAlerts).toBeDefined())
  if (action === 'pair') fireEvent.click(screen.getAllByText('A — C')[0])
  else if (action === 'mode') fireEvent.click(screen.getByRole('button', { name: 'Mock' }))
  else fireEvent.click(action === 'SEEK' ? screen.getByText('SEEK tới mốc này') : screen.getAllByText(action)[0])
  await act(async () => { finishAlerts(ok({ session_id: sessionId, session_version: 0, snapshot_id: snapshotId, anchor_utc: anchor, total: 1, items: [alertItem()] })); await Promise.resolve() })
  expect(document.querySelector('.alert-card')).toBeNull()
})

it('restores the active S5 session after entering S5 without creating a second session', async () => {
  activeSessionResponse = () => Promise.resolve(ok({ session: { ...session, status: 'READY' } }))
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: 'S5 nhiều tàu' }))
  await screen.findByText('A — B')
  expect(screen.getByTestId('simulation-time')).toHaveTextContent(anchor)
  expect(fetch.mock.calls.filter(([url, options]) => String(url).endsWith('/replay/sessions') && options?.method === 'POST')).toHaveLength(0)
})

it('recovers the active session after a create race returns HTTP 409', async () => {
  let discoveryCount = 0
  activeSessionResponse = () => Promise.resolve(ok({ session: ++discoveryCount >= 3 ? session : null }))
  sessionCreate = () => Promise.resolve({ ok: false, status: 409, json: async () => ({ detail: { message: 'Only one active fixture session per process is supported' } }) })
  await openFixture()
  expect(screen.getByTestId('session-id')).toHaveTextContent(sessionId)
  expect(fetch.mock.calls.filter(([url, options]) => String(url).endsWith('/replay/sessions') && options?.method === 'POST')).toHaveLength(1)
  expect(screen.queryByText(/HTTP 409/)).not.toBeInTheDocument()
})

it('shows a retry action when active-session discovery fails', async () => {
  activeSessionResponse = () => Promise.resolve({ ok: false, status: 503, json: async () => ({ detail: { message: 'temporarily unavailable' } }) })
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: 'S5 nhiều tàu' }))
  expect((await screen.findAllByText(/HTTP 503/)).length).toBeGreaterThan(0)
  activeSessionResponse = () => Promise.resolve(ok({ session }))
  fireEvent.click(screen.getByRole('button', { name: 'Thử lại khôi phục phiên' }))
  await screen.findByText('A — B')
  expect(screen.getByTestId('session-id')).toHaveTextContent(sessionId)
})

it('ignores a delayed session recovery response after the user changes mode', async () => {
  let finishDiscovery
  activeSessionResponse = () => new Promise((resolve) => { finishDiscovery = resolve })
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: 'S5 nhiều tàu' }))
  await waitFor(() => expect(finishDiscovery).toBeDefined())
  fireEvent.click(screen.getByRole('button', { name: 'Mock' }))
  await act(async () => { finishDiscovery(ok({ session })); await Promise.resolve() })
  expect(screen.queryByText('A — B')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Mock' })).toHaveAttribute('aria-pressed', 'true')
  expect(fetch.mock.calls.some(([url]) => String(url).endsWith('/candidates'))).toBe(false)
})
