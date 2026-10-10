import { Clock3, MapPin, Pencil, X } from 'lucide-react'
import { minutes } from '../../utils/formatters'
import Button from '../ui/Button'

export default function StopCard({ stop, index, onEdit, onRemove }) {
  return <article className="stop-card">
    <span className="stop-number">{index + 1}</span>
    <div className="min-w-0 flex-1"><h3 className="font-medium">{stop.title}</h3><p className="mt-1 flex items-start gap-1.5 text-xs text-neutral-500"><MapPin size={13} className="mt-0.5 shrink-0" />{stop.location.label}</p>
      <p className="mt-2 flex items-center gap-1.5 text-xs text-neutral-500"><Clock3 size={13} />{minutes(stop.duration_minutes)}{stop.fixed_start ? ' · Appointment' : ''}</p>
    </div>
    <div className="flex shrink-0"><Button variant="ghost" className="icon-button" onClick={onEdit} aria-label={`Edit ${stop.title}`}><Pencil size={15} /></Button>
      {onRemove && <Button variant="ghost" className="icon-button" onClick={onRemove} aria-label={`Remove unsaved stop ${stop.title}`}><X size={17} /></Button>}
    </div>
  </article>
}
