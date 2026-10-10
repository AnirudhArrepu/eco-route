import { useState } from 'react'
import { createRoutine, updateRoutine } from '../../api/routines'
import { locationFromPlace } from '../../utils/formatters'
import PlaceSearch from '../planning/PlaceSearch'
import Button from '../ui/Button'
import Input from '../ui/Input'
import ErrorMessage from '../ui/ErrorMessage'

export const weekdays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
export default function RoutineForm({ initial, onSaved, onCancel, signalRef }) {
  const [name, setName] = useState(initial?.name || '')
  const [weekday, setWeekday] = useState(initial?.weekday ?? 0)
  const [title, setTitle] = useState(initial?.stop?.title || '')
  const [place, setPlace] = useState(initial?.stop?.location ? { ...initial.stop.location, title: initial.stop.location.label } : null)
  const [duration, setDuration] = useState(initial?.stop?.duration_minutes || 30)
  const [active, setActive] = useState(initial?.active ?? true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const save = async event => {
    event.preventDefault(); setError(null); setBusy(true); signalRef.current = new AbortController()
    try {
      if (!name.trim() || !title.trim() || !place) throw new Error('Enter a routine name, task, and selected place.')
      if (!Number.isInteger(Number(duration)) || Number(duration) < 1 || Number(duration) > 1440) throw new Error('Duration must be between 1 and 1440 whole minutes.')
      const routine = { name: name.trim(), weekday: Number(weekday), active, stop: {
        ...initial?.stop, title: title.trim(), type: 'routine', location: locationFromPlace(place), duration_minutes: Number(duration), mandatory: initial?.stop?.mandatory ?? false,
      } }
      const result = initial ? await updateRoutine(initial.id, routine, signalRef.current.signal) : await createRoutine(routine, signalRef.current.signal)
      onSaved(result)
    } catch (err) { if (err.name !== 'AbortError') setError(err) }
    finally { setBusy(false) }
  }
  return <form onSubmit={save} className="grid gap-4"><fieldset disabled={busy} className="grid min-w-0 gap-4">
    <Input label="Routine name" required maxLength={128} value={name} onChange={e => setName(e.target.value)} placeholder="A little Monday ritual" />
    <label className="field"><span>Day of the week</span><select value={weekday} onChange={e => setWeekday(e.target.value)}>{weekdays.map((day, i) => <option key={day} value={i}>{day}</option>)}</select></label>
    <PlaceSearch label="Place" value={place} onChange={setPlace} />
    <Input label="Task" required maxLength={256} value={title} onChange={e => setTitle(e.target.value)} />
    <Input label="Duration (minutes)" type="number" min="1" max="1440" step="1" required value={duration} onChange={e => setDuration(e.target.value)} />
    <label className="checkbox-label"><input type="checkbox" checked={active} onChange={e => setActive(e.target.checked)} />Include this routine on matching weekdays</label>
  </fieldset><p className="text-xs leading-5 text-neutral-500">New routines have flexible timing and are included when you opt in during planning. Editing routines does not change an existing schedule.</p>
    {initial?.stop && ['earliest_start', 'latest_start', 'latest_end', 'fixed_start'].some(key => initial.stop[key]) && <p className="notice text-xs">This routine has dated time constraints from the backend. Those dates are preserved; the backend does not automatically move them to future weeks.</p>}
    <ErrorMessage error={error} /><div className="flex flex-wrap gap-3"><Button type="submit" busy={busy}>Save routine</Button><Button variant="secondary" disabled={busy} onClick={onCancel}>Cancel</Button></div>
  </form>
}
