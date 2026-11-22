import { useCallback, useEffect, useMemo, useState } from 'react'
import { MapContainer, Marker, Polyline, TileLayer, Tooltip, useMap } from 'react-leaflet'
import L from 'leaflet'

const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')

function formatUtc(value) {
  if (!value) return '—'
  return new Date(value).toISOString().replace('.000Z', 'Z')
}

function shipIcon(track, selected) {
  const color = track.data_status === 'STALE' ? '#f0aa53' : '#44d7c0'
  const rotation = track.current_state?.cog_deg ?? 0
  return L.divIcon({
    className: 'ship-marker-wrap',
    html: `<div class="ship-marker ${selected ? 'selected' : ''}" style="--ship-color:${color}"><svg viewBox="0 0 28 34" style="transform:rotate(${rotation}deg)" aria-hidden="true"><path d="M14 2 24 28 14 23 4 28Z"/><path class="ship-marker-core" d="M14 7 19 23 14 20 9 23Z"/></svg></div>`,
    iconSize: [38, 42],
    iconAnchor: [19, 21],
  })
}

function FitTracks({ tracks }) {
  const map = useMap()
  useEffect(() => {
    const points = tracks.filter((track) => track.current_state).map((track) => [track.current_state.latitude, track.current_state.longitude])
    if (points.length === 1) map.setView(points[0], 11)
    if (points.length > 1) map.fitBounds(points, { padding: [60, 60], maxZoom: 12 })
  }, [map, tracks])
  return null
}

function StatusBadge({ status }) {
  const label = status === 'VALID' ? 'LIVE MOCK' : status === 'STALE' ? 'STALE MOCK' : `${status} MOCK`
  return <span className={`status-badge ${status.toLowerCase()}`}>{label}</span>
}

function TrackDetails({ track }) {
  if (!track) {
    return <div className="detail-empty"><span className="detail-empty-icon">⌖</span><p>Chọn một marker để xem snapshot và lịch sử 10 mốc.</p></div>
  }
  const state = track.current_state
  return (
    <section className="details-card" aria-label="Chi tiết tàu được chọn">
      <div className="details-heading">
        <div>
          <span className="eyebrow">TRACK SNAPSHOT</span>
          <h2>{track.vessel_id}</h2>
        </div>
        <StatusBadge status={track.data_status} />
      </div>
      <div className="detail-grid">
        <div><span>MMSI</span><strong>{track.mmsi || 'Mock ID · không gán MMSI'}</strong></div>
        <div><span>Nguồn</span><strong>{track.source_type} · simulated</strong></div>
        <div><span>Anchor UTC</span><strong>{formatUtc(track.anchor_timestamp)}</strong></div>
        <div><span>Vị trí</span><strong>{state ? `${state.latitude.toFixed(5)}, ${state.longitude.toFixed(5)}` : 'Chưa có fix'}</strong></div>
        <div><span>SOG</span><strong>{state ? `${state.sog_kn.toFixed(1)} kn` : '—'}</strong></div>
        <div><span>COG</span><strong>{state ? `${state.cog_deg.toFixed(1)}°` : '—'}</strong></div>
      </div>
      <div className="history-title"><span>LỊCH SỬ AS-OF</span><span>{track.history.length} mốc · đến anchor</span></div>
      <ol className="history-list">
        {[...track.history].reverse().map((point) => (
          <li key={point.nominal_timestamp} className={point.nominal_timestamp === track.anchor_timestamp ? 'anchor-row' : ''}>
            <span className="history-dot" />
            <time dateTime={point.nominal_timestamp}>{formatUtc(point.nominal_timestamp)}</time>
            <span>{point.sog_kn.toFixed(1)} kn</span>
            <span>{point.cog_deg.toFixed(0)}°</span>
            {point.source_age_seconds > 60 && <em>age {Math.round(point.source_age_seconds)}s</em>}
          </li>
        ))}
      </ol>
    </section>
  )
}

