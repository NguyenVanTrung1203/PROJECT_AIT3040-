import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import App from './App.jsx'
import fixtureEvents from '../../backend/app/fixtures/t12_replay_events.json'

vi.mock('react-leaflet', () => ({
  MapContainer: ({ children }) => <div data-testid="map">{children}</div>,
  TileLayer: () => <div data-testid="tile-layer" />,
  Polyline: ({ positions, pathOptions }) => <output data-testid="history-line" data-class={pathOptions?.className} data-positions={JSON.stringify(positions)} />,
  Marker: ({ position, eventHandlers, children, icon }) => (
    <button data-testid="marker" data-position={JSON.stringify(position)} data-icon-html={icon?.html} onClick={eventHandlers?.click}>
      {children}
    </button>
  ),
  Tooltip: ({ children }) => <span>{children}</span>,
  useMap: () => ({ setView: vi.fn(), fitBounds: vi.fn() }),
}))

vi.mock('leaflet', () => ({ default: { divIcon: (config) => config } }))

const anchor = '2025-10-01T12:00:00Z'

function makeTrack(id, status = 'VALID', offset = 0) {
  const history = Array.from({ length: 10 }, (_, index) => {
    const nominal = new Date(Date.parse(anchor) - (9 - index) * 60_000).toISOString()
    return {
      nominal_timestamp: nominal,
      source_timestamp: nominal,
      original_source_timestamp: null,
      latitude: 55.68 + offset + index * 0.0001,
      longitude: 12.56 + offset + index * 0.0002,
      sog_kn: 10,
      cog_deg: 45,
      source_age_seconds: 0,
    }
  })
  return {
    schema_version: '1.0.0',
    vessel_id: id,
    mmsi: null,
    source_type: 'SYNTHETIC_AIS',
    is_simulated: true,
    anchor_timestamp: anchor,
    current_state: history.at(-1),
    history,
    data_status: status,
  }
}

function makeStaleTrack(id) {
  const track = makeTrack(id, 'STALE')
  const latest = {
    ...track.history.at(-1),
    source_timestamp: new Date(Date.parse(anchor) - 180_000).toISOString(),
    source_age_seconds: 180,
  }
  track.history[track.history.length - 1] = latest
  track.current_state = latest
  return track
}

function makePartialTrack(id, anchorTime, latitude, longitude, sourceTime = anchorTime) {
  const point = {
    nominal_timestamp: anchorTime,
    source_timestamp: sourceTime,
    original_source_timestamp: sourceTime,
    latitude,
    longitude,
    sog_kn: 8,
    cog_deg: 45,
    source_age_seconds: (Date.parse(anchorTime) - Date.parse(sourceTime)) / 1000,
  }
  return {
    schema_version: '1.0.0',
    vessel_id: id,
    mmsi: null,
    source_type: 'SYNTHETIC_AIS',
    is_simulated: true,
    anchor_timestamp: anchorTime,
    current_state: null,
    history: [point],
    data_status: 'INSUFFICIENT_DATA',
  }
}

function apiResponse(items, total = items.length) {
  return { ok: true, json: async () => ({ items, total }) }
}

function detailResponse(track) {
  return { ok: true, json: async () => track }
}

function replaySession(id, status, version, simulationTime = '2024-11-01T00:09:00Z') {
  return { session_id: id, source_id: 'fixture-denmark-10m-v1', simulation_time: simulationTime, status, version }
}

function replayPage(items, snapshotId = '123e4567-e89b-42d3-a456-426614174010', simulationTime = '2024-11-01T00:09:00Z') {
  return { ok: true, json: async () => ({ items, total: items.length, snapshot_id: snapshotId, simulation_time: simulationTime }) }
}

