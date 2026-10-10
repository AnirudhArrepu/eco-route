import { ChevronDown, Clock3, Pencil } from 'lucide-react'
import { formatTime } from '../../utils/dateTime'
import { minutes } from '../../utils/formatters'
import Button from '../ui/Button'

export default function TimelineStop({ stop, timing, index, timezone, previous, onEdit }) {
  const delta = previous?.start_at && timing?.start_at ? Math.round((Date.parse(timing.start_at) - Date.parse(previous.start_at)) / 60000) : null
  return <li className="timeline-stop">
    <span className="timeline-number">{index + 1}</span>
    <div className="min-w-0 flex-1">
      {timing && <p className="mb-2 text-xs text-neutral-500">{minutes(timing.travel_minutes)} travel{timing.waiting_minutes > 0 ? ` · ${minutes(timing.waiting_minutes)} waiting` : ''}</p>}
      <details><summary className="timeline-summary"><span className="min-w-0"><span className="block text-sm font-semibold">{stop.location?.label || stop.title}</span><span className="mt-1 block text-sm text-neutral-500">{stop.title}</span></span><ChevronDown size={16} className="shrink-0 text-neutral-400" /></summary>
        <div className="mt-3 grid gap-2 text-xs text-neutral-500">
          <p>Arrival {formatTime(timing?.arrival_at, timezone)} · Leave {formatTime(timing?.end_at, timezone)}</p>
          <p>Priority {stop.priority ?? 3} · {stop.mandatory ? 'Mandatory' : 'Flexible'}{stop.fixed_start ? ` · Appointment ${formatTime(stop.fixed_start, timezone)}` : ''}</p>
          {stop.earliest_start && <p>Earliest start: {formatTime(stop.earliest_start, timezone)}</p>}
          {stop.latest_start && <p>Latest start: {formatTime(stop.latest_start, timezone)}</p>}
          {stop.latest_end && <p>Finish by: {formatTime(stop.latest_end, timezone)}</p>}
          {onEdit && <Button variant="secondary" className="justify-self-start" onClick={() => onEdit(stop)}><Pencil size={14} />Edit stop details</Button>}
        </div>
      </details>
      <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
        <span className="font-medium">{formatTime(timing?.start_at, timezone)} – {formatTime(timing?.end_at, timezone)}</span><span className="flex items-center gap-1 text-neutral-500"><Clock3 size={12} />{minutes(stop.duration_minutes)}</span>
        {delta !== null && <span className="rounded bg-neutral-100 px-2 py-1">{delta === 0 ? 'Time unchanged' : `${delta > 0 ? '+' : ''}${delta} min from original`}</span>}
      </div>
    </div>
  </li>
}
