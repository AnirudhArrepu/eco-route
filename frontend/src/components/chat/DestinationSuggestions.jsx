import { MapPin, ArrowUpRight } from 'lucide-react'

export default function DestinationSuggestions({ candidates, selected, onSelect }) {
  if (!candidates?.length) return <p className="notice text-sm">No destinations were returned. Try a more specific request, or search for a place directly below.</p>
  return <div className="grid gap-3" aria-label="Destination candidates">{candidates.map((candidate, index) =>
    <button type="button" key={`${candidate.id || candidate.label}-${index}`} aria-pressed={selected === candidate} onClick={() => onSelect(candidate)} className={`destination-card ${selected === candidate ? 'border-neutral-900 bg-neutral-50' : 'border-neutral-200'}`}>
      <MapPin size={18} className="mt-0.5 shrink-0" /><span className="min-w-0 flex-1"><span className="block font-medium">{candidate.title || candidate.label}</span><span className="mt-1 block text-xs text-neutral-500">{candidate.label}</span></span><ArrowUpRight size={16} className="shrink-0" />
    </button>)}</div>
}
