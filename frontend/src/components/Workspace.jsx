import { useEffect, useState } from 'react'
import { Activity, BarChart3, CalendarClock, CalendarDays, Check, ChevronLeft, ChevronRight, CircleCheckBig, Clock3, Gauge, LogOut, MapPinned, Menu, Plus, Route, Search, ShieldCheck, TimerReset, Trash2, Truck, User, UserCheck, UserX, Users, X } from 'lucide-react'
import { addDriver, deleteTrip, getDrivers, getTrip, getTrips, setDriverStatus, updateProfile } from '../api'
import DatePicker from './DatePicker'

const fmtDate = (value) => {
  if (!value) return 'Not available'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'Not available' : date.toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' })
}
const fmtHours = (value) => {
  const hours = Number(value || 0)
  const whole = Math.floor(hours)
  const minutes = Math.round((hours - whole) * 60)
  return minutes ? `${whole}h ${minutes}m` : `${whole}h`
}

export function WorkspaceHeader({ user, section, setSection, onLogout }) {
  const [menuOpen, setMenuOpen] = useState(false)
  const driverNav = [['planner', 'Trip planner', MapPinned], ['trips', 'My trips', CalendarDays], ['time', 'Time spent', BarChart3], ['profile', 'Profile', User]]
  const adminNav = [['drivers', 'Drivers', Users], ['analytics', 'Analytics', BarChart3], ['requests', 'Requests', UserCheck], ['add', 'Add driver', Plus]]
  const nav = user.role === 'admin' ? adminNav : driverNav
  function navigate(id) { setSection(id); setMenuOpen(false) }
  return <header className={`workspace-header ${menuOpen ? 'menu-open' : ''}`}><a className="brand" href="#"><span className="brand-mark"><Truck size={20} /></span><span>ROADBOOK<small>{user.role === 'admin' ? 'FLEET ADMIN' : 'DRIVER PORTAL'}</small></span></a><button className="workspace-menu-toggle" type="button" onClick={() => setMenuOpen((open) => !open)} aria-expanded={menuOpen} aria-controls="workspace-navigation" aria-label={menuOpen ? 'Close navigation menu' : 'Open navigation menu'}>{menuOpen ? <X size={21} /> : <Menu size={22} />}<span>Menu</span></button><nav id="workspace-navigation" aria-label={`${user.role} navigation`}>{nav.map(([id, label, Icon]) => <button className={section === id ? 'active' : ''} onClick={() => navigate(id)} key={id}><Icon size={16} />{label}</button>)}</nav><div className="account-menu"><span className="avatar">{user.name.slice(0, 1)}</span><div><strong>{user.name}</strong><small>{user.role}</small></div><button onClick={onLogout} title="Sign out"><LogOut size={17} /></button></div></header>
}

