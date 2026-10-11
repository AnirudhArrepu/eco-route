import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { ArrowLeft, ArrowRight, Plus } from 'lucide-react'
import { createSchedule, previewSchedule } from '../api/schedules'
import { usePlan } from '../context/PlanContext'
import { localDate, localTimezone, zonedTimestamp } from '../utils/dateTime'
import { locationFromPlace } from '../utils/formatters'
import ScheduleForm from '../components/planning/ScheduleForm'
import StopForm from '../components/planning/StopForm'
import StopCard from '../components/planning/StopCard'
import TaskExtractionPanel from '../components/planning/TaskExtractionPanel'
import SchedulePreview from '../components/planning/SchedulePreview'
import Button from '../components/ui/Button'
import ErrorMessage from '../components/ui/ErrorMessage'
import Modal from '../components/ui/Modal'

const headings = ['When are you heading out?', 'Where will you start and finish?', 'What places do you need to visit?', 'A day that works for you.']
export default function PlannerPage() {
  const { draft: savedDraft, setDraft, requestText, setRequestText, setActiveId } = usePlan()
  const [draft, updateDraft] = useState(() => savedDraft || { date: localDate(), timezone: localTimezone(), startTime: '09:00', endTime: '18:00',
    startPlace: null, endPlace: null, returnToStart: true, stops: [], includeRoutines: true })
  const [step, setStep] = useState(0)
  const [editing, setEditing] = useState(null)
  const [showStopForm, setShowStopForm] = useState(false)
  const [preview, setPreview] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [exitOpen, setExitOpen] = useState(false)
  const controller = useRef(null)
  const headingRef = useRef(null)
  const navigate = useNavigate()
  const location = useLocation()
  const initialText = location.state?.requestText
  useEffect(() => { if (initialText) setRequestText(initialText) }, [initialText, setRequestText])
  useEffect(() => { setDraft(draft) }, [draft, setDraft])
  useEffect(() => { headingRef.current?.focus() }, [step])
  useEffect(() => () => controller.current?.abort(), [])
  const change = patch => { updateDraft(current => ({ ...current, ...patch })); setPreview(null); setError(null) }
  const next = async () => {
    setError(null)
    try {
      const start = zonedTimestamp(draft.date, draft.startTime, draft.timezone)
      const end = zonedTimestamp(draft.date, draft.endTime, draft.timezone)
      if (start >= end) throw new Error('End time must be after start time on the same day.')
      if (step === 0) { setStep(1); return }
      if (!draft.startPlace || (!draft.returnToStart && !draft.endPlace)) throw new Error('Choose your starting and finishing places from the search results.')
      if (step === 1) { setStep(2); return }
      if (!draft.stops.length && !draft.includeRoutines) throw new Error('Add at least one destination, or include your saved routines.')
      const body = { date: draft.date, timezone: draft.timezone, start_at: start, end_at: end,
        start_location: locationFromPlace(draft.startPlace), end_location: locationFromPlace(draft.returnToStart ? draft.startPlace : draft.endPlace),
        stops: draft.stops, constraints: [], include_routines: draft.includeRoutines }
      setBusy(true); controller.current = new AbortController()
      const response = await previewSchedule(body, controller.current.signal)
      setPreview({ body, response }); setStep(3)
    } catch (err) { if (err.name !== 'AbortError') setError(err) }
    finally { setBusy(false) }
  }
  const save = async () => {
    if (!preview?.response.feasible || busy) return
    setError(null); setBusy(true); controller.current = new AbortController()
    try {
      const result = await createSchedule(preview.body, controller.current.signal)
      if (!result?.id) throw new Error('The server did not return a schedule ID. Check your saved plan before retrying.')
      setActiveId(result.id); setDraft(null); setRequestText(''); navigate('/itinerary')
    } catch (err) { if (err.name !== 'AbortError') setError(err) }
    finally { setBusy(false) }
  }
  const storeStop = stop => {
    change({ stops: editing ? draft.stops.map(item => item.id === editing.id ? stop : item) : [...draft.stops, stop] })
    setEditing(null); setShowStopForm(false)
  }
  const addExtractedStop = stop => change({ stops: [...draft.stops, stop] })
  return <section className="page-planner">
    <div className="flex items-center justify-between gap-3"><Button variant="ghost" disabled={busy} onClick={() => step ? (setStep(step - 1), setError(null)) : setExitOpen(true)}><ArrowLeft size={16} />{step ? 'Back' : 'Home'}</Button><span className="text-xs text-neutral-500">STEP {step + 1} OF 4</span></div>
    <div className="step-progress" aria-label={`Step ${step + 1} of 4`}>{headings.map((_, i) => <span key={i} className={i <= step ? 'bg-neutral-900' : 'bg-neutral-200'} />)}</div>
    <h1 ref={headingRef} tabIndex={-1} className="page-title mt-9 outline-none">{headings[step]}</h1>
    <p className="mt-3 text-sm leading-6 text-neutral-500">{step === 0 ? 'Let’s start with a little time for what matters.' : step === 1 ? 'A good day starts with a starting point.' : step === 2 ? 'Tell us your errands. We’ll find each stop, then work out the order.' : 'Your plan stays unsaved until you confirm.'}</p>
    <fieldset disabled={busy} className="mt-8 min-w-0">
      {step < 2 && <ScheduleForm step={step} draft={draft} onChange={change} />}
      {step === 2 && <div className="grid gap-4">
        <TaskExtractionPanel text={requestText} onTextChange={setRequestText} date={draft.date} timezone={draft.timezone} startPlace={draft.startPlace} endPlace={draft.returnToStart ? draft.startPlace : draft.endPlace} onAdd={addExtractedStop} />
        {draft.stops.map((stop, index) => <StopCard key={stop.id} stop={stop} index={index} onEdit={() => { setEditing(stop); setShowStopForm(true) }} onRemove={() => change({ stops: draft.stops.filter(item => item.id !== stop.id) })} />)}
        {showStopForm ? <div className="rounded-xl border border-neutral-200 p-4 sm:p-6"><h2 className="mb-5 font-semibold">{editing ? 'Adjust this stop' : 'One more thing to do'}</h2><StopForm key={editing?.id || 'new'} initial={editing} date={draft.date} timezone={draft.timezone} bias={draft.startPlace}
          onSubmit={storeStop} onCancel={() => { setEditing(null); setShowStopForm(false) }} /></div>
          : <Button variant="secondary" className="w-full" onClick={() => { setEditing(null); setShowStopForm(true) }}><Plus size={17} />Add a destination manually</Button>}
        {!draft.stops.length && !showStopForm && <p className="py-3 text-center text-sm text-neutral-500">Choose a place for each extracted task or add destinations manually.</p>}
      </div>}
      {step === 3 && preview && <SchedulePreview preview={preview.response} body={preview.body} />}
    </fieldset>
    <div className="mt-6"><ErrorMessage error={error} /></div>
    <div className="planner-actions">{step < 3 ? <Button className="w-full" busy={busy} disabled={step === 2 && showStopForm} onClick={next}>{step === 2 ? 'Preview my day' : 'Continue'}<ArrowRight size={17} /></Button>
      : <div className="grid gap-3"><Button className="w-full" busy={busy} disabled={!preview?.response.feasible} onClick={save}>Confirm & save plan<ArrowRight size={17} /></Button>
        <Button variant="secondary" disabled={busy} onClick={() => { setStep(2); setPreview(null) }}>Adjust my plan</Button></div>}
      <p className="mt-3 text-center text-xs text-neutral-500">Your account’s travel mode applies to the full plan. Change it in Settings.</p>
    </div>
    <Modal open={exitOpen} title="Keep your draft?" onClose={() => setExitOpen(false)}><p className="mb-5 text-sm text-neutral-500">Your draft will stay here while you explore, until you sign out or reload.</p><Button onClick={() => navigate('/')}>Keep draft & go home</Button></Modal>
  </section>
}
