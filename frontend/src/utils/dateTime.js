export const localTimezone = () => Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
const pad = value => String(value).padStart(2, '0')
export function localDate(date = new Date()) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

// Resolve a wall-clock value in an IANA zone without adding a date library.
// A round trip rejects nonexistent DST times rather than silently moving them.
function wallParts(date, timezone) {
  const parts = new Intl.DateTimeFormat('en-GB', { timeZone: timezone, year: 'numeric', month: '2-digit',
    day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(date)
  const p = Object.fromEntries(parts.map(part => [part.type, part.value]))
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`
}
export function zonedTimestamp(date, time, timezone) {
  if (!date || !time) throw new Error('Choose a date and time.')
  const wall = `${date}T${time.slice(0, 5)}`
  const target = Date.parse(`${wall}:00Z`)
  if (!Number.isFinite(target)) throw new Error('Choose a valid date and time.')
  let instant = target
  for (let i = 0; i < 4; i += 1) {
    const represented = Date.parse(`${wallParts(new Date(instant), timezone)}:00Z`)
    const correction = target - represented
    if (!correction) break
    instant += correction
  }
  if (wallParts(new Date(instant), timezone) !== wall) throw new Error('This time does not exist in the selected timezone. Choose another time.')
  return new Date(instant).toISOString()
}
export function toWallInput(value, timezone) {
  if (!value) return ''
  return wallParts(new Date(value), timezone)
}
export function fromWallInput(value, timezone) {
  if (!value) return null
  const [date, time] = value.split('T')
  return zonedTimestamp(date, time, timezone)
}
export function formatTime(value, timezone) {
  if (!value) return '—'
  const date = new Date(value)
  if (!Number.isFinite(date.getTime())) return '—'
  return new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit', timeZone: timezone }).format(date)
}
export function formatDate(value) {
  if (!value) return 'Your day'
  return new Intl.DateTimeFormat(undefined, { weekday: 'long', month: 'short', day: 'numeric' }).format(new Date(`${value}T12:00:00`))
}
