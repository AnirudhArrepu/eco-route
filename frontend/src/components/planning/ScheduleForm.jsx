import Input from '../ui/Input'
import PlaceSearch from './PlaceSearch'

export default function ScheduleForm({ step, draft, onChange }) {
  if (step === 0) return <div className="grid gap-5">
    <Input label="Date" type="date" required value={draft.date} onChange={e => onChange({ date: e.target.value })} />
    <div className="grid grid-cols-2 gap-4"><Input label="Start time" type="time" required value={draft.startTime} onChange={e => onChange({ startTime: e.target.value })} />
      <Input label="End time" type="time" required value={draft.endTime} onChange={e => onChange({ endTime: e.target.value })} /></div>
    <p className="text-xs text-neutral-500">Times in {draft.timezone}. Choose a same-day window.</p>
    <label className="checkbox-label"><input type="checkbox" checked={draft.includeRoutines} onChange={e => onChange({ includeRoutines: e.target.checked })} />Include my saved routines</label>
  </div>
  return <div className="grid gap-6">
    <PlaceSearch label="Starting point" value={draft.startPlace} onChange={startPlace => onChange({ startPlace })} />
    <label className="checkbox-label"><input type="checkbox" checked={draft.returnToStart} onChange={e => onChange({ returnToStart: e.target.checked })} />Finish where I started</label>
    {!draft.returnToStart && <PlaceSearch label="Finish point" value={draft.endPlace} onChange={endPlace => onChange({ endPlace })} bias={draft.startPlace} />}
  </div>
}
