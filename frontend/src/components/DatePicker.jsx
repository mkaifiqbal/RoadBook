import { useEffect, useId, useRef, useState } from 'react'
import { CalendarDays, ChevronLeft, ChevronRight, Clock3, X } from 'lucide-react'

const WEEKDAYS = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su']

const pad = (value) => String(value).padStart(2, '0')
const dateKey = (date) => `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`

function parseValue(value) {
  if (!value) return null
  const [datePart] = value.split('T')
  const [year, month, day] = datePart.split('-').map(Number)
  if (!year || !month || !day) return null
  const date = new Date(year, month - 1, day)
  return Number.isNaN(date.getTime()) ? null : date
}

function monthCells(month) {
  const first = new Date(month.getFullYear(), month.getMonth(), 1)
  const mondayOffset = (first.getDay() + 6) % 7
  const start = new Date(first)
  start.setDate(first.getDate() - mondayOffset)
  return Array.from({ length: 42 }, (_, index) => {
    const date = new Date(start)
    date.setDate(start.getDate() + index)
    return date
  })
}

function displayDate(value, placeholder) {
  const date = parseValue(value)
  if (!date) return placeholder
  return date.toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' })
}

export default function DatePicker({ value, onChange, label, placeholder = 'Select date', includeTime = false, min, max }) {
  const id = useId()
  const wrapperRef = useRef(null)
  const selectedDate = parseValue(value)
  const [open, setOpen] = useState(false)
  const [visibleMonth, setVisibleMonth] = useState(() => selectedDate || new Date())
  const timeValue = includeTime && value.includes('T') ? value.split('T')[1].slice(0, 5) : '08:00'
  const todayKey = dateKey(new Date())
  const selectedKey = selectedDate ? dateKey(selectedDate) : ''
  const cells = monthCells(visibleMonth)

  useEffect(() => {
    const close = (event) => {
      if (!wrapperRef.current?.contains(event.target)) setOpen(false)
    }
    document.addEventListener('pointerdown', close)
    return () => document.removeEventListener('pointerdown', close)
  }, [])

  function selectDate(date) {
    const nextDate = dateKey(date)
    onChange(includeTime ? `${nextDate}T${timeValue}` : nextDate)
    setVisibleMonth(new Date(date.getFullYear(), date.getMonth(), 1))
    if (!includeTime) setOpen(false)
  }

  function selectTime(event) {
    const nextTime = event.target.value
    const nextDate = selectedKey || dateKey(new Date())
    onChange(`${nextDate}T${nextTime}`)
  }

  function clear(event) {
    event.stopPropagation()
    onChange('')
  }

  function shiftMonth(amount) {
    setVisibleMonth((current) => new Date(current.getFullYear(), current.getMonth() + amount, 1))
  }

  return (
    <div className={`roadbook-date-picker ${open ? 'open' : ''}`} ref={wrapperRef}>
      <button type="button" className="date-trigger" onClick={() => setOpen((current) => !current)} aria-expanded={open} aria-controls={`${id}-calendar`}>
        <span className="date-trigger-icon"><CalendarDays size={17} /></span>
        <span className="date-trigger-copy">
          {label && <small>{label}</small>}
          <strong className={value ? '' : 'placeholder'}>{displayDate(value, placeholder)}</strong>
        </span>
        {includeTime && value && <span className="date-trigger-time"><Clock3 size={13} />{timeValue}</span>}
        {value && <span className="date-clear" onClick={clear} role="button" tabIndex="0" aria-label="Clear date"><X size={14} /></span>}
      </button>

      {open && (
        <div className="calendar-popover" id={`${id}-calendar`}>
          <div className="calendar-toolbar">
            <button type="button" onClick={() => shiftMonth(-1)} aria-label="Previous month"><ChevronLeft size={17} /></button>
            <strong>{visibleMonth.toLocaleDateString([], { month: 'long', year: 'numeric' })}</strong>
            <button type="button" onClick={() => shiftMonth(1)} aria-label="Next month"><ChevronRight size={17} /></button>
          </div>
          <div className="calendar-weekdays">{WEEKDAYS.map((day) => <span key={day}>{day}</span>)}</div>
          <div className="calendar-grid">
            {cells.map((date) => {
              const key = dateKey(date)
              const outside = date.getMonth() !== visibleMonth.getMonth()
              const disabled = (min && key < min) || (max && key > max)
              return <button type="button" key={key} className={`${outside ? 'outside' : ''} ${key === todayKey ? 'today' : ''} ${key === selectedKey ? 'selected' : ''}`} disabled={disabled} onClick={() => selectDate(date)}>{date.getDate()}</button>
            })}
          </div>
          {includeTime && (
            <div className="calendar-time-row">
              <span><Clock3 size={15} /><span><small>Departure time</small><strong>Local time</strong></span></span>
              <input type="time" value={timeValue} onChange={selectTime} aria-label="Departure time" />
            </div>
          )}
          <div className="calendar-footer">
            <button type="button" onClick={() => { setVisibleMonth(new Date()); selectDate(new Date()) }}>Today</button>
            {includeTime && <button type="button" className="calendar-done" onClick={() => setOpen(false)}>Done</button>}
          </div>
        </div>
      )}
    </div>
  )
}