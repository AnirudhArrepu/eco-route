import { request } from './client'
export const getPreferences = signal => request('/v1/preferences', { signal })
export const createPreference = (key, value, signal) => request('/v1/preferences', { method: 'POST', body: { key, value, confidence: 1, source: 'explicit' }, signal })
export const updatePreference = (key, value, signal) => request(`/v1/preferences/${encodeURIComponent(key)}`, { method: 'PUT', body: { value, confidence: 1, source: 'explicit' }, signal })
export const deletePreference = (key, signal) => request(`/v1/preferences/${encodeURIComponent(key)}`, { method: 'DELETE', signal })
