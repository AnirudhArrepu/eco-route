import { useState } from 'react'
import { Check, ListPlus, Sparkles } from 'lucide-react'
import { extractPlanTasks } from '../../api/agent'
import { locationFromPlace, uniqueId } from '../../utils/formatters'
import PlaceSearch from './PlaceSearch'
import Button from '../ui/Button'
import ErrorMessage from '../ui/ErrorMessage'

export default function TaskExtractionPanel({ text, onTextChange, date, timezone, bias, onAdd }) {
  const [tasks, setTasks] = useState([])
  const [selected, setSelected] = useState({})
  const [added, setAdded] = useState({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [question, setQuestion] = useState('')
  const extract = async event => {
    event.preventDefault(); setBusy(true); setError(null); setQuestion(''); setTasks([]); setSelected({}); setAdded({})
    try {
      const result = await extractPlanTasks({ text, date, timezone })
      setTasks(result.tasks || []); setQuestion(result.clarification_question || '')
      if (!result.tasks?.length && !result.clarification_question) setQuestion('No errands were found. Add places you need to visit in your request.')
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
    <div><p className="eyebrow mb-1">FROM YOUR REQUEST</p><p className="text-sm text-neutral-600">We’ll identify each errand; choose its exact place before adding it to your plan.</p></div>
    <form onSubmit={extract} className="grid gap-3">
      <label className="field"><span>Your errands and any deadlines</span><textarea rows={3} maxLength={4000} value={text} onChange={e => onTextChange(e.target.value)} placeholder="I need to visit the grocery store and pharmacy before 5 pm" /></label>
      <Button type="submit" variant="secondary" busy={busy} disabled={!text.trim()}><Sparkles size={16} />Find my stops</Button>
    </form>
    <ErrorMessage error={error} />
    {question && <p role="status" className="text-sm text-neutral-600">{question}</p>}
    {tasks.map((task, index) => <article key={`${index}-${task.destination_query}`} className="grid gap-3 border-t border-neutral-200 pt-4 sm:grid-cols-[1fr_auto] sm:items-end">
      <div className="grid gap-2"><div><h3 className="font-medium">{task.title}</h3><p className="text-xs text-neutral-500">Search: {task.destination_query}{task.duration_minutes ? ` · ${task.duration_minutes} min` : ' · 30 min suggested'}{task.latest_end ? ` · finish by ${new Date(task.latest_end).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}` : ''}{task.fixed_start ? ` · appointment ${new Date(task.fixed_start).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}` : ''}</p></div>
        <PlaceSearch label={`Exact place for ${task.title}`} value={selected[index]} onChange={place => setSelected(value => ({ ...value, [index]: place }))} bias={bias} initialQuery={task.destination_query} placeholder={task.destination_query} />
      </div>
      <Button type="button" variant="secondary" disabled={!selected[index] || added[index]} onClick={() => addTask(task, index)}>{added[index] ? <><Check size={16} />Added</> : <><ListPlus size={16} />Add stop</>}</Button>
    </article>)}
  </section>
}
