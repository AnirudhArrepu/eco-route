import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, MapPin } from 'lucide-react'
import { usePlan } from '../context/PlanContext'
import PlaceSearch from '../components/planning/PlaceSearch'
import Button from '../components/ui/Button'
import ErrorMessage from '../components/ui/ErrorMessage'

export default function DiscoverPage() {
  const [place, setPlace] = useState(null)
  const [bias, setBias] = useState(null)
  const [error, setError] = useState(null)
  const [locating, setLocating] = useState(false)
  const { setRequestText, activeId } = usePlan()
  const navigate = useNavigate()
  const locate = () => {
    setError(null)
    if (!navigator.geolocation) { setError('Location is unavailable in this browser. Search by name or address instead.'); return }
    setLocating(true)
    navigator.geolocation.getCurrentPosition(position => {
      setBias({ latitude: position.coords.latitude, longitude: position.coords.longitude }); setLocating(false)
    }, () => { setError('Could not access your location. You can still search by name or address.'); setLocating(false) }, { timeout: 10000, maximumAge: 60000 })
  }
  return <section className="page-narrow py-10 sm:py-16"><p className="eyebrow">A PLACE TO START</p><h1 className="page-title mt-4">Find your next stop.</h1><p className="mt-3 text-neutral-500">Search real places by name, address, or what you need nearby.</p>
    <div className="mt-8 grid gap-5"><Button variant="secondary" className="justify-self-start" busy={locating} onClick={locate}><MapPin size={17} />{bias ? 'Update my search location' : 'Search near my location'}</Button>
      {bias && <p role="status" className="text-xs text-neutral-500">Your location is used as a search bias. Results are not ranked for the entire itinerary.</p>}
      <ErrorMessage error={error} /><PlaceSearch label="Look for a place" value={place} onChange={setPlace} bias={bias} />
      {place && <div className="notice"><h2 className="font-medium">{place.title}</h2><p className="mt-1 text-sm text-neutral-500">{place.label}</p><Button className="mt-5" onClick={() => {
        const text = `Visit ${place.title || place.label} (${place.label})`
        setRequestText(text); navigate('/plan', { state: { requestText: text } })
      }}>Plan a visit<ArrowRight size={16} /></Button></div>}
      {activeId && <Button variant="ghost" className="justify-self-start" onClick={() => navigate('/itinerary', { state: { ask: true } })}>Ask EcoRoute inside my itinerary<ArrowRight size={16} /></Button>}
      <p className="text-xs leading-5 text-neutral-500">Place results do not verify inventory, prices, or current opening hours.</p>
    </div>
  </section>
}
