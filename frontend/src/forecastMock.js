const FORECAST_POINTS = 15
const UTC_Z_SECONDS = /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$/
const FORECAST_KEYS = [
  'schema_version', 'forecast_timestamps', 'forecast_displacement_en_nm',
  'forecast_common_en_nm', 'forecast_lat_lon', 'geographic_availability',
  'coordinate_origin', 'anchor_positions_en_nm',
]
const ORIGIN_KEYS = [
  'origin_latitude', 'origin_longitude', 'origin_timestamp', 'origin_vessel_id',
  'coordinate_method', 'coordinate_unit', 'coordinate_dtype', 'geographic_mapping_status',
]

function requireValue(condition, message) {
  if (!condition) throw new Error(`Forecast V1 validation failed: ${message}`)
}

function isUtcSeconds(value) {
  if (typeof value !== 'string' || !UTC_Z_SECONDS.test(value)) return false
  const parsed = Date.parse(value)
  return Number.isFinite(parsed) && new Date(parsed).toISOString().replace('.000Z', 'Z') === value
}

function finitePair(value) {
  return Array.isArray(value) && value.length === 2 && value.every(Number.isFinite)
}

function finiteMatrix(value, rows, columns) {
  return Array.isArray(value) && value.length === rows &&
    value.every((row) => Array.isArray(row) && row.length === columns && row.every(finitePair))
}

export function validateForecastV1(forecast, { anchorTimestamp } = {}) {
  requireValue(forecast && typeof forecast === 'object' && !Array.isArray(forecast), 'payload must be an object')
  requireValue(JSON.stringify(Object.keys(forecast).sort()) === JSON.stringify([...FORECAST_KEYS].sort()), 'unexpected or missing top-level fields')
  requireValue(forecast.schema_version === '1.0.0', 'schema_version must be 1.0.0')
  requireValue(Array.isArray(forecast.forecast_timestamps) && forecast.forecast_timestamps.length === FORECAST_POINTS, 'exactly 15 timestamps are required')
  const anchor = anchorTimestamp || forecast.coordinate_origin?.origin_timestamp
  requireValue(isUtcSeconds(anchor), 'anchor must be a UTC Z timestamp at whole seconds')
  const anchorMs = Date.parse(anchor)
  forecast.forecast_timestamps.forEach((timestamp, index) => {
    requireValue(isUtcSeconds(timestamp), `timestamp ${index + 1} must be UTC Z at whole seconds`)
    requireValue(Date.parse(timestamp) === anchorMs + (index + 1) * 60_000, `timestamp ${index + 1} must equal anchor + ${index + 1} minute(s)`)
  })
  requireValue(finiteMatrix(forecast.forecast_displacement_en_nm, 2, FORECAST_POINTS), 'displacement must be finite [2,15,2]')
  requireValue(finiteMatrix(forecast.forecast_common_en_nm, 2, FORECAST_POINTS), 'common EN must be finite [2,15,2]')
  requireValue(Array.isArray(forecast.anchor_positions_en_nm) && forecast.anchor_positions_en_nm.length === 2 &&
    forecast.anchor_positions_en_nm.every(finitePair), 'anchor positions must be finite [2,2]')
  for (let vessel = 0; vessel < 2; vessel += 1) {
    for (let point = 0; point < FORECAST_POINTS; point += 1) {
      const expected = forecast.anchor_positions_en_nm[vessel].map((value, axis) => value + forecast.forecast_displacement_en_nm[vessel][point][axis])
      requireValue(expected.every((value, axis) => Math.abs(value - forecast.forecast_common_en_nm[vessel][point][axis]) <= 1e-9), 'common EN must equal anchor plus displacement')
    }
  }

  requireValue(['AVAILABLE', 'UNAVAILABLE', 'SIMULATED'].includes(forecast.geographic_availability), 'invalid geographic_availability')
  if (forecast.geographic_availability === 'UNAVAILABLE') {
    requireValue(forecast.forecast_lat_lon === null, 'unavailable geography requires null coordinates')
  } else {
    requireValue(finiteMatrix(forecast.forecast_lat_lon, 2, FORECAST_POINTS), 'coordinates must be finite [2,15,2]')
    requireValue(forecast.forecast_lat_lon.every((line) => line.every(([lat, lon]) => lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180)), 'coordinates must be valid latitude/longitude')
  }

  const origin = forecast.coordinate_origin
  requireValue(origin && typeof origin === 'object' && !Array.isArray(origin), 'coordinate_origin is required')
  requireValue(JSON.stringify(Object.keys(origin).sort()) === JSON.stringify([...ORIGIN_KEYS].sort()), 'unexpected or missing coordinate_origin fields')
  requireValue(Number.isFinite(origin.origin_latitude) && origin.origin_latitude >= -90 && origin.origin_latitude <= 90, 'origin latitude is invalid')
  requireValue(Number.isFinite(origin.origin_longitude) && origin.origin_longitude >= -180 && origin.origin_longitude <= 180, 'origin longitude is invalid')
  requireValue(isUtcSeconds(origin.origin_timestamp) && origin.origin_timestamp === anchor, 'origin timestamp must equal the forecast anchor')
  requireValue(typeof origin.origin_vessel_id === 'string' && origin.origin_vessel_id.length > 0, 'origin vessel id is required')
  requireValue(origin.coordinate_method === 'LOCAL_DEGREES_COS_LAT0' && origin.coordinate_unit === 'nautical_mile' && origin.coordinate_dtype === 'float64', 'coordinate method metadata must match Forecast V1')
  requireValue(['VERIFIED_REAL', 'VERIFIED_SIMULATED', 'UNAVAILABLE'].includes(origin.geographic_mapping_status), 'invalid geographic mapping status')
  requireValue(forecast.geographic_availability !== 'UNAVAILABLE' || origin.geographic_mapping_status === 'UNAVAILABLE', 'unavailable geography must be marked unavailable at origin')
  requireValue(forecast.geographic_availability !== 'SIMULATED' || origin.geographic_mapping_status === 'VERIFIED_SIMULATED', 'simulated geography must be marked simulated at origin')
  return true
}

