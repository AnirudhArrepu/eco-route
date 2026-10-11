import { useState } from 'react'
import { Check, ListPlus, Sparkles } from 'lucide-react'
import { extractPlanTasks } from '../../api/agent'
import { searchPlacesOnRoute } from '../../api/places'
import { locationFromPlace, uniqueId } from '../../utils/formatters'
import PlaceSearch from './PlaceSearch'
import Button from '../ui/Button'
import ErrorMessage from '../ui/ErrorMessage'

export default function TaskExtractionPanel({ text, onTextChange, date, timezone, startPlace, endPlace, onAdd }) {
  const [tasks, setTasks] = useState([])
  const [selected, setSelected] = useState({})
  const [routeOptions, setRouteOptions] = useState({})
  const [added, setAdded] = useState({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [question, setQuestion] = useState('')
  const [extraction, setExtraction] = useState(null)
  const extract = async event => {
    event.preventDefault(); setBusy(true); setError(null); setQuestion(''); setTasks([]); setSelected({}); setRouteOptions({}); setAdded({}); setExtraction(null)
    try {
      const result = await extractPlanTasks({ text, date, timezone })
      const extracted = result.tasks || []
      setTasks(extracted); setQuestion(result.clarification_question || '')
      setExtraction({ source: result.extraction_source, reason: result.fallback_reason })
      if (startPlace && endPlace && extracted.length) {
        const start = locationFromPlace(startPlace)
        const end = locationFromPlace(endPlace)
        const ranked = await Promise.all(extracted.map(async task => {
          try {
            const response = await searchPlacesOnRoute({ query: task.destination_query, start_location: start, end_location: end })
            return response.places || []
          } catch { return [] }
        }))
        const options = Object.fromEntries(ranked.map((places, index) => [index, places]))
        setRouteOptions(options)
        setSelected(Object.fromEntries(ranked.flatMap((places, index) => places.length ? [[index, places[0]]] : [])))
      }
      if (!extracted.length && !result.clarification_question) setQuestion('No errands were found. Add places you need to visit in your request.')
    } catch (err) { setError(err) } finally { setBusy(false) }
  }
  const addTask = (task, index) => {
    const place = selected[index]
    if (!place) return
    onAdd({ id: uniqueId(), title: task.title, type: task.fixed_start ? 'appointment' : 'errand',
      location: locationFromPlace(place), duration_minutes: task.duration_minutes || 30,
      priority: 3, mandatory: true, latest_end: task.latest_end || null, fixed_start: task.fixed_start || null,
      earliest_start: null, latest_start: null, source: 'user' })
    setAdded(value => ({ ...value, [index]: true }))
  }
  return <section className="notice grid gap-4" aria-label="Extract stops from request">
    <div><p className="eyebrow mb-1">FROM YOUR REQUEST</p><p className="text-sm text-neutral-600">We’ll find each errand and preselect the real place that adds the least routed distance. You can change any suggestion.</p></div>
    <form onSubmit={extract} className="grid gap-3">
      <label className="field"><span>Your errands and any deadlines</span><textarea rows={3} maxLength={4000} value={text} onChange={e => onTextChange(e.target.value)} placeholder="I need to visit the grocery store and pharmacy before 5 pm" /></label>
      <Button type="submit" variant="secondary" busy={busy} disabled={!text.trim()}><Sparkles size={16} />Find my stops</Button>
    </form>
    <ErrorMessage error={error} />
    {extraction && <p role="status" className="text-xs leading-5 text-neutral-500">{extraction.source === 'mantle'
      ? 'Tasks parsed by Bedrock Mantle. Review the suggested stops and timing.'
      : extraction.reason === 'mantle_response_invalid'
        ? 'Mantle returned an unreadable response, so a simple local parser was used. Review the tasks and timing before adding them.'
        : extraction.reason === 'mantle_request_failed'
          ? 'Bedrock Mantle did not respond, so a simple local parser was used. Review the tasks and timing before adding them.'
          : 'Bedrock Mantle is not configured for this environment, so a simple local parser was used.'}</p>}
    {question && <p role="status" className="text-sm text-neutral-600">{question}</p>}
    {tasks.map((task, index) => <article key={`${index}-${task.destination_query}`} className="grid gap-3 border-t border-neutral-200 pt-4 sm:grid-cols-[1fr_auto] sm:items-end">
      <div className="grid gap-2"><div><h3 className="font-medium">{task.title}</h3><p className="text-xs text-neutral-500">Search: {task.destination_query}{task.duration_minutes ? ` · ${task.duration_minutes} min` : ' · 30 min suggested'}{task.latest_end ? ` · finish by ${new Date(task.latest_end).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', timeZone: timezone })}` : ''}{task.fixed_start ? ` · appointment ${new Date(task.fixed_start).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', timeZone: timezone })}` : ''}</p></div>
        {routeOptions[index]?.length > 0 && <label className="field"><span>Best route fit{selected[index]?.detour_km !== undefined ? ` · +${selected[index].detour_km.toFixed(1)} km detour` : ''}</span><select value={selected[index]?.id || selected[index]?.label || ''} onChange={event => setSelected(value => ({ ...value, [index]: routeOptions[index].find(place => (place.id || place.label) === event.target.value) }))}>{routeOptions[index].map(place => <option key={place.id || place.label} value={place.id || place.label}>{place.route_rank === 1 ? 'Least detour · ' : ''}{place.title || place.label} · +{place.detour_km.toFixed(1)} km</option>)}</select></label>}
        <PlaceSearch label={`Exact place for ${task.title}`} value={selected[index]} onChange={place => setSelected(value => ({ ...value, [index]: place }))} bias={startPlace} initialQuery={task.destination_query} placeholder={task.destination_query} />
      </div>
      <Button type="button" variant="secondary" disabled={!selected[index] || added[index]} onClick={() => addTask(task, index)}>{added[index] ? <><Check size={16} />Added</> : <><ListPlus size={16} />Add stop</>}</Button>
    </article>)}
  </section>
}
