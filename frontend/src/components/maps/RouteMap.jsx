import { useEffect, useMemo, useRef } from 'react'
import L from 'leaflet'
import 'leaflet.markercluster'
import 'leaflet/dist/leaflet.css'
import 'leaflet.markercluster/dist/MarkerCluster.css'
import 'leaflet.markercluster/dist/MarkerCluster.Default.css'

function coordinates(location) {
  if (!Number.isFinite(location?.latitude) || !Number.isFinite(location?.longitude)) return null
  if (location.latitude < -90 || location.latitude > 90 || location.longitude < -180 || location.longitude > 180) return null
  return [location.latitude, location.longitude]
}

function markerIcon(label, kind) {
  return L.divIcon({
    className: 'route-marker-container',
    html: `<span class="route-marker route-marker-${kind}">${label}</span>`,
    iconSize: [30, 30],
    iconAnchor: [15, 15],
  })
}

function popupContent(title, label) {
  const content = document.createElement('div')
  content.append(document.createTextNode(title))
  if (label) content.append(document.createElement('br'), document.createTextNode(label))
  return content
}

function addMarkers(group, schedule, start, finish, stops) {
  if (start) {
    group.addLayer(L.marker(start, { icon: markerIcon('S', 'endpoint') })
      .bindPopup(popupContent('Start', schedule.start_location?.label || 'Starting point')))
  }
  for (const stop of stops) {
    group.addLayer(L.marker(stop.point, { icon: markerIcon(String(stop.index + 1), 'stop') })
      .bindPopup(popupContent(`${stop.index + 1}. ${stop.title}`, stop.location?.label)))
  }
  if (finish) {
    group.addLayer(L.marker(finish, { icon: markerIcon('F', 'finish') })
      .bindPopup(popupContent('Finish', schedule.end_location?.label || 'Finish point')))
  }
}

export default function RouteMap({ schedule }) {
  const container = useRef(null)
  const map = useRef(null)
  const routeLayer = useRef(null)
  const start = useMemo(() => coordinates(schedule.start_location), [schedule.start_location])
  const finish = useMemo(() => coordinates(schedule.end_location), [schedule.end_location])
  const stops = useMemo(() => schedule.stops.map((stop, index) => ({
    ...stop,
    index,
    point: coordinates(stop.location),
  })).filter(stop => stop.point), [schedule.stops])
  const points = useMemo(() => [start, ...stops.map(stop => stop.point), finish].filter(Boolean), [finish, start, stops])
  const bounds = useMemo(() => points.length ? L.latLngBounds(points) : null, [points])

  useEffect(() => {
    const instance = L.map(container.current, { scrollWheelZoom: false })
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxZoom: 19,
    }).addTo(instance)
    map.current = instance
    routeLayer.current = L.layerGroup().addTo(instance)
    return () => {
      instance.remove()
      map.current = null
      routeLayer.current = null
    }
  }, [])

  useEffect(() => {
    const instance = map.current
    const layer = routeLayer.current
    if (!instance || !layer) return
    layer.clearLayers()
    if (points.length > 1) {
      layer.addLayer(L.polyline(points, { color: '#111827', weight: 3, opacity: 0.7, dashArray: '7 8' }))
    }
    const markers = L.markerClusterGroup({
      maxClusterRadius: 32,
      showCoverageOnHover: false,
      spiderfyOnMaxZoom: true,
      iconCreateFunction: cluster => L.divIcon({
        className: 'route-marker-container',
        html: `<span class="route-marker route-marker-cluster">${cluster.getChildCount()}</span>`,
        iconSize: [34, 34],
        iconAnchor: [17, 17],
      }),
    })
    addMarkers(markers, schedule, start, finish, stops)
    layer.addLayer(markers)
    if (bounds) instance.fitBounds(bounds, { padding: [32, 32], maxZoom: 14 })
    instance.invalidateSize()
  }, [bounds, finish, points, schedule, start, stops])

  return <section className="map-placeholder" aria-label="Itinerary map">
    <div className="map-label"><span className="h-1.5 w-1.5 rounded-full bg-neutral-900" />YOUR JOURNEY, AT A GLANCE</div>
    {points.length > 0
      ? <div ref={container} className="route-map" role="application" aria-label="Map showing route stops" />
      : <div className="map-empty"><p className="text-sm font-medium">Map locations unavailable</p><p className="mt-2 max-w-56 text-xs leading-5 text-neutral-500">Add coordinates to the start, finish, and stops to see them on a map.</p></div>}
    <div className="map-footer"><span>Dashed line shows stop order only, not road directions.</span></div>
  </section>
}
