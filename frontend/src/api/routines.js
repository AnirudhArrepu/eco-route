import { request } from './client'
export const getRoutines = signal => request('/v1/routines', { signal })
export const createRoutine = (routine, signal) => request('/v1/routines', { method: 'POST', body: { routine }, signal })
export const updateRoutine = (id, routine, signal) => request(`/v1/routines/${encodeURIComponent(id)}`, { method: 'PUT', body: { routine }, signal })
export const deleteRoutine = (id, signal) => request(`/v1/routines/${encodeURIComponent(id)}`, { method: 'DELETE', signal })
