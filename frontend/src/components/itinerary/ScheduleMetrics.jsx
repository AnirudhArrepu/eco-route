import { Clock3, Footprints, MapPin } from 'lucide-react'
import { distance, minutes } from '../../utils/formatters'

export default function ScheduleMetrics({ metrics }) {
  if (!metrics) return <p className="text-sm text-neutral-500">Metrics are unavailable for this plan.</p>
  return <dl className="metrics-grid">
    {[[Clock3, 'Est. travel', minutes(metrics.travel_minutes)], [Footprints, 'Distance', distance(metrics.distance_km)], [MapPin, 'Stops', metrics.stop_count ?? '—']].map(([Icon, label, value]) =>
      <div key={label}><dt className="flex items-center gap-1.5 text-xs text-neutral-500"><Icon size={13} />{label}</dt><dd className="mt-2 text-lg font-medium">{value}</dd></div>)}
  </dl>
}
