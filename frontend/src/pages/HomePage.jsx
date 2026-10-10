import { ArrowUpRight, CalendarDays, Compass, MapPin, Route } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { usePlan } from '../context/PlanContext'
import ChatInput from '../components/chat/ChatInput'

export default function HomePage() {
  const { requestText, setRequestText, activeId } = usePlan()
  const navigate = useNavigate()
  const plan = text => { setRequestText(text); navigate('/plan', { state: { requestText: text } }) }
  return <section className="home-screen">
    <div className="home-content">
      <div className="eyebrow"><span className="inline-block h-1.5 w-1.5 rounded-full bg-neutral-900" /> YOUR DAY, WITH A LITTLE DIRECTION</div>
      <div className="home-symbol" aria-hidden="true"><Route size={32} strokeWidth={1.2} /></div>
      <h1 className="home-heading">Where can I help you<br className="hidden sm:block" /> go today?</h1>
      <p className="mt-5 text-base text-neutral-500 sm:text-lg">Tell me what you need to get done.</p>
      <div className="quick-actions">
        <button className="quick-action" onClick={() => plan(requestText)}><CalendarDays size={19} /><span>Plan my day</span><ArrowUpRight size={16} /></button>
        <button className="quick-action" onClick={() => navigate('/discover')}><MapPin size={19} /><span>Find nearby places</span><ArrowUpRight size={16} /></button>
        <button className="quick-action" onClick={() => navigate('/itinerary')}><Compass size={19} /><span>Open my itinerary</span><ArrowUpRight size={16} /></button>
      </div>
      {activeId && <button onClick={() => navigate('/itinerary')} className="mt-6 text-sm text-neutral-500 underline underline-offset-4">Pick up where you left off</button>}
    </div>
    <div className="home-composer">
      <ChatInput value={requestText} onChange={setRequestText} onSend={plan} />
      <p className="mt-3 text-center text-xs leading-5 text-neutral-400">Start with a guided plan. You’re always in control of the changes.<span className="block sm:inline"> Voice coming soon.</span></p>
    </div>
    <footer className="home-footer"><span>MOVE THROUGH YOUR DAY, MINDFULLY.</span><span>Made for the everyday journey <span aria-hidden="true">↗</span></span></footer>
  </section>
}
