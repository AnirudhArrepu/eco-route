import { Clock3, Footprints, MapPin, Sprout } from 'lucide-react'
import { distance, minutes } from '../../utils/formatters'

export default function ScheduleMetrics({ metrics }) {
  if (!metrics) return <p className="text-sm text-neutral-500">Metrics are unavailable for this plan.</p>
  const savings = metrics.distance_savings
  const transitScenario = savings?.public_transport_scenario
  const co2Value = savings?.estimated_co2_saved_kg
  const co2Added = savings?.estimated_co2_added_kg
  const co2ImpactLabel = co2Added > 0 ? 'Estimated CO₂ added' : 'Estimated CO₂ saved'
  const co2ImpactValue = co2Added > 0 ? `${co2Added.toFixed(2)} kg` : co2Value !== null && co2Value !== undefined ? `${co2Value.toFixed(2)} kg` : null
  return <>
    <dl className="metrics-grid">
    {[[Clock3, 'Est. travel', minutes(metrics.travel_minutes)], [Footprints, 'Combined route', distance(metrics.distance_km)], [MapPin, 'Stops', metrics.stop_count ?? '—'], ...(savings ? [[Sprout, 'Estimated km saved', distance(savings.saved_km)], [Sprout, co2ImpactLabel, co2ImpactValue], [Sprout, 'Separate trips combined', `${savings.separate_trips} to ${savings.combined_trips}`]] : [])].filter(([, , value]) => value !== null).map(([Icon, label, value]) =>
      <div key={label}><dt className="flex items-center gap-1.5 text-xs text-neutral-500"><Icon size={13} />{label}</dt><dd className="mt-2 text-lg font-medium">{value}</dd></div>)}
    {savings && <div className="col-span-full text-xs leading-5 text-neutral-500"><dt>Compared with one separate start-to-finish trip per stop. CO₂ is a scenario estimate: {savings.co2_factor_source}.{savings.co2_factor_source_url ? <> <a className="underline" href={savings.co2_factor_source_url} target="_blank" rel="noreferrer">Emission factor source</a>.</> : ''} Actual emissions vary by vehicle and fuel; this estimate covers direct tailpipe CO₂ only.{savings.additional_km > 0 ? ` This route is estimated to add ${distance(savings.additional_km)} against that baseline.` : ''}</dt></div>}
    </dl>
    {transitScenario && <aside className="notice col-span-full text-sm" aria-label="Public transport emissions estimate">
      <p className="font-medium">If you use public transport, estimated CO₂e savings: {transitScenario.estimated_co2e_saved_kg.toFixed(2)} kg</p>
      <p className="mt-1 text-xs leading-5 text-neutral-500">For the same {distance(transitScenario.distance_km)} distance: solo car {transitScenario.estimated_car_co2_kg.toFixed(2)} kg CO₂ vs public transport {transitScenario.estimated_public_transport_co2e_kg.toFixed(2)} kg CO₂e.</p>
      <p className="mt-2 text-xs leading-5 text-neutral-500">Estimate only — {transitScenario.public_transport_factor_source}. {transitScenario.warning} EcoRoute does not provide public-transport directions or timetables.</p>
      <p className="mt-1 text-xs leading-5 text-neutral-500">Car factor: {transitScenario.car_factor_source}. <a className="underline" href={transitScenario.car_factor_source_url} target="_blank" rel="noreferrer">Source</a>.</p>
    </aside>}
  </>
}
