import { useEffect, useRef, useState } from 'react'
import { approveProposal, getProposal, rejectProposal } from '../../api/proposals'
import { getSchedule } from '../../api/schedules'
import { ApiError } from '../../api/client'
import { formatTime } from '../../utils/dateTime'
import { minutes, uniqueId } from '../../utils/formatters'
import { readSession, writeSession } from '../../utils/storage'
import BottomSheet from '../ui/BottomSheet'
import Button from '../ui/Button'
import ErrorMessage from '../ui/ErrorMessage'
import ScheduleMetrics from './ScheduleMetrics'
import Timeline from './Timeline'
import { PlanConflicts } from '../planning/SchedulePreview'

export default function ProposalReview({ proposal: initial, schedule, onClose, onApproved }) {
  const [proposal, setProposal] = useState(initial)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [now, setNow] = useState(Date.now())
  const [refreshFailed, setRefreshFailed] = useState(false)
  const controller = useRef(null)
  const storageKey = `ecoroute:approval:${initial.id}`
  const key = useRef(readSession(storageKey))
  const [uncertain, setUncertain] = useState(Boolean(key.current))
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 10000)
    return () => { clearInterval(timer); controller.current?.abort() }
  }, [])
  const expiresAt = Date.parse(proposal.expires_at)
  const expired = !Number.isFinite(expiresAt) || expiresAt <= now
  const stale = proposal.base_revision !== schedule.current_revision
  const pending = proposal.status === 'pending'
  const after = proposal.metrics?.after
  const before = proposal.metrics?.before
  const approve = async () => {
    if (busy) return
    setBusy(true); setError(null); controller.current = new AbortController()
    try {
      const latest = await getProposal(proposal.id, controller.current.signal)
      setProposal(latest)
      // An uncertain previous response may have committed. Reuse its key to reconcile.
      if (latest.status === 'approved') {
        setRefreshFailed(true)
      } else {
        const current = await getSchedule(schedule.id, controller.current.signal)
        if (latest.base_revision !== current.current_revision) throw new ApiError('The plan changed. Keep the original and request a new proposal.', 409)
        if (latest.status !== 'pending' || !latest.feasible) throw new ApiError('This proposal can no longer be approved.', 409)
        if (!Number.isFinite(Date.parse(latest.expires_at)) || Date.parse(latest.expires_at) <= Date.now()) throw new ApiError('This proposal expired. Request another change.', 410)
        if (!key.current) key.current = uniqueId()
        writeSession(storageKey, key.current); setUncertain(true)
        await approveProposal(proposal.id, key.current, controller.current.signal)
      }
      writeSession(storageKey, null); setUncertain(false)
      setProposal(current => ({ ...current, status: 'approved' }))
      try { await onApproved(); onClose(true) } catch (err) { setRefreshFailed(true); throw new Error(`Changes were approved, but the itinerary could not be refreshed. ${err.message}`) }
    } catch (err) {
      if (err.status === 409 || err.status === 410) { setUncertain(false); writeSession(storageKey, null) }
      if (err.name !== 'AbortError') setError(err)
    }
    finally { setBusy(false) }
  }
  const reject = async () => {
    setBusy(true); setError(null); controller.current = new AbortController()
    try {
      const latest = await getProposal(proposal.id, controller.current.signal)
      setProposal(latest)
      if (latest.status === 'approved') {
        setRefreshFailed(true)
        throw new Error('These changes were already approved. Refresh the approved itinerary to continue.')
      } else if (latest.status === 'pending') {
        await rejectProposal(proposal.id, controller.current.signal)
      }
      writeSession(storageKey, null); onClose(true)
    } catch (err) { if (err.name !== 'AbortError') setError(err) }
    finally { setBusy(false) }
  }
  const reload = async () => {
    setBusy(true); setError(null)
    try { await onApproved(); onClose(true) } catch (err) { setError(err) } finally { setBusy(false) }
  }
  return <BottomSheet open title="Review changes" onClose={() => { if (!busy) onClose(false) }}>
    <div className="grid gap-6">
      <p className="text-sm text-neutral-500">Your current plan stays in place until you approve. Proposal for revision {proposal.base_revision}.</p>
      {(expired || stale || !pending) && <p role="status" className="notice">{proposal.status === 'approved' ? 'Changes have been approved.' : expired ? 'This proposal has expired. Request a new change.' : stale ? 'The plan changed since this proposal. Request a new change.' : `Proposal status: ${proposal.status}.`}</p>}
      <ScheduleMetrics metrics={after} />
      {before && after && <p className="text-sm text-neutral-500">Travel changes by {after.travel_minutes - before.travel_minutes >= 0 ? '+' : ''}{(after.travel_minutes - before.travel_minutes).toFixed(1)} min. Original travel: {minutes(before.travel_minutes)}.</p>}
      <PlanConflicts conflicts={proposal.conflicts} />
      {!proposal.feasible && <p className="notice">This proposal is infeasible and cannot be approved. Adjust a time window, duration, or destination.</p>}
      <Timeline stops={proposal.proposed_stops} timeline={after?.timeline || []} previousTimeline={before?.timeline || []} timezone={schedule.timezone} schedule={schedule} metrics={after} />
      {proposal.explanation_facts?.length > 0 && <ul className="list-disc space-y-2 pl-4 text-xs text-neutral-500">{proposal.explanation_facts.map((fact, i) => <li key={i}>{fact}</li>)}</ul>}
      <p className="text-xs text-neutral-500">Expires {formatTime(proposal.expires_at, schedule.timezone)} · Estimates are revalidated on approval.</p>
      <ErrorMessage error={error} />
      <div className="grid gap-3 sm:grid-cols-2">
        {refreshFailed || proposal.status === 'approved' ? <Button busy={busy} onClick={reload}>Refresh approved itinerary</Button>
          : <Button busy={busy} disabled={!uncertain && (!proposal.feasible || !pending || expired || stale)} onClick={approve}>{uncertain ? 'Check approval & retry' : 'Approve changes'}</Button>}
        <Button variant="secondary" disabled={busy} onClick={proposal.status === 'approved' ? reload : reject}>{proposal.status === 'approved' ? 'Refresh & close review' : 'Keep original plan'}</Button>
      </div>
    </div>
  </BottomSheet>
}
