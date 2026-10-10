import { request } from './client'
const path = id => `/v1/proposals/${encodeURIComponent(id)}`
export const getProposal = (id, signal) => request(path(id), { signal })
export const approveProposal = (id, idempotency_key, signal) => request(`${path(id)}/approve`, { method: 'POST', body: { idempotency_key }, signal })
export const rejectProposal = (id, signal) => request(`${path(id)}/reject`, { method: 'POST', body: { reason: 'User chose to keep the original plan' }, signal })
