import { Check, CircleAlert } from 'lucide-react'
import ScheduleMetrics from '../itinerary/ScheduleMetrics'
import Timeline from '../itinerary/Timeline'

export function PlanConflicts({ conflicts = [] }) {
  if (!conflicts.length) return null
  return <div className="notice"><p className="mb-2 font-medium">A few things need adjusting</p><ul className="list-disc space-y-1 pl-4 text-sm">{conflicts.map((conflict, i) => <li key={i}>{typeof conflict === 'string' ? conflict : conflict.reason || conflict.constraint_type}</li>)}</ul></div>
}
export default function SchedulePreview({ preview, body }) {
  return <div className="grid gap-6">
    <div className="flex items-start gap-3">{preview.feasible ? <Check size={21} /> : <CircleAlert size={21} />}<div><h2 className="font-semibold">{preview.feasible ? 'Your day fits together.' : 'Let’s make a little more room.'}</h2><p className="mt-1 text-sm text-neutral-500">{preview.feasible ? 'Review the order and timing before saving.' : 'Adjust your stops or available time, then preview again.'}</p></div></div>
    <ScheduleMetrics metrics={preview.metrics} />
    <PlanConflicts conflicts={preview.conflicts} />
    <Timeline stops={preview.stops} timeline={preview.timeline} metrics={preview.metrics} timezone={body.timezone} schedule={body} />
    <div className="notice text-xs text-neutral-500"><p>{preview.travel_estimate_source === 'local_mock' ? 'Local development travel estimates. These are not live route results.' : 'Travel times are estimates and may change.'}</p>
      {preview.search_truncated && <p className="mt-2">The itinerary search is bounded, so another stop order may be shorter.</p>}
      {preview.explanation_facts?.length > 0 && <ul className="mt-2 list-disc space-y-1 pl-4">{preview.explanation_facts.map((fact, i) => <li key={i}>{fact}</li>)}</ul>}
    </div>
  </div>
}
