import { Sparkles } from 'lucide-react'

export default function ChatMessage({ role, children }) {
  return <div className={`chat-message ${role === 'user' ? 'chat-message-user' : ''}`}>
    {role !== 'user' && <Sparkles size={18} className="mt-0.5 shrink-0" aria-hidden="true" />}
    <div className="min-w-0 whitespace-pre-wrap text-sm leading-6">{children}</div>
  </div>
}
