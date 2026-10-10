// Storage is optional (private browsing and browser policy can disable it).
export function readSession(key) {
  try { return sessionStorage.getItem(key) } catch { return null }
}
export function writeSession(key, value) {
  try { if (value === null) sessionStorage.removeItem(key); else sessionStorage.setItem(key, value) } catch { /* Keep working in memory. */ }
}