describe('mock track map', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('renders mock markers and history with Leaflet latitude/longitude order', async () => {
    const one = makeTrack('mock-vessel-001')
    const two = makeTrack('mock-vessel-002', 'STALE', 0.02)
    fetch.mockResolvedValueOnce(apiResponse([one, two]))
    render(<App />)

    expect(await screen.findByText('mock-vessel-001')).toBeInTheDocument()
    expect(screen.getByTestId('tile-layer')).toBeInTheDocument()
    const markers = screen.getAllByTestId('marker')
    expect(markers).toHaveLength(2)
    expect(JSON.parse(markers[0].dataset.position)).toEqual([one.current_state.latitude, one.current_state.longitude])
    const lines = screen.getAllByTestId('history-line')
    expect(lines).toHaveLength(2)
    expect(JSON.parse(lines[0].dataset.positions)).toHaveLength(10)
    expect(screen.getByText('MOCK DATA')).toBeInTheDocument()
  })

  it('loads selected vessel details and shows its UTC history', async () => {
    const track = makeTrack('mock-vessel-001')
    fetch.mockResolvedValueOnce(apiResponse([track])).mockResolvedValueOnce(detailResponse(track))
    render(<App />)
    const marker = await screen.findByTestId('marker')
    fireEvent.click(marker)
    expect(await screen.findByLabelText('Chi tiết tàu được chọn')).toBeInTheDocument()
    expect(screen.getByText('10/10 mốc · đến anchor')).toBeInTheDocument()
    const historyRows = screen.getAllByRole('listitem')
    expect(historyRows).toHaveLength(10)
    expect(historyRows[0]).toHaveTextContent('2025-10-01T12:00:00Z')
  })

  it('shows empty state when API returns no tracks', async () => {
    fetch.mockResolvedValueOnce(apiResponse([]))
    render(<App />)
    expect(await screen.findByText('Chưa có tàu trong snapshot')).toBeInTheDocument()
    expect(screen.getByText('Chưa có snapshot để hiển thị.')).toBeInTheDocument()
  })

  it('shows API error and retries after the user asks', async () => {
    fetch.mockRejectedValueOnce(new Error('API offline')).mockResolvedValueOnce(apiResponse([]))
    render(<App />)
    expect(await screen.findByText('Replay/Mock API lỗi')).toBeInTheDocument()
    expect(screen.getByText('API offline')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }))
    expect(await screen.findByText('Chưa có tàu trong snapshot')).toBeInTheDocument()
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))
  })

  it('refreshes the list and renders stale age for mock-vessel-004', async () => {
    const valid = makeTrack('mock-vessel-001')
    const stale = makeStaleTrack('mock-vessel-004')
    fetch.mockResolvedValueOnce(apiResponse([valid]))
      .mockResolvedValueOnce(apiResponse([stale]))
      .mockResolvedValueOnce(detailResponse(stale))
    render(<App />)

    expect(await screen.findByText('mock-vessel-001')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Refresh replay data' }))
    expect(await screen.findByText('mock-vessel-004')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('marker'))
    expect(await screen.findByText('STALE MOCK')).toBeInTheDocument()
    expect(screen.getByText('age 180s')).toBeInTheDocument()
    expect(fetch).toHaveBeenCalledTimes(3)
  })
})

