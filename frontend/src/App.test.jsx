import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import App from './App.jsx'

vi.mock('react-leaflet', () => ({
  MapContainer: ({ children }) => <div data-testid="map">{children}</div>,
  TileLayer: () => <div data-testid="tile-layer" />,
  Polyline: ({ positions }) => <output data-testid="history-line" data-positions={JSON.stringify(positions)} />,
  Marker: ({ position, eventHandlers, children }) => (
    <button data-testid="marker" data-position={JSON.stringify(position)} onClick={eventHandlers?.click}>
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

function apiResponse(items, total = items.length) {
  return { ok: true, json: async () => ({ items, total }) }
}

function detailResponse(track) {
  return { ok: true, json: async () => track }
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
    expect(screen.getByText('10 mốc · đến anchor')).toBeInTheDocument()
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
    expect(await screen.findByText('Không kết nối được Mock API')).toBeInTheDocument()
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
    fireEvent.click(screen.getByRole('button', { name: 'Tải lại dữ liệu' }))
    expect(await screen.findByText('mock-vessel-004')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('marker'))
    expect(await screen.findByText('STALE MOCK')).toBeInTheDocument()
    expect(screen.getByText('age 180s')).toBeInTheDocument()
    expect(fetch).toHaveBeenCalledTimes(3)
  })
})
