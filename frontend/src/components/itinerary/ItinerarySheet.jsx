import { useEffect, useId, useState } from 'react'
import { ChevronDown, ChevronUp, Maximize2, Minimize2 } from 'lucide-react'
import Button from '../ui/Button'

export default function ItinerarySheet({ stops, summary, children }) {
  const [level, setLevel] = useState(() => window.matchMedia('(min-width: 64rem)').matches ? 2 : 1)
  const id = useId()
  useEffect(() => {
    const query = window.matchMedia('(min-width: 64rem)')
    const resize = () => setLevel(query.matches ? 2 : 1)
    query.addEventListener('change', resize)
    return () => query.removeEventListener('change', resize)
  }, [])
  return <section className={`itinerary-sheet sheet-level-${level}`} aria-label="Your itinerary">
    <div className="sheet-handle" aria-hidden="true" />
    <div className="sheet-heading"><div className="min-w-0"><p className="eyebrow">YOUR ITINERARY</p><h2 className="mt-1 text-lg font-semibold">{stops.length} stops. One thoughtful day.</h2><p className="mt-1 text-xs text-neutral-500">{summary}</p></div>
      <div className="sheet-controls"><Button variant="ghost" className="icon-button" aria-controls={id} aria-expanded={level > 0} aria-label={level === 0 ? 'Expand itinerary to upcoming stops' : 'Collapse itinerary'} onClick={() => setLevel(level === 0 ? 1 : 0)}>{level === 0 ? <ChevronUp size={19} /> : <ChevronDown size={19} />}</Button>
        <Button variant="ghost" className="icon-button" aria-controls={id} aria-expanded={level === 2} aria-label={level === 2 ? 'Show upcoming stops' : 'Show complete itinerary'} onClick={() => setLevel(level === 2 ? 1 : 2)}>{level === 2 ? <Minimize2 size={16} /> : <Maximize2 size={16} />}</Button></div>
    </div>
    <div id={id} className="sheet-content" inert={level === 0 ? true : undefined}>{children(level)}</div>
  </section>
}
