import { useEffect, useRef, useState } from 'react'
import { askAgent } from '../../api/agent'
import { addStop } from '../../api/schedules'
import useWorkflowPolling from '../../hooks/useWorkflowPolling'
import { locationFromPlace } from '../../utils/formatters'
import BottomSheet from '../ui/BottomSheet'
import Button from '../ui/Button'
import Input from '../ui/Input'
import ErrorMessage from '../ui/ErrorMessage'
import LoadingState from '../ui/LoadingState'
import PlaceSearch from '../planning/PlaceSearch'
import ChatInput from './ChatInput'
import ChatMessage from './ChatMessage'
import DestinationSuggestions from './DestinationSuggestions'

export default function ChatPanel({ open, onClose, schedule, onProposal }) {
  const [text, setText] = useState('')
  const [sent, setSent] = useState('')
  const [response, setResponse] = useState(null)
  const [selected, setSelected] = useState(null)
  const [task, setTask] = useState('')
  const [duration, setDuration] = useState(30)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const controller = useRef(null)
  const proposalCallback = useRef(onProposal)
  const handledResult = useRef(null)
  proposalCallback.current = onProposal
  const workflow = useWorkflowPolling(schedule.id)
  useEffect(() => () => controller.current?.abort(), [])
  useEffect(() => {
    if (!workflow.result || handledResult.current === workflow.result) return
    handledResult.current = workflow.result
    setResponse(workflow.result)
    if (workflow.result.id && Array.isArray(workflow.result.proposed_stops)) proposalCallback.current(workflow.result)
  }, [workflow.result])
  const send = async requestText => {
    if (busy || workflow.busy) return
    workflow.reset()
    setError(null); setResponse(null); setSelected(null); setSent(requestText); setBusy(true)
    controller.current = new AbortController()
    try {
      const result = await askAgent({ schedule_id: schedule.id, text: requestText, timezone: schedule.timezone }, controller.current.signal)
      if (result.execution_arn) workflow.start(result.execution_arn)
      else {
        setResponse(result)
        if (result.id && Array.isArray(result.proposed_stops)) onProposal(result)
      }
    } catch (err) { if (err.name !== 'AbortError') setError(err) }
    finally { setBusy(false) }
  }
  const choose = place => { setSelected(place); setTask(place?.title || place?.label || '') }
  const propose = async event => {
    event.preventDefault()
    if (!selected || busy) return
    setBusy(true); setError(null); controller.current = new AbortController()
    try {
      if (!task.trim()) throw new Error('Enter a task title for this destination.')
      if (!Number.isInteger(Number(duration)) || Number(duration) < 1 || Number(duration) > 1440) throw new Error('Enter a whole number between 1 and 1440 minutes.')
      const proposal = await addStop(schedule.id, { title: task.trim(), type: 'errand', location: locationFromPlace(selected),
        duration_minutes: Number(duration), priority: 3, mandatory: true, source: 'amazon_location' }, controller.current.signal)
      onProposal(proposal)
    } catch (err) { if (err.name !== 'AbortError') setError(err) }
    finally { setBusy(false) }
  }
  const question = response?.question || response?.intent?.clarification_question
  const isDiscovery = response?.status === 'destination_candidates' || response?.status === 'needs_destination_selection'
  return <BottomSheet open={open} onClose={onClose} title="Ask EcoRoute" className="assistant-sheet">
    <div className="assistant-content">
      <div className="assistant-history">
      <p className="text-xs leading-5 text-neutral-500">Find a destination or request a supported change to this plan. Each request is independent. For a clarification, revise your full request with the answer included.</p>
      {!sent && !response && !workflow.busy && <ChatMessage>What would make your day a little easier? Try “Find a pharmacy near my starting point”.</ChatMessage>}
      {sent && <ChatMessage role="user">{sent}</ChatMessage>}
      {question && <ChatMessage>{question}</ChatMessage>}
      {response?.message && <ChatMessage>{response.message}</ChatMessage>}
      {isDiscovery && <DestinationSuggestions candidates={response.candidates} selected={selected} onSelect={choose} />}
      {response && !question && !isDiscovery && !response.proposed_stops && <ChatMessage>The request finished without destination suggestions. Please send a specific place request or use direct search.</ChatMessage>}
      {(isDiscovery || question) && <PlaceSearch label="Or search for a destination" value={selected} onChange={choose} bias={schedule.start_location} />}
      {selected && <form onSubmit={propose} className="grid gap-4 rounded-xl border border-neutral-200 p-4">
        <p className="text-sm font-medium">Add this destination to your day</p>
        <Input label="Task title" required maxLength={256} value={task} onChange={e => setTask(e.target.value)} />
        <Input label="Duration (minutes)" type="number" required min="1" max="1440" step="1" value={duration} onChange={e => setDuration(e.target.value)} />
        <Button type="submit" busy={busy} disabled={workflow.busy}>Review addition</Button><p className="text-xs text-neutral-500">This creates a proposal. Your plan changes only after approval.</p>
      </form>}
      {workflow.busy && <div><LoadingState>Finding a little direction…</LoadingState><Button variant="ghost" onClick={workflow.pause}>Pause checking</Button></div>}
      <ErrorMessage error={error || workflow.error} />
      {workflow.executionArn && !workflow.busy && (workflow.error || workflow.status === 'PAUSED') && <Button variant="secondary" onClick={workflow.resume}>Resume checking workflow</Button>}
      {workflow.executionArn && <details className="text-xs text-neutral-500"><summary>Workflow details</summary><p className="mt-2 break-all">{workflow.executionArn}</p><p className="mt-1">{workflow.status}</p></details>}
      </div>
      <div className="assistant-composer"><ChatInput value={text} onChange={setText} onSend={send} busy={busy || workflow.busy} placeholder="Find a place or describe one change…" />
      <p className="text-xs leading-5 text-neutral-500">Suggestions do not verify prices, stock, or opening hours.</p>
      </div>
    </div>
  </BottomSheet>
}
