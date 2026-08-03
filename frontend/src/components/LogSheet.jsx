import { FileText } from 'lucide-react'

const rows = [
  ['off_duty', '1', 'Off duty'], ['sleeper_berth', '2', 'Sleeper berth'],
  ['driving', '3', 'Driving'], ['on_duty', '4', 'On duty (not driving)'],
]
const rowIndex = Object.fromEntries(rows.map(([status], index) => [status, index]))
const x0 = 126, gridW = 720, rowH = 38, y0 = 78
const minuteX = (minute) => x0 + (minute / 1440) * gridW
const rowY = (status) => y0 + rowIndex[status] * rowH + rowH / 2
const formatHours = (value = 0) => value === 0 ? '—' : Number(value).toFixed(2).replace(/\.00$/, '')

function linePath(entries) {
  if (!entries.length) return ''
  let path = `M ${minuteX(entries[0].start_minute)} ${rowY(entries[0].status)}`
  entries.forEach((entry, index) => {
    const endX = minuteX(entry.end_minute)
    path += ` H ${endX}`
    const next = entries[index + 1]
    if (next) path += ` V ${rowY(next.status)}`
  })
  return path
}

export default function LogSheet({ log, index }) {
  const date = new Date(`${log.date}T12:00:00`).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })
  return (
    <article className="log-card animate-in" style={{ animationDelay: `${index * 70}ms` }}>
      <div className="log-card-heading">
        <div><span className="document-icon"><FileText size={17} /></span><div><strong>Driver&apos;s Daily Log</strong><span>Day {log.day_number} · {date}</span></div></div>
        <span className="sheet-counter">Sheet {log.day_number}</span>
      </div>
      <div className="log-paper-scroll">
        <div className="log-paper">
          <div className="log-header">
            <div><small>Driver</small><strong>{log.driver_name || '—'}</strong></div>
            <div><small>Carrier</small><strong>{log.carrier_name || '—'}</strong></div>
            <div><small>Truck no.</small><strong>{log.truck_number || '—'}</strong></div>
            <div><small>Miles today</small><strong>{log.miles_driving_today.toLocaleString()}</strong></div>
            <div><small>Date</small><strong>{date}</strong></div>
          </div>
          <svg viewBox="0 0 920 250" role="img" aria-label={`Daily duty status graph for ${date}`}>
            <rect x={x0} y={y0} width={gridW} height={rowH * 4} fill="#fffdf8" stroke="#b9b7ae" />
            {Array.from({ length: 97 }, (_, index) => {
              const x = x0 + (index / 96) * gridW
              const major = index % 4 === 0
              return <line key={index} x1={x} x2={x} y1={y0 - (major ? 10 : 4)} y2={y0 + rowH * 4} stroke={major ? '#a5a49d' : '#dedcd3'} strokeWidth={major ? 0.9 : 0.45} />
            })}
            {Array.from({ length: 5 }, (_, index) => <line key={index} x1={x0} x2={x0 + gridW} y1={y0 + index * rowH} y2={y0 + index * rowH} stroke="#aaa89f" />)}
            {Array.from({ length: 25 }, (_, hour) => <text key={hour} x={x0 + hour * gridW / 24} y={y0 - 16} textAnchor="middle" className="hour-label">{hour === 0 || hour === 24 ? 'M' : hour > 12 ? hour - 12 : hour}</text>)}
            {rows.map(([status, code, label], index) => <g key={status}><text x="12" y={y0 + index * rowH + 17} className="row-code">{code}</text><text x="35" y={y0 + index * rowH + 18} className="row-label">{label}</text><text x="883" y={y0 + index * rowH + 23} textAnchor="middle" className="row-total">{formatHours(log.totals_hours[status])}</text></g>)}
            <text x="883" y={y0 - 16} textAnchor="middle" className="total-label">TOTAL</text>
            <path d={linePath(log.entries)} fill="none" stroke="#e34d31" strokeWidth="4" strokeLinejoin="round" strokeLinecap="round" />
            <text x="12" y="245" className="route-caption">From: {log.from_label || '—'}  ·  To: {log.to_label || '—'}</text>
          </svg>
          <div className="remarks-table">
            <div className="remarks-title">Remarks / Shipping documents</div>
            <div className="remarks-head"><span>Time</span><span>Duty status</span><span>Activity and location</span></div>
            <div className="remarks-body">
              {log.remarks.length ? log.remarks.map((remark, i) => (
                <div className="remark-row" key={`${remark.minute}-${i}`}>
                  <time>{remark.time}</time>
                  <span>{rows.find(([status]) => status === remark.status)?.[2] || remark.status}</span>
                  <strong>{remark.label}</strong>
                </div>
              )) : <div className="remark-row empty"><span>—</span><span>Off duty</span><strong>No status changes recorded</strong></div>}
            </div>
            <div className="remarks-footer"><span>From: <strong>{log.from_label || '—'}</strong></span><span>To: <strong>{log.to_label || '—'}</strong></span><span>Total on duty: <strong>{formatHours(log.total_on_duty_hours)} hrs</strong></span></div>
          </div>
        </div>
      </div>
    </article>
  )
}