import { useEffect, useId, useRef, useState } from 'react'
import { ArrowRight, CalendarClock, CircleDot, LoaderCircle, MapPin, PackageCheck, RotateCcw, Search, Truck } from 'lucide-react'
import { searchLocations } from '../api'
import DatePicker from './DatePicker'

const initialForm = {
  current_location: '', pickup_location: '', dropoff_location: '', current_cycle_used: 0,
  driver_name: '', carrier_name: '', truck_number: '', start_time: '',
}

const locationFields = [
  { name: 'current_location', label: 'Current location', placeholder: 'e.g. Chicago, IL', icon: CircleDot, tone: 'current' },
  { name: 'pickup_location', label: 'Pickup', placeholder: 'e.g. Indianapolis, IN', icon: PackageCheck, tone: 'pickup' },
  { name: 'dropoff_location', label: 'Drop-off', placeholder: 'e.g. Atlanta, GA', icon: MapPin, tone: 'dropoff' },
]

function LocationField({ field, value, onChange }) {
  const { name, label, placeholder, icon: Icon, tone } = field
  const listId = useId()
  const wrapperRef = useRef(null)
  const [suggestions, setSuggestions] = useState([])
  const [open, setOpen] = useState(false)
  const [searching, setSearching] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)

  useEffect(() => {
    if (!open || value.trim().length < 3) return undefined

    const controller = new AbortController()
    const timer = window.setTimeout(async () => {
      setSearching(true)
      try {
        const results = await searchLocations(value.trim(), controller.signal)
        setSuggestions(results)
        setActiveIndex(-1)
      } catch (error) {
        if (error.name !== 'AbortError') setSuggestions([])
      } finally {
        if (!controller.signal.aborted) setSearching(false)
      }
    }, 450)

    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [open, value])

  useEffect(() => {
    const close = (event) => {
      if (!wrapperRef.current?.contains(event.target)) setOpen(false)
    }
    document.addEventListener('pointerdown', close)
    return () => document.removeEventListener('pointerdown', close)
  }, [])

  function select(place) {
    onChange(name, place.name)
    setOpen(false)
    setSuggestions([])
  }

  function handleKeyDown(event) {
    if (!open || !suggestions.length) return
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActiveIndex((index) => Math.min(index + 1, suggestions.length - 1))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActiveIndex((index) => Math.max(index - 1, 0))
    } else if (event.key === 'Enter' && activeIndex >= 0) {
      event.preventDefault()
      select(suggestions[activeIndex])
    } else if (event.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <label className="field location-field" ref={wrapperRef}>
      <span>{label}</span>
      <div className="input-shell location-combobox">
        <Icon className={`field-icon ${tone}`} size={17} />
        <input
          name={name}
          value={value}
          onChange={(event) => {
            const nextValue = event.target.value
            onChange(name, nextValue)
            setOpen(true)
            if (nextValue.trim().length < 3) {
              setSuggestions([])
              setSearching(false)
              setActiveIndex(-1)
            }
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          required
          autoComplete="off"
          role="combobox"
          aria-autocomplete="list"
          aria-expanded={open && (searching || suggestions.length > 0)}
          aria-controls={listId}
          aria-activedescendant={activeIndex >= 0 ? `${listId}-${activeIndex}` : undefined}
        />
        {searching ? <LoaderCircle className="location-search-icon spin" size={16} /> : <Search className="location-search-icon" size={15} />}
        {open && value.trim().length >= 3 && (searching || suggestions.length > 0) && (
          <div className="location-suggestions" id={listId} role="listbox">
            <div className="suggestion-caption">Real places via OpenStreetMap</div>
            {suggestions.map((place, index) => (
              <button
                type="button"
                role="option"
                aria-selected={index === activeIndex}
                id={`${listId}-${index}`}
                key={`${place.lat}-${place.lon}`}
                className={index === activeIndex ? 'active' : ''}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => select(place)}
              >
                <MapPin size={15} /> <span>{place.name}</span>
              </button>
            ))}
            {searching && !suggestions.length && <div className="suggestion-loading">Searching verified locations…</div>}
          </div>
        )}
      </div>
    </label>
  )
}

export default function TripForm({ onSubmit, loading, user }) {
  const [form, setForm] = useState(() => ({
    ...initialForm,
    driver_name: user?.name || '',
    carrier_name: user?.carrier_name || '',
    truck_number: user?.truck_number || '',
  }))
  const [showDetails, setShowDetails] = useState(false)
  const setField = (name, value) => setForm((current) => ({ ...current, [name]: value }))
  const update = (event) => setField(event.target.name, event.target.value)

  function submit(event) {
    event.preventDefault()
    const payload = { ...form, current_cycle_used: Number(form.current_cycle_used), save: true }
    if (!payload.start_time) delete payload.start_time
    onSubmit(payload)
  }

  return (
    <form className="planner-form" onSubmit={submit}>
      <div className="form-heading">
        <div>
          <span className="eyebrow">New dispatch</span>
          <h1>Plan a compliant run</h1>
          <p>Route, required stops, and driver logs in one pass.</p>
        </div>
        <div className="form-heading-icon"><Truck size={22} /></div>
      </div>

      <div className="route-inputs">
        <span className="route-rail" />
        {locationFields.map((field) => <LocationField field={field} value={form[field.name]} onChange={setField} key={field.name} />)}
      </div>

      <label className="field cycle-field">
        <span><span>Current cycle used</span><strong>{Number(form.current_cycle_used).toFixed(1)} hrs</strong></span>
        <input type="range" name="current_cycle_used" min="0" max="70" step="0.5" value={form.current_cycle_used} onChange={update} />
        <div className="range-labels"><span>0h</span><span>70h limit</span></div>
      </label>

      <button className="details-toggle" type="button" onClick={() => setShowDetails((value) => !value)} aria-expanded={showDetails}>
        <span><CalendarClock size={16} /> Driver & trip details <small>Optional</small></span>
        <ArrowRight size={16} className={showDetails ? 'rotate' : ''} />
      </button>

      {showDetails && (
        <div className="detail-grid animate-in">
          <label className="field"><span>Driver name</span><input name="driver_name" value={form.driver_name} onChange={update} placeholder="Jordan Ellis" /></label>
          <label className="field"><span>Carrier</span><input name="carrier_name" value={form.carrier_name} onChange={update} placeholder="Northline Freight" /></label>
          <label className="field"><span>Truck number <small>this trip</small></span><input name="truck_number" value={form.truck_number} onChange={update} placeholder="TRK-204" /></label>
          <label className="field date-field"><span>Start date & time</span><DatePicker value={form.start_time} onChange={(value) => setField('start_time', value)} placeholder="Choose departure" includeTime /></label>
        </div>
      )}

      <button className="primary-button" disabled={loading} type="submit">
        {loading ? <><span className="button-spinner" /> Building your trip plan</> : <>Plan trip <ArrowRight size={18} /></>}
      </button>
      <div className="compliance-note"><RotateCcw size={14} /><span>Calculated for the FMCSA 70-hour / 8-day cycle</span></div>
    </form>
  )
}