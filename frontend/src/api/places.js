import { request } from './client'
export const searchPlaces = (query, bias, signal) => request('/v1/places/search', {
  query: { query, ...(Number.isFinite(bias?.latitude) && Number.isFinite(bias?.longitude)
    ? { latitude: bias.latitude, longitude: bias.longitude } : {}) }, signal,
})
export const searchPlacesOnRoute = (body, signal) => request('/v1/places/route-search', { method: 'POST', body, signal })
