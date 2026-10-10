import { useId } from 'react'
import { ArrowUp, Mic } from 'lucide-react'
import Button from '../ui/Button'

export default function ChatInput({ value, onChange, onSend, busy = false, placeholder = 'What’s on your list today?' }) {
  const id = useId()
  return <form className="chat-composer" onSubmit={event => { event.preventDefault(); if (value.trim() && !busy) onSend(value.trim()) }}>
    <label htmlFor={id} className="sr-only">Your request</label>
    <textarea id={id} rows={2} maxLength={4000} value={value} placeholder={placeholder} disabled={busy}
      onChange={event => onChange(event.target.value)} onKeyDown={event => {
        if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
          event.preventDefault()
          if (value.trim() && !busy) onSend(value.trim())
        }
      }} />
    <div className="flex items-center justify-between gap-3">
      <span className="composer-caption">Voice coming soon<span className="hidden sm:inline"> · Make room for your day.</span></span>
      <div className="flex items-center gap-2">
        <span title="Voice transcription — Coming soon" className="inline-flex"><button type="button" disabled aria-label="Voice transcription — Coming soon" className="icon-button text-neutral-400"><Mic size={18} /></button></span>
        <Button type="submit" className="icon-button send-button" busy={busy} disabled={!value.trim()} aria-label="Send request">{!busy && <ArrowUp size={20} />}</Button>
      </div>
    </div>
    <span className="sr-only">Voice transcription coming soon. Press Shift and Enter for a new line.</span>
  </form>
}