export default function App() {
  const [tracks, setTracks] = useState([])
  const [selected, setSelected] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)

  const loadTracks = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const response = await fetch(`${API_BASE}/api/v1/mock/tracks`)
      if (!response.ok) throw new Error(`API trả về HTTP ${response.status}`)
      const payload = await response.json()
      if (!Array.isArray(payload.items)) throw new Error('Phản hồi API thiếu danh sách items')
      setTracks(payload.items)
      setSelected((current) => current ? payload.items.find((item) => item.vessel_id === current.vessel_id) || null : null)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Không thể tải dữ liệu tàu.')
      setTracks([])
      setSelected(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadTracks() }, [loadTracks, refreshKey])

  const onSelect = useCallback(async (track) => {
    setSelected(track)
    try {
      const response = await fetch(`${API_BASE}/api/v1/mock/tracks/${encodeURIComponent(track.vessel_id)}`)
      if (!response.ok) throw new Error(`Không tải được lịch sử (${response.status})`)
      setSelected(await response.json())
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Không tải được lịch sử tàu.')
    }
  }, [])

  const historyLines = useMemo(() => tracks.filter((track) => track.history.length > 0).map((track) => ({
    id: track.vessel_id,
    status: track.data_status,
    positions: track.history.map((point) => [point.latitude, point.longitude]),
  })), [tracks])

  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="AIT3040 Track Map home"><span className="brand-mark">A</span><span><strong>AIT3040</strong><small>MARITIME SAFETY SYSTEM</small></span></a>
        <div className="topbar-right"><span className="connection-dot" /> MOCK API <span className="topbar-divider" /> SPRINT 01</div>
      </header>

      <section className="page-heading" id="top">
        <div><span className="eyebrow">DATA EXPLORER / TRACKS</span><h1>Vessel movement</h1><p>Vị trí hiện tại và lịch sử AIS as-of theo snapshot UTC.</p></div>
        <div className="mock-stamp"><span>◆</span> MOCK DATA <small>KHÔNG PHẢI AIS THẬT</small></div>
      </section>

      <section className="workspace">
        <div className="map-panel">
          <div className="map-toolbar"><div className="map-title"><span className="map-pulse" /> KATTEGAT · DENMARK <small>55.6°N — 12.7°E</small></div><button className="refresh-button" onClick={() => setRefreshKey((key) => key + 1)} disabled={loading} aria-label="Tải lại dữ liệu">↻ <span>Refresh</span></button></div>
          <div className="map-canvas">
            <MapContainer center={[55.69, 12.61]} zoom={9} scrollWheelZoom className="leaflet-map">
              <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
              <FitTracks tracks={tracks} />
              {historyLines.map((line) => <Polyline key={line.id} positions={line.positions} pathOptions={{ color: line.status === 'STALE' ? '#f0aa53' : '#48d7c0', weight: selected?.vessel_id === line.id ? 4 : 2.5, opacity: selected?.vessel_id === line.id ? 0.95 : 0.54, dashArray: line.status === 'STALE' ? '7 7' : undefined }} />)}
              {tracks.filter((track) => track.current_state).map((track) => (
                <Marker key={track.vessel_id} position={[track.current_state.latitude, track.current_state.longitude]} icon={shipIcon(track, selected?.vessel_id === track.vessel_id)} eventHandlers={{ click: () => onSelect(track) }}>
                  <Tooltip direction="top" offset={[0, -13]}>{track.vessel_id} · {track.data_status}</Tooltip>
                </Marker>
              ))}
            </MapContainer>
            {loading && <div className="map-overlay"><span className="spinner" />Đang tải snapshot…</div>}
            {!loading && error && <div className="map-overlay error-overlay"><strong>Không kết nối được Mock API</strong><span>{error}</span><button onClick={() => setRefreshKey((key) => key + 1)}>Thử lại</button></div>}
            {!loading && !error && tracks.length === 0 && <div className="map-overlay empty-overlay"><strong>Chưa có tàu trong snapshot</strong><span>API trả về danh sách rỗng.</span></div>}
            <div className="map-legend"><span><i className="legend-valid" />VALID</span><span><i className="legend-stale" />STALE</span><span><i className="legend-line" />HISTORY</span></div>
            <div className="map-attribution">Leaflet · OpenStreetMap</div>
          </div>
          <div className="map-footer"><span>● SNAPSHOT UTC</span><strong>{tracks[0] ? formatUtc(tracks[0].anchor_timestamp) : '—'}</strong><span>·</span><span>NO FUTURE MESSAGES</span></div>
        </div>

        <aside className="side-panel">
          <div className="fleet-heading"><div><span className="eyebrow">AIS MOCK FEED</span><h2>Vessels <span>{tracks.length.toString().padStart(2, '0')}</span></h2></div><span className="feed-live">LOCAL</span></div>
          <p className="side-copy">Mỗi marker hiển thị fix cuối tại anchor cùng 10 mốc history trước đó.</p>
          <div className="vessel-list" aria-label="Danh sách tàu">
            {tracks.map((track, index) => (
              <button className={`vessel-row ${selected?.vessel_id === track.vessel_id ? 'active' : ''}`} key={track.vessel_id} onClick={() => onSelect(track)}>
                <span className={`vessel-index ${track.data_status.toLowerCase()}`}>{String(index + 1).padStart(2, '0')}</span>
                <span className="vessel-main"><strong>{track.vessel_id}</strong><small>{track.current_state?.latitude.toFixed(3)}, {track.current_state?.longitude.toFixed(3)}</small></span>
                <span className={`row-state ${track.data_status.toLowerCase()}`}>{track.data_status}</span>
              </button>
            ))}
            {!loading && !error && tracks.length === 0 && <div className="list-empty">Chưa có snapshot để hiển thị.</div>}
          </div>
          <TrackDetails track={selected} />
          <div className="scope-note"><span>i</span><p>Dữ liệu deterministic để kiểm tra giao diện. Không có MMSI thật, risk score hoặc nhãn an toàn.</p></div>
        </aside>
      </section>
      <footer className="page-footer"><span>AIT3040 · S1_T04 MOCK DATA API & MAP</span><span>COORDINATES · LATITUDE / LONGITUDE</span></footer>
    </main>
  )
}
