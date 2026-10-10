import { request } from './client'
const post = (path, body, signal) => request(`/v1/auth/${path}`, { method: 'POST', body, signal, publicRequest: true })
export const signUp = (body, signal) => post('signup', body, signal)
export const confirmEmail = (body, signal) => post('confirm', body, signal)
export const resendConfirmation = (email, signal) => post('resend-confirmation', { email }, signal)
export const login = (body, signal) => post('login', body, signal)
export const refreshTokens = (refresh_token) => post('refresh', { refresh_token })
export const getAccount = (signal) => request('/v1/auth/me', { signal })
