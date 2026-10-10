import { Clock3, Footprints, MapPin, Sprout } from 'lucide-react'
import { distance, minutes } from '../../utils/formatters'

export default function ScheduleMetrics({ metrics }) {
  if (!metrics) return <p className="text-sm text-neutral-500">Metrics are unavailable for this plan.</p>
  const savings = metrics.distance_savings
  return <dl className="metrics-grid">
    {[[Clock3, 'Est. travel', minutes(metrics.travel_minutes)], [Footprints, 'Combined route', distance(metrics.distance_km)], [MapPin, 'Stops', metrics.stop_count ?? '—'], ...(savings ? [[Sprout, 'Estimated km saved', distance(savings.saved_km)], [Sprout, 'Separate trips combined', `${savings.separate_trips} to ${savings.combined_trips}`]] : [])].map(([Icon, label, value]) =>
      <div key={label}><dt className="flex items-center gap-1.5 text-xs text-neutral-500"><Icon size={13} />{label}</dt><dd className="mt-2 text-lg font-medium">{value}</dd></div>)}
    {savings && <div className="col-span-full text-xs leading-5 text-neutral-500"><dt>Compared with one separate start-to-finish trip per stop. This is a route-distance estimate; fuel and emissions depend on vehicle and fuel type.{savings.additional_km > 0 ? ` This route is estimated to add ${distance(savings.additional_km)} against that baseline.` : ''}</dt></div>}
  </dl>
}
