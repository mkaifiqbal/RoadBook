import { useEffect, useState } from 'react'
import { AlertCircle, BedDouble, CalendarDays, Check, ChevronDown, Clock3, Coffee, Download, Fuel, Gauge, Map, Route, ShieldCheck, Truck, X } from 'lucide-react'
import { getProfile, planTrip, setAccessToken } from './api'
import TripForm from './components/TripForm'
import RouteMap from './components/RouteMap'
import LogSheet from './components/LogSheet'
import AuthScreen from './components/AuthScreen'
import { AdminPanel, FleetAnalyticsPanel, ProfilePanel, TimeSpentPanel, TripsPanel, WorkspaceHeader } from './components/Workspace'

const DRIVER_SECTIONS = ['planner', 'trips', 'time', 'profile']
const ADMIN_SECTIONS = ['drivers', 'analytics', 'requests', 'add']

const defaultSection = (role) => role === 'admin' ? 'drivers' : 'planner'

const restoreSection = (role) => {
  const allowed = role === 'admin' ? ADMIN_SECTIONS : DRIVER_SECTIONS
  const hashed = window.location.hash.replace(/^#\/?/, '')
  if (allowed.includes(hashed)) return hashed
  const saved = localStorage.getItem(`roadbook_section_${role}`)
  return allowed.includes(saved) ? saved : defaultSection(role)
}

const persistSection = (role, section) => {
  localStorage.setItem(`roadbook_section_${role}`, section)
  window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}#${section}`)
}

const formatDuration = (hours) => {
  const whole = Math.floor(hours || 0)
  const minutes = Math.round(((hours || 0) - whole) * 60)
  return minutes ? `${whole}h ${minutes}m` : `${whole}h`
}

function LoadingOverlay() {
  return <div className="loading-overlay" role="status"><div className="loading-card"><div className="loading-road"><Truck size={24} /><span /></div><h2>Building a compliant route</h2><p>Geocoding stops, routing the truck, and checking every HOS window.</p><div className="loading-steps"><span><Check size={14} /> Validating dispatch</span><span className="active"><span className="mini-spinner" /> Simulating duty status</span><span>Drawing daily logs</span></div></div></div>
}

function EmptyState() {
  return <section className="empty-state"><div className="empty-map"><span className="map-line line-a" /><span className="map-line line-b" /><span className="map-line line-c" /><i className="empty-pin one" /><i className="empty-pin two" /><i className="empty-pin three" /></div><div><span className="eyebrow">Ready when you are</span><h2>Your route plan will appear here</h2><p>Enter the trip details to generate a map, compliant stop schedule, and daily driver logs.</p><div className="rule-pills"><span>11h drive limit</span><span>14h window</span><span>30m break</span><span>70h / 8 days</span></div></div></section>
}

function Summary({ plan }) {
  const s = plan.summary
  const cards = [
    { label: 'Route distance', value: `${Number(s.total_miles).toLocaleString()} mi`, sub: plan.route.estimated ? 'Estimated route' : 'Road mileage', icon: Route },
    { label: 'Drive time', value: formatDuration(s.driving_hours), sub: `${s.days} daily ${s.days === 1 ? 'log' : 'logs'}`, icon: Clock3 },
    { label: 'Required stops', value: plan.stops.length, sub: `${s.ten_hour_resets} rest · ${s.thirty_minute_breaks} breaks`, icon: Coffee },
    { label: 'Cycle remaining', value: `${s.cycle_remaining}h`, sub: `${s.cycle_used_at_end}h used at arrival`, icon: Gauge },
  ]
  return <div className="summary-grid">{cards.map(({ label, value, sub, icon: Icon }, index) => <article className="metric-card animate-in" style={{ animationDelay: `${index * 60}ms` }} key={label}><span className="metric-icon"><Icon size={18} /></span><div><span>{label}</span><strong>{value}</strong><small>{sub}</small></div></article>)}</div>
}

const eventIcon = { fuel: Fuel, break: Coffee, rest: BedDouble, restart: ShieldCheck, cycle_wait: ShieldCheck, pickup: Truck, dropoff: Truck }

