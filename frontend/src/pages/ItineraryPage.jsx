import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { ArrowRight, History, Plus, RefreshCw, Sparkles } from 'lucide-react'
import { getSchedule, getTimeline, replanSchedule } from '../api/schedules'
import { getProposal } from '../api/proposals'
import { usePlan } from '../context/PlanContext'
import { formatDate, formatTime } from '../utils/dateTime'
import { minutes } from '../utils/formatters'
import { readSession, writeSession } from '../utils/storage'
import Button from '../components/ui/Button'
import Input from '../components/ui/Input'
import BottomSheet from '../components/ui/BottomSheet'
import ErrorMessage from '../components/ui/ErrorMessage'
import LoadingState from '../components/ui/LoadingState'
import ItinerarySheet from '../components/itinerary/ItinerarySheet'
import Timeline from '../components/itinerary/Timeline'
import ScheduleMetrics from '../components/itinerary/ScheduleMetrics'
import ProposalReview from '../components/itinerary/ProposalReview'
import RevisionHistory from '../components/itinerary/RevisionHistory'
import StopForm from '../components/planning/StopForm'
import { PlanConflicts } from '../components/planning/SchedulePreview'
import ChatPanel from '../components/chat/ChatPanel'

const RouteMap = lazy(() => import('../components/maps/RouteMap'))

