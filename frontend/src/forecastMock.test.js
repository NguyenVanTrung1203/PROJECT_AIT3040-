import { describe, expect, it } from 'vitest'
import { buildMockForecastV1, validateForecastV1 } from './forecastMock.js'

const anchor = '2024-11-01T00:09:00Z'

function syntheticTrack(overrides = {}) {
  return {
    vessel_id: 'simulated:t12-demo:kattegat-001',
    source_type: 'SYNTHETIC_AIS',
    is_simulated: true,
    data_status: 'VALID',
    anchor_timestamp: anchor,
    current_state: { latitude: 55.68, longitude: 12.56 },
    ...overrides,
  }
}

describe('Forecast V1 synthetic map fixture', () => {
  it('builds 15 future UTC points with contract-shaped arrays and explicit simulated mapping', () => {
    const result = buildMockForecastV1(syntheticTrack())
    expect(result.reason).toBeNull()
    expect(validateForecastV1(result.forecast, { anchorTimestamp: anchor })).toBe(true)
    expect(result.forecast.forecast_timestamps).toHaveLength(15)
    expect(result.forecast.forecast_timestamps[0]).toBe('2024-11-01T00:10:00Z')
    expect(result.forecast.forecast_timestamps.at(-1)).toBe('2024-11-01T00:24:00Z')
    expect(result.forecast.forecast_displacement_en_nm).toHaveLength(2)
    expect(result.forecast.forecast_displacement_en_nm[0]).toHaveLength(15)
    expect(result.forecast.geographic_availability).toBe('SIMULATED')
    expect(result.forecast.coordinate_origin.geographic_mapping_status).toBe('VERIFIED_SIMULATED')
  })

  it('refuses real AIS, invalid status, and invalid positions', () => {
    expect(buildMockForecastV1(syntheticTrack({ source_type: 'REAL_AIS', is_simulated: false })).forecast).toBeNull()
    expect(buildMockForecastV1(syntheticTrack({ data_status: 'STALE' })).forecast).toBeNull()
    expect(buildMockForecastV1(syntheticTrack({ current_state: { latitude: 95, longitude: 12 } })).forecast).toBeNull()
  })

  it('rejects timestamps that are not exactly anchor plus one to fifteen minutes', () => {
    const forecast = buildMockForecastV1(syntheticTrack()).forecast
    forecast.forecast_timestamps[0] = anchor
    expect(() => validateForecastV1(forecast, { anchorTimestamp: anchor })).toThrow(/timestamp 1/)
  })

  it('rejects non-finite coordinates and impossible geography', () => {
    const forecast = buildMockForecastV1(syntheticTrack()).forecast
    forecast.forecast_displacement_en_nm[1][14][0] = Number.NaN
    expect(() => validateForecastV1(forecast, { anchorTimestamp: anchor })).toThrow(/displacement/)

    const second = buildMockForecastV1(syntheticTrack()).forecast
    second.forecast_lat_lon[0][0][0] = 91
    expect(() => validateForecastV1(second, { anchorTimestamp: anchor })).toThrow(/latitude\/longitude/)
  })

  it('allows an explicitly unavailable geographic mapping only with null lat/lon', () => {
    const forecast = buildMockForecastV1(syntheticTrack()).forecast
    forecast.geographic_availability = 'UNAVAILABLE'
    forecast.forecast_lat_lon = null
    forecast.coordinate_origin.geographic_mapping_status = 'UNAVAILABLE'
    expect(validateForecastV1(forecast, { anchorTimestamp: anchor })).toBe(true)
  })
})