function StopsTimeline({ stops }) {
  const formatTime = (value) => new Date(value).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
  return <div className="stops-list">{stops.map((stop, index) => { const Icon = eventIcon[stop.type] || Clock3; return <div className="stop-row" key={`${stop.arrive}-${index}`}><div className={`stop-node ${stop.type}`}><Icon size={15} /></div><div><strong>{stop.title || stop.type}</strong><span>{stop.label}</span></div><div className="stop-time"><strong>{formatTime(stop.arrive)}</strong><span>{stop.minutes >= 60 ? formatDuration(stop.minutes / 60) : `${stop.minutes} min`}</span></div></div> })}</div>
}

function PlanResults({ plan }) {
  const [tab, setTab] = useState('overview')
  const [showAssumptions, setShowAssumptions] = useState(false)
  return <div className="results animate-in">
    <div className="results-title"><div><span className="status-badge"><Check size={13} /> Compliant plan</span><h2>{plan.header.from_label} <span>to</span> {plan.header.to_label}</h2><p>Trip #{plan.trip_id || 'preview'} · Starts {new Date(plan.summary.start_time).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}</p></div><div className="provider-badge"><ShieldCheck size={15} /> FMCSA rules applied</div></div>
    {plan.route.estimated && <div className="route-estimate-banner"><AlertCircle size={17} /><div><strong>Road route unavailable</strong><span>This map is a straight-line estimate, not a drivable truck path. Check the locations and try again later. If the places are separated by water or inaccessible terrain, use a ferry or other permitted transport instead of dispatching the truck across it.</span></div></div>}
    <Summary plan={plan} />
    <div className="results-toolbar"><div className="tabs" role="tablist"><button className={tab === 'overview' ? 'active' : ''} onClick={() => setTab('overview')}><Map size={16} /> Route overview</button><button className={tab === 'logs' ? 'active' : ''} onClick={() => setTab('logs')}><CalendarDays size={16} /> Daily logs <span>{plan.logs.length}</span></button></div>{tab === 'logs' && <button type="button" className="print-all-button" onClick={() => window.print()}><Download size={16} /> Download all {plan.logs.length} sheets</button>}</div>
    {tab === 'overview' ? <div className="overview-grid"><section className="content-card map-card"><div className="section-heading"><div><span className="eyebrow">Live itinerary</span><h3>Route & required stops</h3></div><span>{plan.route.provider.replaceAll('-', ' ')}</span></div><RouteMap plan={plan} /></section><section className="content-card schedule-card"><div className="section-heading"><div><span className="eyebrow">HOS schedule</span><h3>Stops along the way</h3></div><span>{plan.stops.length} stops</span></div><StopsTimeline stops={plan.stops} /></section></div> : <div className="logs-stack">{plan.logs.map((log, index) => <LogSheet log={log} index={index} key={log.date} />)}</div>}
    <button className="assumptions-toggle" onClick={() => setShowAssumptions((value) => !value)}><span><AlertCircle size={16} /> Planning assumptions & compliance notes</span><ChevronDown size={17} className={showAssumptions ? 'rotate-down' : ''} /></button>
    {showAssumptions && <ul className="assumptions animate-in">{plan.assumptions.map((item) => <li key={item}>{item}</li>)}</ul>}
  </div>
}

