import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { MapContainer, Marker, Polyline, TileLayer, Tooltip, useMap } from 'react-leaflet'
import L from 'leaflet'
import { buildMockForecastV1 } from './forecastMock.js'

const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')
const DEMO_SOURCE_ID = 'fixture-denmark-10m-v1'
const DEMO_SOURCE_START = '2024-11-01T00:00:00Z'
const DEMO_SOURCE_END = '2024-11-01T00:10:00Z'
const SEEK_MAX_SECONDS = 599
const REPLAY_POLL_MS = 1000

function formatUtc(value) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isFinite(date.getTime()) ? date.toISOString().replace('.000Z', 'Z') : '—'
}

function seekTimeAt(offsetSeconds) {
  return new Date(Date.parse(DEMO_SOURCE_START) + Number(offsetSeconds) * 1000).toISOString().replace('.000Z', 'Z')
}

function secondsFromStart(value) {
  const seconds = Math.floor((Date.parse(value) - Date.parse(DEMO_SOURCE_START)) / 1000)
  return Math.max(0, Math.min(SEEK_MAX_SECONDS, seconds))
}

function controlKey() {
  return globalThis.crypto?.randomUUID?.() || `replay-control-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

async function errorMessage(response, prefix) {
  let detail = ''
  try {
    const body = await response.json()
    detail = body?.detail?.message || body?.message || body?.detail?.error_code || ''
  } catch { /* non-JSON error response */ }
  return `${prefix} (HTTP ${response.status})${detail ? `: ${detail}` : ''}`
}

function shipIcon(track, selected) {
  const color = track.data_status === 'STALE' ? '#f0aa53' : track.data_status === 'INSUFFICIENT_DATA' ? '#79baff' : '#44d7c0'
  const rotation = track.current_state?.cog_deg ?? 0
  const insufficientClass = track.data_status === 'INSUFFICIENT_DATA' ? 'insufficient' : ''
  return L.divIcon({
    className: 'ship-marker-wrap',
    html: `<div class="ship-marker ${insufficientClass} ${selected ? 'selected' : ''}" style="--ship-color:${color}"><svg viewBox="0 0 28 34" style="transform:rotate(${rotation}deg)" aria-hidden="true"><path d="M14 2 24 28 14 23 4 28Z"/><path class="ship-marker-core" d="M14 7 19 23 14 20 9 23Z"/></svg></div>`,
    iconSize: [38, 42],
    iconAnchor: [19, 21],
  })
}

function isValidCoordinate(point) {
  return point && Number.isFinite(point.latitude) && point.latitude >= -90 && point.latitude <= 90 &&
    Number.isFinite(point.longitude) && point.longitude >= -180 && point.longitude <= 180
}

function getDisplayPoint(track, mode) {
  if (track?.data_status === 'STALE' || track?.data_status === 'INVALID_DATA') {
    return mode === 'mock' ? track.current_state || null : null
  }
  if (track?.data_status !== 'INSUFFICIENT_DATA') return track?.current_state || null
  if (typeof track.anchor_timestamp !== 'string' || !track.anchor_timestamp.endsWith('Z')) return null
  const anchorMs = Date.parse(track.anchor_timestamp)
  if (!Number.isFinite(anchorMs) || !Array.isArray(track.history)) return null
  const point = track.history.find((item) => item.nominal_timestamp === track.anchor_timestamp)
  if (!point || !isValidCoordinate(point) || typeof point.source_timestamp !== 'string' || !point.source_timestamp.endsWith('Z')) return null
  const sourceMs = Date.parse(point.source_timestamp)
  const ageSeconds = (anchorMs - sourceMs) / 1000
  if (!Number.isFinite(sourceMs) || sourceMs > anchorMs || ageSeconds < 0 || ageSeconds > 60 ||
      !Number.isFinite(point.source_age_seconds) || Math.abs(point.source_age_seconds - ageSeconds) > 1e-6) return null
  return point
}

function getRenderableHistory(track, mode) {
  const history = Array.isArray(track?.history) ? track.history : []
  if (mode === 'mock') return history
  const anchorMs = Date.parse(track?.anchor_timestamp)
  if (!Number.isFinite(anchorMs)) return []
  return history.filter((point) => {
    if (!isValidCoordinate(point) || typeof point.nominal_timestamp !== 'string' || !point.nominal_timestamp.endsWith('Z') ||
        typeof point.source_timestamp !== 'string' || !point.source_timestamp.endsWith('Z')) return false
    const nominalMs = Date.parse(point.nominal_timestamp)
    const sourceMs = Date.parse(point.source_timestamp)
    const ageSeconds = (nominalMs - sourceMs) / 1000
    return Number.isFinite(nominalMs) && Number.isFinite(sourceMs) && nominalMs <= anchorMs && sourceMs <= nominalMs &&
      ageSeconds >= 0 && ageSeconds <= 60 && Number.isFinite(point.source_age_seconds) &&
      Math.abs(point.source_age_seconds - ageSeconds) <= 1e-6
  })
}

function FitTracks({ tracks, mode }) {
  const map = useMap()
  useEffect(() => {
    const points = tracks.map((track) => getDisplayPoint(track, mode)).filter(Boolean).map((point) => [point.latitude, point.longitude])
    if (points.length === 1) map.setView(points[0], 11)
    if (points.length > 1) map.fitBounds(points, { padding: [60, 60], maxZoom: 12 })
  }, [map, tracks])
  return null
}

function StatusBadge({ status, mode }) {
  const label = mode === 'mock'
    ? (status === 'VALID' ? 'LIVE MOCK' : status === 'STALE' ? 'STALE MOCK' : `${status} MOCK`)
    : status
  return <span className={`status-badge ${String(status || 'invalid').toLowerCase()}`}>{label}</span>
}

function TrackDetails({ track, mode }) {
  if (!track) {
    return <div className="detail-empty"><span className="detail-empty-icon">⌖</span><p>Chọn một marker để xem snapshot và lịch sử as-of.</p></div>
  }
  const state = getDisplayPoint(track, mode)
  const history = getRenderableHistory(track, mode)
  return (
    <section className="details-card" aria-label="Chi tiết tàu được chọn">
      <div className="details-heading">
        <div><span className="eyebrow">TRACK SNAPSHOT</span><h2>{track.vessel_id}</h2></div>
        <StatusBadge status={track.data_status} mode={mode} />
      </div>
      <div className="detail-grid">
        <div><span>MMSI</span><strong>{track.mmsi || 'Không gán MMSI'}</strong></div>
        <div><span>Nguồn</span><strong>{track.source_type} · {track.is_simulated ? 'simulated trajectory' : 'real AIS'}</strong></div>
        <div><span>Anchor UTC</span><strong>{formatUtc(track.anchor_timestamp)}</strong></div>
        <div><span>AIS fix UTC</span><strong>{formatUtc(state?.source_timestamp)}</strong></div>
        <div><span>Observed as-of position</span><strong>{state ? `${state.latitude.toFixed(5)}, ${state.longitude.toFixed(5)}` : 'No valid fix at anchor'}</strong></div>
        <div><span>SOG</span><strong>{state ? `${state.sog_kn.toFixed(1)} kn` : '—'}</strong></div>
        <div><span>COG</span><strong>{state ? `${state.cog_deg.toFixed(1)}°` : '—'}</strong></div>
      </div>
      <div className="history-title"><span>LỊCH SỬ AS-OF</span><span>{history.length}/10 mốc · đến anchor</span></div>
      <ol className="history-list">
        {[...history].reverse().map((point) => (
          <li key={point.nominal_timestamp} className={point.nominal_timestamp === track.anchor_timestamp ? 'anchor-row' : ''}>
            <span className="history-dot" />
            <time dateTime={point.nominal_timestamp}>{formatUtc(point.nominal_timestamp)}</time>
            <span>{Number.isFinite(point.sog_kn) ? `${point.sog_kn.toFixed(1)} kn` : '—'}</span>
            <span>{Number.isFinite(point.cog_deg) ? `${point.cog_deg.toFixed(0)}°` : '—'}</span>
            {point.source_age_seconds > 60 && <em>age {Math.round(point.source_age_seconds)}s</em>}
          </li>
        ))}
      </ol>
    </section>
  )
}

export default function App() {
  const [mode, setMode] = useState('mock')
  const [tracks, setTracks] = useState([])
  const [selected, setSelected] = useState(null)
  const [session, setSession] = useState(null)
  const [snapshotId, setSnapshotId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [controlError, setControlError] = useState('')
  const [controlBusy, setControlBusy] = useState(false)
  const [pendingControl, setPendingControl] = useState(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [seekOffset, setSeekOffset] = useState(540)
  const [forecastEnabled, setForecastEnabled] = useState(false)
  const generationRef = useRef(0)
  const sessionRef = useRef(session)
  const snapshotRef = useRef(snapshotId)
  sessionRef.current = session
  snapshotRef.current = snapshotId

  useEffect(() => {
    if (mode !== 'mock') return undefined
    let cancelled = false
    const controller = new AbortController()
    setLoading(true)
    setError('')
    fetch(`${API_BASE}/api/v1/mock/tracks`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(await errorMessage(response, 'Mock API lỗi'))
        const payload = await response.json()
        if (!Array.isArray(payload.items)) throw new Error('Phản hồi Mock API thiếu items')
        if (cancelled) return
        setTracks(payload.items)
        setSelected((current) => current ? payload.items.find((item) => item.vessel_id === current.vessel_id) || null : null)
      })
      .catch((cause) => {
        if (cancelled || cause?.name === 'AbortError') return
        setError(cause instanceof Error ? cause.message : 'Không thể tải dữ liệu tàu.')
        setTracks([])
        setSelected(null)
      })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true; controller.abort() }
  }, [mode, refreshKey])

  useEffect(() => {
    if (mode !== 'replay' || !session?.session_id) return undefined
    const sessionId = session.session_id
    const generation = generationRef.current
    let cancelled = false
    let shouldStop = false
    let timer
    let controller

    const poll = async () => {
      controller = new AbortController()
      try {
        const sessionResponse = await fetch(`${API_BASE}/api/v1/replay/sessions/${encodeURIComponent(sessionId)}`, { signal: controller.signal })
        if (!sessionResponse.ok) {
          if (sessionResponse.status === 410 && !cancelled) {
            shouldStop = true
            setSession((current) => current?.session_id === sessionId ? { ...current, status: 'EXPIRED' } : current)
          }
          throw new Error(await errorMessage(sessionResponse, 'Replay session lỗi'))
        }
        const nextSession = await sessionResponse.json()
        if (['ENDED', 'EXPIRED'].includes(nextSession.status)) shouldStop = true
        if (cancelled || generation !== generationRef.current) return
        const currentSession = sessionRef.current
        if (currentSession?.session_id === sessionId && currentSession.version > nextSession.version) return

        const tracksResponse = await fetch(`${API_BASE}/api/v1/replay/sessions/${encodeURIComponent(sessionId)}/tracks?limit=50&offset=0`, { signal: controller.signal })
        if (!tracksResponse.ok) throw new Error(await errorMessage(tracksResponse, 'Replay tracks lỗi'))
        const payload = await tracksResponse.json()
        if (!Array.isArray(payload.items) || !payload.snapshot_id || !payload.simulation_time) {
          throw new Error('Replay API thiếu items, snapshot_id hoặc simulation_time')
        }
        if (cancelled || generation !== generationRef.current || sessionRef.current?.session_id !== sessionId) return
        setSession((current) => current?.session_id === sessionId && current.version > nextSession.version ? current : nextSession)
        setTracks(payload.items)
        setSnapshotId(payload.snapshot_id)
        setSelected((current) => current ? payload.items.find((item) => item.vessel_id === current.vessel_id) || null : null)
        setSeekOffset(secondsFromStart(nextSession.simulation_time))
        setError('')
      } catch (cause) {
        if (cancelled || cause?.name === 'AbortError' || generation !== generationRef.current) return
        setError(cause instanceof Error ? cause.message : 'Không thể tải Replay snapshot.')
      } finally {
        if (!cancelled && !shouldStop && generation === generationRef.current) timer = window.setTimeout(poll, REPLAY_POLL_MS)
      }
    }

    poll()
    return () => { cancelled = true; window.clearTimeout(timer); controller?.abort() }
  }, [mode, session?.session_id, refreshKey])

  const switchMode = useCallback((nextMode) => {
    generationRef.current += 1
    setMode(nextMode)
    setTracks([])
    setSelected(null)
    setSession(null)
    setSnapshotId(null)
    setError('')
    setControlError('')
    setPendingControl(null)
    setForecastEnabled(false)
    setLoading(false)
  }, [])

  const startReplay = useCallback(async () => {
    const generation = generationRef.current
    setLoading(true)
    setError('')
    setControlError('')
    try {
      const response = await fetch(`${API_BASE}/api/v1/replay/sessions`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_id: DEMO_SOURCE_ID }),
      })
      if (!response.ok) throw new Error(await errorMessage(response, 'Không tạo được Replay session'))
      const next = await response.json()
      if (generation !== generationRef.current) return
      setTracks([])
      setSelected(null)
      setSnapshotId(null)
      setSession(next)
      setSeekOffset(secondsFromStart(next.simulation_time))
    } catch (cause) {
      if (generation !== generationRef.current) return
      setError(cause instanceof Error ? cause.message : 'Không thể tạo Replay session.')
    } finally {
      if (generation === generationRef.current) setLoading(false)
    }
  }, [])

  const dispatchControl = useCallback(async (operation) => {
    if (!operation || controlBusy) return
    setPendingControl(operation)
    setControlBusy(true)
    setControlError('')
    try {
      const headers = { 'Content-Type': 'application/json' }
      if (operation.idempotencyKey) headers['Idempotency-Key'] = operation.idempotencyKey
      const body = { action: operation.action, expected_version: operation.expectedVersion }
      if (operation.action === 'SEEK') body.target_time = operation.targetTime
      const response = await fetch(`${API_BASE}/api/v1/replay/sessions/${encodeURIComponent(operation.sessionId)}/control`, {
        method: 'POST', headers, body: JSON.stringify(body),
      })
      if (!response.ok) {
        const message = await errorMessage(response, `${operation.action} thất bại`)
        if (response.status === 409) setPendingControl(null)
        throw new Error(message)
      }
      const next = await response.json()
      if (operation.generation !== generationRef.current) return
      if (sessionRef.current?.session_id !== operation.sessionId) return
      setPendingControl(null)
      setControlError('')
      if (next.session_id !== operation.sessionId) {
        generationRef.current += 1
        setTracks([])
        setSelected(null)
        setSnapshotId(null)
        setForecastEnabled(false)
      } else {
        generationRef.current += 1
        setRefreshKey((key) => key + 1)
      }
      setSession(next)
    } catch (cause) {
      if (operation.generation !== generationRef.current) return
      setControlError(cause instanceof Error ? cause.message : `Replay ${operation.action} thất bại.`)
    } finally {
      setControlBusy(false)
    }
  }, [controlBusy])

  const requestControl = useCallback((action, targetTime) => {
    if (!session) return
    const operation = {
      sessionId: session.session_id,
      action,
      expectedVersion: session.version,
      generation: generationRef.current,
      targetTime: action === 'SEEK' ? targetTime : undefined,
      idempotencyKey: ['RESET', 'SEEK'].includes(action) ? controlKey() : null,
    }
    dispatchControl(operation)
  }, [dispatchControl, session])

  const selectTrack = useCallback(async (track) => {
    setSelected(track)
    const generation = generationRef.current
    const selectedSessionId = mode === 'replay' ? session?.session_id : null
    const selectedSnapshotId = mode === 'replay' ? snapshotId : null
    const path = mode === 'mock'
      ? `${API_BASE}/api/v1/mock/tracks/${encodeURIComponent(track.vessel_id)}`
      : `${API_BASE}/api/v1/replay/sessions/${encodeURIComponent(selectedSessionId)}/tracks/${encodeURIComponent(track.vessel_id)}?snapshot_id=${encodeURIComponent(selectedSnapshotId || '')}`
    try {
      const response = await fetch(path)
      if (!response.ok) throw new Error(await errorMessage(response, 'Không tải được lịch sử'))
      const detail = await response.json()
      if (generation !== generationRef.current || (mode === 'replay' && (sessionRef.current?.session_id !== selectedSessionId || snapshotRef.current !== selectedSnapshotId))) return
      setSelected(detail)
    } catch (cause) {
      if (generation !== generationRef.current) return
      setError(cause instanceof Error ? cause.message : 'Không tải được lịch sử tàu.')
    }
  }, [mode, session?.session_id, snapshotId])

  const retryControl = () => { if (pendingControl) dispatchControl(pendingControl) }
  const replayCanControl = session && ['READY', 'PLAYING', 'PAUSED'].includes(session.status) && !controlBusy && !pendingControl
  const seekPreview = seekTimeAt(seekOffset)
  const forecastResult = useMemo(() => forecastEnabled && mode === 'replay'
    ? buildMockForecastV1(selected)
    : { forecast: null, reason: null }, [forecastEnabled, mode, selected])
  const forecastLines = forecastResult.forecast?.forecast_lat_lon || []
  const historyLines = useMemo(() => tracks.map((track) => ({
    id: track.vessel_id,
    status: track.data_status,
    positions: getRenderableHistory(track, mode).map((point) => [point.latitude, point.longitude]),
  })).filter((line) => line.positions.length > 0), [mode, tracks])

  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="AIT3040 Track Map home"><span className="brand-mark">A</span><span><strong>AIT3040</strong><small>MARITIME SAFETY SYSTEM</small></span></a>
        <div className="topbar-right"><span className="connection-dot" /> {mode === 'mock' ? 'MOCK API' : 'REPLAY API'} <span className="topbar-divider" /> {mode === 'mock' ? 'SPRINT 01' : 'S4_T17'}</div>
      </header>

      <section className="page-heading" id="top">
        <div><span className="eyebrow">DATA EXPLORER / TRACKS</span><h1>Vessel movement</h1><p>Vị trí và history lấy từ simulation clock UTC của backend.</p></div>
        <div className="mock-stamp"><span>◆</span> {mode === 'mock' ? 'MOCK DATA' : 'SYNTHETIC REPLAY FIXTURE'} <small>{mode === 'mock' ? 'KHÔNG PHẢI AIS THẬT' : 'KHÔNG PHẢI NGUỒN AIS ĐÃ XÁC MINH'}</small></div>
      </section>

      <section className="workspace">
        <div className="map-panel">
          <div className="map-toolbar">
            <div className="map-title"><span className="map-pulse" /> KATTEGAT · DENMARK <small>55.6°N — 12.7°E</small></div>
            <div className="map-actions">
              {mode === 'replay' && session && <button className="refresh-button" onClick={() => requestControl('RESET')} disabled={!replayCanControl} aria-label="Reset replay">RESET</button>}
              <button className="refresh-button" onClick={() => { generationRef.current += 1; setRefreshKey((key) => key + 1) }} disabled={loading} aria-label="Refresh replay data">↻ <span>Refresh</span></button>
            </div>
          </div>
          <div className="map-canvas">
            <MapContainer center={[55.69, 12.61]} zoom={9} scrollWheelZoom className="leaflet-map">
              <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
              <FitTracks tracks={tracks} mode={mode} />
              {historyLines.map((line) => <Polyline key={`history-${line.id}`} positions={line.positions} pathOptions={{ className: 'history-path', color: line.status === 'STALE' ? '#f0aa53' : '#48d7c0', weight: selected?.vessel_id === line.id ? 4 : 2.5, opacity: selected?.vessel_id === line.id ? 0.95 : 0.54, dashArray: line.status === 'STALE' ? '7 7' : undefined }} />)}
              {forecastLines.map((line, index) => <Polyline key={`forecast-${index}`} positions={line} pathOptions={{ className: 'forecast-mock-path', color: index === 0 ? '#d68cff' : '#87a8ff', weight: 3, opacity: 0.95, dashArray: '3 9' }} />)}
              {tracks.map((track) => ({ track, point: getDisplayPoint(track, mode) })).filter(({ point }) => point).map(({ track, point }) => (
                <Marker key={track.vessel_id} position={[point.latitude, point.longitude]} icon={shipIcon(track, selected?.vessel_id === track.vessel_id)} eventHandlers={{ click: () => selectTrack(track) }}>
                  <Tooltip direction="top" offset={[0, -13]}>{track.vessel_id} · {track.data_status}{track.data_status === "INSUFFICIENT_DATA" ? ` · observed ${formatUtc(point.source_timestamp)}` : ""}</Tooltip>
                </Marker>
              ))}
            </MapContainer>
            {loading && <div className="map-overlay"><span className="spinner" />Đang tải snapshot…</div>}
            {!loading && error && <div className="map-overlay error-overlay"><strong>Replay/Mock API lỗi</strong><span>{error}</span><button onClick={() => { generationRef.current += 1; setRefreshKey((key) => key + 1) }}>Thử lại</button></div>}
            {!loading && !error && tracks.length === 0 && <div className="map-overlay empty-overlay"><strong>Chưa có tàu trong snapshot</strong><span>API trả về danh sách rỗng hoặc chưa bắt đầu session.</span></div>}
            <div className="map-legend"><span><i className="legend-valid" />VALID</span>{mode === 'replay' && <span><i className="legend-insufficient" />INSUFFICIENT_DATA</span>}<span><i className="legend-stale" />STALE</span><span><i className="legend-line" />HISTORY</span>{forecastLines.length > 0 && <span><i className="legend-forecast" />FORECAST MOCK</span>}</div>
            <div className="map-attribution">Leaflet · OpenStreetMap</div>
          </div>
          <div className="map-footer"><span>SIMULATION UTC</span><strong>{mode === 'replay' ? formatUtc(session?.simulation_time) : formatUtc(tracks[0]?.anchor_timestamp)}</strong><span>·</span><span>NO FUTURE AIS MESSAGES</span></div>
        </div>

        <aside className="side-panel">
          <div className="fleet-heading"><div><span className="eyebrow">{mode === 'mock' ? 'AIS MOCK FEED' : 'REPLAY SESSION'}</span><h2>Vessels <span>{tracks.length.toString().padStart(2, '0')}</span></h2></div><span className="feed-live">{mode === 'mock' ? 'LOCAL' : session?.status || 'FIXTURE'}</span></div>
          <div className="data-mode-switch" role="group" aria-label="Chế độ dữ liệu">
            <button className={mode === 'mock' ? 'mode-button active' : 'mode-button'} aria-pressed={mode === 'mock'} onClick={() => switchMode('mock')}>Mock</button>
            <button className={mode === 'replay' ? 'mode-button active' : 'mode-button'} aria-pressed={mode === 'replay'} onClick={() => switchMode('replay')}>Replay fixture</button>
          </div>

          {mode === 'replay' && <section className="replay-controls" aria-label="Replay controls">
            <div className="replay-controls-heading"><strong>REPLAY CONTROLS</strong><span>{session?.status || 'NO SESSION'}</span></div>
            {!session && <button className="replay-start-button" disabled={loading} onClick={startReplay}>Bắt đầu replay fixture</button>}
            {session && <>
              <dl className="session-facts">
                <div><dt>SIMULATION UTC</dt><dd data-testid="simulation-time">{formatUtc(session.simulation_time)}</dd></div>
                <div><dt>SESSION ID</dt><dd data-testid="session-id">{session.session_id}</dd></div>
                <div><dt>STATUS / VERSION</dt><dd data-testid="session-status">{session.status} · v{session.version}</dd></div>
              </dl>
              <div className="control-buttons">
                {session.status === 'READY' && <button onClick={() => requestControl('PLAY')} disabled={!replayCanControl}>PLAY</button>}
                {session.status === 'PLAYING' && <button onClick={() => requestControl('PAUSE')} disabled={!replayCanControl}>PAUSE</button>}
                {session.status === 'PAUSED' && <><button onClick={() => requestControl('PLAY')} disabled={!replayCanControl}>PLAY</button><button onClick={() => requestControl('RESUME')} disabled={!replayCanControl}>RESUME</button></>}
                {['READY', 'PLAYING', 'PAUSED'].includes(session.status) && <button onClick={() => requestControl('RESET')} disabled={!replayCanControl}>RESET</button>}
                {['ENDED', 'EXPIRED'].includes(session.status) && <button onClick={startReplay} disabled={loading}>Tạo session mới</button>}
              </div>
              {['READY', 'PLAYING', 'PAUSED'].includes(session.status) && <div className="seek-control">
                <label htmlFor="replay-seek">SEEK UTC · <time>{seekPreview}</time></label>
                <input id="replay-seek" aria-label="Seek UTC time" type="range" min="0" max={SEEK_MAX_SECONDS} step="1" value={seekOffset} onChange={(event) => setSeekOffset(Number(event.target.value))} disabled={!replayCanControl} />
                <button onClick={() => requestControl('SEEK', seekPreview)} disabled={!replayCanControl}>SEEK tới mốc này</button>
              </div>}
              {pendingControl && controlError && <button className="retry-control" onClick={retryControl} disabled={controlBusy}>Thử lại {pendingControl.action} với cùng Idempotency-Key</button>}
              {controlError && <p className="control-error" role="alert">{controlError}</p>}
              {session.status === 'PLAYING' && <p className="clock-note">Clock do backend tiến theo monotonic time; UI chỉ poll session và track.</p>}
            </>}
          </section>}

          {mode === 'replay' && <section className="forecast-controls" aria-label="Forecast mock map layer">
            <label><input type="checkbox" aria-label="Bật Forecast Mock" checked={forecastEnabled} disabled={!selected || !session || selected.data_status !== "VALID" || selected.history?.length !== 10} onChange={(event) => setForecastEnabled(event.target.checked)} /> Bật lớp Forecast Mock</label>
            {forecastEnabled && <><strong className="forecast-warning">MOCK FORECAST — NOT MODEL OUTPUT</strong><span className="forecast-caption">Synthetic fixture độc lập; không có risk score, CPA, threshold hoặc alert.</span>{forecastResult.reason && <span className="forecast-caption" role="status">{forecastResult.reason}</span>}</>}
          </section>}

          <p className="side-copy">Marker hiển thị trạng thái tại simulation anchor; history chỉ lấy event as-of từ Replay API.</p>
          <div className="vessel-list" aria-label="Danh sách tàu">
            {tracks.map((track, index) => (
              <button className={`vessel-row ${selected?.vessel_id === track.vessel_id ? 'active' : ''}`} key={track.vessel_id} onClick={() => selectTrack(track)}>
                <span className={`vessel-index ${String(track.data_status).toLowerCase()}`}>{String(index + 1).padStart(2, '0')}</span>
                <span className="vessel-main"><strong>{track.vessel_id}</strong><small>{getDisplayPoint(track, mode) ? `${getDisplayPoint(track, mode).latitude.toFixed(3)}, ${getDisplayPoint(track, mode).longitude.toFixed(3)}` : 'Chưa có fix tại anchor'}</small></span>
                <span className={`row-state ${String(track.data_status).toLowerCase()}`}>{track.data_status}</span>
              </button>
            ))}
            {!loading && !error && tracks.length === 0 && <div className="list-empty">Chưa có snapshot để hiển thị.</div>}
          </div>
          <TrackDetails track={selected} mode={mode} />
          <div className="scope-note"><span>i</span><p>{mode === 'mock' ? 'T04 Mock API độc lập với Replay session. Chuyển mode không sửa Mock data.' : 'Replay dùng synthetic fixture. Forecast được gắn nhãn mock và không phải đầu ra model hay AIS thật.'}</p></div>
        </aside>
      </section>
      <footer className="page-footer"><span>AIT3040 · {mode === 'mock' ? 'S1_T04 MOCK DATA MAP' : 'S4_T17 REPLAY CONTROLS'}</span><span>COORDINATES · LATITUDE / LONGITUDE</span></footer>
    </main>
  )
}
