import { request } from './client'
export const askAgent = (body, signal) => request('/v1/agent/requests', { method: 'POST', body, signal })
export const getWorkflowStatus = (execution_arn, signal) => request('/v1/workflows/status', { query: { execution_arn }, signal })
