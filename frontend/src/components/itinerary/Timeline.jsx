import { formatTime } from '../../utils/dateTime'
import { minutes } from '../../utils/formatters'
import TimelineStop from './TimelineStop'

export default function Timeline({ stops = [], allStops = stops, timeline = [], timezone, schedule, metrics, previousTimeline = [], onEdit }) {
  return <div>
    {schedule && <div className="timeline-endpoint"><span className="endpoint-dot" /><div><p className="text-xs text-neutral-500">Start · {formatTime(schedule.start_at, timezone)}</p><p className="mt-1 text-sm font-medium">{schedule.start_location?.label || 'Starting point'}</p></div></div>}
    {stops.length ? <ol className="timeline-list">{stops.map((stop, index) => <TimelineStop key={stop.id || index} stop={stop} index={allStops.findIndex(item => item.id === stop.id)}
      timing={timeline.find(item => item.stop_id === stop.id)} previous={previousTimeline.find(item => item.stop_id === stop.id)} timezone={timezone} onEdit={onEdit} />)}</ol>
      : <p className="py-6 text-sm text-neutral-500">No stops in this plan yet.</p>}
    {schedule && <div className="timeline-endpoint"><span className="endpoint-dot endpoint-dot-end" /><div><p className="text-xs text-neutral-500">Finish · {formatTime(metrics?.return_arrival_at, timezone)}{metrics?.return_travel_minutes !== undefined ? ` · ${minutes(metrics.return_travel_minutes)} travel` : ''}</p><p className="mt-1 text-sm font-medium">{schedule.end_location?.label || 'Finish point'}</p></div></div>}
  </div>
}
