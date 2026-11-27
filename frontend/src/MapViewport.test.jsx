import { cleanup, render } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { FitTracks } from './App.jsx'

const { map } = vi.hoisted(() => ({ map: { setView: vi.fn(), fitBounds: vi.fn() } }))
vi.mock('react-leaflet', () => ({
  useMap: () => map, MapContainer: () => null, TileLayer: () => null,
  Marker: () => null, Polyline: () => null, CircleMarker: () => null, Tooltip: () => null,
}))
vi.mock('leaflet', () => ({ default: { divIcon: vi.fn() } }))

const track = (latitude, longitude) => ({ data_status: 'VALID', current_state: { latitude, longitude } })
beforeEach(() => vi.clearAllMocks())
afterEach(cleanup)

it('fits once after data arrives and preserves the user viewport across track updates', () => {
  const view = render(<FitTracks mode="s5" tracks={[]} />)
  expect(map.fitBounds).not.toHaveBeenCalled()
  view.rerender(<FitTracks mode="s5" tracks={[track(55.7, 12.5), track(55.8, 12.6)]} />)
  expect(map.fitBounds).toHaveBeenCalledTimes(1)
  // These rerenders represent polling, control, pair/forecast and alert updates.
  for (let i = 0; i < 4; i++) view.rerender(<FitTracks mode="s5" tracks={[track(55.7 + i / 100, 12.5)]} />)
  expect(map.fitBounds).toHaveBeenCalledTimes(1)
  expect(map.setView).not.toHaveBeenCalled()
})

it('fits again only when the mode changes and data for it arrives', () => {
  const view = render(<FitTracks mode="s5" tracks={[track(55.7, 12.5)]} />)
  expect(map.setView).toHaveBeenCalledTimes(1)
  view.rerender(<FitTracks mode="replay" tracks={[]} />)
  expect(map.fitBounds).not.toHaveBeenCalled()
  view.rerender(<FitTracks mode="replay" tracks={[track(55.6, 12.4), track(55.8, 12.6)]} />)
  expect(map.fitBounds).toHaveBeenCalledTimes(1)
  view.rerender(<FitTracks mode="replay" tracks={[track(55.9, 12.7)]} />)
  expect(map.setView).toHaveBeenCalledTimes(1)
})
