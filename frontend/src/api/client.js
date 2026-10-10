const baseUrl = (import.meta.env.VITE_API_BASE_URL || '').trim().replace(/\/+$/, '')
export const isApiConfigured = Boolean(baseUrl)

let auth = { getToken: () => null, refresh: async () => null, clear: () => {} }
export function configureAuth(handlers) { auth = handlers }

export class ApiError extends Error {
  constructor(message, status = 0, detail = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

function describe(detail, status) {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map(item => item.msg || item.reason || 'Invalid input').join('; ')
  if (detail?.message) return detail.message
  return ({ 401: 'Please sign in again.', 403: 'You do not have access to this resource.',
    404: 'This resource was not found for your account.', 409: 'This plan changed. Refresh and request a new proposal.',
    410: 'This proposal expired. Request a new proposal.', 422: 'Please check your inputs and planning constraints.',
    429: 'Too many requests. Please wait a moment.', 502: 'The backend service could not complete this request.',
    503: 'This service is temporarily unavailable.' })[status] || `Request failed (${status}).`
}

export async function request(path, { method = 'GET', body, query, signal, publicRequest = false } = {}) {
  if (!baseUrl) throw new ApiError('Add VITE_API_BASE_URL to your local environment to connect EcoRoute.')
  let url
  try {
    url = new URL(`${baseUrl}${path}`)
    if (!['http:', 'https:'].includes(url.protocol)) throw new Error('Invalid protocol')
  } catch { throw new ApiError('Set VITE_API_BASE_URL to a valid absolute HTTP or HTTPS API URL.') }
  Object.entries(query || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null) url.searchParams.set(key, String(value))
  })
  const controller = new AbortController()
  let timedOut = false
  const abort = () => controller.abort()
  if (signal?.aborted) abort()
  signal?.addEventListener('abort', abort, { once: true })
  const timeout = setTimeout(() => { timedOut = true; abort() }, 30000)
  try {
    for (let attempt = 0; attempt < 2; attempt += 1) {
      const token = publicRequest ? null : auth.getToken()
      if (!publicRequest && !token) throw new ApiError('Sign in to continue.', 401)
      const response = await fetch(url, {
        method, signal: controller.signal, credentials: 'omit',
        headers: { Accept: 'application/json', ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
          ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
      })
      if (response.status === 401 && !publicRequest && attempt === 0) {
        try { await auth.refresh() } catch (error) { if (auth.getToken() === token) auth.clear(); throw error }
        continue
      }
      const raw = response.status === 204 ? '' : await response.text()
      let data = null
      if (raw) {
        try { data = JSON.parse(raw) } catch {
          throw new ApiError(response.ok ? 'The server returned an invalid JSON response.' : describe(null, response.status), response.status)
        }
      }
      if (!response.ok) {
        if (response.status === 401 && !publicRequest && auth.getToken() === token) auth.clear()
        throw new ApiError(describe(data?.detail, response.status), response.status, data?.detail)
      }
      return data
    }
  } catch (error) {
    if (timedOut) throw new ApiError('The request timed out. Please try again.')
    if (error.name === 'AbortError' || error instanceof ApiError) throw error
    throw new ApiError('Could not connect. Check your connection and backend configuration.')
  } finally {
    clearTimeout(timeout)
    signal?.removeEventListener('abort', abort)
  }
}
