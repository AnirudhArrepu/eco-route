import { useState } from 'react'
import { fromWallInput, toWallInput } from '../../utils/dateTime'
import { locationFromPlace, uniqueId } from '../../utils/formatters'
import PlaceSearch from './PlaceSearch'
import Input from '../ui/Input'
import Button from '../ui/Button'
import ErrorMessage from '../ui/ErrorMessage'

const timeFields = [['earliest_start', 'Earliest start'], ['latest_start', 'Latest start'], ['latest_end', 'Finish by (deadline)'], ['fixed_start', 'Fixed appointment']]
export default function StopForm({ initial, timezone, date, bias, onSubmit, onCancel, editing = false, busy = false, submitLabel }) {
  const [place, setPlace] = useState(initial?.location ? { ...initial.location, title: initial.location.label } : null)
  const [title, setTitle] = useState(initial?.title || '')
  const [duration, setDuration] = useState(initial?.duration_minutes || 30)
  const [priority, setPriority] = useState(initial?.priority ?? 3)
  const [mandatory, setMandatory] = useState(initial?.mandatory ?? true)
  const [times, setTimes] = useState(() => Object.fromEntries(timeFields.map(([key]) => [key, toWallInput(initial?.[key], timezone)])))
  const [error, setError] = useState(null)
  const submit = event => {
    event.preventDefault(); setError(null)
    try {
      if (!place || !title.trim()) throw new Error('Choose a place and enter a task title.')
      if (!Number.isInteger(Number(duration)) || Number(duration) < 1 || Number(duration) > 1440) throw new Error('Duration must be a whole number between 1 and 1440 minutes.')
      const timestamps = Object.fromEntries(timeFields.map(([key]) => [key,
        initial?.[key] && times[key] === toWallInput(initial[key], timezone)
          ? initial[key] : fromWallInput(times[key], timezone)]))
      if (timestamps.earliest_start && timestamps.latest_start && Date.parse(timestamps.earliest_start) > Date.parse(timestamps.latest_start)) throw new Error('Earliest start must be before latest start.')
      if (timestamps.fixed_start && timestamps.latest_end && Date.parse(timestamps.fixed_start) + Number(duration) * 60000 > Date.parse(timestamps.latest_end)) throw new Error('The appointment duration extends beyond the deadline.')
      onSubmit({ ...(initial?.id ? { id: initial.id } : { id: uniqueId() }), title: title.trim(),
        type: editing ? initial.type : timestamps.fixed_start ? 'appointment' : 'errand', location: locationFromPlace(place),
        duration_minutes: Number(duration), priority: Number(priority), mandatory, ...timestamps, source: initial?.source || 'user' })
    } catch (err) { setError(err) }
  }
  return <form onSubmit={submit} className="grid gap-5">
    <fieldset disabled={busy} className="grid min-w-0 gap-5">
      {editing ? <div className="notice"><p className="font-medium">{title}</p><p className="mt-1 text-xs text-neutral-500">{place?.label}</p></div>
        : <><PlaceSearch label="Destination" value={place} onChange={setPlace} bias={bias} />
          <Input label="What do you need to do?" placeholder="Pick up groceries, meet a friend…" required maxLength={256} value={title} onChange={e => setTitle(e.target.value)} /></>}
      <Input label="How long will you need?" type="number" min="1" max="1440" step="1" required value={duration} onChange={e => setDuration(e.target.value)} hint="Duration in minutes, excluding travel." />
      <details className="advanced-fields" open={editing || undefined}><summary>Time windows & priorities <span className="text-neutral-400">Optional</span></summary>
        <div className="mt-5 grid gap-4 sm:grid-cols-2">
          {timeFields.map(([key, label]) => <Input key={key} label={label} type="datetime-local" value={times[key]} step="60"
            onChange={e => setTimes(previous => ({ ...previous, [key]: e.target.value }))} hint={key === 'fixed_start' ? `Local time in ${timezone}. Plan date: ${date}.` : undefined} />)}
          <label className="field"><span>Priority</span><select value={priority} onChange={e => setPriority(e.target.value)}>{[1, 2, 3, 4, 5].map(n => <option value={n} key={n}>{n}{n === 1 ? ' · Low' : n === 5 ? ' · High' : ''}</option>)}</select></label>
          <label className="checkbox-label sm:self-end"><input type="checkbox" checked={mandatory} onChange={e => setMandatory(e.target.checked)} />Mandatory stop</label>
        </div>
      </details>
    </fieldset>
    <ErrorMessage error={error} />
    <div className="flex flex-wrap gap-3"><Button type="submit" busy={busy}>{submitLabel || (editing ? 'Preview changes' : 'Add to my stops')}</Button>{onCancel && <Button variant="secondary" disabled={busy} onClick={onCancel}>Cancel</Button>}</div>
  </form>
}
