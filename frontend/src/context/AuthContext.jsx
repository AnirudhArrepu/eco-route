import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { configureAuth, ApiError } from '../api/client'
import * as api from '../api/auth'

const AuthContext = createContext(null)
export function AuthProvider({ children }) {
  // Tokens stay in memory, never in browser storage or logs.
  const sessionRef = useRef(null)
  const refreshRef = useRef(null)
  const [account, setAccount] = useState(null)
  const clear = useCallback(() => { sessionRef.current = null; setAccount(null) }, [])
  const refresh = useCallback(async () => {
    if (!refreshRef.current) {
      const current = sessionRef.current
      if (!current?.refresh_token) throw new ApiError('Your session expired. Please sign in again.', 401)
      refreshRef.current = api.refreshTokens(current.refresh_token).then(tokens => {
        if (sessionRef.current !== current) throw new ApiError('Your session changed. Sign in again.', 401)
        if (!tokens.id_token) throw new ApiError('Token refresh failed. Please sign in again.', 401)
        sessionRef.current = { ...tokens, refresh_token: tokens.refresh_token || current.refresh_token }
        return tokens.id_token
      }).finally(() => { refreshRef.current = null })
    }
    return refreshRef.current
  }, [])
  useEffect(() => {
    configureAuth({ getToken: () => sessionRef.current?.id_token, refresh, clear })
    return () => configureAuth({ getToken: () => null, refresh: async () => null, clear: () => {} })
  }, [refresh, clear])
  const signIn = async (credentials, signal) => {
    const tokens = await api.login(credentials, signal)
    if (!tokens?.id_token) throw new ApiError('Sign-in did not return an ID token.')
    sessionRef.current = tokens
    try {
      const user = await api.getAccount(signal)
      setAccount({ ...user, email: credentials.email })
    } catch (error) { clear(); throw error }
  }
  return <AuthContext.Provider value={{ account, signIn, signOut: clear }}>{children}</AuthContext.Provider>
}
export const useAuth = () => useContext(AuthContext)
