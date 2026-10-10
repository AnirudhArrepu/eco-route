export function minutes(value) {
  if (value === undefined || value === null || !Number.isFinite(Number(value))) return '—'
  const n = Math.round(Number(value))
  return n >= 60 ? `${Math.floor(n / 60)}h${n % 60 ? ` ${n % 60}m` : ''}` : `${n} min`
}
export const distance = value => value === undefined || value === null ? '—' : `${Number(value).toFixed(1)} km`
export function locationFromPlace(place) {
  return { ...(place.id ? { id: place.id } : {}), latitude: place.latitude, longitude: place.longitude, label: place.label || place.title }
}
export function uniqueId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID()
  if (!globalThis.crypto?.getRandomValues) throw new Error('A secure browser context is required to create an identifier.')
  return Array.from(globalThis.crypto.getRandomValues(new Uint8Array(16)), byte => byte.toString(16).padStart(2, '0')).join('')
}