export function TripsPanel({ onOpen, driverId }) {
  const [trips, setTrips] = useState([]); const [loading, setLoading] = useState(true); const [deleting, setDeleting] = useState(null); const [error, setError] = useState('')
  const [query, setQuery] = useState(''); const [sortOrder, setSortOrder] = useState('newest'); const [page, setPage] = useState(1)
  useEffect(() => { getTrips(driverId).then(setTrips).finally(() => setLoading(false)) }, [driverId])
  async function remove(trip) {
    if (!window.confirm(`Delete the upcoming trip to ${trip.dropoff_location}? This cannot be undone.`)) return
    setDeleting(trip.id); setError('')
    try { await deleteTrip(trip.id); setTrips((items) => items.filter((item) => item.id !== trip.id)) }
    catch (err) { setError(err.message) }
    finally { setDeleting(null) }
  }
  async function open(trip) { onOpen((await getTrip(trip.id)).plan) }
  const searchTerm = query.trim().toLowerCase()
  const filteredTrips = trips.filter((trip) => !searchTerm || [trip.id, trip.current_location, trip.pickup_location, trip.dropoff_location, trip.status, fmtDate(trip.start_time), fmtDate(trip.end_time)].some((value) => String(value || '').toLowerCase().includes(searchTerm)))
  const sortedTrips = [...filteredTrips].sort((a, b) => {
    const aTime = new Date(a.start_time).getTime() || 0
    const bTime = new Date(b.start_time).getTime() || 0
    return sortOrder === 'newest' ? bTime - aTime : aTime - bTime
  })
  const pageSize = 10
  const totalPages = Math.max(1, Math.ceil(sortedTrips.length / pageSize))
  const currentPage = Math.min(page, totalPages)
  const visibleTrips = sortedTrips.slice((currentPage - 1) * pageSize, currentPage * pageSize)
  const firstResult = sortedTrips.length ? (currentPage - 1) * pageSize + 1 : 0
  const lastResult = Math.min(currentPage * pageSize, sortedTrips.length)
  function changeQuery(value) { setQuery(value); setPage(1) }
  function changeSort(value) { setSortOrder(value); setPage(1) }
  return <section className="dashboard-section trips-section"><div className="dashboard-title trips-title"><div><span className="eyebrow">Route archive</span><h1>{driverId ? 'Driver trip history' : 'My trips'}</h1><p>Review upcoming assignments and reopen completed route plans with their original log sheets.</p></div><div className="trip-title-tools"><label className="trip-search"><Search size={16} /><input type="search" value={query} onChange={(event) => changeQuery(event.target.value)} placeholder="Search route, date or trip #" aria-label="Search trips" />{query && <button type="button" onClick={() => changeQuery('')} aria-label="Clear trip search"><X size={14} /></button>}</label><label className="trip-sort"><span>Sort by date</span><select value={sortOrder} onChange={(event) => changeSort(event.target.value)} aria-label="Sort trips by date"><option value="newest">Newest first</option><option value="oldest">Oldest first</option></select></label><span className="count-pill">{filteredTrips.length} {filteredTrips.length === 1 ? 'trip' : 'trips'}</span></div></div>
    {error && <div className="trip-error">{error}</div>}
    <div className="trip-collection">{loading ? <div className="data-card panel-empty">Loading trips…</div> : !trips.length ? <div className="data-card panel-empty"><CalendarDays size={28} /><strong>No saved trips yet</strong><span>Planned runs will appear here automatically.</span></div> : !visibleTrips.length ? <div className="data-card panel-empty"><Search size={28} /><strong>No matching trips</strong><span>Try a city, status, date, or trip number.</span><button className="clear-search-button" type="button" onClick={() => changeQuery('')}>Clear search</button></div> : visibleTrips.map((trip) => <article className={`trip-card ${trip.status}`} key={trip.id}><div className="trip-card-accent" /><div className="trip-card-main"><div className="trip-card-top"><span className="trip-route-icon"><Route size={20} /></span><span className={`trip-status ${trip.status}`}>{trip.status === 'completed' ? <CircleCheckBig size={13} /> : <CalendarClock size={13} />}{trip.status === 'in_progress' ? 'In progress' : trip.status}</span><span className="trip-number">TRIP #{String(trip.id).padStart(3, '0')}</span></div><div className="trip-route"><div><span className="route-dot pickup" /><small>Pickup</small><strong>{trip.pickup_location}</strong></div><span className="route-connector"><span /><ChevronRight size={16} /><span /></span><div><span className="route-dot destination" /><small>Destination</small><strong>{trip.dropoff_location}</strong></div></div><div className="trip-timeline"><CalendarDays size={14} /><span><small>Starts</small><strong>{fmtDate(trip.start_time)}</strong></span><ChevronRight size={13} /><span><small>{trip.status === 'completed' ? 'Finished' : 'Estimated finish'}</small><strong>{fmtDate(trip.end_time)}</strong></span></div></div><div className="trip-metrics"><div><small>Distance</small><strong>{Number(trip.total_miles).toLocaleString()}<span> mi</span></strong></div><div><small>Duration</small><strong>{trip.total_days}<span> {trip.total_days === 1 ? 'day' : 'days'}</span></strong></div><div><small>Drive</small><strong>{fmtHours(trip.driving_hours)}</strong></div><div><small>On duty</small><strong>{fmtHours(trip.on_duty_hours)}</strong></div></div><div className="trip-card-actions"><button className="open-trip-button" onClick={() => open(trip)}><MapPinned size={15} /> Open route plan <ChevronRight size={15} /></button><button className="delete-trip-button" disabled={!trip.can_delete || deleting === trip.id} title={trip.delete_restriction || 'Delete this trip'} onClick={() => remove(trip)}><Trash2 size={14} /> {deleting === trip.id ? 'Deleting…' : trip.can_delete ? 'Delete upcoming trip' : 'Delete unavailable'}</button></div></article>)}</div>
    {!loading && sortedTrips.length > 0 && <nav className="trip-pagination" aria-label="Trip archive pages"><span>Showing <strong>{firstResult}–{lastResult}</strong> of <strong>{sortedTrips.length}</strong></span><div><button type="button" onClick={() => setPage((value) => Math.max(1, value - 1))} disabled={currentPage === 1} aria-label="Previous trips page"><ChevronLeft size={15} /> Previous</button><span>Page <strong>{currentPage}</strong> of {totalPages}</span><button type="button" onClick={() => setPage((value) => Math.min(totalPages, value + 1))} disabled={currentPage === totalPages} aria-label="Next trips page">Next <ChevronRight size={15} /></button></div></nav>}
  </section>
}

export function ProfilePanel({ user, onUpdated }) {
  const [form, setForm] = useState({ truck_number: user.truck_number || '', carrier_name: user.carrier_name || '' }); const [saved, setSaved] = useState(false)
  async function submit(event) { event.preventDefault(); onUpdated(await updateProfile(form)); setSaved(true); setTimeout(() => setSaved(false), 2200) }
  return <section className="dashboard-section narrow-section"><div className="dashboard-title"><div><span className="eyebrow">Driver account</span><h1>Profile settings</h1><p>Manage your account identity and the dispatch details used when you create a trip.</p></div></div><form className="data-card profile-card" onSubmit={submit}><div className="profile-identity"><span className="large-avatar">{user.name.slice(0,1).toUpperCase()}</span><div className="profile-person"><strong>{user.name}</strong><span>{user.email}</span></div><div className="account-status"><span className="status-indicator" /><span><small>Account status</small><strong>Active</strong></span></div></div><div className="profile-form-heading"><span className="profile-form-icon"><Truck size={18} /></span><div><h2>Dispatch details</h2><p>These values are filled into new trip plans automatically. You can change them for any individual trip.</p></div></div><label className="auth-field"><span>Preferred truck number</span><div><Truck size={17} /><input value={form.truck_number} onChange={(e) => setForm({...form, truck_number:e.target.value})} placeholder="TRK-204" /></div></label><label className="auth-field"><span>Carrier name</span><div><ShieldCheck size={17} /><input value={form.carrier_name} onChange={(e) => setForm({...form, carrier_name:e.target.value})} placeholder="Northline Freight" /></div></label><button className="primary-button">{saved ? <><Check size={17} /> Profile saved</> : 'Save profile'}</button></form></section>
}

export function TimeSpentPanel() {
  const [trips, setTrips] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [range, setRange] = useState('month')
  const [customStart, setCustomStart] = useState('')
  const [customEnd, setCustomEnd] = useState('')

  useEffect(() => { getTrips().then(setTrips).catch((err) => setError(err.message)).finally(() => setLoading(false)) }, [])

  const today = new Date()
  const monthStart = new Date(today.getFullYear(), today.getMonth(), 1)
  const nextMonthStart = new Date(today.getFullYear(), today.getMonth() + 1, 1)
  const filteredTrips = trips.filter((trip) => {
    const date = new Date(trip.start_time)
    if (Number.isNaN(date.getTime())) return false
    if (range === 'all') return true
    if (range === 'custom') {
      const start = customStart ? new Date(`${customStart}T00:00:00`) : null
      const end = customEnd ? new Date(`${customEnd}T23:59:59`) : null
      return (!start || date >= start) && (!end || date <= end)
    }
    return date >= monthStart && date < nextMonthStart
  })
  const elapsedTrips = filteredTrips.filter((trip) => trip.status !== 'upcoming')
  const byDate = Object.values(filteredTrips.reduce((days, trip) => {
    const date = new Date(trip.start_time)
    if (Number.isNaN(date.getTime())) return days
    const key = date.toISOString().slice(0, 10)
    if (!days[key]) days[key] = { key, date, elapsedDriving: 0, upcomingDriving: 0, plannedDuty: 0, trips: 0 }
    const driving = Number(trip.driving_hours || 0)
    if (trip.status === 'upcoming') days[key].upcomingDriving += driving
    else days[key].elapsedDriving += driving
    days[key].plannedDuty += Math.max(Number(trip.on_duty_hours || 0), driving)
    days[key].trips += 1
    return days
  }, {})).sort((a, b) => a.date - b.date)
  const peakHours = Math.max(1, ...byDate.flatMap((day) => [day.elapsedDriving, day.upcomingDriving, day.plannedDuty]))
  const chartMax = Math.max(5, Math.ceil(peakHours / 5) * 5)
  const yTicks = [chartMax, chartMax * .75, chartMax * .5, chartMax * .25, 0]
  const completed = filteredTrips.filter((trip) => trip.status === 'completed').length
  const active = filteredTrips.filter((trip) => trip.status === 'in_progress').length
  const upcoming = filteredTrips.filter((trip) => trip.status === 'upcoming').length
  const elapsedDriving = elapsedTrips.reduce((sum, trip) => sum + Number(trip.driving_hours || 0), 0)
  const elapsedDuty = elapsedTrips.reduce((sum, trip) => sum + Math.max(Number(trip.on_duty_hours || 0), Number(trip.driving_hours || 0)), 0)
  const upcomingDriving = filteredTrips.filter((trip) => trip.status === 'upcoming').reduce((sum, trip) => sum + Number(trip.driving_hours || 0), 0)
  const utilization = elapsedDuty ? Math.round((elapsedDriving / elapsedDuty) * 100) : 0
  const chartTotal = Math.max(filteredTrips.length, 1)
  const completedEnd = `${(completed / chartTotal) * 100}%`
  const activeEnd = `${((completed + active) / chartTotal) * 100}%`

  if (loading) return <section className="dashboard-section analytics-section"><div className="dashboard-title"><div><span className="eyebrow">Driver analytics</span><h1>Time spent</h1></div></div><div className="analytics-loading"><span /><span /><span /></div></section>
  return <section className="dashboard-section analytics-section"><div className="dashboard-title"><div><span className="eyebrow">Driver analytics</span><h1>Time spent</h1><p>Understand your elapsed driving and on-duty workload, organized by trip start date.</p></div><div className={`analytics-period ${range === 'custom' ? 'show-custom' : ''}`}><div className="period-presets" role="group" aria-label="Analytics date range"><button type="button" className={range === 'month' ? 'active' : ''} onClick={() => setRange('month')}>This month</button><button type="button" className={range === 'all' ? 'active' : ''} onClick={() => setRange('all')}>All time</button><button type="button" className={range === 'custom' ? 'active' : ''} onClick={() => setRange('custom')}><CalendarDays size={13} /> Custom</button></div>{range === 'custom' && <div className="custom-range"><DatePicker label="Start" value={customStart} onChange={setCustomStart} placeholder="From date" max={customEnd || undefined} /><span className="range-arrow">→</span><DatePicker label="End" value={customEnd} onChange={setCustomEnd} placeholder="To date" min={customStart || undefined} /></div>}</div></div>
    {error && <div className="trip-error">{error}</div>}
    <div className="time-kpis"><article><span className="time-kpi-icon driving"><Truck size={18} /></span><div><small>Elapsed driving</small><strong>{fmtHours(elapsedDriving)}</strong><span>Completed and active trips</span></div></article><article><span className="time-kpi-icon duty"><Clock3 size={18} /></span><div><small>Elapsed on duty</small><strong>{fmtHours(elapsedDuty)}</strong><span>Driving plus other duty</span></div></article><article><span className="time-kpi-icon utilization"><Activity size={18} /></span><div><small>Driving utilization</small><strong>{utilization}%</strong><span>Share of duty time driving</span></div></article><article><span className="time-kpi-icon scheduled"><TimerReset size={18} /></span><div><small>Upcoming driving</small><strong>{fmtHours(upcomingDriving)}</strong><span>{upcoming} upcoming {upcoming === 1 ? 'trip' : 'trips'}</span></div></article></div>
    <div className="analytics-grid"><article className="analytics-card time-chart-card"><div className="analytics-card-heading"><div><span className="eyebrow">Daily breakdown</span><h2>Travel & duty by date</h2></div></div>{byDate.length ? <><div className="histogram-scroll"><div className="histogram" role="img" aria-label="Grouped histogram of travel, upcoming travel, and planned on-duty hours by trip date"><div className="histogram-y-title">Hours</div><div className="histogram-y-axis">{yTicks.map((tick) => <span key={tick} style={{ bottom: `${(tick / chartMax) * 100}%` }}>{Number.isInteger(tick) ? tick : tick.toFixed(1)}</span>)}</div><div className="histogram-plot">{yTicks.map((tick) => <i className="histogram-gridline" key={tick} style={{ bottom: `${(tick / chartMax) * 100}%` }} />)}<div className="histogram-groups">{byDate.map((day) => <div className="histogram-group" key={day.key}><div className="histogram-bars">{[['travel', day.elapsedDriving, 'Travel'], ['upcoming', day.upcomingDriving, 'Upcoming'], ['duty', day.plannedDuty, 'Planned duty']].map(([tone, value, label]) => <div className={`histogram-bar ${tone} ${value ? '' : 'zero'}`} key={tone} style={{ '--bar-height': `${(value / chartMax) * 100}%` }} data-tooltip={`${label}: ${fmtHours(value)}`}><span>{value ? fmtHours(value) : ''}</span></div>)}</div><div className="histogram-date"><strong>{day.date.toLocaleDateString([], { month: 'short', day: 'numeric' })}</strong><small>{day.trips} {day.trips === 1 ? 'trip' : 'trips'}</small></div></div>)}</div></div></div></div><div className="chart-legend chart-legend-bottom"><span><i className="drive" /> Travel</span><span><i className="upcoming" /> Upcoming</span><span><i className="duty" /> Planned duty</span></div></> : <div className="analytics-empty"><BarChart3 size={30} /><strong>No trip time planned yet</strong><span>Saved trips will build your date-wise travel and duty histogram.</span></div>}</article>
      <aside className="analytics-card status-chart-card"><div className="analytics-card-heading"><div><span className="eyebrow">Trip mix</span><h2>Plan status</h2></div></div><div className="status-donut" style={{ '--completed-end': completedEnd, '--active-end': activeEnd }}><div><strong>{filteredTrips.length}</strong><span>trips in range</span></div></div><div className="status-breakdown"><div><i className="completed" /><span>Completed</span><strong>{completed}</strong></div><div><i className="active" /><span>In progress</span><strong>{active}</strong></div><div><i className="upcoming" /><span>Upcoming</span><strong>{upcoming}</strong></div></div><p className="analytics-note"><ShieldCheck size={15} /> Time is derived from your generated HOS plans. Upcoming hours stay separate until their trip begins.</p></aside></div>
  </section>
}

export function FleetAnalyticsPanel() {
  const [drivers, setDrivers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => { getDrivers().then(setDrivers).catch((err) => setError(err.message)).finally(() => setLoading(false)) }, [])

  const activeDrivers = drivers.filter((driver) => driver.status === 'active').length
  const tripCount = drivers.reduce((sum, driver) => sum + Number(driver.trip_count || 0), 0)
  const completedHours = drivers.reduce((sum, driver) => sum + Number(driver.completed_driving_hours || 0), 0)
  const upcomingHours = drivers.reduce((sum, driver) => sum + Number(driver.scheduled_driving_hours || 0), 0)
  const totalDriving = drivers.reduce((sum, driver) => sum + Number(driver.total_driving_hours || 0), 0)
  const totalDuty = drivers.reduce((sum, driver) => sum + Number(driver.total_on_duty_hours || 0), 0)
  const averageTrip = tripCount ? totalDriving / tripCount : 0
  const averageDriver = activeDrivers ? totalDriving / activeDrivers : 0
  const utilization = totalDuty ? Math.round((totalDriving / totalDuty) * 100) : 0
  const workloadTotal = Math.max(completedHours + upcomingHours, 1)
  const completedShare = (completedHours / workloadTotal) * 100
  const rankedDrivers = [...drivers].sort((a, b) => Number(b.total_driving_hours || 0) - Number(a.total_driving_hours || 0))
  const maxDriverHours = Math.max(1, ...rankedDrivers.map((driver) => Math.max(Number(driver.total_on_duty_hours || 0), Number(driver.total_driving_hours || 0))))

  if (loading) return <section className="dashboard-section fleet-analytics"><div className="dashboard-title"><div><span className="eyebrow">Fleet intelligence</span><h1>Operations analytics</h1></div></div><div className="analytics-loading"><span /><span /><span /></div></section>
  return <section className="dashboard-section fleet-analytics"><div className="dashboard-title"><div><span className="eyebrow">Fleet intelligence</span><h1>Operations analytics</h1><p>Compare completed work, scheduled workload, duty utilization, and average driving across the fleet.</p></div><span className="count-pill">{drivers.length} enrolled drivers</span></div>
    {error && <div className="trip-error">{error}</div>}
    <div className="fleet-kpis"><article><span className="fleet-kpi-icon completed"><Clock3 size={18} /></span><div><small>Hours driven</small><strong>{fmtHours(completedHours)}</strong><span>Elapsed fleet driving</span></div></article><article><span className="fleet-kpi-icon upcoming"><CalendarClock size={18} /></span><div><small>Upcoming hours</small><strong>{fmtHours(upcomingHours)}</strong><span>Scheduled driving</span></div></article><article><span className="fleet-kpi-icon average"><Activity size={18} /></span><div><small>Average per trip</small><strong>{fmtHours(averageTrip)}</strong><span>{tripCount} total trips</span></div></article><article><span className="fleet-kpi-icon utilization"><Gauge size={18} /></span><div><small>Driving utilization</small><strong>{utilization}%</strong><span>{fmtHours(totalDuty)} total duty</span></div></article></div>
    <div className="fleet-analytics-grid"><article className="fleet-analytics-card fleet-workload-card"><div className="fleet-card-heading"><div><span className="eyebrow">Workload horizon</span><h2>Completed vs upcoming</h2></div><strong>{fmtHours(totalDriving)}</strong></div><div className="fleet-workload-bar" aria-label={`${fmtHours(completedHours)} completed and ${fmtHours(upcomingHours)} upcoming`}><span className="completed" style={{ width: `${completedShare}%` }} /><span className="upcoming" style={{ width: `${100 - completedShare}%` }} /></div><div className="fleet-workload-legend"><div><i className="completed" /><span>Hours already driven</span><strong>{fmtHours(completedHours)}</strong><small>{Math.round(completedShare)}% of planned driving</small></div><div><i className="upcoming" /><span>Upcoming driving</span><strong>{fmtHours(upcomingHours)}</strong><small>{Math.round(100 - completedShare)}% still scheduled</small></div></div><div className="fleet-insight-row"><div><small>Active drivers</small><strong>{activeDrivers} / {drivers.length}</strong></div><div><small>Average per active driver</small><strong>{fmtHours(averageDriver)}</strong></div><div><small>Non-driving duty</small><strong>{fmtHours(Math.max(totalDuty - totalDriving, 0))}</strong></div></div></article>
      <aside className="fleet-analytics-card fleet-utilization-card"><div className="fleet-card-heading"><div><span className="eyebrow">Duty efficiency</span><h2>Fleet utilization</h2></div></div><div className="fleet-utilization-ring" style={{ '--utilization': `${Math.min(utilization, 100) * 3.6}deg` }}><div><strong>{utilization}%</strong><span>of duty spent driving</span></div></div><div className="fleet-utilization-stats"><div><span>Driving</span><strong>{fmtHours(totalDriving)}</strong></div><div><span>Other duty</span><strong>{fmtHours(Math.max(totalDuty - totalDriving, 0))}</strong></div></div></aside></div>
    <article className="fleet-analytics-card driver-comparison-card"><div className="fleet-card-heading"><div><span className="eyebrow">Driver comparison</span><h2>Hours by driver</h2></div><div className="driver-chart-legend"><span><i className="completed" /> Driven</span><span><i className="upcoming" /> Upcoming</span><span><i className="duty" /> Total duty</span></div></div>{rankedDrivers.length ? <div className="driver-comparison-list">{rankedDrivers.map((driver) => { const completed = Number(driver.completed_driving_hours || 0); const upcoming = Number(driver.scheduled_driving_hours || 0); const duty = Number(driver.total_on_duty_hours || 0); return <div className="driver-comparison-row" key={driver.id}><div className="driver-chart-name"><span className="avatar">{driver.name.slice(0, 1)}</span><div><strong>{driver.name}</strong><small>{driver.trip_count} {driver.trip_count === 1 ? 'trip' : 'trips'} · {driver.status}</small></div></div><div className="driver-bars"><div className="driver-duty-track"><span style={{ width: `${(duty / maxDriverHours) * 100}%` }} /></div><div className="driver-driving-track"><span className="completed" style={{ width: `${(completed / maxDriverHours) * 100}%` }} /><span className="upcoming" style={{ width: `${(upcoming / maxDriverHours) * 100}%` }} /></div></div><strong className="driver-chart-total">{fmtHours(completed + upcoming)}<small>{fmtHours(duty)} duty</small></strong></div>})}</div> : <div className="analytics-empty"><BarChart3 size={30} /><strong>No fleet data yet</strong><span>Driver workload will appear after trips are planned.</span></div>}</article>
  </section>
}

export function AdminPanel({ section, onOpenPlan }) {
  const [drivers, setDrivers] = useState([]); const [selected, setSelected] = useState(() => { const id = Number(localStorage.getItem('roadbook_admin_driver')); return id ? { id } : null }); const [notice, setNotice] = useState('')
  const [query, setQuery] = useState(''); const [page, setPage] = useState(1)
  useEffect(() => { if (section !== 'add') { getDrivers(section === 'requests' ? 'pending' : '').then(setDrivers) } }, [section])
  async function change(id, status) { await setDriverStatus(id, status); setNotice(`Driver status changed to ${status}.`); getDrivers(section === 'requests' ? 'pending' : '').then(setDrivers) }
  if (section === 'drivers' && selected) return <div><button className="back-button" onClick={() => { setSelected(null); localStorage.removeItem('roadbook_admin_driver') }}>← Back to drivers</button><TripsPanel driverId={selected.id} onOpen={onOpenPlan} /></div>
  if (section === 'add') return <AddDriver onAdded={(user) => setNotice(`${user.name} is active and can sign in.`)} notice={notice} />
  const searchTerm = query.trim().toLowerCase()
  const filteredDrivers = section === 'drivers' ? drivers.filter((driver) => !searchTerm || [driver.name, driver.email, driver.truck_number, driver.carrier_name, driver.status].some((value) => String(value || '').toLowerCase().includes(searchTerm))) : drivers
  const pageSize = 10
  const totalPages = Math.max(1, Math.ceil(filteredDrivers.length / pageSize))
  const currentPage = Math.min(page, totalPages)
  const visibleDrivers = filteredDrivers.slice((currentPage - 1) * pageSize, currentPage * pageSize)
  const firstResult = filteredDrivers.length ? (currentPage - 1) * pageSize + 1 : 0
  const lastResult = Math.min(currentPage * pageSize, filteredDrivers.length)
  function searchDrivers(value) { setQuery(value); setPage(1) }
  return <section className="dashboard-section"><div className="dashboard-title admin-directory-title"><div><span className="eyebrow">{section === 'requests' ? 'Access control' : 'Fleet directory'}</span><h1>{section === 'requests' ? 'Pending requests' : 'All drivers'}</h1><p>{section === 'requests' ? 'Review self-service account requests before granting access.' : 'Manage account access and inspect each driver’s trip records.'}</p></div>{section === 'drivers' ? <div className="driver-directory-tools"><label className="trip-search driver-search"><Search size={16} /><input type="search" value={query} onChange={(event) => searchDrivers(event.target.value)} placeholder="Search drivers…" aria-label="Search drivers by name, email, truck, carrier, or status" />{query && <button type="button" onClick={() => searchDrivers('')} aria-label="Clear driver search"><X size={14} /></button>}</label><span className="count-pill">{filteredDrivers.length} {filteredDrivers.length === 1 ? 'driver' : 'drivers'}</span></div> : <span className="count-pill">{drivers.length} drivers</span>}</div>{notice && <div className="inline-notice">{notice}</div>}<div className="data-card"><div className="table-head"><span>Driver</span><span>Equipment</span><span>{section === 'requests' ? 'Requested' : 'Trips / hours'}</span><span>Actions</span></div>{!drivers.length ? <div className="panel-empty"><UserCheck size={28} /><strong>{section === 'requests' ? 'Approval queue is clear' : 'No drivers found'}</strong></div> : !visibleDrivers.length ? <div className="panel-empty"><Search size={28} /><strong>No matching drivers</strong><span>Try a name, email, truck number, carrier, or status.</span><button className="clear-search-button" type="button" onClick={() => searchDrivers('')}>Clear search</button></div> : visibleDrivers.map((driver) => <div className="driver-row" key={driver.id}><div><span className="avatar">{driver.name.slice(0,1)}</span><span><strong>{driver.name}</strong><small>{driver.email}</small></span></div><span><strong>{driver.truck_number || 'Not assigned'}</strong><small>{driver.carrier_name || 'No carrier'}</small></span><span><strong>{section === 'requests' ? fmtDate(driver.requested_at) : `${driver.trip_count} trips · ${driver.total_driving_hours}h drive`}</strong><small className={`status-text ${driver.status}`}>{section === 'requests' ? driver.status : `${driver.total_on_duty_hours}h total duty · ${driver.status}`}</small></span><div className="row-actions">{section === 'requests' ? <><button className="approve" onClick={() => change(driver.id,'active')}><UserCheck size={15} /> Approve</button><button className="reject" onClick={() => change(driver.id,'rejected')}><UserX size={15} /> Reject</button></> : <><button onClick={() => { setSelected(driver); localStorage.setItem('roadbook_admin_driver', driver.id) }}>View trips</button><button onClick={() => change(driver.id, driver.status === 'suspended' ? 'active' : 'suspended')}>{driver.status === 'suspended' ? 'Reactivate' : 'Suspend'}</button></>}</div></div>)}</div>{section === 'drivers' && filteredDrivers.length > 0 && <nav className="trip-pagination driver-pagination" aria-label="Driver directory pages"><span>Showing <strong>{firstResult}–{lastResult}</strong> of <strong>{filteredDrivers.length}</strong></span><div><button type="button" onClick={() => setPage((value) => Math.max(1, value - 1))} disabled={currentPage === 1}><ChevronLeft size={15} /> Previous</button><span>Page <strong>{currentPage}</strong> of {totalPages}</span><button type="button" onClick={() => setPage((value) => Math.min(totalPages, value + 1))} disabled={currentPage === totalPages}>Next <ChevronRight size={15} /></button></div></nav>}</section>
}

function AddDriver({ onAdded, notice }) {
  const [form,setForm] = useState({name:'',email:'',password:'',truck_number:'',carrier_name:''}); const [error,setError]=useState(''); const [busy,setBusy]=useState(false)
  async function submit(e){e.preventDefault();setBusy(true);setError('');try{const user=await addDriver(form);onAdded(user);setForm({name:'',email:'',password:'',truck_number:'',carrier_name:''})}catch(err){setError(err.message)}finally{setBusy(false)}}
  return <section className="dashboard-section narrow-section"><div className="dashboard-title"><div><span className="eyebrow">Direct onboarding</span><h1>Add an active driver</h1><p>Admin-created accounts skip the approval queue and can sign in immediately.</p></div></div>{notice&&<div className="inline-notice">{notice}</div>}<form className="data-card add-driver-card" onSubmit={submit}>{[['name','Full name','Jordan Ellis'],['email','Email address','driver@northline.com'],['password','Temporary password','At least 8 characters'],['truck_number','Default truck','TRK-204'],['carrier_name','Carrier name','Northline Freight']].map(([name,label,placeholder])=><label className="auth-field" key={name}><span>{label}</span><div><input type={name==='password'?'password':name==='email'?'email':'text'} name={name} value={form[name]} onChange={(e)=>setForm({...form,[name]:e.target.value})} required={!['truck_number','carrier_name'].includes(name)} minLength={name==='password'?8:undefined} placeholder={placeholder}/></div></label>)}{error&&<div className="auth-error">{error}</div>}<button className="primary-button" disabled={busy}><Plus size={17}/>{busy?'Creating account…':'Create active driver'}</button></form></section>
}