describe('Replay V1 fixture map', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('starts and resets a fixture session into a separate session', async () => {
    const track = makeTrack('simulated:t12-demo:kattegat-001')
    const session = { session_id: '123e4567-e89b-42d3-a456-426614174000', source_id: 'fixture-denmark-10m-v1', simulation_time: '2024-11-01T00:00:00Z', status: 'READY', version: 0 }
    const resetSession = { session_id: '123e4567-e89b-42d3-a456-426614174001', source_id: 'fixture-denmark-10m-v1', simulation_time: '2024-11-01T00:00:00Z', status: 'READY', version: 0 }
    fetch.mockResolvedValueOnce(apiResponse([]))
      .mockResolvedValueOnce({ ok: true, json: async () => session })
      .mockResolvedValueOnce({ ok: true, json: async () => session })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ items: [track], total: 1, snapshot_id: '123e4567-e89b-42d3-a456-426614174010', simulation_time: anchor }) })
      .mockResolvedValueOnce(detailResponse(track))
      .mockResolvedValueOnce({ ok: true, json: async () => resetSession })
      .mockResolvedValueOnce({ ok: true, json: async () => resetSession })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ items: [track], total: 1, snapshot_id: '123e4567-e89b-42d3-a456-426614174011', simulation_time: anchor }) })

    render(<App />)
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1))
    fireEvent.click(screen.getByRole('button', { name: 'Replay fixture' }))
    fireEvent.click(screen.getByRole('button', { name: 'Bắt đầu replay fixture' }))

    const marker = await screen.findByTestId('marker')
    expect(screen.getByTestId('simulation-time')).toHaveTextContent('2024-11-01T00:00:00Z')
    expect(JSON.parse(marker.dataset.position)).toEqual([track.current_state.latitude, track.current_state.longitude])
    fireEvent.click(marker)
    await waitFor(() => expect(document.querySelectorAll('.history-list li')).toHaveLength(10))
    expect(screen.getByText(/SYNTHETIC_AIS.*simulated trajectory/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Reset replay' }))
    expect(await screen.findByText(/123e4567-e89b-42d3-a456-426614174001/)).toBeInTheDocument()
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(8))
    expect(fetch.mock.calls[1][1].method).toBe('POST')
    expect(JSON.parse(fetch.mock.calls[1][1].body)).toMatchObject({ source_id: 'fixture-denmark-10m-v1' })
    expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({ source_id: 'fixture-denmark-10m-v1' })
    expect(fetch.mock.calls[5][1].headers['Idempotency-Key']).toBeTruthy()
    expect(JSON.parse(fetch.mock.calls[5][1].body)).toMatchObject({ action: 'RESET', expected_version: 0 })
  })

  it('drives PLAY, PAUSE, RESUME, and SEEK with server versions and UTC target', async () => {
    const track = makeTrack('simulated:t12-demo:kattegat-001')
    const id = '123e4567-e89b-42d3-a456-426614174000'
    const seekId = '123e4567-e89b-42d3-a456-426614174099'
    fetch.mockResolvedValueOnce(apiResponse([]))
      .mockResolvedValueOnce({ ok: true, json: async () => replaySession(id, 'READY', 0) })
      .mockResolvedValueOnce({ ok: true, json: async () => replaySession(id, 'READY', 0) })
      .mockResolvedValueOnce(replayPage([track]))
      .mockResolvedValueOnce({ ok: true, json: async () => replaySession(id, 'PLAYING', 1) })
      .mockResolvedValueOnce({ ok: true, json: async () => replaySession(id, 'PLAYING', 1) })
      .mockResolvedValueOnce(replayPage([track]))
      .mockResolvedValueOnce({ ok: true, json: async () => replaySession(id, 'PAUSED', 2) })
      .mockResolvedValueOnce({ ok: true, json: async () => replaySession(id, 'PAUSED', 2) })
      .mockResolvedValueOnce(replayPage([track]))
      .mockResolvedValueOnce({ ok: true, json: async () => replaySession(seekId, 'PAUSED', 0, '2024-11-01T00:04:00Z') })
      .mockResolvedValueOnce({ ok: true, json: async () => replaySession(seekId, 'PAUSED', 0, '2024-11-01T00:04:00Z') })
      .mockResolvedValueOnce(replayPage([] , '123e4567-e89b-42d3-a456-426614174011', '2024-11-01T00:04:00Z'))

    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Replay fixture' }))
    fireEvent.click(screen.getByRole('button', { name: 'Bắt đầu replay fixture' }))
    await screen.findByRole('button', { name: 'PLAY', exact: true })

    fireEvent.click(screen.getByRole('button', { name: 'PLAY', exact: true }))
    await screen.findByRole('button', { name: 'PAUSE', exact: true })
    fireEvent.click(screen.getByRole('button', { name: 'PAUSE', exact: true }))
    await screen.findByRole('button', { name: 'RESUME', exact: true })
    fireEvent.change(screen.getByRole('slider', { name: 'Seek UTC time' }), { target: { value: '240' } })
    expect(screen.getByText('2024-11-01T00:04:00Z')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /SEEK/ }))

    expect(await screen.findByTestId('session-id')).toHaveTextContent(seekId)
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(13))
    expect(JSON.parse(fetch.mock.calls[4][1].body)).toEqual({ action: 'PLAY', expected_version: 0 })
    expect(JSON.parse(fetch.mock.calls[7][1].body)).toEqual({ action: 'PAUSE', expected_version: 1 })
    expect(JSON.parse(fetch.mock.calls[10][1].body)).toMatchObject({ action: 'SEEK', expected_version: 2, target_time: '2024-11-01T00:04:00Z' })
    expect(fetch.mock.calls[10][1].headers['Idempotency-Key']).toBeTruthy()
    expect(screen.queryByTestId('marker')).not.toBeInTheDocument()
  })

  it('retries a failed RESET with the same Idempotency-Key and never shows success early', async () => {
    const id = '123e4567-e89b-42d3-a456-426614174000'
    const newId = '123e4567-e89b-42d3-a456-426614174001'
    fetch.mockResolvedValueOnce(apiResponse([]))
      .mockResolvedValueOnce({ ok: true, json: async () => replaySession(id, 'READY', 0) })
      .mockResolvedValueOnce({ ok: true, json: async () => replaySession(id, 'READY', 0) })
      .mockResolvedValueOnce(replayPage([]))
      .mockResolvedValueOnce({ ok: false, status: 503, json: async () => ({ detail: { message: 'temporary failure' } }) })
      .mockResolvedValueOnce({ ok: true, json: async () => replaySession(newId, 'READY', 0, '2024-11-01T00:00:00Z') })
      .mockResolvedValueOnce({ ok: true, json: async () => replaySession(newId, 'READY', 0, '2024-11-01T00:00:00Z') })
      .mockResolvedValueOnce(replayPage([], '123e4567-e89b-42d3-a456-426614174011', '2024-11-01T00:00:00Z'))
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Replay fixture' }))
    fireEvent.click(screen.getByRole('button', { name: 'Bắt đầu replay fixture' }))
    await screen.findByTestId('session-id')
    fireEvent.click(screen.getByRole('button', { name: 'Reset replay' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('HTTP 503')
    expect(screen.getByTestId('session-id')).toHaveTextContent(id)
    fireEvent.click(screen.getByRole('button', { name: /Thử lại RESET/ }))
    expect(await screen.findByTestId('session-id')).toHaveTextContent(newId)
    expect(fetch.mock.calls[4][1].headers['Idempotency-Key']).toBe(fetch.mock.calls[5][1].headers['Idempotency-Key'])
    expect(fetch.mock.calls[4][1].body).toBe(fetch.mock.calls[5][1].body)
  })

  it('recovers from an expected-version conflict through a fresh server snapshot', async () => {
    const id = '123e4567-e89b-42d3-a456-426614174000'
    fetch.mockResolvedValueOnce(apiResponse([]))
      .mockResolvedValueOnce({ ok: true, json: async () => replaySession(id, 'READY', 0) })
      .mockResolvedValueOnce({ ok: true, json: async () => replaySession(id, 'READY', 0) })
      .mockResolvedValueOnce(replayPage([]))
      .mockResolvedValueOnce({ ok: false, status: 409, json: async () => ({ error_code: 'VERSION_CONFLICT', message: 'stale version' }) })
      .mockResolvedValueOnce({ ok: true, json: async () => replaySession(id, 'PAUSED', 1) })
      .mockResolvedValueOnce(replayPage([]))
      .mockResolvedValueOnce({ ok: true, json: async () => replaySession(id, 'PLAYING', 2) })
      .mockResolvedValueOnce({ ok: true, json: async () => replaySession(id, 'PLAYING', 2) })
      .mockResolvedValueOnce(replayPage([]))
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Replay fixture' }))
    fireEvent.click(screen.getByRole('button', { name: 'Bắt đầu replay fixture' }))
    await screen.findByRole('button', { name: 'PLAY', exact: true })
    fireEvent.click(screen.getByRole('button', { name: 'PLAY', exact: true }))
    expect(await screen.findByRole('alert')).toHaveTextContent('HTTP 409')
    expect(screen.getByRole('button', { name: 'PLAY', exact: true })).toBeEnabled()
    fireEvent.click(screen.getByRole('button', { name: 'Refresh replay data' }))
    await screen.findByRole('button', { name: 'RESUME', exact: true })
    fireEvent.click(screen.getByRole('button', { name: 'RESUME', exact: true }))
    await waitFor(() => expect(JSON.parse(fetch.mock.calls[7][1].body)).toEqual({ action: 'RESUME', expected_version: 1 }))
  })

  it('draws only explicitly labeled synthetic Forecast V1 mock lines', async () => {
    const track = makeTrack('simulated:t12-demo:kattegat-001')
    fetch.mockResolvedValueOnce(apiResponse([]))
      .mockResolvedValueOnce({ ok: true, json: async () => replaySession('123e4567-e89b-42d3-a456-426614174000', 'READY', 0) })
      .mockResolvedValueOnce({ ok: true, json: async () => replaySession('123e4567-e89b-42d3-a456-426614174000', 'READY', 0) })
      .mockResolvedValueOnce(replayPage([track]))
      .mockResolvedValueOnce(detailResponse(track))
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Replay fixture' }))
    fireEvent.click(screen.getByRole('button', { name: 'Bắt đầu replay fixture' }))
    const marker = await screen.findByTestId('marker')
    fireEvent.click(marker)
    await screen.findByLabelText(/Chi tiết tàu được chọn/)
    fireEvent.click(screen.getByRole('checkbox', { name: 'Bật Forecast Mock' }))
    expect(screen.getByText('MOCK FORECAST — NOT MODEL OUTPUT')).toBeInTheDocument()
    expect(screen.getAllByTestId('history-line').filter((line) => line.dataset.class === 'forecast-mock-path')).toHaveLength(2)
    expect(screen.getByText(/không có risk score, CPA, threshold hoặc alert/i)).toBeInTheDocument()
  })

  it.each([0, 1, 5, 8])('shows a fresh partial-history marker at minute %i without setting current_state', async (minute) => {
    const anchorTime = `2024-11-01T00:${String(minute).padStart(2, '0')}:00Z`
    const eligiblePoint = makePartialTrack('simulated:t17:early-001', anchorTime, 55.68, 12.56)
    const futureTime = new Date(Date.parse(anchorTime) + 60_000).toISOString()
    const staleTime = new Date(Date.parse(anchorTime) - 61_000).toISOString()
    const futurePoint = makePartialTrack('simulated:t17:future-002', anchorTime, 56, 13, futureTime)
    const stalePoint = makePartialTrack('simulated:t17:stale-003', anchorTime, 57, 14, staleTime)
    const staleStatus = makePartialTrack('simulated:t17:stale-status-004', anchorTime, 58, 15)
    staleStatus.data_status = 'STALE'
    const invalidStatus = makePartialTrack('simulated:t17:invalid-005', anchorTime, 59, 16)
    invalidStatus.data_status = 'INVALID_DATA'
    const sessionId = '123e4567-e89b-42d3-a456-426614174000'
    fetch.mockResolvedValueOnce(apiResponse([]))
      .mockResolvedValueOnce({ ok: true, json: async () => replaySession(sessionId, 'READY', 0, anchorTime) })
      .mockResolvedValueOnce({ ok: true, json: async () => replaySession(sessionId, 'READY', 0, anchorTime) })
      .mockResolvedValueOnce(replayPage([eligiblePoint, futurePoint, stalePoint, staleStatus, invalidStatus], '123e4567-e89b-42d3-a456-426614174010', anchorTime))
      .mockResolvedValueOnce(detailResponse(eligiblePoint))

    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Replay fixture' }))
    fireEvent.click(screen.getByRole('button', { name: 'Bắt đầu replay fixture' }))
    const marker = await screen.findByTestId('marker')
    expect(screen.getAllByTestId('marker')).toHaveLength(1)
    expect(JSON.parse(marker.dataset.position)).toEqual([55.68, 12.56])
    expect(marker.dataset.iconHtml).toContain('insufficient')
    const replayHistoryLines = screen.getAllByTestId('history-line').filter((line) => line.dataset.class === 'history-path')
    expect(replayHistoryLines).toHaveLength(3)
    expect(replayHistoryLines.every((line) => !JSON.parse(line.dataset.positions).some(([lat, lon]) => lat === 56 || lat === 57))).toBe(true)
    fireEvent.click(marker)
    await screen.findByText('AIS fix UTC')
    expect(screen.getByText(/1\/10/)).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: 'Bật Forecast Mock' })).toBeDisabled()
    expect(screen.getAllByTestId('history-line').filter((line) => line.dataset.class === 'forecast-mock-path')).toHaveLength(0)
  })

  it('replaces the previous session marker with the reset session partial fix', async () => {
    const oldTrack = makeTrack('simulated:t12-demo:kattegat-001')
    const anchorTime = '2024-11-01T00:00:00Z'
    const newTrack = makePartialTrack(oldTrack.vessel_id, anchorTime, 54.25, 11.75)
    const oldId = '123e4567-e89b-42d3-a456-426614174000'
    const newId = '123e4567-e89b-42d3-a456-426614174001'
    fetch.mockResolvedValueOnce(apiResponse([]))
      .mockResolvedValueOnce({ ok: true, json: async () => replaySession(oldId, 'READY', 0) })
      .mockResolvedValueOnce({ ok: true, json: async () => replaySession(oldId, 'READY', 0) })
      .mockResolvedValueOnce(replayPage([oldTrack]))
      .mockResolvedValueOnce({ ok: true, json: async () => replaySession(newId, 'READY', 0, anchorTime) })
      .mockResolvedValueOnce({ ok: true, json: async () => replaySession(newId, 'READY', 0, anchorTime) })
      .mockResolvedValueOnce(replayPage([newTrack], '123e4567-e89b-42d3-a456-426614174011', anchorTime))

    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Replay fixture' }))
    fireEvent.click(screen.getByRole('button', { name: 'Bắt đầu replay fixture' }))
    const oldMarker = await screen.findByTestId('marker')
    const oldPosition = JSON.parse(oldMarker.dataset.position)
    fireEvent.click(screen.getByRole('button', { name: 'Reset replay' }))
    expect(await screen.findByTestId('session-id')).toHaveTextContent(newId)
    const newMarker = await screen.findByTestId('marker')
    expect(JSON.parse(newMarker.dataset.position)).toEqual([54.25, 11.75])
    expect(JSON.parse(newMarker.dataset.position)).not.toEqual(oldPosition)
    expect(newMarker.dataset.iconHtml).toContain('insufficient')
    expect(screen.getByRole('checkbox', { name: 'Bật Forecast Mock' })).toBeDisabled()
  })
})


