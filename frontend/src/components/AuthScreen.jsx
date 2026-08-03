import { useState } from 'react'
import { ArrowRight, CheckCircle2, KeyRound, LockKeyhole, Mail, Route, ShieldCheck, Truck, User } from 'lucide-react'
import { login, signup } from '../api'

const demoAccounts = [
  { role: 'Administrator', email: 'admin@roadbook.demo', password: 'RoadbookAdmin!2026', icon: ShieldCheck },
  { role: 'Driver', email: 'driver@roadbook.demo', password: 'RoadbookDriver!2026', icon: Truck },
]

export default function AuthScreen({ onAuthenticated }) {
  const [mode, setMode] = useState('login')
  const [form, setForm] = useState({ name: '', email: '', password: '', truck_number: '' })
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const update = (event) => setForm((value) => ({ ...value, [event.target.name]: event.target.value }))

  function fillDemoCredentials(account) {
    setMode('login')
    setMessage('')
    setError('')
    setForm((value) => ({ ...value, email: account.email, password: account.password }))
  }

  async function submit(event) {
    event.preventDefault(); setBusy(true); setError(''); setMessage('')
    try {
      if (mode === 'signup') {
        const data = await signup(form)
        setMessage(data.detail)
      } else {
        onAuthenticated(await login({ email: form.email, password: form.password }))
      }
    } catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }

  return <main className="auth-page">
    <section className="auth-story">
      <a className="brand" href="#"><span className="brand-mark"><Route size={21} /></span><span>ROADBOOK<small>ELD TRIP PLANNER</small></span></a>
      <div><span className="hero-kicker"><span /> Fleet operations, simplified</span><h1>Plan legal runs.<br /><em>Keep every driver moving.</em></h1><p>One secure workspace for FMCSA-aware dispatch planning, daily logs, and driver oversight.</p></div>
      <div className="auth-proof"><span><ShieldCheck size={18} /> Approval-controlled access</span><span><Truck size={18} /> Per-trip equipment tracking</span></div>
    </section>
    <section className="auth-panel"><div className="auth-card animate-in">
      <div className="auth-tabs"><button className={mode === 'login' ? 'active' : ''} onClick={() => { setMode('login'); setMessage(''); setError('') }}>Sign in</button><button className={mode === 'signup' ? 'active' : ''} onClick={() => { setMode('signup'); setMessage(''); setError('') }}>Driver signup</button></div>
      <span className="eyebrow">{mode === 'login' ? 'Welcome back' : 'Request access'}</span><h2>{mode === 'login' ? 'Sign in to Roadbook' : 'Create your driver account'}</h2><p>{mode === 'login' ? 'Use your approved driver or administrator account.' : 'An administrator will review your request before you can sign in.'}</p>
      {mode === 'login' && <div className="demo-access">
        <div className="demo-access-heading"><span><KeyRound size={13} /> Assessment demo access</span><small>Click a role to autofill</small></div>
        <div className="demo-account-grid">{demoAccounts.map((account) => {
          const Icon = account.icon
          return <button type="button" key={account.role} onClick={() => fillDemoCredentials(account)} className="demo-account">
            <span className="demo-account-icon"><Icon size={15} /></span>
            <span className="demo-account-copy"><strong>{account.role}</strong><code>{account.email}</code><code>{account.password}</code></span>
            <ArrowRight size={14} />
          </button>
        })}</div>
      </div>}
      {message ? <div className="auth-success"><CheckCircle2 size={22} /><div><strong>Request received</strong><span>{message}</span></div></div> : <form onSubmit={submit}>
        {mode === 'signup' && <label className="auth-field"><span>Full name</span><div><User size={17} /><input name="name" value={form.name} onChange={update} required placeholder="Jordan Ellis" /></div></label>}
        <label className="auth-field"><span>Email address</span><div><Mail size={17} /><input type="email" name="email" value={form.email} onChange={update} required placeholder="driver@northline.com" /></div></label>
        <label className="auth-field"><span>Password</span><div><LockKeyhole size={17} /><input type="password" name="password" value={form.password} onChange={update} required minLength="8" placeholder="At least 8 characters" /></div></label>
        {mode === 'signup' && <label className="auth-field"><span>Truck number <small>optional</small></span><div><Truck size={17} /><input name="truck_number" value={form.truck_number} onChange={update} placeholder="TRK-204" /></div></label>}
        {error && <div className="auth-error">{error}</div>}
        <button className="primary-button" disabled={busy}>{busy ? <><span className="button-spinner" /> Please wait</> : <>{mode === 'login' ? 'Sign in' : 'Submit request'} <ArrowRight size={17} /></>}</button>
      </form>}
      {message && <button className="text-button" onClick={() => { setMode('login'); setMessage('') }}>Back to sign in</button>}
    </div></section>
  </main>
}