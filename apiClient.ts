/**
 * apiClient.ts
 * ============
 * Replaces fakeData.ts — fetches real data from FastAPI backend.
 * 
 * Place this in: src/data/apiClient.ts
 * Then update your components to import from here instead of fakeData.ts
 */

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000"

// ============================================================
// Generic fetch helper
// ============================================================
async function apiFetch<T>(endpoint: string): Promise<T> {
  const res = await fetch(`${API_BASE}${endpoint}`)
  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${await res.text()}`)
  }
  return res.json()
}

// ============================================================
// TYPES
// ============================================================
export interface PopulationPoint {
  data_date: string
  individuals: number
}

export interface Camp {
  id: number
  name: string
  zone: string
  camp_type: string
  population: number
  capacity: number
  lat: number
  lng: number
  status: string
  source: string
}

export interface Truck {
  id: string
  name: string
  status: string
  cargo: string
  lat: number
  lng: number
  eta: string
  updated_at: string
}

export interface Alert {
  id: number
  severity: string
  zone: string
  message: string
  acknowledged: boolean
  created_at: string
}

export interface DashboardData {
  stats: {
    total_population: number
    population_as_of: string
    tents: number
    latrines: number
    water_points: number
    aid_trucks: number
    last_update: string
  }
  population_trend: PopulationPoint[]
  camps: Camp[]
  trucks: Truck[]
  alerts: Alert[]
  resource_needs: Record<string, number>
  flights: any[]
}

// ============================================================
// API CALLS
// ============================================================

/** Get everything the dashboard needs in one call */
export async function getDashboardData(): Promise<DashboardData> {
  return apiFetch<DashboardData>("/api/dashboard")
}

/** Get population timeseries for chart */
export async function getPopulationTrend(days = 30): Promise<PopulationPoint[]> {
  const data = await apiFetch<{ data: PopulationPoint[] }>(`/api/population/trend?days=${days}`)
  return data.data
}

/** Get latest population count */
export async function getLatestPopulation() {
  return apiFetch("/api/population/latest")
}

/** Get all camp locations for map */
export async function getCamps(): Promise<Camp[]> {
  const data = await apiFetch<{ camps: Camp[] }>("/api/camps")
  return data.camps
}

/** Get AI detection stats */
export async function getDetectionStats(flightId?: string) {
  const url = flightId
    ? `/api/detections/stats?flight_id=${flightId}`
    : "/api/detections/stats"
  return apiFetch(url)
}

/** Get all trucks */
export async function getTrucks(): Promise<Truck[]> {
  const data = await apiFetch<{ trucks: Truck[] }>("/api/trucks")
  return data.trucks
}

/** Get active alerts */
export async function getAlerts(): Promise<Alert[]> {
  const data = await apiFetch<{ alerts: Alert[] }>("/api/alerts")
  return data.alerts
}

/** Acknowledge an alert */
export async function acknowledgeAlert(alertId: number, by = "dashboard-user") {
  const res = await fetch(`${API_BASE}/api/alerts/acknowledge`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ alert_id: alertId, acknowledged_by: by })
  })
  return res.json()
}

/** Create a new drone flight */
export async function createFlight(data: {
  flight_number: number
  area: string
  altitude_m: number
  pilot_name?: string
}) {
  const res = await fetch(`${API_BASE}/api/flights`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data)
  })
  return res.json()
}

/** Get resource needs summary */
export async function getResourceSummary() {
  return apiFetch("/api/resources/summary")
}

/** Health check */
export async function healthCheck() {
  return apiFetch("/health")
}