describe('Replay seek draft', () => {
  beforeEach(() => vi.stubGlobal('fetch', vi.fn()))
  afterEach(() => { cleanup(); vi.unstubAllGlobals() })

  it('preserves the selected target through polling and a failed seek', async () => {
    const id = '123e4567-e89b-42d3-a456-426614174000'
    const session = replaySession(id, 'PAUSED', 0, '2024-11-01T00:02:00Z')
    fetch.mockImplementation(async (url, options = {}) => {
      if (url.includes('/mock/tracks')) return apiResponse([])
      if (url.endsWith('/sessions') && options.method === 'POST') return { ok: true, json: async () => session }
      if (url.endsWith('/control')) return { ok: false, status: 503, json: async () => ({ message: 'offline' }) }
      if (url.includes('/tracks?')) return replayPage([], '123e4567-e89b-42d3-a456-426614174010', session.simulation_time)
      return { ok: true, json: async () => session }
    })
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Replay fixture' }))
    fireEvent.click(screen.getByRole('button', { name: 'Bắt đầu replay fixture' }))
    const slider = await screen.findByRole('slider', { name: 'Seek UTC time' })
    await waitFor(() => expect(slider).toHaveValue('120'))
    fireEvent.change(slider, { target: { value: '540' } })
    await new Promise((resolve) => setTimeout(resolve, 1200))
    expect(slider).toHaveValue('540')
    fireEvent.click(screen.getByRole('button', { name: /SEEK tới/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent('HTTP 503')
    expect(slider).toHaveValue('540')
  })
})


it('clears an edited seek target on reset and on a new replay session', async () => {
  const id = '123e4567-e89b-42d3-a456-426614174000'
  const resetId = '123e4567-e89b-42d3-a456-426614174001'
  let active = replaySession(id, 'READY', 0, '2024-11-01T00:02:00Z')
  vi.stubGlobal('fetch', vi.fn(async (url, options = {}) => {
    if (url.includes('/mock/tracks')) return apiResponse([])
    if (url.endsWith('/sessions') && options.method === 'POST') return { ok: true, json: async () => active }
    if (url.endsWith('/control')) {
      active = replaySession(resetId, 'READY', 0, '2024-11-01T00:00:00Z')
      return { ok: true, json: async () => active }
    }
    if (url.includes('/tracks?')) return replayPage([], '123e4567-e89b-42d3-a456-426614174010', active.simulation_time)
    return { ok: true, json: async () => active }
  }))
  try {
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Replay fixture' }))
    fireEvent.click(screen.getByRole('button', { name: 'Bắt đầu replay fixture' }))
    const slider = await screen.findByRole('slider', { name: 'Seek UTC time' })
    await waitFor(() => expect(slider).toHaveValue('120'))
    fireEvent.change(slider, { target: { value: '540' } })
    fireEvent.click(screen.getByRole('button', { name: 'Reset replay' }))
    await waitFor(() => expect(screen.getByTestId('session-id')).toHaveTextContent(resetId))
    expect(slider).toHaveValue('0')
    fireEvent.change(slider, { target: { value: '300' } })
    fireEvent.click(screen.getByRole('button', { name: 'Mock', exact: true }))
    fireEvent.click(screen.getByRole('button', { name: 'Replay fixture' }))
    fireEvent.click(screen.getByRole('button', { name: 'Bắt đầu replay fixture' }))
    await waitFor(() => expect(screen.getByRole('slider', { name: 'Seek UTC time' })).toHaveValue('0'))
  } finally {
    cleanup()
    vi.unstubAllGlobals()
  }
})


describe('delayed replay responses', () => {
  afterEach(() => { cleanup(); vi.unstubAllGlobals() })

  it.each(['RESET', 'SEEK', 'MODE'])('ignores old track polling after %s', async (action) => {
    const oldId = '123e4567-e89b-42d3-a456-426614174000'
    const newId = '123e4567-e89b-42d3-a456-426614174001'
    const oldTrack = makeTrack('simulated:old:ship')
    const newTrack = makePartialTrack('simulated:new:ship', '2024-11-01T00:00:00Z', 54.25, 11.75)
    let resolveOld
    let oldRequested = false
    const oldResponse = new Promise((resolve) => { resolveOld = resolve })
    vi.stubGlobal('fetch', vi.fn(async (url, options = {}) => {
      if (url.includes('/mock/tracks')) return apiResponse([])
      if (url.endsWith('/sessions') && options.method === 'POST') return { ok: true, json: async () => replaySession(oldId, 'READY', 0) }
      if (url.includes(oldId) && url.includes('/tracks?')) { oldRequested = true; return oldResponse }
      if (url.endsWith('/control')) return { ok: true, json: async () => replaySession(newId, 'READY', 0, '2024-11-01T00:00:00Z') }
      if (url.includes(newId) && url.includes('/tracks?')) return replayPage([newTrack], '123e4567-e89b-42d3-a456-426614174011', '2024-11-01T00:00:00Z')
      return { ok: true, json: async () => replaySession(url.includes(newId) ? newId : oldId, 'READY', 0, url.includes(newId) ? '2024-11-01T00:00:00Z' : undefined) }
    }))
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Replay fixture' }))
    fireEvent.click(screen.getByRole('button', { name: 'Bắt đầu replay fixture' }))
    await waitFor(() => expect(oldRequested).toBe(true))
    if (action === 'MODE') {
      fireEvent.click(screen.getByRole('button', { name: 'Mock', exact: true }))
    } else {
      if (action === 'SEEK') {
        fireEvent.change(screen.getByRole('slider', { name: 'Seek UTC time' }), { target: { value: '120' } })
        fireEvent.click(screen.getByRole('button', { name: /SEEK tới/ }))
      } else fireEvent.click(screen.getByRole('button', { name: 'Reset replay' }))
      await waitFor(() => expect(screen.getByTestId('session-id')).toHaveTextContent(newId))
      await screen.findByText('simulated:new:ship')
    }
    await act(async () => { resolveOld(replayPage([oldTrack])); await Promise.resolve() })
    expect(screen.queryByText('simulated:old:ship')).not.toBeInTheDocument()
    if (action !== 'MODE') expect(screen.getByTestId('session-id')).toHaveTextContent(newId)
  })
})


describe('delayed session GET and loading', () => {
  afterEach(() => { cleanup(); vi.unstubAllGlobals() })

  it.each(['SEEK', 'RESET', 'MODE'])('ignores a late old session GET after %s', async (action) => {
    const oldId = '123e4567-e89b-42d3-a456-426614174000'
    const newId = '123e4567-e89b-42d3-a456-426614174001'
    const oldTime = '2024-11-01T00:09:00Z'
    const newTime = '2024-11-01T00:00:00Z'
    const oldTrack = makeTrack('simulated:old:ship')
    const newTrack = makePartialTrack('simulated:new:ship', newTime, 54.25, 11.75)
    let resolveOld, oldGetCount = 0
    const delayed = new Promise(resolve => { resolveOld = resolve })
    vi.stubGlobal('fetch', vi.fn(async (url, options = {}) => {
      if (url.includes('/mock/tracks')) return apiResponse([])
      if (url.endsWith('/sessions') && options.method === 'POST') return { ok: true, json: async () => replaySession(oldId, 'READY', 0, oldTime) }
      if (url.endsWith('/control')) return { ok: true, json: async () => replaySession(newId, 'PAUSED', 0, newTime) }
      if (url.includes('/tracks?')) return url.includes(newId)
        ? replayPage([newTrack], '123e4567-e89b-42d3-a456-426614174011', newTime)
        : replayPage([oldTrack], '123e4567-e89b-42d3-a456-426614174010', oldTime)
      if (url.includes('/tracks/')) return detailResponse(oldTrack)
      if (url.endsWith(oldId)) {
        oldGetCount += 1
        if (oldGetCount > 1) return delayed
        return { ok: true, json: async () => replaySession(oldId, 'READY', 0, oldTime) }
      }
      return { ok: true, json: async () => replaySession(newId, 'PAUSED', 0, newTime) }
    }))
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Replay fixture' }))
    fireEvent.click(screen.getByRole('button', { name: 'Bắt đầu replay fixture' }))
    fireEvent.click(await screen.findByTestId('marker'))
    await screen.findByLabelText('Chi tiết tàu được chọn')
    fireEvent.click(screen.getByRole('checkbox', { name: 'Bật Forecast Mock' }))
    expect(screen.getByText('MOCK FORECAST — NOT MODEL OUTPUT')).toBeInTheDocument()
    await waitFor(() => expect(oldGetCount).toBeGreaterThan(1), { timeout: 2500 })
    if (action === 'MODE') {
      fireEvent.click(screen.getByRole('button', { name: 'Mock', exact: true }))
    } else {
      if (action === 'SEEK') {
        fireEvent.change(screen.getByRole('slider', { name: 'Seek UTC time' }), { target: { value: '120' } })
        fireEvent.click(screen.getByRole('button', { name: /SEEK tới/ }))
      } else fireEvent.click(screen.getByRole('button', { name: 'Reset replay' }))
      await waitFor(() => expect(screen.getByTestId('session-id')).toHaveTextContent(newId))
      await screen.findByText('simulated:new:ship')
    }
    await act(async () => { resolveOld({ ok: true, json: async () => replaySession(oldId, 'PLAYING', 99, oldTime) }); await Promise.resolve() })
    expect(screen.queryByText('simulated:old:ship')).not.toBeInTheDocument()
    expect(screen.queryByText('MOCK FORECAST — NOT MODEL OUTPUT')).not.toBeInTheDocument()
    if (action !== 'MODE') {
      expect(screen.getByTestId('session-id')).toHaveTextContent(newId)
      expect(screen.getByTestId('session-status')).toHaveTextContent('PAUSED')
      expect(screen.getByTestId('simulation-time')).toHaveTextContent(newTime)
      expect(screen.getByRole('slider', { name: 'Seek UTC time' })).toHaveValue('0')
      expect(JSON.parse(screen.getByTestId('marker').dataset.position)).toEqual([54.25, 11.75])
    }
  })

  it('shows loading while a request is pending and then renders empty state', async () => {
    let resolveFetch
    vi.stubGlobal('fetch', vi.fn(() => new Promise(resolve => { resolveFetch = resolve })))
    render(<App />)
    expect(screen.getByText('Đang tải snapshot…')).toBeInTheDocument()
    await act(async () => { resolveFetch(apiResponse([])); await Promise.resolve() })
    expect(await screen.findByText('Chưa có tàu trong snapshot')).toBeInTheDocument()
    expect(screen.queryByText('Đang tải snapshot…')).not.toBeInTheDocument()
  })
})


describe('fixture playback and geometry', () => {
  afterEach(() => { cleanup(); vi.unstubAllGlobals() })
  function fixtureTrack(minute, second = 0) {
    const time = '2024-11-01T00:' + String(minute).padStart(2, '0') + ':' + String(second).padStart(2, '0') + 'Z'
    const events = fixtureEvents.slice(0, minute + 1)
    const history = events.map((e, i) => ({ nominal_timestamp: i === events.length - 1 ? time : e.timestamp_utc,
      source_timestamp: e.timestamp_utc, original_source_timestamp: e.original_source_timestamp,
      latitude: e.latitude, longitude: e.longitude, sog_kn: e.sog_kn, cog_deg: e.cog_deg,
      source_age_seconds: i === events.length - 1 ? second : 0 }))
    return { schema_version: '1.0.0', vessel_id: events[0].vessel_id, mmsi: null, source_type: 'SYNTHETIC_AIS',
      is_simulated: true, anchor_timestamp: time, current_state: minute === 9 ? history.at(-1) : null,
      data_status: minute === 9 ? 'VALID' : 'INSUFFICIENT_DATA', history }
  }
  it('moves marker across an observation boundary without showing a future point', async () => {
    const id = '123e4567-e89b-42d3-a456-426614174000', before = fixtureTrack(0, 59), after = fixtureTrack(1)
    let phase = false
    vi.stubGlobal('fetch', vi.fn(async (url, options = {}) => {
      if (url.includes('/mock/tracks')) return apiResponse([])
      if (url.endsWith('/sessions') && options.method === 'POST') return { ok: true, json: async () => replaySession(id, 'READY', 0, before.anchor_timestamp) }
      if (url.endsWith('/control')) { phase = true; return { ok: true, json: async () => replaySession(id, 'PLAYING', 1, after.anchor_timestamp) } }
      if (url.includes('/tracks?')) return replayPage([phase ? after : before], '123e4567-e89b-42d3-a456-426614174010', (phase ? after : before).anchor_timestamp)
      return { ok: true, json: async () => replaySession(id, phase ? 'PLAYING' : 'READY', phase ? 1 : 0, (phase ? after : before).anchor_timestamp) }
    }))
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Replay fixture' }))
    fireEvent.click(screen.getByRole('button', { name: 'Bắt đầu replay fixture' }))
    const marker = await screen.findByTestId('marker')
    expect(JSON.parse(marker.dataset.position)).toEqual([fixtureEvents[0].latitude, fixtureEvents[0].longitude])
    expect(screen.getByTestId('simulation-time')).toHaveTextContent('00:00:59Z')
    fireEvent.click(screen.getByRole('button', { name: 'PLAY', exact: true }))
    await waitFor(() => expect(JSON.parse(screen.getByTestId('marker').dataset.position)).toEqual([fixtureEvents[1].latitude, fixtureEvents[1].longitude]))
    expect(screen.getByTestId('simulation-time')).toHaveTextContent('00:01:00Z')
  })
  it('draws ordered fixture history at 00:09 and replaces it after backward seek', async () => {
    const oldId = '123e4567-e89b-42d3-a456-426614174000', newId = '123e4567-e89b-42d3-a456-426614174001'
    const full = fixtureTrack(9), partial = fixtureTrack(2)
    vi.stubGlobal('fetch', vi.fn(async (url, options = {}) => {
      if (url.includes('/mock/tracks')) return apiResponse([])
      if (url.endsWith('/sessions') && options.method === 'POST') return { ok: true, json: async () => replaySession(oldId, 'READY', 0, full.anchor_timestamp) }
      if (url.endsWith('/control')) return { ok: true, json: async () => replaySession(newId, 'PAUSED', 0, partial.anchor_timestamp) }
      if (url.includes('/tracks?')) return url.includes(newId) ? replayPage([partial], '123e4567-e89b-42d3-a456-426614174011', partial.anchor_timestamp) : replayPage([full], '123e4567-e89b-42d3-a456-426614174010', full.anchor_timestamp)
      return { ok: true, json: async () => replaySession(url.includes(newId) ? newId : oldId, url.includes(newId) ? 'PAUSED' : 'READY', 0, url.includes(newId) ? partial.anchor_timestamp : full.anchor_timestamp) }
    }))
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Replay fixture' }))
    fireEvent.click(screen.getByRole('button', { name: 'Bắt đầu replay fixture' }))
    await screen.findByTestId('marker')
    const line = () => screen.getAllByTestId('history-line').find(item => item.dataset.class === 'history-path')
    const coordinates = n => fixtureEvents.slice(0, n).map(e => [e.latitude, e.longitude])
    expect(JSON.parse(line().dataset.positions)).toEqual(coordinates(10))
    fireEvent.change(screen.getByRole('slider', { name: 'Seek UTC time' }), { target: { value: '120' } })
    fireEvent.click(screen.getByRole('button', { name: /SEEK tới/ }))
    await waitFor(() => expect(JSON.parse(line().dataset.positions)).toEqual(coordinates(3)))
    expect(screen.getByTestId('simulation-time')).toHaveTextContent('00:02:00Z')
  })
})
