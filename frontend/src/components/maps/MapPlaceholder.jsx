import { Map, MoveUpRight } from 'lucide-react'

export default function MapPlaceholder() {
  return <section className="map-placeholder" aria-label="Map placeholder">
    <div className="map-label"><span className="h-1.5 w-1.5 rounded-full bg-neutral-400" />YOUR JOURNEY, AT A GLANCE</div>
    <div className="map-empty"><span className="map-icon"><Map size={28} strokeWidth={1.2} /></span><h2 className="mt-5 text-sm font-medium">Map integration coming soon</h2><p className="mt-2 max-w-56 text-xs leading-5 text-neutral-500">For now, your itinerary has all the direction you need.</p></div>
    <div className="map-footer"><span>No map or route geometry is displayed.</span><MoveUpRight size={17} /></div>
  </section>
}
