import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import App from './App.jsx'

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
