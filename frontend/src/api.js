const API_BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

let accessToken = localStorage.getItem('roadbook_access') || ''

export function setAccessToken(token) {
  accessToken = token || ''
  if (accessToken) localStorage.setItem('roadbook_access', accessToken)
  else localStorage.removeItem('roadbook_access')
}

async function request(path, options = {}) {
  let response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: {
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        ...options.headers,
      },
    })
  } catch {
    throw new Error('We could not reach Roadbook. Make sure the Django server is running.')
  }
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    const fieldError = Object.values(data).flat().find(Boolean)
    const error = new Error(data.detail || fieldError || 'Something went wrong. Please try again.')
    error.status = response.status
    throw error
  }
  return data
}

export async function planTrip(payload) {
  return request('/api/plan-trip/', { method: 'POST', body: JSON.stringify(payload) })
}

export const login = (payload) => request('/api/auth/login/', { method: 'POST', body: JSON.stringify(payload) })
export const signup = (payload) => request('/api/auth/signup/', { method: 'POST', body: JSON.stringify(payload) })
export const getProfile = () => request('/api/auth/profile/')
export const updateProfile = (payload) => request('/api/auth/profile/', { method: 'PATCH', body: JSON.stringify(payload) })
export const getTrips = (driverId) => request(`/api/trips/${driverId ? `?driver=${driverId}` : ''}`)
export const getTrip = (id) => request(`/api/trips/${id}/`)
export const deleteTrip = (id) => request(`/api/trips/${id}/`, { method: 'DELETE' })
export const getDrivers = (status) => request(`/api/admin/drivers/${status ? `?status=${status}` : ''}`)
export const addDriver = (payload) => request('/api/admin/drivers/', { method: 'POST', body: JSON.stringify(payload) })
export const setDriverStatus = (id, status) => request(`/api/admin/drivers/${id}/status/`, { method: 'PATCH', body: JSON.stringify({ status }) })

export async function searchLocations(query, signal) {
  let response
  try {
    response = await fetch(`${API_BASE}/api/locations/?q=${encodeURIComponent(query)}`, { signal })
  } catch (error) {
    if (error.name === 'AbortError') throw error
    throw new Error('Location suggestions are unavailable while the Django server is offline.', { cause: error })
  }
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(data.detail || 'Location suggestions are temporarily unavailable.')
  return data.results || []
}