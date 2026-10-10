import { useEffect, useRef, useState } from 'react'
import { Bike, Car, Footprints, History, LogOut, Pencil, Plus, Trash2 } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { usePlan } from '../context/PlanContext'
import { getPreferences, createPreference, updatePreference, deletePreference } from '../api/preferences'
import { getRoutines, deleteRoutine } from '../api/routines'
import Button from '../components/ui/Button'
import BottomSheet from '../components/ui/BottomSheet'
import ErrorMessage from '../components/ui/ErrorMessage'
import LoadingState from '../components/ui/LoadingState'
import PreferenceEditor from '../components/settings/PreferenceEditor'
import RoutineForm, { weekdays } from '../components/settings/RoutineForm'
import RevisionHistory from '../components/itinerary/RevisionHistory'

export default function SettingsPage() {
  const [preferences, setPreferences] = useState([])
  const [routines, setRoutines] = useState([])
  const [busy, setBusy] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [editor, setEditor] = useState(null)
  const [deleting, setDeleting] = useState(null)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [deleteError, setDeleteError] = useState(null)
  const mutationController = useRef(null)
  const { account, signOut } = useAuth()
  const { activeId } = usePlan()
  const navigate = useNavigate()
  useEffect(() => {
    const controller = new AbortController(); setBusy(true); setError(null)
    Promise.all([getPreferences(controller.signal), getRoutines(controller.signal)]).then(([prefs, saved]) => {
      if (!controller.signal.aborted) { setPreferences(prefs); setRoutines(saved) }
    }).catch(err => { if (!controller.signal.aborted) setError(err) })
      .finally(() => { if (!controller.signal.aborted) setBusy(false) })
    return () => controller.abort()
  }, [attempt])
  useEffect(() => () => mutationController.current?.abort(), [])
  const preference = preferences.find(item => item.key === 'travel_mode')
  const mode = preference?.value?.mode?.toLowerCase() || 'walking'
  const saveMode = async next => {
    if (busy || saving || mode === next) return
    setSaving(true); setError(null); setNotice(''); mutationController.current = new AbortController()
    try {
      const result = preference ? await updatePreference('travel_mode', { mode: next }, mutationController.current.signal)
        : await createPreference('travel_mode', { mode: next }, mutationController.current.signal)
      setPreferences(current => [...current.filter(item => item.key !== 'travel_mode'), result])
      setNotice('Travel mode saved. Refresh your itinerary to recalculate estimates in this mode.')
    } catch (err) { if (err.name !== 'AbortError') setError(err) }
    finally { setSaving(false) }
  }
  const remove = async () => {
    setSaving(true); setDeleteError(null); mutationController.current = new AbortController()
    try {
      if (deleting.kind === 'preference') {
        await deletePreference(deleting.item.key, mutationController.current.signal)
        setPreferences(current => current.filter(item => item.key !== deleting.item.key))
      } else {
        await deleteRoutine(deleting.item.id, mutationController.current.signal)
        setRoutines(current => current.filter(item => item.id !== deleting.item.id))
      }
      setDeleting(null); setNotice('Removed successfully.')
    } catch (err) { if (err.name !== 'AbortError') setDeleteError(err) }
    finally { setSaving(false) }
  }
  const requestRemove = value => { setDeleteError(null); setDeleting(value) }
  const saved = (kind, result) => {
    if (kind === 'preference') setPreferences(current => [...current.filter(item => item.key !== result.key), result])
    else setRoutines(current => [...current.filter(item => item.id !== result.id), result])
    setEditor(null); setNotice(`${kind === 'preference' ? 'Preference' : 'Routine'} saved.`)
  }
  return <section className="page-settings py-10 sm:py-14"><p className="eyebrow">MAKE IT YOUR OWN</p><h1 className="page-title mt-4">Your way through the day.</h1><p className="mt-3 text-sm text-neutral-500">Small preferences. A more familiar journey.</p>
    {busy && <LoadingState>Loading your preferences…</LoadingState>}<div className="mt-6"><ErrorMessage error={error} /></div>
    {error && <Button variant="secondary" className="mt-3" disabled={busy || saving} onClick={() => setAttempt(n => n + 1)}>Reload settings</Button>}
    {notice && <p role="status" className="notice mt-5">{notice}</p>}
    <section className="settings-section"><div><h2 className="text-base font-semibold">How do you like to travel?</h2><p className="mt-2 text-sm leading-6 text-neutral-500">One mode applies to the full plan. This account preference is used whenever the backend calculates travel, including existing itineraries.</p></div>
      <div className="mode-grid">{[[Footprints, 'walking', 'Walking'], [Bike, 'bicycle', 'Bicycle'], [Car, 'car', 'Car']].map(([Icon, value, label]) => <button key={value} aria-pressed={mode === value} disabled={busy || saving || Boolean(error)} onClick={() => saveMode(value)} className={`mode-option ${mode === value ? 'selected' : ''}`}><Icon size={21} strokeWidth={1.5} /><span>{label}</span></button>)}</div>
      {preference && <Button variant="ghost" disabled={saving || busy} onClick={() => requestRemove({ kind: 'preference', item: preference })}>Reset to walking</Button>}
      <p className="text-xs text-neutral-500">Public transport and EV routing are coming later.</p>
    </section>
    <section className="settings-section"><div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="font-semibold">Saved routines</h2><p className="mt-2 text-sm text-neutral-500">A little rhythm for your week.</p></div><Button variant="secondary" disabled={busy || Boolean(error)} onClick={() => setEditor({ kind: 'routine', item: null })}><Plus size={16} />Add routine</Button></div>
      {!busy && !routines.length && <p className="empty-state">No routines yet. Start with a regular stop.</p>}
      {routines.map(routine => <article key={routine.id} className="settings-row"><div className="min-w-0 flex-1"><h3 className="text-sm font-medium">{routine.name}</h3><p className="mt-1 text-xs text-neutral-500">{weekdays[routine.weekday]} · {routine.stop.duration_minutes} min · {routine.active ? 'Active' : 'Paused'}</p><p className="mt-2 text-xs text-neutral-500">{routine.stop.location?.label}</p></div><Button variant="ghost" className="icon-button" disabled={saving} onClick={() => setEditor({ kind: 'routine', item: routine })} aria-label={`Edit ${routine.name}`}><Pencil size={15} /></Button><Button variant="ghost" className="icon-button" disabled={saving} onClick={() => requestRemove({ kind: 'routine', item: routine })} aria-label={`Delete ${routine.name}`}><Trash2 size={15} /></Button></article>)}
    </section>
    <section className="settings-section"><details><summary className="flex cursor-pointer items-center justify-between text-sm font-semibold">Advanced preferences<span className="text-neutral-400">+</span></summary><div className="mt-5 grid gap-3">
      <p className="text-xs leading-5 text-neutral-500">Create and manage values stored by the preferences API.</p>
      {preferences.filter(item => item.key !== 'travel_mode').map(item => <article key={item.key} className="settings-row"><div className="min-w-0 flex-1"><h3 className="text-sm font-medium">{item.key}</h3><pre className="mt-2 whitespace-pre-wrap break-all text-xs text-neutral-500">{JSON.stringify(item.value, null, 2)}</pre></div><Button variant="ghost" className="icon-button" disabled={saving} onClick={() => setEditor({ kind: 'preference', item })} aria-label={`Edit ${item.key}`}><Pencil size={15} /></Button><Button variant="ghost" className="icon-button" disabled={saving} onClick={() => requestRemove({ kind: 'preference', item })} aria-label={`Delete ${item.key}`}><Trash2 size={15} /></Button></article>)}
      <Button variant="secondary" className="justify-self-start" disabled={busy || Boolean(error)} onClick={() => setEditor({ kind: 'preference', item: null })}><Plus size={16} />Add preference</Button>
    </div></details></section>
    <section className="settings-section"><h2 className="font-semibold">Your account & plans</h2><p className="text-sm text-neutral-500 break-all">{account.email}</p><div className="flex flex-wrap gap-3"><Button variant="secondary" disabled={!activeId} onClick={() => setHistoryOpen(true)}><History size={16} />Revision history</Button><Button variant="ghost" onClick={() => { signOut(); navigate('/') }}><LogOut size={16} />Sign out</Button></div><p className="text-xs text-neutral-500">Tokens stay in memory. Reloading the page requires signing in again.</p></section>
    {editor && <BottomSheet open title={`${editor.item ? 'Edit' : 'Add'} ${editor.kind}`} onClose={() => { mutationController.current?.abort(); setEditor(null) }}>
      {editor.kind === 'routine' ? <RoutineForm key={editor.item?.id || 'new-routine'} initial={editor.item} signalRef={mutationController} onSaved={result => saved('routine', result)} onCancel={() => setEditor(null)} />
        : <PreferenceEditor key={editor.item?.key || 'new-pref'} initial={editor.item} signalRef={mutationController} onSaved={result => saved('preference', result)} onCancel={() => setEditor(null)} />}
    </BottomSheet>}
    <BottomSheet open={Boolean(deleting)} title="Remove this item?" onClose={() => { if (!saving) setDeleting(null) }}><p className="mb-5 text-sm text-neutral-500">Remove {deleting?.item?.name || deleting?.item?.key} from your saved settings? Existing schedule stops will stay in place.</p><ErrorMessage error={deleteError} /><div className="mt-5 flex flex-wrap gap-3"><Button busy={saving} onClick={remove}>Remove item</Button><Button variant="secondary" disabled={saving} onClick={() => setDeleting(null)}>Keep it</Button></div></BottomSheet>
    {historyOpen && activeId && <RevisionHistory scheduleId={activeId} onClose={() => setHistoryOpen(false)} />}
  </section>
}
