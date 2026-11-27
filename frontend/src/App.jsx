import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { CircleMarker, MapContainer, Marker, Polyline, TileLayer, Tooltip, useMap } from 'react-leaflet'
import L from 'leaflet'
import { buildMockForecastV1 } from './forecastMock.js'

const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')
const DEMO_SOURCE_ID = 'fixture-denmark-10m-v1'
const S5_SOURCE_ID = 's5-01-synthetic-denmark-v1'
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

function secondsFromStart(value, maxSeconds = SEEK_MAX_SECONDS) {
  const seconds = Math.floor((Date.parse(value) - Date.parse(DEMO_SOURCE_START)) / 1000)
  return Math.max(0, Math.min(maxSeconds, seconds))
}

async function expectedEncounterId(sessionId, pairId, anchor) {
  if (!globalThis.crypto?.subtle) throw new Error('Không thể xác minh định danh encounter trên trình duyệt này.')
  const bytes = new TextEncoder().encode(JSON.stringify([sessionId, pairId, anchor]))
  const hash = await globalThis.crypto.subtle.digest('SHA-256', bytes)
  return 'enc:v1:' + Array.from(new Uint8Array(hash), (byte) => byte.toString(16).padStart(2, '0')).join('')
}

function bindingKey(binding, pairId = binding?.pairId) {
  return binding ? JSON.stringify([binding.sessionId, binding.version, binding.snapshotId, binding.anchor, pairId]) : ''
}

function decisionLabel(risk) {
  if (risk?.decision_status !== 'DECIDED' || typeof risk.alert_triggered !== 'boolean') return 'UNAVAILABLE'
  return risk.alert_triggered ? 'ALERT' : 'NO ALERT'
}

function metric(value, unit = '', digits = 3) {
  return Number.isFinite(value) ? `${value.toFixed(digits)}${unit}` : '—'
}