export default function ItineraryPage() {
  const { activeId, setActiveId } = usePlan()
  const [idInput, setIdInput] = useState('')
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [editError, setEditError] = useState(null)
  const [editing, setEditing] = useState(null)
  const [saving, setSaving] = useState(false)
  const [proposal, setProposal] = useState(null)
  const [pendingId, setPendingId] = useState('')
  const [historyOpen, setHistoryOpen] = useState(false)
  const [switchOpen, setSwitchOpen] = useState(false)
  const location = useLocation()
  const [assistantOpen, setAssistantOpen] = useState(Boolean(location.state?.ask))
  const controller = useRef(null)
  const editController = useRef(null)
  const navigate = useNavigate()
  const load = useCallback(async signal => {
    const [schedule, timeline] = await Promise.all([getSchedule(activeId, signal), getTimeline(activeId, signal)])
    if (signal?.aborted) return
    if (schedule.current_revision !== timeline.revision) throw new Error('The schedule changed while loading. Refresh to load a consistent itinerary.')
    setData({ schedule, ...timeline })
  }, [activeId])
  useEffect(() => {
    setData(null); setProposal(null); setEditing(null); setError(null)
    setPendingId(activeId ? readSession(`ecoroute:proposal:${activeId}`) || '' : '')
    if (!activeId) return
    controller.current = new AbortController(); const signal = controller.current.signal
    setBusy(true)
    load(signal).catch(err => { if (!signal.aborted) setError(err) }).finally(() => { if (!signal.aborted) setBusy(false) })
    return () => controller.current?.abort()
  }, [activeId, load])
  useEffect(() => () => editController.current?.abort(), [])
  const refresh = async () => {
    controller.current?.abort(); controller.current = new AbortController(); setBusy(true); setError(null)
    try { await load(controller.current.signal) } catch (err) { if (err.name !== 'AbortError') setError(err) } finally { setBusy(false) }
  }
  const approved = async () => {
    controller.current?.abort(); controller.current = new AbortController()
    await load(controller.current.signal)
  }
  const receiveProposal = result => {
    setAssistantOpen(false); setEditing(null); setProposal(result); setPendingId(result.id)
    writeSession(`ecoroute:proposal:${activeId}`, result.id)
  }
  const closeProposal = resolved => {
    setProposal(null)
    if (resolved) { setPendingId(''); writeSession(`ecoroute:proposal:${activeId}`, null) }
  }
  const reopenProposal = async () => {
    setBusy(true); setError(null); controller.current?.abort(); controller.current = new AbortController()
    try { setProposal(await getProposal(pendingId, controller.current.signal)) }
    catch (err) {
      if (err.status === 404) { setPendingId(''); writeSession(`ecoroute:proposal:${activeId}`, null) }
      if (err.name !== 'AbortError') setError(err)
    }
    finally { setBusy(false) }
  }
  const editStop = async stop => {
    setSaving(true); setEditError(null); editController.current = new AbortController()
    const keys = ['duration_minutes', 'earliest_start', 'latest_start', 'latest_end', 'fixed_start', 'priority', 'mandatory']
    const updates = Object.fromEntries(keys.map(key => [key, stop[key]]))
    try { receiveProposal(await replanSchedule(activeId, { [stop.id]: updates }, editController.current.signal)) }
    catch (err) { if (err.name !== 'AbortError') setEditError(err) }
    finally { setSaving(false) }
  }
  const opener = <form onSubmit={event => { event.preventDefault(); if (idInput.trim()) { setActiveId(idInput.trim()); setSwitchOpen(false) } }} className="grid gap-4">
    <Input label="Saved schedule ID" value={idInput} onChange={e => setIdInput(e.target.value)} required maxLength={128} placeholder="Paste your schedule ID" />
    <Button type="submit">Open saved plan<ArrowRight size={16} /></Button><p className="text-xs leading-5 text-neutral-500">EcoRoute remembers your active schedule in this browser tab. The backend does not provide a list of previous schedules.</p>
  </form>
  if (!activeId) return <section className="page-narrow py-12 sm:py-20"><p className="eyebrow">A LITTLE SPACE FOR YOUR DAY</p><h1 className="page-title mt-4">Your next journey starts here.</h1><p className="mb-8 mt-4 text-neutral-500">Build a plan, then keep every stop in one place.</p><Button onClick={() => navigate('/plan')}><Plus size={17} />Plan my day</Button><div className="mt-10 border-t border-neutral-200 pt-8">{opener}</div></section>
  if (!data) return <section className="page-narrow py-10">{busy && <LoadingState>Getting your day together…</LoadingState>}<ErrorMessage error={error} /><div className="mt-5 flex flex-wrap gap-3"><Button variant="secondary" disabled={busy} onClick={refresh}>Try again</Button><Button variant="ghost" onClick={() => setActiveId('')}>Open another plan</Button></div></section>
  const { schedule } = data
  const summary = `${formatTime(schedule.start_at, schedule.timezone)} – ${formatTime(schedule.end_at, schedule.timezone)} · ${minutes(data.metrics?.travel_minutes)} est. travel`
  return <section className="itinerary-page">
    <div className="itinerary-toolbar"><div className="min-w-0"><p className="eyebrow">A DAY, THOUGHTFULLY PLANNED</p><h1 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">{formatDate(schedule.date)}</h1><p className="mt-2 text-xs text-neutral-500">{summary} · {schedule.timezone}</p></div>
      <div className="flex flex-wrap items-center gap-2"><Button variant="secondary" className="icon-button" disabled={busy} onClick={refresh} aria-label="Refresh itinerary"><RefreshCw size={17} /></Button>
        <Button variant="secondary" className="icon-button" onClick={() => setHistoryOpen(true)} aria-label="Open revision history"><History size={18} /></Button>
        <Button onClick={() => setAssistantOpen(true)}><Sparkles size={16} /><span>Ask EcoRoute</span></Button></div>
    </div>
    <ErrorMessage error={error} />
    {pendingId && <div className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-neutral-200 p-4"><p className="text-sm text-neutral-500">A recent proposal is available to review.</p><Button variant="secondary" disabled={busy} onClick={reopenProposal}>Review changes</Button></div>}
    <div className="itinerary-grid">
      <Suspense fallback={<section className="map-placeholder" aria-label="Loading itinerary map"><div className="map-empty text-sm text-neutral-500">Loading map…</div></section>}>
        <RouteMap schedule={schedule} />
      </Suspense>
      <ItinerarySheet stops={schedule.stops} summary={`Revision ${schedule.current_revision} · ${data.feasible ? 'Feasible plan' : 'Needs attention'}`}>
        {level => {
          const upcoming = data.timeline?.filter(item => Date.parse(item.end_at) >= Date.now()).map(item => item.stop_id) || []
          const visibleStops = level === 2 ? schedule.stops : upcoming.length ? schedule.stops.filter(stop => upcoming.includes(stop.id)).slice(0, 2) : schedule.stops.slice(0, 2)
          return <div className="grid gap-6"><ScheduleMetrics metrics={data.metrics} /><PlanConflicts conflicts={data.conflicts} />
            {level < 2 && <p className="text-xs text-neutral-500">{upcoming.length ? 'Upcoming stops · expand to see the complete day' : 'First stops · expand to see the complete day'}</p>}
            <Timeline stops={visibleStops} allStops={schedule.stops} timeline={data.timeline} timezone={schedule.timezone} schedule={level === 2 ? schedule : undefined} metrics={data.metrics} onEdit={stop => { setEditError(null); setEditing(stop) }} />
            <p className="text-xs leading-5 text-neutral-500">{data.travel_estimate_source === 'local_mock' ? 'Local development travel estimates; not live routes.' : 'Travel estimates may change. Current traffic and opening hours are not guaranteed.'}</p>
            <details className="text-xs text-neutral-500"><summary>Plan details</summary><p className="mt-2 break-all">Schedule ID: {schedule.id}</p><Button variant="ghost" className="mt-2" onClick={() => setSwitchOpen(true)}>Open another saved plan</Button></details>
          </div>
        }}
      </ItinerarySheet>
    </div>
    <ChatPanel key={schedule.id} open={assistantOpen} onClose={() => setAssistantOpen(false)} schedule={schedule} onProposal={receiveProposal} />
    {proposal && <ProposalReview key={proposal.id} proposal={proposal} schedule={schedule} onClose={closeProposal} onApproved={approved} />}
    {editing && <BottomSheet open title="Adjust this stop" onClose={() => { if (!saving) setEditing(null) }}><StopForm key={editing.id} initial={editing} editing timezone={schedule.timezone} date={schedule.date} busy={saving} onSubmit={editStop} onCancel={() => setEditing(null)} /><div className="mt-5"><ErrorMessage error={editError} /></div></BottomSheet>}
    {historyOpen && <RevisionHistory scheduleId={schedule.id} revision={schedule.current_revision} onClose={() => setHistoryOpen(false)} />}
    <BottomSheet open={switchOpen} title="Open a saved plan" onClose={() => setSwitchOpen(false)}>{opener}</BottomSheet>
  </section>
}
