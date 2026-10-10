import { useEffect, useId, useState } from 'react'
import { Check, MapPin, Search } from 'lucide-react'
import { searchPlaces } from '../../api/places'
import ErrorMessage from '../ui/ErrorMessage'
import LoadingState from '../ui/LoadingState'

export default function PlaceSearch({ label, value, onChange, bias, initialQuery = '', placeholder = 'Search a place or address' }) {
  const id = useId()
  const [query, setQuery] = useState(value?.title || value?.label || initialQuery)
  const [places, setPlaces] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [searched, setSearched] = useState(false)
  const [focused, setFocused] = useState(false)
  const [active, setActive] = useState(-1)
  const [retry, setRetry] = useState(0)
  const latitude = bias?.latitude
  const longitude = bias?.longitude
  useEffect(() => { setQuery(value ? (value.title || value.label || '') : initialQuery) }, [value, initialQuery])
  useEffect(() => {
    const controller = new AbortController()
    setPlaces([]); setSearched(false); setError(null); setActive(-1); setBusy(false)
    if (value || query.trim().length < 2) return () => controller.abort()
    setBusy(true)
    const timer = setTimeout(async () => {
      try {
        const result = await searchPlaces(query.trim(), { latitude, longitude }, controller.signal)
        if (!controller.signal.aborted) {
          setPlaces((result.places || []).filter(place => Number.isFinite(place.latitude) && Number.isFinite(place.longitude)))
          setSearched(true)
        }
      } catch (err) { if (!controller.signal.aborted) setError(err) }
      finally { if (!controller.signal.aborted) setBusy(false) }
    }, 350)
    return () => { clearTimeout(timer); controller.abort() }
  }, [query, value, latitude, longitude, retry])
  const select = place => { onChange(place); setQuery(place.title || place.label); setPlaces([]); setFocused(false) }
  const open = focused && !value && query.trim().length >= 2
  return <div className="field place-search" onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) setFocused(false) }}>
    <label htmlFor={id}>{label}</label>
    <div className="relative">
      <Search size={17} className="pointer-events-none absolute left-3.5 top-3.5 text-neutral-400" aria-hidden="true" />
      <input id={id} role="combobox" aria-autocomplete="list" aria-expanded={open} aria-controls={open ? `${id}-results` : undefined}
        aria-activedescendant={open && active >= 0 ? `${id}-option-${active}` : undefined}
        autoComplete="off" placeholder={placeholder} maxLength={300} value={query} className="!pl-10 !pr-10"
        onFocus={() => setFocused(true)}
        onChange={event => { setQuery(event.target.value); onChange(null); setFocused(true) }}
        onKeyDown={event => {
          if (event.key === 'Escape') { setFocused(false); return }
          if (!open || !places.length) return
          if (event.key === 'ArrowDown') { event.preventDefault(); setActive(i => (i + 1) % places.length) }
          if (event.key === 'ArrowUp') { event.preventDefault(); setActive(i => (i - 1 + places.length) % places.length) }
          if (event.key === 'Enter' && active >= 0) { event.preventDefault(); select(places[active]) }
        }} />
      {value && <Check size={17} className="absolute right-3.5 top-3.5" aria-label="Place selected" />}
    </div>
    {value && <p className="text-xs text-neutral-500">{value.label}</p>}
    {open && <div className="search-results">
      {busy && <LoadingState>Searching places…</LoadingState>}
      <ErrorMessage error={error} />
      {error && <button type="button" className="text-sm underline" onClick={() => setRetry(n => n + 1)}>Try search again</button>}
      <ul id={`${id}-results`} role="listbox" aria-label={`${label} suggestions`}>
        {places.map((place, index) => <li key={`${place.id || place.label}-${index}`} role="presentation">
          <button type="button" id={`${id}-option-${index}`} role="option" aria-selected={active === index}
            className={`place-option ${active === index ? 'bg-neutral-100' : ''}`} onMouseDown={e => e.preventDefault()} onClick={() => select(place)}>
            <MapPin size={17} className="mt-1 shrink-0 text-neutral-400" /><span><span className="block font-medium">{place.title || place.label}</span><span className="mt-1 block text-xs text-neutral-500">{place.label}</span></span>
          </button>
        </li>)}
      </ul>
      {searched && !places.length && <p role="status" className="py-3 text-sm text-neutral-500">No places found. Try a different place or address.</p>}
    </div>}
    {!value && <p className="text-xs text-neutral-500">Type at least two characters, then choose a result.</p>}
  </div>
}
