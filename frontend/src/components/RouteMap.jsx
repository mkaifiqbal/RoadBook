import { useEffect } from 'react'
import L from 'leaflet'
import { MapContainer, Marker, Polyline, Popup, TileLayer, useMap } from 'react-leaflet'
import { BedDouble, Coffee, Fuel, MapPin, PackageCheck, RotateCcw } from 'lucide-react'
import { renderToStaticMarkup } from 'react-dom/server'

const stopIcons = { fuel: Fuel, break: Coffee, rest: BedDouble, restart: RotateCcw, pickup: PackageCheck, dropoff: MapPin }

function markerIcon(type, role) {
  const Icon = stopIcons[type] || stopIcons[role] || MapPin
  return L.divIcon({
    className: 'map-div-icon',
    html: renderToStaticMarkup(<div className={`map-pin ${type || role}`}><Icon size={15} /></div>),
    iconSize: [34, 34], iconAnchor: [17, 17], popupAnchor: [0, -18],
  })
}

function FitRoute({ geometry }) {
  const map = useMap()
  useEffect(() => {
    if (!geometry?.length) return undefined

    const fit = () => {
      map.invalidateSize({ pan: false })
      map.fitBounds(L.latLngBounds(geometry), { padding: [45, 45], maxZoom: 9 })
    }
    const frame = window.requestAnimationFrame(fit)
    const timer = window.setTimeout(fit, 350)
    const container = map.getContainer()
    const observer = new ResizeObserver(fit)
    observer.observe(container)

    return () => {
      window.cancelAnimationFrame(frame)
      window.clearTimeout(timer)
      observer.disconnect()
    }
  }, [geometry, map])
  return null
}

export default function RouteMap({ plan }) {
  const geometry = plan.route.geometry
  const notices = plan.route.notices || []
  return (
    <div className="map-wrap">
      <MapContainer center={geometry[0] || [39.5, -98.35]} zoom={5} zoomControl={false} scrollWheelZoom>
        <TileLayer attribution='&copy; OpenStreetMap contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
        <Polyline positions={geometry} pathOptions={{ color: '#173f35', weight: 8, opacity: 0.15 }} />
        <Polyline positions={geometry} pathOptions={{ color: '#f15a3a', weight: 4, opacity: 1 }} />
        {plan.waypoints.map((point) => (
          <Marker position={[point.lat, point.lon]} icon={markerIcon(null, point.role)} key={point.role}>
            <Popup><strong>{point.role === 'current' ? 'Start' : point.role}</strong><br />{point.label}</Popup>
          </Marker>
        ))}
        {plan.stops.filter((stop) => !['pickup', 'dropoff'].includes(stop.type)).map((stop, index) => (
          <Marker position={[stop.lat, stop.lon]} icon={markerIcon(stop.type)} key={`${stop.arrive}-${index}`}>
            <Popup><strong>{stop.title}</strong><br />{stop.label}<br /><small>{stop.minutes} minutes</small></Popup>
          </Marker>
        ))}
        <FitRoute geometry={geometry} />
      </MapContainer>
      {notices.length > 0 && <div className="route-notice"><strong>Truck route warning</strong>{notices.map((notice) => <span key={notice}>{notice}</span>)}</div>}
      <div className="map-legend"><span><i className="legend-route" /> Planned route</span><span><i className="legend-stop" /> HOS stop</span></div>
    </div>
  )
}