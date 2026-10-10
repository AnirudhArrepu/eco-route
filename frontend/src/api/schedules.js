import { request } from './client'
const path = id => `/v1/schedules/${encodeURIComponent(id)}`
export const previewSchedule = (body, signal) => request('/v1/schedules/preview', { method: 'POST', body, signal })
export const createSchedule = (body, signal) => request('/v1/schedules', { method: 'POST', body, signal })
export const getSchedule = (id, signal) => request(path(id), { signal })
export const getTimeline = (id, signal) => request(`${path(id)}/timeline`, { signal })
export const getRevisions = (id, signal) => request(`${path(id)}/revisions`, { signal })
export const addStop = (id, destination, signal) => request(`${path(id)}/stops`, { method: 'POST',
  body: { destination, allow_reordering_flexible_stops: true, max_reordered_stops: 3 }, signal })
export const replanSchedule = (id, updates, signal) => request(`${path(id)}/replan`, { method: 'POST',
  body: { updates, reason: 'User edited stop details', allow_reordering_flexible_stops: true, max_reordered_stops: 3 }, signal })
