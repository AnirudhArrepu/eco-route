import { useEffect, useState } from 'react'
import { getRevisions } from '../../api/schedules'
import BottomSheet from '../ui/BottomSheet'
import Button from '../ui/Button'
import ErrorMessage from '../ui/ErrorMessage'
import LoadingState from '../ui/LoadingState'

export default function RevisionHistory({ scheduleId, revision, onClose }) {
  const [revisions, setRevisions] = useState([])
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState(null)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const controller = new AbortController(); setBusy(true); setError(null)
    getRevisions(scheduleId, controller.signal).then(result => { if (!controller.signal.aborted) setRevisions(result) })
      .catch(err => { if (!controller.signal.aborted) setError(err) })
      .finally(() => { if (!controller.signal.aborted) setBusy(false) })
    return () => controller.abort()
  }, [scheduleId, revision, attempt])
  return <BottomSheet open title="Revision history" onClose={onClose}>
    {busy && <LoadingState>Loading saved revisions…</LoadingState>}<ErrorMessage error={error} />
    {error && <Button variant="secondary" onClick={() => setAttempt(n => n + 1)}>Try again</Button>}
    <ol className="grid gap-4">{revisions.map(revision => <li key={revision.id} className="rounded-xl border border-neutral-200 p-4"><p className="text-sm font-semibold">Revision {revision.revision_number}</p><p className="mt-2 text-sm text-neutral-500">{revision.reason}</p><p className="mt-2 text-xs text-neutral-400">{new Date(revision.created_at).toLocaleString()}</p>
      <details className="mt-3 text-xs"><summary>View saved stops</summary><ol className="mt-2 list-decimal space-y-2 pl-5">{(revision.snapshot?.stops || []).map(stop => <li key={stop.id}>{stop.title} · {stop.duration_minutes} min</li>)}</ol></details>
    </li>)}</ol>
    {!busy && !error && !revisions.length && <p className="text-sm text-neutral-500">No revisions were returned.</p>}
  </BottomSheet>
}