function validateForecastGeometry(risk, anchor) {
  if (risk.forecast_status !== 'AVAILABLE' || !risk.forecast) return { lines: null, message: '' }
  const forecast = risk.forecast
  const timestamps = forecast.forecast_timestamps
  if (!['M5A', 'CV'].includes(risk.model_status?.active_model) || !Array.isArray(timestamps) || timestamps.length !== 15 || timestamps.some((time, index) => Date.parse(time) !== Date.parse(anchor) + (index + 1) * 60000)) {
    throw new Error('Forecast có model hoặc horizon không hợp lệ.')
  }
  const lines = forecast.forecast_lat_lon
  if (forecast.geographic_availability === 'UNAVAILABLE' || lines === null) return { lines: null, message: 'Forecast có sẵn nhưng không có tọa độ địa lý để vẽ.' }
  if (!Array.isArray(lines) || lines.length !== 2 || lines.some((line) => !Array.isArray(line) || line.length !== 15 || line.some((point) => !Array.isArray(point) || point.length !== 2 || !Number.isFinite(point[0]) || point[0] < -90 || point[0] > 90 || !Number.isFinite(point[1]) || point[1] < -180 || point[1] > 180))) {
    throw new Error('Tọa độ forecast không hợp lệ.')
  }
  return { lines, message: '' }
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

async function readActiveS5Session(signal) {
  const response = await fetch(`${API_BASE}/api/v1/runtime/active-session`, { signal })
  if (!response.ok) throw new Error(await errorMessage(response, 'Không kiểm tra được S5 session hiện hành'))
  const payload = await response.json()
  if (!payload || !Object.hasOwn(payload, 'session')) throw new Error('Active-session API trả về envelope không hợp lệ.')
  const active = payload.session
  if (active === null) return null
  if (!active || active.source_id !== S5_SOURCE_ID || typeof active.session_id !== 'string' ||
      !active.session_id || !Number.isInteger(active.version) || active.version < 0 ||
      !['READY', 'PAUSED', 'PLAYING'].includes(active.status) || !Number.isFinite(Date.parse(active.simulation_time))) {
    throw new Error('Active-session API không trả về S5 session hợp lệ.')
  }
  return active
}

function shipIcon(track, selected, activeAlert = false) {
  const color = track.data_status === 'STALE' ? '#f0aa53' : track.data_status === 'INSUFFICIENT_DATA' ? '#79baff' : '#44d7c0'
  const rotation = track.current_state?.cog_deg ?? track.history?.at(-1)?.cog_deg ?? 0
  const insufficientClass = track.data_status === 'INSUFFICIENT_DATA' ? 'insufficient' : ''
  return L.divIcon({
    className: 'ship-marker-wrap',
    html: `<div class="ship-marker ${insufficientClass} ${selected ? 'selected' : ''} ${activeAlert ? 'active-alert' : ''}" style="--ship-color:${color}"><svg viewBox="0 0 28 34" style="transform:rotate(${rotation}deg)" aria-hidden="true"><path d="M14 2 24 28 14 23 4 28Z"/><path class="ship-marker-core" d="M14 7 19 23 14 20 9 23Z"/></svg></div>`,
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
  const [coverage, setCoverage] = useState(null)
  const [selectedPair, setSelectedPair] = useState(null)
  const [realForecast, setRealForecast] = useState(null)
  const [forecastBusy, setForecastBusy] = useState(false)
  const [forecastMessage, setForecastMessage] = useState('')
  const [runtimeStatus, setRuntimeStatus] = useState(null)
  const [riskEvaluations, setRiskEvaluations] = useState([])
  const [alertPanel, setAlertPanel] = useState({ status: 'idle', items: [], error: '' })
  const [batchState, setBatchState] = useState(null)
  const [schedulerState, setSchedulerState] = useState(null)
  const [s5DiscoveryStatus, setS5DiscoveryStatus] = useState('ready')
  const [s5DiscoveryError, setS5DiscoveryError] = useState('')
  const pairRef = useRef(null)
  const forecastGuardRef = useRef(0)
  const assessmentGuardRef = useRef(0)
  const batchGuardRef = useRef(0)
  const batchControllerRef = useRef(null)
  const evaluationControllerRef = useRef(null)
  const alertControllerRef = useRef(null)
  const assessmentCacheRef = useRef(new Map())
  const s5SessionRef = useRef(null)
  const s5DiscoveryGuardRef = useRef(0)
  const s5DiscoveryControllerRef = useRef(null)
  const seekEditingRef = useRef(false)
  const generationRef = useRef(0)
  const sessionRef = useRef(session)
  const snapshotRef = useRef(snapshotId)
  sessionRef.current = session
  snapshotRef.current = snapshotId

  const clearRealForecast = useCallback(() => {
    forecastGuardRef.current += 1
    assessmentGuardRef.current += 1
    batchGuardRef.current += 1
    batchControllerRef.current?.abort()
    batchControllerRef.current = null
    evaluationControllerRef.current?.abort()
    evaluationControllerRef.current = null
    alertControllerRef.current?.abort()
    alertControllerRef.current = null
    assessmentCacheRef.current.clear()
    setRealForecast(null)
    setForecastBusy(false)
    setForecastMessage('')
    setRiskEvaluations([])
    setAlertPanel({ status: 'idle', items: [], error: '' })
    setBatchState(null)
  }, [])

  const adoptS5Session = useCallback((next) => {
    generationRef.current += 1
    clearRealForecast()
    pairRef.current = null
    snapshotRef.current = null
    s5SessionRef.current = next
    sessionRef.current = next
    setMode('s5')
    setSession(next)
    setTracks([])
    setSelected(null)
    setSnapshotId(null)
    setCoverage(null)
    setSelectedPair(null)
    setSeekOffset(secondsFromStart(next.simulation_time, 1259))
    setForecastEnabled(false)
    setError('')
    setControlError('')
    setPendingControl(null)
    seekEditingRef.current = false
    setLoading(false)
    setS5DiscoveryStatus('ready')
    setS5DiscoveryError('')
  }, [clearRealForecast])

  useEffect(() => {
    if (mode !== 's5') return undefined
    const controller = new AbortController()
    const discoveryToken = ++s5DiscoveryGuardRef.current
    const appGeneration = generationRef.current
    s5DiscoveryControllerRef.current = controller
    setS5DiscoveryStatus('loading')
    setS5DiscoveryError('')
    readActiveS5Session(controller.signal)
      .then((active) => {
        if (controller.signal.aborted || discoveryToken !== s5DiscoveryGuardRef.current) return
        if (appGeneration === generationRef.current && active) adoptS5Session(active)
        else setS5DiscoveryStatus('ready')
      })
      .catch((cause) => {
        if (controller.signal.aborted || discoveryToken !== s5DiscoveryGuardRef.current || cause?.name === 'AbortError') return
        const message = cause instanceof Error ? cause.message : 'Không thể kiểm tra S5 session hiện hành.'
        setS5DiscoveryStatus('error')
        setS5DiscoveryError(message)
        setError(message)
        setLoading(false)
      })
    return () => {
      controller.abort()
      if (s5DiscoveryControllerRef.current === controller) s5DiscoveryControllerRef.current = null
    }
  }, [mode, adoptS5Session])

  const retryS5Discovery = useCallback(async () => {
    s5DiscoveryControllerRef.current?.abort()
    const controller = new AbortController()
    s5DiscoveryControllerRef.current = controller
    const discoveryToken = ++s5DiscoveryGuardRef.current
    const appGeneration = generationRef.current
    setS5DiscoveryStatus('loading')
    setS5DiscoveryError('')
    try {
      const active = await readActiveS5Session(controller.signal)
      if (controller.signal.aborted || discoveryToken !== s5DiscoveryGuardRef.current) return
      if (appGeneration !== generationRef.current) {
        setS5DiscoveryStatus('ready')
        return
      }
      if (active) adoptS5Session(active)
      else setS5DiscoveryStatus('ready')
    } catch (cause) {
      if (controller.signal.aborted || discoveryToken !== s5DiscoveryGuardRef.current || cause?.name === 'AbortError') return
      const message = cause instanceof Error ? cause.message : 'Không thể kiểm tra S5 session hiện hành.'
      setS5DiscoveryStatus('error')
      setS5DiscoveryError(message)
    } finally {
      if (s5DiscoveryControllerRef.current === controller) s5DiscoveryControllerRef.current = null
    }
  }, [adoptS5Session])

  useEffect(() => {
    if (mode !== 'mock' || s5DiscoveryStatus === 'loading') return undefined
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
  }, [mode, refreshKey, s5DiscoveryStatus])

  useEffect(() => {
    if (!['replay', 's5'].includes(mode) || !session?.session_id) return undefined
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

        let nextCoverage = null
        if (mode === 's5') {
          const candidateResponse = await fetch(`${API_BASE}/api/v1/runtime/sessions/${encodeURIComponent(sessionId)}/candidates`, { signal: controller.signal })
          if (!candidateResponse.ok) throw new Error(await errorMessage(candidateResponse, 'Candidate snapshot lỗi'))
          nextCoverage = await candidateResponse.json()
          if (nextCoverage.session_id !== sessionId || nextCoverage.session_version !== nextSession.version || nextCoverage.anchor_utc !== nextSession.simulation_time || !Array.isArray(nextCoverage.pairs)) return
        }
        const snapshotQuery = nextCoverage ? `&snapshot_id=${encodeURIComponent(nextCoverage.snapshot_id)}` : ''
        const tracksResponse = await fetch(`${API_BASE}/api/v1/replay/sessions/${encodeURIComponent(sessionId)}/tracks?limit=50&offset=0${snapshotQuery}`, { signal: controller.signal })
        if (!tracksResponse.ok) throw new Error(await errorMessage(tracksResponse, 'Replay tracks lỗi'))
        const payload = await tracksResponse.json()
        if (!Array.isArray(payload.items) || !payload.snapshot_id || !payload.simulation_time) {
          throw new Error('Replay API thiếu items, snapshot_id hoặc simulation_time')
        }
        if (cancelled || generation !== generationRef.current || sessionRef.current?.session_id !== sessionId) return
        if (nextCoverage && (payload.snapshot_id !== nextCoverage.snapshot_id || payload.simulation_time !== nextCoverage.anchor_utc || payload.items.some((track) => track.anchor_timestamp !== nextCoverage.anchor_utc))) return
        if (mode === 's5' && (snapshotRef.current !== payload.snapshot_id || sessionRef.current?.version !== nextSession.version || sessionRef.current?.simulation_time !== nextSession.simulation_time)) clearRealForecast()
        if (mode === 's5') {
          snapshotRef.current = payload.snapshot_id
          sessionRef.current = nextSession
          s5SessionRef.current = nextSession
          setCoverage(nextCoverage)
          setSelectedPair((current) => {
            const updated = nextCoverage.pairs.find((pair) => pair.pair_id === current?.pair_id) || null
            pairRef.current = updated
            return updated
          })
        }
        setSession((current) => current?.session_id === sessionId && current.version > nextSession.version ? current : nextSession)
        setTracks(payload.items)
        setSnapshotId(payload.snapshot_id)
        setSelected((current) => current ? payload.items.find((item) => item.vessel_id === current.vessel_id) || null : null)
        if (!seekEditingRef.current) setSeekOffset(secondsFromStart(nextSession.simulation_time, mode === 's5' ? 1259 : SEEK_MAX_SECONDS))
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
  }, [mode, session?.session_id, refreshKey, clearRealForecast])

  const switchMode = useCallback((nextMode) => {
    generationRef.current += 1
    clearRealForecast()
    pairRef.current = null
    setSelectedPair(null)
    setCoverage(null)
    seekEditingRef.current = false
    setMode(nextMode)
    setTracks([])
    setSelected(null)
    const restoredSession = nextMode === 's5' ? s5SessionRef.current : null
    sessionRef.current = restoredSession
    snapshotRef.current = null
    setSession(restoredSession)
    setSnapshotId(null)
    setError('')
    setControlError('')
    setPendingControl(null)
    setForecastEnabled(false)
    setLoading(false)
    if (nextMode === 's5') {
      setS5DiscoveryStatus('loading')
      setS5DiscoveryError('')
    }
  }, [clearRealForecast])

  const startReplay = useCallback(async () => {
    const generation = generationRef.current
    let discoveryFailed = false
    setLoading(true)
    setError('')
    setControlError('')
    try {
      if (mode === 's5') {
        setS5DiscoveryStatus('loading')
        setS5DiscoveryError('')
        let active
        try {
          active = await readActiveS5Session()
        } catch (cause) {
          if (generation !== generationRef.current) return
          discoveryFailed = true
          const message = cause instanceof Error ? cause.message : 'Không kiểm tra được S5 session hiện hành.'
          setS5DiscoveryStatus('error')
          setS5DiscoveryError(message)
          throw cause
        }
        if (generation !== generationRef.current) return
        if (active) {
          adoptS5Session(active)
          return
        }
      }
      const response = await fetch(`${API_BASE}/api/v1/replay/sessions`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_id: mode === 's5' ? S5_SOURCE_ID : DEMO_SOURCE_ID }),
      })
      if (!response.ok) {
        if (mode === 's5' && response.status === 409) {
          let active
          try {
            active = await readActiveS5Session()
          } catch (cause) {
            if (generation !== generationRef.current) return
            discoveryFailed = true
            const message = cause instanceof Error ? cause.message : 'Không kiểm tra được S5 session sau HTTP 409.'
            setS5DiscoveryStatus('error')
            setS5DiscoveryError(message)
            throw cause
          }
          if (generation !== generationRef.current) return
          if (active) {
            adoptS5Session(active)
            return
          }
        }
        const prefix = mode === 's5' && response.status === 409
          ? 'Backend báo xung đột session S5 nhưng discovery chưa tìm thấy phiên có thể khôi phục'
          : 'Không tạo được Replay session'
        throw new Error(await errorMessage(response, prefix))
      }
      const next = await response.json()
      if (generation !== generationRef.current) return
      setTracks([])
      setSelected(null)
      setSnapshotId(null)
      seekEditingRef.current = false
      setSession(next)
      sessionRef.current = next
      if (mode === 's5') s5SessionRef.current = next
      setSeekOffset(secondsFromStart(next.simulation_time))
      if (mode === 's5') setS5DiscoveryStatus('ready')
    } catch (cause) {
      if (generation !== generationRef.current) return
      setError(cause instanceof Error ? cause.message : 'Không thể tạo Replay session.')
      if (mode === 's5' && !discoveryFailed) setS5DiscoveryStatus('ready')
    } finally {
      if (generation === generationRef.current) setLoading(false)
    }
  }, [mode, adoptS5Session, s5DiscoveryStatus])

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
      if (operation.action === 'SEEK' || operation.action === 'RESET') {
        seekEditingRef.current = false
        setSeekOffset(secondsFromStart(next.simulation_time, mode === 's5' ? 1259 : SEEK_MAX_SECONDS))
      }
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
      sessionRef.current = next
      if (mode === 's5') {
        s5SessionRef.current = next
        snapshotRef.current = null
        setCoverage(null)
        pairRef.current = null
        setSelectedPair(null)
      }
    } catch (cause) {
      if (operation.generation !== generationRef.current) return
      setControlError(cause instanceof Error ? cause.message : `Replay ${operation.action} thất bại.`)
    } finally {
      setControlBusy(false)
    }
  }, [controlBusy, mode])

  const requestControl = useCallback((action, targetTime) => {
    if (!session) return
    if (mode === 's5') clearRealForecast()
    const operation = {
      sessionId: session.session_id,
      action,
      expectedVersion: session.version,
      generation: generationRef.current,
      targetTime: action === 'SEEK' ? targetTime : undefined,
      idempotencyKey: ['RESET', 'SEEK'].includes(action) ? controlKey() : null,
    }
    dispatchControl(operation)
  }, [dispatchControl, session, mode, clearRealForecast])

  const selectTrack = useCallback(async (track) => {
    setSelected(track)
    const generation = generationRef.current
    const selectedSessionId = mode !== 'mock' ? session?.session_id : null
    const selectedSnapshotId = mode !== 'mock' ? snapshotId : null
    const path = mode === 'mock'
      ? `${API_BASE}/api/v1/mock/tracks/${encodeURIComponent(track.vessel_id)}`
      : `${API_BASE}/api/v1/replay/sessions/${encodeURIComponent(selectedSessionId)}/tracks/${encodeURIComponent(track.vessel_id)}?snapshot_id=${encodeURIComponent(selectedSnapshotId || '')}`
    try {
      const response = await fetch(path)
      if (!response.ok) throw new Error(await errorMessage(response, 'Không tải được lịch sử'))
      const detail = await response.json()
      if (generation !== generationRef.current || (mode !== 'mock' && (sessionRef.current?.session_id !== selectedSessionId || snapshotRef.current !== selectedSnapshotId))) return
      setSelected(detail)
    } catch (cause) {
      if (generation !== generationRef.current) return
      setError(cause instanceof Error ? cause.message : 'Không tải được lịch sử tàu.')
    }
  }, [mode, session?.session_id, snapshotId])

  const saveRiskEvaluation = useCallback((record) => {
    const key = bindingKey(record.binding, record.pairId)
    const stored = { ...record, key }
    assessmentCacheRef.current.set(key, stored)
    setRiskEvaluations((current) => [...current.filter((item) => item.key !== key), stored])
    return stored
  }, [])

  const requestRiskEvaluation = useCallback(async (binding, pair, signal) => {
    const response = await fetch(`${API_BASE}/api/v1/runtime/sessions/${encodeURIComponent(binding.sessionId)}/evaluate`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, signal,
      body: JSON.stringify({ snapshot_id: binding.snapshotId, pair_id: pair.pair_id, request_id: controlKey() }),
    })
    if (!response.ok) {
      const prefix = response.status === 409 ? 'Snapshot đã cũ hoặc xung đột' : response.status === 503 ? 'Runtime unavailable' : 'Không thể đánh giá rủi ro'
      const error = new Error(await errorMessage(response, prefix))
      error.status = response.status
      throw error
    }
    const payload = await response.json()
    const expected = await expectedEncounterId(binding.sessionId, pair.pair_id, binding.anchor)
    const risk = payload.risk
    if (payload.session_id !== binding.sessionId || payload.session_version !== binding.version || payload.snapshot_id !== binding.snapshotId || payload.anchor_utc !== binding.anchor || risk?.replay_session_id !== binding.sessionId || risk?.anchor_timestamp !== binding.anchor || risk?.pair_id !== pair.pair_id || risk?.encounter_id !== expected || JSON.stringify(risk?.vessel_ids) !== JSON.stringify(pair.vessel_ids) || ![true, false, null].includes(risk?.alert_triggered)) {
      throw new Error('Kết quả không khớp session, snapshot, cặp tàu hoặc encounter.')
    }
    const geometry = validateForecastGeometry(risk, binding.anchor)
    return { binding, pairId: pair.pair_id, vesselIds: pair.vessel_ids, risk, lines: geometry.lines, geometryMessage: geometry.message }
  }, [])

  const loadAlerts = useCallback(async (binding, expectedPairId, token) => {
    const isCurrent = () => token === assessmentGuardRef.current && sessionRef.current?.session_id === binding.sessionId && sessionRef.current?.version === binding.version && sessionRef.current?.simulation_time === binding.anchor && sessionRef.current?.status === 'PAUSED' && snapshotRef.current === binding.snapshotId && (pairRef.current?.pair_id || null) === expectedPairId
    alertControllerRef.current?.abort()
    const controller = new AbortController()
    alertControllerRef.current = controller
    setAlertPanel({ status: 'loading', items: [], error: '' })
    try {
      const response = await fetch(`${API_BASE}/api/v1/runtime/sessions/${encodeURIComponent(binding.sessionId)}/alerts?snapshot_id=${encodeURIComponent(binding.snapshotId)}`, { signal: controller.signal })
      if (!response.ok) {
        const prefix = response.status === 409 ? 'Snapshot cảnh báo đã cũ' : response.status === 503 ? 'Alert runtime unavailable' : 'Không tải được cảnh báo'
        const error = new Error(await errorMessage(response, prefix))
        error.status = response.status
        throw error
      }
      const payload = await response.json()
      if (payload.session_id !== binding.sessionId || payload.session_version !== binding.version || payload.snapshot_id !== binding.snapshotId || payload.anchor_utc !== binding.anchor || !Array.isArray(payload.items)) throw new Error('Danh sách cảnh báo không khớp session/snapshot/anchor.')
      const candidates = new Map((coverage?.pairs || []).map((pair) => [pair.pair_id, pair]))
      for (const item of payload.items) {
        const candidate = candidates.get(item.pair_id)
        const expectedEncounter = await expectedEncounterId(binding.sessionId, item.pair_id, item.latest_evaluation_timestamp)
        if (!candidate || item.replay_session_id !== binding.sessionId || JSON.stringify(item.vessel_ids) !== JSON.stringify(candidate.vessel_ids) || item.latest_encounter_id !== expectedEncounter || !['ACTIVE', 'DATA_UNAVAILABLE', 'RESOLVED'].includes(item.alert_status)) throw new Error('Một cảnh báo có identity, lifecycle hoặc encounter không hợp lệ.')
      }
      if (isCurrent()) setAlertPanel({ status: 'ready', items: payload.items, error: '' })
    } catch (cause) {
      if (cause?.name === 'AbortError' || !isCurrent()) return
      setAlertPanel({ status: 'error', items: [], error: cause instanceof Error ? cause.message : 'Alert runtime unavailable' })
    } finally {
      if (alertControllerRef.current === controller) alertControllerRef.current = null
    }
  }, [coverage])

  const selectPair = useCallback((pair) => {
    assessmentGuardRef.current += 1
    batchGuardRef.current += 1
    batchControllerRef.current?.abort()
    batchControllerRef.current = null
    evaluationControllerRef.current?.abort()
    evaluationControllerRef.current = null
    alertControllerRef.current?.abort()
    alertControllerRef.current = null
    setAlertPanel((current) => current.status === 'loading' ? { status: 'idle', items: [], error: '' } : current)
    setForecastBusy(false)
    setBatchState((current) => current?.running ? { ...current, running: false, cancelled: true, message: 'Đã dừng vì cặp tàu được chọn thay đổi.' } : current)
    pairRef.current = pair
    setSelectedPair(pair)
    const current = sessionRef.current
    const snapshot = snapshotRef.current
    const binding = current && snapshot ? { sessionId: current.session_id, version: current.version, snapshotId: snapshot, anchor: current.simulation_time } : null
    const cached = binding ? assessmentCacheRef.current.get(bindingKey(binding, pair.pair_id)) : null
    setRealForecast(cached || null)
    setForecastMessage(pair.unavailable_reason ? `INSUFFICIENT_DATA · ${pair.unavailable_reason}` : cached?.geometryMessage || '')
  }, [])

  const evaluatePair = useCallback(async () => {
    const pair = pairRef.current
    const current = sessionRef.current
    const pinned = snapshotRef.current
    if (!pair || !current || current.status !== 'PAUSED' || !pinned || batchState?.running) return
    const binding = { sessionId: current.session_id, version: current.version, snapshotId: pinned, anchor: current.simulation_time }
    const token = ++assessmentGuardRef.current
    const isCurrent = () => token === assessmentGuardRef.current && sessionRef.current?.session_id === binding.sessionId && sessionRef.current?.version === binding.version && sessionRef.current?.simulation_time === binding.anchor && sessionRef.current?.status === 'PAUSED' && snapshotRef.current === binding.snapshotId && pairRef.current?.pair_id === pair.pair_id
    const cached = assessmentCacheRef.current.get(bindingKey(binding, pair.pair_id))
    if (cached) {
      setRealForecast(cached)
      setForecastMessage(cached.geometryMessage || '')
      return
    }
    const controller = new AbortController()
    evaluationControllerRef.current?.abort()
    evaluationControllerRef.current = controller
    setForecastMessage('')
    setForecastBusy(true)
    try {
      const result = await requestRiskEvaluation(binding, pair, controller.signal)
      if (!isCurrent()) return
      const stored = saveRiskEvaluation(result)
      setRealForecast(stored)
      setForecastMessage(stored.geometryMessage || '')
      await loadAlerts(binding, pair.pair_id, token)
    } catch (cause) {
      if (isCurrent()) setForecastMessage(cause instanceof Error ? cause.message : 'Runtime unavailable')
    } finally {
      if (evaluationControllerRef.current === controller) evaluationControllerRef.current = null
      if (isCurrent()) setForecastBusy(false)
    }
  }, [batchState?.running, loadAlerts, requestRiskEvaluation, saveRiskEvaluation])

  const evaluateAllPairs = useCallback(async () => {
    const current = sessionRef.current
    const pinned = snapshotRef.current
    const pairs = coverage?.pairs || []
    if (mode !== 's5' || !current || current.status !== 'PAUSED' || !pinned || !pairs.length || batchState?.running || forecastBusy) return
    const binding = { sessionId: current.session_id, version: current.version, snapshotId: pinned, anchor: current.simulation_time }
    const selectedAtStart = pairRef.current?.pair_id || null
    const batchToken = ++batchGuardRef.current
    const assessmentToken = ++assessmentGuardRef.current
    evaluationControllerRef.current?.abort()
    evaluationControllerRef.current = null
    alertControllerRef.current?.abort()
    const controller = new AbortController()
    batchControllerRef.current?.abort()
    batchControllerRef.current = controller
    const isCurrent = () => batchToken === batchGuardRef.current && assessmentToken === assessmentGuardRef.current && sessionRef.current?.session_id === binding.sessionId && sessionRef.current?.version === binding.version && sessionRef.current?.simulation_time === binding.anchor && sessionRef.current?.status === 'PAUSED' && snapshotRef.current === binding.snapshotId && (pairRef.current?.pair_id || null) === selectedAtStart
    const initial = pairs.map((pair) => ({ pairId: pair.pair_id, vesselIds: pair.vessel_ids, status: 'PENDING', riskScore: null, threshold: null, model: null }))
    setBatchState({ running: true, cancelled: false, processed: 0, total: pairs.length, items: initial, message: '' })
    setForecastMessage('')
    let refreshAlerts = true
    for (const pair of pairs) {
      if (!isCurrent()) return
      try {
        const cached = assessmentCacheRef.current.get(bindingKey(binding, pair.pair_id))
        const result = cached || await requestRiskEvaluation(binding, pair, controller.signal)
        if (!isCurrent()) return
        const stored = cached || saveRiskEvaluation(result)
        const row = { pairId: pair.pair_id, vesselIds: pair.vessel_ids, status: decisionLabel(stored.risk), riskScore: stored.risk.risk_score, threshold: stored.risk.threshold, model: stored.risk.model_status?.active_model || null }
        setBatchState((previous) => previous ? { ...previous, processed: previous.processed + 1, items: previous.items.map((item) => item.pairId === row.pairId ? row : item) } : previous)
        if (pairRef.current?.pair_id === pair.pair_id) {
          setRealForecast(stored)
          setForecastMessage(stored.geometryMessage || '')
        }
      } catch (cause) {
        if (!isCurrent() || cause?.name === 'AbortError') return
        const rowStatus = cause?.status === 409 || cause?.status === 503 ? 'UNAVAILABLE' : 'FAILED'
        setBatchState((previous) => previous ? { ...previous, processed: previous.processed + 1, items: previous.items.map((item) => item.pairId === pair.pair_id ? { ...item, status: rowStatus, message: cause?.message || 'Request thất bại' } : item), message: cause?.message || 'Request thất bại' } : previous)
        if ([409, 503].includes(cause?.status)) {
          refreshAlerts = false
          setForecastMessage(cause.message)
          break
        }
      }
    }
    if (refreshAlerts && isCurrent()) await loadAlerts(binding, selectedAtStart, assessmentToken)
    if (batchControllerRef.current === controller) batchControllerRef.current = null
    if (batchToken === batchGuardRef.current && assessmentToken === assessmentGuardRef.current) setBatchState((previous) => previous ? { ...previous, running: false } : previous)
  }, [batchState?.running, coverage, forecastBusy, loadAlerts, mode, requestRiskEvaluation, saveRiskEvaluation])

  useEffect(() => {
    if (mode !== 's5') return undefined
    let cancelled = false
    fetch(`${API_BASE}/api/v1/runtime/status`).then((response) => response.ok ? response.json() : null).then((body) => { if (!cancelled) setRuntimeStatus(body) }).catch(() => { if (!cancelled) setRuntimeStatus(null) })
    return () => { cancelled = true }
  }, [mode, realForecast])

  useEffect(() => {
    if (mode !== 's5' || !session?.session_id) {
      setSchedulerState(null)
      return undefined
    }
    const sessionId = session.session_id
    let cancelled = false
    let timer
    let controller
    const pollScheduler = async () => {
      controller = new AbortController()
      try {
        const response = await fetch(`${API_BASE}/api/v1/runtime/scheduler?session_id=${encodeURIComponent(sessionId)}`, { signal: controller.signal })
        if (!response.ok) throw new Error(await errorMessage(response, 'Không đọc được trạng thái automatic monitoring'))
        const payload = await response.json()
        if (!cancelled && sessionRef.current?.session_id === sessionId) setSchedulerState(payload)
      } catch (cause) {
        if (!cancelled && cause?.name !== 'AbortError' && sessionRef.current?.session_id === sessionId) {
          setSchedulerState((current) => ({ ...(current || {}), scheduler_error: cause instanceof Error ? cause.message : 'Scheduler unavailable' }))
        }
      } finally {
        if (!cancelled) timer = window.setTimeout(pollScheduler, REPLAY_POLL_MS)
      }
    }
    pollScheduler()
    return () => { cancelled = true; window.clearTimeout(timer); controller?.abort() }
  }, [mode, session?.session_id])

  const retryControl = () => { if (pendingControl) dispatchControl(pendingControl) }
  const replayCanControl = session && ['READY', 'PLAYING', 'PAUSED'].includes(session.status) && !controlBusy && !pendingControl
  const seekPreview = seekTimeAt(seekOffset)
  const forecastResult = useMemo(() => forecastEnabled && mode === 'replay'
    ? buildMockForecastV1(selected)
    : { forecast: null, reason: null }, [forecastEnabled, mode, selected])
  const activeBinding = session?.session_id && snapshotId ? { sessionId: session.session_id, version: session.version, snapshotId, anchor: session.simulation_time } : null
  const selectedEvaluationKey = activeBinding && selectedPair ? bindingKey(activeBinding, selectedPair.pair_id) : ''
  const automaticBatch = schedulerState?.latest_batch && schedulerState.latest_batch.session_id === session?.session_id
    ? schedulerState.latest_batch : null
  const automaticBatchAgeSeconds = automaticBatch && Number.isFinite(Date.parse(session?.simulation_time))
    ? (Date.parse(session.simulation_time) - Date.parse(automaticBatch.anchor_utc)) / 1000 : Infinity
  const automaticBatchCurrent = Boolean(session?.status === 'PLAYING' && schedulerState?.monitoring_status === 'PLAYING' &&
    automaticBatch?.session_generation === session?.version && automaticBatchAgeSeconds >= 0 && automaticBatchAgeSeconds < 60)
  const automaticEvaluations = useMemo(() => {
    if (!automaticBatch || automaticBatch.session_generation !== session?.version || !Array.isArray(automaticBatch.pairs)) return []
    return automaticBatch.pairs.map((item) => {
      const pair = coverage?.pairs?.find((candidate) => candidate.pair_id === item.pair_id)
      if (!pair || !item.risk || !Array.isArray(item.vessel_ids) || JSON.stringify(item.vessel_ids) !== JSON.stringify(pair.vessel_ids)) return null
      let geometry = { lines: null, message: '' }
      try { geometry = validateForecastGeometry(item.risk, automaticBatch.anchor_utc) } catch { return null }
      const binding = { sessionId: automaticBatch.session_id, version: automaticBatch.session_generation,
        snapshotId: automaticBatch.snapshot_id, anchor: automaticBatch.anchor_utc }
      return { binding, pairId: item.pair_id, vesselIds: item.vessel_ids, risk: item.risk,
        lines: geometry.lines, geometryMessage: geometry.message, auto: true }
    }).filter(Boolean)
  }, [automaticBatch, coverage, session?.version])
  const manualRiskEvaluation = selectedEvaluationKey ? riskEvaluations.find((item) => item.key === selectedEvaluationKey) || null : null
  const selectedRiskEvaluation = session?.status === 'PLAYING'
    ? automaticBatchCurrent ? automaticEvaluations.find((item) => item.pairId === selectedPair?.pair_id) || null : null
    : manualRiskEvaluation
  const currentForecast = mode === 's5' && selectedRiskEvaluation ? selectedRiskEvaluation : null
  const forecastLines = mode === 's5' && (session?.status !== 'PLAYING' || automaticBatchCurrent) ? currentForecast?.lines || [] : mode === 's5' ? [] : forecastResult.forecast?.forecast_lat_lon || []
  const visibleAlertItems = session?.status === 'PLAYING' && automaticBatch
    ? automaticBatch.alerts || [] : alertPanel.items
  const activeAlertPairIds = useMemo(() => new Set(visibleAlertItems.filter((item) => item.alert_status === 'ACTIVE').map((item) => item.pair_id)), [visibleAlertItems])
  const alertVesselIds = useMemo(() => new Set(visibleAlertItems.filter((item) => item.alert_status === 'ACTIVE').flatMap((item) => item.vessel_ids)), [visibleAlertItems])
  const cpaPoints = useMemo(() => {
    const risk = selectedRiskEvaluation?.risk
    const record = selectedRiskEvaluation
    const minutes = risk?.predicted_closest_time_minutes
    const timestamp = risk?.predicted_closest_timestamp
    const forecast = risk?.forecast
    if (!record || !Array.isArray(record.lines) || !Number.isInteger(minutes) || minutes < 1 || minutes > 15 || !timestamp || !Array.isArray(forecast?.forecast_timestamps)) return []
    const index = minutes - 1
    if (Date.parse(forecast.forecast_timestamps[index]) !== Date.parse(timestamp) || Date.parse(timestamp) !== Date.parse(record.binding.anchor) + minutes * 60000) return []
    return record.lines.map((line, vesselIndex) => ({ position: line[index], vesselIndex, timestamp, distance: risk.predicted_min_distance_nm }))
  }, [selectedRiskEvaluation])
  const assessedPairCount = session?.status === 'PLAYING'
    ? automaticBatchCurrent ? (automaticBatch?.evaluated || 0) : 0
    : activeBinding ? riskEvaluations.filter((item) => item.binding.sessionId === activeBinding.sessionId && item.binding.version === activeBinding.version && item.binding.snapshotId === activeBinding.snapshotId && item.binding.anchor === activeBinding.anchor).length : 0
  const batchCounts = batchState?.items.reduce((counts, item) => { counts[item.status] = (counts[item.status] || 0) + 1; return counts }, {}) || {}
  const automaticCounts = automaticBatch?.pairs?.reduce((counts, item) => {
    const status = decisionLabel(item.risk)
    counts[status] = (counts[status] || 0) + 1
    return counts
  }, {}) || {}
  const visibleAlertsStatus = session?.status === 'PLAYING'
    ? schedulerState?.scheduler_error ? 'error' : schedulerState?.running && !automaticBatch ? 'loading' : automaticBatch ? 'ready' : 'idle'
    : alertPanel.status
  const historyLines = useMemo(() => tracks.map((track) => ({
    id: track.vessel_id,
    status: track.data_status,
    positions: getRenderableHistory(track, mode).map((point) => [point.latitude, point.longitude]),
  })).filter((line) => line.positions.length > 0), [mode, tracks])

  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="AIT3040 Track Map home"><span className="brand-mark">A</span><span><strong>AIT3040</strong><small>MARITIME SAFETY SYSTEM</small></span></a>
        <div className="topbar-right"><span className="connection-dot" /> {mode === 'mock' ? 'MOCK API' : 'REPLAY API'} <span className="topbar-divider" /> {mode === 's5' ? 'ACADEMIC PROTOTYPE' : mode === 'mock' ? 'SPRINT 01' : 'S4_T17'}</div>
      </header>

      <section className="page-heading" id="top">
        <div><span className="eyebrow">DATA EXPLORER / TRACKS</span><h1>Vessel movement</h1><p>Vị trí và history lấy từ simulation clock UTC của backend.</p></div>
        <div className="mock-stamp"><span>◆</span> {mode === 'mock' ? 'MOCK DATA' : 'SYNTHETIC REPLAY FIXTURE'} <small>{mode === 'mock' ? 'KHÔNG PHẢI AIS THẬT' : 'KHÔNG PHẢI NGUỒN AIS ĐÃ XÁC MINH'}</small></div>
      </section>

      <section className={mode === 's5' ? 'workspace s5-dashboard' : 'workspace'}>
        <div className="map-panel">
          <div className="map-toolbar">
            <div className="map-title"><span className="map-pulse" /> KATTEGAT · DENMARK <small>55.6°N — 12.7°E</small></div>
            <div className="map-actions">
              {mode !== 'mock' && session && <button className="refresh-button" onClick={() => requestControl('RESET')} disabled={!replayCanControl} aria-label="Reset replay">RESET</button>}
              <button className="refresh-button" onClick={() => { if (mode === 's5') clearRealForecast(); generationRef.current += 1; setRefreshKey((key) => key + 1) }} disabled={loading} aria-label="Refresh replay data">↻ <span>Refresh</span></button>
            </div>
          </div>
          <div className="map-canvas">
            <MapContainer center={[55.69, 12.61]} zoom={9} scrollWheelZoom className="leaflet-map">
              <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
              <FitTracks tracks={tracks} mode={mode} />
              {historyLines.map((line) => <Polyline key={`history-${line.id}`} positions={line.positions} pathOptions={{ className: 'history-path', color: mode === 's5' && activeAlertPairIds.size && alertVesselIds.has(line.id) ? '#ff657c' : mode === 's5' && selectedPair?.vessel_ids?.includes(line.id) ? (selectedPair.vessel_ids[0] === line.id ? '#ffc165' : '#67b9ff') : line.status === 'STALE' ? '#f0aa53' : '#48d7c0', weight: selected?.vessel_id === line.id || selectedPair?.vessel_ids?.includes(line.id) || alertVesselIds.has(line.id) ? 4 : 2.5, opacity: 0.88, dashArray: line.status === 'STALE' ? '7 7' : undefined }} />)}
              {forecastLines.map((line, index) => <Polyline key={`forecast-${index}`} positions={line} pathOptions={{ className: mode === 's5' ? 'forecast-real-path' : 'forecast-mock-path', color: mode === 's5' ? (index === 0 ? '#ffc165' : '#67b9ff') : (index === 0 ? '#d68cff' : '#87a8ff'), weight: 3, opacity: 0.95, dashArray: '5 8' }} />)}
              {cpaPoints.map((point) => <CircleMarker key={`cpa-${point.vesselIndex}`} center={point.position} radius={9} pathOptions={{ color: point.vesselIndex === 0 ? '#ffc165' : '#67b9ff', weight: 3, fillColor: '#0a1724', fillOpacity: 0.95 }}><Tooltip>CPA dự báo · {formatUtc(point.timestamp)} · {metric(point.distance, ' NM')}</Tooltip></CircleMarker>)}
              {tracks.map((track) => ({ track, point: getDisplayPoint(track, mode) })).filter(({ point }) => point).map(({ track, point }) => (
                <Marker key={track.vessel_id} position={[point.latitude, point.longitude]} icon={shipIcon(track, selected?.vessel_id === track.vessel_id || selectedPair?.vessel_ids?.includes(track.vessel_id), alertVesselIds.has(track.vessel_id))} eventHandlers={{ click: () => selectTrack(track) }}>
                  <Tooltip direction="top" offset={[0, -13]} permanent className={alertVesselIds.has(track.vessel_id) ? 'vessel-map-label alert-map-label' : 'vessel-map-label'}>{track.vessel_id} · {track.data_status}{alertVesselIds.has(track.vessel_id) ? ' · ALERT' : ''}{track.data_status === "INSUFFICIENT_DATA" ? ` · observed ${formatUtc(point.source_timestamp)}` : ""}</Tooltip>
                </Marker>
              ))}
            </MapContainer>
            {loading && <div className="map-overlay"><span className="spinner" />Đang tải snapshot…</div>}
            {!loading && error && <div className="map-overlay error-overlay"><strong>Replay/Mock API lỗi</strong><span>{error}</span><button onClick={() => { generationRef.current += 1; setRefreshKey((key) => key + 1) }}>Thử lại</button></div>}
            {!loading && !error && tracks.length === 0 && <div className="map-overlay empty-overlay"><strong>Chưa có tàu trong snapshot</strong><span>API trả về danh sách rỗng hoặc chưa bắt đầu session.</span></div>}
            <div className="map-legend"><span><i className="legend-valid" />VALID</span>{mode !== 'mock' && <span><i className="legend-insufficient" />INSUFFICIENT_DATA</span>}<span><i className="legend-stale" />STALE</span><span><i className="legend-line" />HISTORY</span>{mode === 's5' && selectedPair && <><span><i className="legend-vessel-a" />TÀU A</span><span><i className="legend-vessel-b" />TÀU B</span></>}{forecastLines.length > 0 && <span><i className="legend-forecast" />{mode === 's5' ? 'FORECAST A / B' : 'FORECAST MOCK'}</span>}{cpaPoints.length > 0 && <span><i className="legend-cpa" />CPA DỰ BÁO</span>}{activeAlertPairIds.size > 0 && <span><i className="legend-alert" />ALERT ACTIVE</span>}</div>
            <div className="map-attribution">Leaflet · OpenStreetMap</div>
          </div>
          <div className="map-footer"><span>SIMULATION UTC</span><strong>{mode !== 'mock' ? formatUtc(session?.simulation_time) : formatUtc(tracks[0]?.anchor_timestamp)}</strong><span>·</span><span>NO FUTURE AIS MESSAGES</span></div>
        </div>

        <aside className="side-panel">
          <div className="fleet-heading"><div><span className="eyebrow">{mode === 'mock' ? 'AIS MOCK FEED' : 'REPLAY SESSION'}</span><h2>Vessels <span>{tracks.length.toString().padStart(2, '0')}</span></h2></div><span className="feed-live">{mode === 'mock' ? 'LOCAL' : session?.status || 'FIXTURE'}</span></div>
          <div className="data-mode-switch" role="group" aria-label="Chế độ dữ liệu">
            <button className={mode === 'mock' ? 'mode-button active' : 'mode-button'} aria-pressed={mode === 'mock'} onClick={() => switchMode('mock')}>Mock</button>
            <button className={mode === 'replay' ? 'mode-button active' : 'mode-button'} aria-pressed={mode === 'replay'} onClick={() => switchMode('replay')}>Replay fixture</button>
            <button className={mode === 's5' ? 'mode-button active' : 'mode-button'} aria-pressed={mode === 's5'} onClick={() => switchMode('s5')}>S5 nhiều tàu</button>
          </div>

          {mode !== 'mock' && <section className="replay-controls" aria-label="Replay controls">
            <div className="replay-controls-heading"><strong>REPLAY CONTROLS</strong><span>{session?.status || 'NO SESSION'}</span></div>
            {!session && mode === 's5' && s5DiscoveryStatus === 'loading' && <p className="forecast-caption" role="status">Đang kiểm tra session S5 hiện hành…</p>}
            {!session && mode === 's5' && s5DiscoveryStatus === 'error' && <div className="session-discovery-error" role="alert"><span>{s5DiscoveryError}</span><button className="retry-control" disabled={loading} onClick={retryS5Discovery}>Thử lại khôi phục phiên</button></div>}
            {!session && (mode === 'replay' || (mode === 's5' && s5DiscoveryStatus === 'ready')) && <button className="replay-start-button" disabled={loading} onClick={startReplay}>Bắt đầu replay fixture</button>}
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
                <input id="replay-seek" aria-label="Seek UTC time" type="range" min="0" max={mode === 's5' ? 1259 : SEEK_MAX_SECONDS} step="1" value={seekOffset} onChange={(event) => { seekEditingRef.current = true; setSeekOffset(Number(event.target.value)) }} disabled={!replayCanControl} />
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

          {mode === 's5' && <section className="s5-pairs" aria-label="Cặp tàu và forecast">
            <div className="s5-section-title"><strong>CẶP TÀU</strong><span>SYNTHETIC · ACADEMIC</span></div>
            {session?.status === 'PLAYING' && <section className="automatic-monitoring" aria-label="Automatic monitoring">
              <div className="automatic-heading"><strong>AUTOMATIC MONITORING</strong><span className={automaticBatchCurrent ? 'auto-live' : 'auto-idle'}>{schedulerState?.monitoring_status || 'WAITING'}</span></div>
              <div className="automatic-facts">
                <span>Replay clock <b>{formatUtc(session.simulation_time)}</b></span>
                <span>Evaluation anchor <b>{formatUtc(schedulerState?.active_anchor || automaticBatch?.anchor_utc)}</b></span>
                <span>Latest completed <b>{formatUtc(schedulerState?.latest_completed_anchor)}</b></span>
                <span>Pairs <b>{automaticBatch ? `${automaticBatch.evaluated}/${automaticBatch.expected}` : '0/0'}</b></span>
                <span>Alert / no-alert / unavailable <b>{automaticCounts.ALERT || 0} / {automaticCounts['NO ALERT'] || 0} / {automaticCounts.UNAVAILABLE || 0}</b></span>
                <span>Latency <b>{automaticBatch ? `${metric(automaticBatch.latency_seconds, ' s', 2)} · P50 ${metric(schedulerState?.latency_p50_seconds, ' s', 2)} · P95 ${metric(schedulerState?.latency_p95_seconds, ' s', 2)} (${schedulerState?.latency_sample_count || 0})` : '—'}</b></span>
                <span>Pending / skipped / failed / deadline misses <b>{schedulerState?.pending_anchor ? formatUtc(schedulerState.pending_anchor) : '—'} / {schedulerState?.skipped_anchors?.length || 0} / {schedulerState?.failed_anchors?.length || 0} / {schedulerState?.missed_deadlines || 0}</b></span>
              </div>
              <strong className="auto-result-state" role="status">{schedulerState?.scheduler_error || (schedulerState?.running ? 'Đang xử lý batch…' : automaticBatchCurrent ? 'Kết quả hiện hành · as-of anchor' : automaticBatch ? `Forecast hết hiệu lực · as-of ${formatUtc(automaticBatch.anchor_utc)}` : schedulerState?.last_outcome || 'Đang chờ anchor phù hợp')}</strong>
              {automaticBatch?.pairs?.length > 0 && <ul className="automatic-pair-results">{automaticBatch.pairs.map((item) => <li key={item.pair_id}><span>{item.vessel_ids.map((id) => id.split(':').at(-1).toUpperCase()).join(' — ')}</span><b className={`result-${decisionLabel(item.risk).toLowerCase().replace(' ', '-')}`}>{decisionLabel(item.risk)}</b>{item.risk?.risk_score != null && <span>{metric(item.risk.risk_score, '', 6)}</span>}</li>)}</ul>}
              <span className="forecast-caption">SYNTHETIC FIXTURE · ACADEMIC PROTOTYPE · Tự động đánh giá khi Replay ở PLAYING.</span>
            </section>}
            {coverage ? <><span className="coverage-caption">Candidate coverage</span><div className="coverage-grid"><span>Expected <b>{coverage.expected}</b></span><span>Evaluated <b>{coverage.evaluated}</b></span><span>Eligible <b>{coverage.eligible}</b></span><span>Unavailable <b>{coverage.unavailable}</b></span></div><span className="coverage-caption">Risk evaluations tại binding này</span><div className="evaluation-coverage"><b>{assessedPairCount}/{coverage.expected}</b><span>cặp đã có kết quả risk</span></div></> : <p className="forecast-caption">Chưa có candidate snapshot.</p>}
            <div className="pair-list" aria-label="Danh sách cặp tàu">{coverage?.pairs.map((pair) => <button key={pair.pair_id} className={`pair-row ${selectedPair?.pair_id === pair.pair_id ? 'active' : ''}`} onClick={() => selectPair(pair)}><span>{pair.vessel_ids.map((id) => id.split(':').at(-1).toUpperCase()).join(' — ')}</span><small>{pair.unavailable_reason ? 'INSUFFICIENT_DATA' : 'ELIGIBLE'}</small></button>)}</div>
            {selectedPair && <><div className="pair-details"><span className="vessel-a">A · {selectedPair.vessel_ids[0]}</span><span className="vessel-b">B · {selectedPair.vessel_ids[1]}</span></div><button className="replay-start-button" aria-label="Dự báo cặp tàu" onClick={evaluatePair} disabled={forecastBusy || batchState?.running || session?.status !== 'PAUSED'}>{forecastBusy ? 'Đang đánh giá cặp tàu…' : selectedPair.unavailable_reason ? 'Đánh giá khả năng dữ liệu' : 'Đánh giá Risk và forecast'}</button></>}
            <button className="batch-button" onClick={evaluateAllPairs} disabled={!coverage?.pairs?.length || batchState?.running || forecastBusy || session?.status !== 'PAUSED'}>{batchState?.running ? `Đang đánh giá ${batchState.processed}/${batchState.total}…` : `Đánh giá tất cả ${coverage?.expected || 10} cặp`}</button>
            <p className="forecast-caption">Khi PAUSED, giữ đánh giá thủ công từng cặp hoặc toàn bộ cặp. Khi PLAYING, backend tự đánh giá tại anchor phút và giao diện chỉ đọc kết quả đã công bố.</p>
            {session?.status !== 'PAUSED' && <p className="forecast-caption">PAUSE hoặc SEEK đến mốc cần đánh giá.</p>}
            {runtimeStatus?.runtime_status === 'UNAVAILABLE' && runtimeStatus.reason !== 'NOT_INITIALIZED' && <p className="control-error">Runtime unavailable · {runtimeStatus.reason}</p>}
            {forecastMessage && <p className="control-error" role="status">{forecastMessage}</p>}
            {batchState && <div className="batch-progress" role="status" aria-label="Tiến độ đánh giá tất cả cặp"><strong>{batchState.cancelled ? 'Batch đã dừng' : batchState.running ? 'Batch đang chạy' : 'Batch hoàn tất'}</strong><span>Đã xử lý {batchState.processed}/{batchState.total}</span><div className="batch-counts"><span>Alert <b>{batchCounts.ALERT || 0}</b></span><span>No-alert <b>{batchCounts['NO ALERT'] || 0}</b></span><span>Unavailable <b>{batchCounts.UNAVAILABLE || 0}</b></span><span>Failed <b>{batchCounts.FAILED || 0}</b></span><span>Pending <b>{batchCounts.PENDING || 0}</b></span></div>{batchState.message && <span className="batch-message">{batchState.message}</span>}<ul className="batch-results">{batchState.items.map((item) => <li key={item.pairId}><span>{item.vesselIds.map((id) => id.split(':').at(-1).toUpperCase()).join(' — ')}</span><b className={`result-${String(item.status).toLowerCase().replace(' ', '-')}`}>{item.status}</b>{item.status === 'ALERT' || item.status === 'NO ALERT' ? <span>{metric(item.riskScore)} / {metric(item.threshold)}</span> : <span>{item.message || '—'}</span>}</li>)}</ul></div>}
            {currentForecast && <div className="real-forecast-info" role="status"><strong>{currentForecast.auto ? 'AUTO · ' : ''}{currentForecast.risk.model_status?.active_model === 'M5A' ? 'M5a · ACTUAL MODEL' : currentForecast.risk.model_status?.active_model === 'CV' ? 'CV FALLBACK' : 'FORECAST UNAVAILABLE'}</strong><span>As-of {formatUtc(currentForecast.binding.anchor)} · +1…+15 phút</span><span><b className="vessel-a">A</b> {currentForecast.vesselIds[0]} · <b className="vessel-b">B</b> {currentForecast.vesselIds[1]}</span><span>Đường liền: history · Nét đứt: forecast</span></div>}
            {session?.status === 'PLAYING' && automaticBatch && !automaticBatchCurrent && <p className="forecast-caption" role="status">Kết quả forecast đã hết hiệu lực; không hiển thị trên bản đồ như forecast hiện tại.</p>}
          </section>}

          {mode === 's5' && <>
            <section className="risk-panel" aria-label="Risk Panel">
              <div className="dashboard-heading"><div><span className="eyebrow">RISK ENGINE V4</span><h2>Đánh giá rủi ro</h2></div><span className="feed-live">{selectedRiskEvaluation ? formatUtc(selectedRiskEvaluation.binding.anchor) : 'CHƯA ĐÁNH GIÁ'}</span></div>
              {!selectedPair && <p className="panel-empty">Chọn một cặp tàu để xem kết quả risk hiện có.</p>}
              {selectedPair && !selectedRiskEvaluation && <p className="panel-empty">Cặp này chưa được đánh giá tại snapshot đang mở. Unavailable/null không có nghĩa là no-alert.</p>}
              {selectedRiskEvaluation && <>
                <div className="risk-decision"><div><span>RISK SCORE · KHÔNG PHẢI XÁC SUẤT</span><strong>{metric(selectedRiskEvaluation.risk.risk_score, '', 6)}</strong><small>Threshold {metric(selectedRiskEvaluation.risk.threshold, '', 3)} · {selectedRiskEvaluation.risk.model_status?.active_model || 'MODEL N/A'}{selectedRiskEvaluation.risk.model_status?.fallback_used ? ' · FALLBACK' : ''}</small></div><b className={`decision-badge ${decisionLabel(selectedRiskEvaluation.risk).toLowerCase().replace(' ', '-')}`}>{decisionLabel(selectedRiskEvaluation.risk)}</b></div>
                <div className="risk-metrics"><div><span>Current DCPA / TCPA</span><b>{metric(selectedRiskEvaluation.risk.current_dcpa_nm, ' NM')} / {metric(selectedRiskEvaluation.risk.current_tcpa_minutes, ' min')}</b></div><div><span>Predicted DCPA / CPA time</span><b>{metric(selectedRiskEvaluation.risk.predicted_min_distance_nm, ' NM')} / {metric(selectedRiskEvaluation.risk.predicted_closest_time_minutes, ' min')}</b></div><div><span>Predicted CPA UTC</span><b>{formatUtc(selectedRiskEvaluation.risk.predicted_closest_timestamp)}</b></div><div><span>Forecast horizon · anchor UTC</span><b>15 min · {formatUtc(selectedRiskEvaluation.risk.anchor_timestamp)}</b></div></div>
                <details className="risk-components"><summary>Thành phần kỹ thuật</summary><div><span>Predicted CPA score</span><b>{metric(selectedRiskEvaluation.risk.predicted_cpa_score, '', 6)}</b></div><div><span>Current CPA score</span><b>{metric(selectedRiskEvaluation.risk.current_cpa_score, '', 6)}</b></div><div><span>Rule proxy</span><b>{metric(selectedRiskEvaluation.risk.rule_score, '', 6)}</b></div><div><span>Decision reason</span><b>{selectedRiskEvaluation.risk.decision_reason || '—'}</b></div><div><span>Current CPA status</span><b>{selectedRiskEvaluation.risk.current_cpa_status || '—'}</b></div></details>
              </>}
            </section>

            <section className="alert-panel" aria-label="Alert List">
              <div className="dashboard-heading"><div><span className="eyebrow">SESSION ALERT STATE</span><h2>Cảnh báo</h2></div><button className="refresh-alerts" onClick={() => activeBinding && selectedPair && loadAlerts(activeBinding, selectedPair.pair_id, ++assessmentGuardRef.current)} disabled={!activeBinding || !selectedPair || session?.status !== 'PAUSED' || alertPanel.status === 'loading' || forecastBusy || batchState?.running}>Làm mới</button></div>
              <p className="alert-scope">ACADEMIC PROTOTYPE · SYNTHETIC FIXTURE · Không gửi cảnh báo hàng hải chính thức.</p>
              {visibleAlertsStatus === 'idle' && <p className="panel-empty">Chưa có alert state cho session hiện hành.</p>}
              {visibleAlertsStatus === 'loading' && <p className="panel-empty"><span className="spinner small" /> Đang chờ batch tự động đầu tiên…</p>}
              {visibleAlertsStatus === 'error' && <p className="control-error" role="alert">Automatic monitoring unavailable · {schedulerState?.scheduler_error || alertPanel.error}</p>}
              {visibleAlertsStatus === 'ready' && visibleAlertItems.length === 0 && <p className="panel-empty">Runtime chưa trả alert record nào cho session này; đây không phải kết luận cho các cặp chưa đánh giá.</p>}
              {visibleAlertsStatus === 'ready' && visibleAlertItems.length > 0 && <ul className="alert-list">{visibleAlertItems.map((item) => <li key={item.alert_id} className={`alert-card alert-${item.alert_status.toLowerCase()}`}><div className="alert-title"><strong>{item.vessel_ids.map((id) => id.split(':').at(-1).toUpperCase()).join(' — ')}</strong><b>{item.alert_status}</b></div><div className="alert-metrics"><span>Risk / threshold <b>{metric(item.risk_score, '', 6)} / {metric(item.threshold, '', 3)}</b></span><span>DCPA / TCPA <b>{metric(item.current_dcpa_nm, ' NM')} / {metric(item.current_tcpa_minutes, ' min')}</b></span><span>Predicted DCPA / CPA <b>{metric(item.predicted_min_distance_nm, ' NM')} / {metric(item.predicted_closest_time_minutes, ' min')}</b></span><span>Model <b>{item.active_model || '—'}</b></span><span>Anchor gần nhất <b>{formatUtc(item.latest_evaluation_timestamp)}</b></span><span>Lý do <b>{item.status_reason || '—'}</b></span></div>{item.alert_status === 'DATA_UNAVAILABLE' && <p className="last-valid-note">DATA_UNAVAILABLE — {item.values_are_last_valid ? `các chỉ số bên trên là lần hợp lệ gần nhất (${formatUtc(item.values_as_of)}), không phải trạng thái hiện tại.` : 'không có chỉ số hiện tại hợp lệ.'}</p>}</li>)}</ul>}
            </section>
          </>}

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
          <div className="scope-note"><span>i</span><p>{mode === 'mock' ? 'T04 Mock API độc lập với Replay session.' : mode === 's5' ? 'Synthetic fixture · academic prototype. Không phải AIS thật hoặc cảnh báo hàng hải chính thức.' : 'Replay dùng synthetic fixture. Forecast được gắn nhãn mock và không phải đầu ra model hay AIS thật.'}</p></div>
        </aside>
      </section>
      <footer className="page-footer"><span>AIT3040 · {mode === 's5' ? 'S5 RISK & ALERT · ACADEMIC PROTOTYPE' : mode === 'mock' ? 'S1_T04 MOCK DATA MAP' : 'S4_T17 REPLAY CONTROLS'}</span><span>COORDINATES · LATITUDE / LONGITUDE</span></footer>
    </main>
  )
}