function validTrackPosition(track) {
  const state = track?.current_state
  return state && Number.isFinite(state.latitude) && state.latitude >= -90 && state.latitude <= 90 &&
    Number.isFinite(state.longitude) && state.longitude >= -180 && state.longitude <= 180
}

export function buildMockForecastV1(track) {
  if (!track || track.source_type !== 'SYNTHETIC_AIS' || track.is_simulated !== true) {
    return { forecast: null, reason: 'Forecast mock chỉ bật với synthetic replay fixture.' }
  }
  if (track.data_status !== 'VALID' || !validTrackPosition(track) || !isUtcSeconds(track.anchor_timestamp)) {
    return { forecast: null, reason: 'Forecast mock cần vị trí địa lý và anchor UTC hợp lệ tại track hiện tại.' }
  }

  const originLat = track.current_state.latitude
  const originLon = track.current_state.longitude
  const cosLat = Math.cos(originLat * Math.PI / 180)
  if (Math.abs(cosLat) <= 1e-12) return { forecast: null, reason: 'Không thể ánh xạ tọa độ mock gần cực.' }

  const anchorPositions = [[0, 0], [0.05, 0]]
  const eastPerMinute = [0.002, -0.001]
  const northPerMinute = [0.001, 0.0015]
  const forecastDisplacement = [0, 1].map((vessel) => Array.from({ length: FORECAST_POINTS }, (_, index) => {
    const minute = index + 1
    return [eastPerMinute[vessel] * minute, northPerMinute[vessel] * minute]
  }))
  const forecastCommon = forecastDisplacement.map((line, vessel) => line.map(([east, north]) => [
    anchorPositions[vessel][0] + east,
    anchorPositions[vessel][1] + north,
  ]))
  const forecastLatLon = forecastCommon.map((line) => line.map(([east, north]) => [
    originLat + north / 60,
    originLon + east / (60 * cosLat),
  ]))
  const forecast = {
    schema_version: '1.0.0',
    forecast_timestamps: Array.from({ length: FORECAST_POINTS }, (_, index) =>
      new Date(Date.parse(track.anchor_timestamp) + (index + 1) * 60_000).toISOString().replace('.000Z', 'Z')),
    forecast_displacement_en_nm: forecastDisplacement,
    forecast_common_en_nm: forecastCommon,
    forecast_lat_lon: forecastLatLon,
    geographic_availability: 'SIMULATED',
    coordinate_origin: {
      origin_latitude: originLat,
      origin_longitude: originLon,
      origin_timestamp: track.anchor_timestamp,
      origin_vessel_id: track.vessel_id,
      coordinate_method: 'LOCAL_DEGREES_COS_LAT0',
      coordinate_unit: 'nautical_mile',
      coordinate_dtype: 'float64',
      geographic_mapping_status: 'VERIFIED_SIMULATED',
    },
    anchor_positions_en_nm: anchorPositions,
  }
  try {
    validateForecastV1(forecast, { anchorTimestamp: track.anchor_timestamp })
    return { forecast, reason: null }
  } catch (error) {
    return { forecast: null, reason: error instanceof Error ? error.message : 'Forecast mock không hợp lệ.' }
  }
}
