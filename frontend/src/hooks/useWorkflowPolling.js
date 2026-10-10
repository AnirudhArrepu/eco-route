import { useCallback, useEffect, useState } from 'react'
import { getWorkflowStatus } from '../api/agent'
import { readSession, writeSession } from '../utils/storage'

export default function useWorkflowPolling(scheduleId) {
  const storageKey = `ecoroute:workflow:${scheduleId}`
  const [executionArn, setExecutionArn] = useState(() => readSession(storageKey) || '')
  const [paused, setPaused] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const [status, setStatus] = useState('')
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  useEffect(() => {
    if (!executionArn || paused) return
    const controller = new AbortController()
    const startedAt = Date.now()
    let timer
    setStatus('RUNNING'); setError(null); setResult(null)
    const poll = async () => {
      if (Date.now() - startedAt >= 120000) {
        setStatus('CLIENT_TIMEOUT'); setError(new Error('This is taking longer than expected. Resume checking the same workflow.')); return
      }
      try {
        const response = await getWorkflowStatus(executionArn, controller.signal)
        if (controller.signal.aborted) return
        setStatus(response.status)
        if (response.status === 'RUNNING') { timer = setTimeout(poll, 2000); return }
        if (response.status !== 'SUCCEEDED') throw new Error(`The workflow ended with ${response.status || 'an unknown status'}${response.error ? ` (${response.error})` : ''}. You can check again or send a new request.`)
        if (!response.result || typeof response.result !== 'object') throw new Error('The workflow finished without a usable result. Try a more specific request.')
        writeSession(storageKey, null)
        setResult(response.result)
      } catch (err) {
        if (!controller.signal.aborted) { setError(err); setStatus('ERROR') }
      }
    }
    poll()
    return () => { controller.abort(); clearTimeout(timer) }
  }, [executionArn, paused, attempt, storageKey])
  const start = useCallback(arn => {
    writeSession(storageKey, arn); setExecutionArn(arn); setPaused(false); setStatus('RUNNING'); setResult(null); setError(null); setAttempt(n => n + 1)
  }, [storageKey])
  const reset = () => {
    writeSession(storageKey, null); setExecutionArn(''); setResult(null); setError(null); setStatus(''); setPaused(false)
  }
  const resume = () => { setPaused(false); setAttempt(n => n + 1) }
  const pause = () => { setPaused(true); setStatus('PAUSED') }
  return { executionArn, status, result, error, start, resume, pause, reset, busy: status === 'RUNNING' && !paused }
}