export default function App() {
  const [user, setUser] = useState(null)
  const [booting, setBooting] = useState(() => Boolean(localStorage.getItem('roadbook_access')))
  const [section, setSection] = useState('planner')
  const [plan, setPlan] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!localStorage.getItem('roadbook_access')) return
    getProfile().then((profile) => { const restored = restoreSection(profile.role); setUser(profile); setSection(restored); persistSection(profile.role, restored) }).catch(() => setAccessToken('')).finally(() => setBooting(false))
  }, [])

  useEffect(() => {
    const handleHashChange = () => {
      if (!user) return
      const allowed = user.role === 'admin' ? ADMIN_SECTIONS : DRIVER_SECTIONS
      const nextSection = window.location.hash.replace(/^#\/?/, '')
      if (!allowed.includes(nextSection) || nextSection === section) return
      setSection(nextSection)
      localStorage.setItem(`roadbook_section_${user.role}`, nextSection)
      setPlan(null)
    }
    window.addEventListener('hashchange', handleHashChange)
    return () => window.removeEventListener('hashchange', handleHashChange)
  }, [section, user])

  function authenticated(data) {
    setAccessToken(data.access)
    setUser(data.user)
    const nextSection = defaultSection(data.user.role)
    persistSection(data.user.role, nextSection)
    setSection(nextSection)
  }

  function logout() {
    setAccessToken(''); setUser(null); setPlan(null); setError('')
  }

  async function handlePlan(payload) {
    setLoading(true); setError('')
    try {
      const nextPlan = await planTrip(payload)
      setPlan(nextPlan)
      // Refresh backend-derived hour categories; a newly saved route may be
      // scheduled or completed depending on its planned end time.
      getProfile().then(setUser).catch(() => {})
      setTimeout(() => document.getElementById('results')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100)
    }
    catch (err) { setError(err.message) }
    finally { setLoading(false) }
  }

  if (booting) return <div className="boot-screen"><span className="brand-mark"><Route size={22} /></span><span className="mini-spinner" /></div>
  if (!user) return <AuthScreen onAuthenticated={authenticated} />

  const navigate = (nextSection) => {
    const allowed = user.role === 'admin' ? ADMIN_SECTIONS : DRIVER_SECTIONS
    if (allowed.includes(nextSection)) persistSection(user.role, nextSection)
    if (user.role === 'admin' && nextSection !== 'drivers') localStorage.removeItem('roadbook_admin_driver')
    setSection(nextSection)
    setPlan(null)
  }
  const openSavedPlan = (savedPlan) => { setPlan(savedPlan); setSection('planview'); window.scrollTo({ top: 0, behavior: 'smooth' }) }
  return <div id="top" className="app-shell workspace-shell">
    <WorkspaceHeader user={user} section={section} setSection={navigate} onLogout={logout} />
    <main className={section === 'planner' ? '' : 'workspace-main'}>
      {user.role === 'admin' ? (
        section === 'planview' ? <div><button className="back-button workspace-back" onClick={() => navigate('drivers')}>← Back to driver records</button><div className="result-area"><PlanResults plan={plan} /></div></div> : section === 'analytics' ? <FleetAnalyticsPanel /> : <AdminPanel key={section} section={section} onOpenPlan={openSavedPlan} />
      ) : section === 'planner' ? <>
        <section className="hero driver-hero"><div className="hero-copy"><span className="hero-kicker"><span /> Welcome back, {user.name.split(' ')[0]}</span><h2>Every mile planned.<br /><em>Every hour accounted for.</em></h2><p>Build a practical route and generate FMCSA-ready daily logs before the wheels start turning.</p><div className="trust-row"><span><ShieldCheck size={16} /> Property-carrying HOS</span><span><Clock3 size={16} /> Minute-accurate</span></div></div><TripForm onSubmit={handlePlan} loading={loading} user={user} /></section>
        {error && <div className="error-banner"><AlertCircle size={19} /><div><strong>We couldn&apos;t build that trip</strong><span>{error}</span></div><button onClick={() => setError('')}><X size={17} /></button></div>}
        <div id="results" className="result-area">{plan ? <PlanResults plan={plan} /> : <EmptyState />}</div>
        <section className="compliance-strip"><div><span className="compliance-seal"><ShieldCheck size={24} /></span><div><span className="eyebrow">Built around Part 395</span><h3>Compliance isn&apos;t an afterthought.</h3></div></div><p>Every plan considers the 11-hour driving limit, 14-hour duty window, 30-minute break, required rest, fuel cadence, and your 70-hour cycle.</p></section>
      </> : section === 'trips' ? <TripsPanel onOpen={openSavedPlan} /> : section === 'time' ? <TimeSpentPanel user={user} /> : section === 'profile' ? <ProfilePanel user={user} onUpdated={setUser} /> : <div><button className="back-button workspace-back" onClick={() => navigate('trips')}>← Back to my trips</button><div className="result-area"><PlanResults plan={plan} /></div></div>}
    </main>
    {loading && <LoadingOverlay />}
  </div>
}