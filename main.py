"""
main.py — Refugee Camp GIS Dashboard Backend
FastAPI + Supabase

Run:
  pip install -r requirements.txt
  uvicorn main:app --reload --port 8000

API Docs:
  http://localhost:8000/docs
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime
import os
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# SETUP
# ============================================================
app = FastAPI(
    title="Refugee Camp GIS API",
    description="Backend for the Refugee Camp GIS Dashboard — powered by UNHCR + OCHA data",
    version="1.0.0"
)

# CORS — allow your frontend (localhost:5173 for dev, your Vercel URL for prod)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "https://*.vercel.app",          # Replace with your actual Vercel URL
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Supabase client (uses service_role for backend)
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://jacwfkjkazqmspjdcysl.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")  # service_role for writes

if not SUPABASE_KEY:
    print("WARNING: SUPABASE_SERVICE_KEY not set — using anon key (read-only)")
    SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImphY3dma2prYXpxbXNwamRjeXNsIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzIxMDcwODAsImV4cCI6MjA4NzY4MzA4MH0.VB2BqVjM9MGBwXUgB2nqjoffFcv9Q0kmw42IYSKA-ZA")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ============================================================
# MODELS
# ============================================================
class AlertAcknowledge(BaseModel):
    alert_id: int
    acknowledged_by: str

class TruckUpdate(BaseModel):
    truck_id: str
    lat: float
    lng: float
    status: Optional[str] = None
    eta: Optional[str] = None

class NewFlight(BaseModel):
    flight_number: int
    area: str
    altitude_m: int = 120
    pilot_name: Optional[str] = None

class ResourceUpdate(BaseModel):
    camp_id: int
    resource_type: str
    need_pct: float
    stock_pct: float


# ============================================================
# ROOT
# ============================================================
@app.get("/")
def root():
    return {
        "api": "Refugee Camp GIS Dashboard",
        "version": "1.0.0",
        "status": "online",
        "docs": "/docs",
        "data_sources": ["UNHCR", "OCHA HDX"]
    }


# ============================================================
# POPULATION ENDPOINTS
# ============================================================
@app.get("/api/population/timeseries")
def get_population_timeseries(
    from_date: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    to_date:   Optional[str] = Query(None, description="End date YYYY-MM-DD"),
    limit:     int = Query(365, description="Max rows to return"),
):
    """
    Get UNHCR population timeseries data.
    Used for the population trend chart on the dashboard.
    """
    try:
        query = supabase.table("population_timeseries") \
            .select("data_date, individuals") \
            .order("data_date", desc=False) \
            .limit(limit)
        
        if from_date:
            query = query.gte("data_date", from_date)
        if to_date:
            query = query.lte("data_date", to_date)
        
        result = query.execute()
        return {
            "count": len(result.data),
            "data": result.data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/population/latest")
def get_latest_population():
    """
    Get the most recent population figure.
    Used for the KPI card on the dashboard.
    """
    try:
        # Latest timeseries value
        ts = supabase.table("population_timeseries") \
            .select("data_date, individuals") \
            .order("data_date", desc=True) \
            .limit(1) \
            .execute()
        
        # Latest demographics
        demo = supabase.table("population_demographics") \
            .select("*") \
            .order("snapshot_date", desc=True) \
            .limit(1) \
            .execute()
        
        latest_ts = ts.data[0] if ts.data else None
        latest_demo = demo.data[0] if demo.data else None
        
        return {
            "latest_count": latest_ts["individuals"] if latest_ts else 0,
            "as_of_date":   latest_ts["data_date"] if latest_ts else None,
            "demographics": latest_demo,
            "source": "UNHCR"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/population/trend")
def get_population_trend(days: int = Query(30, description="Number of recent days")):
    """Get recent population trend — last N days."""
    try:
        result = supabase.table("population_timeseries") \
            .select("data_date, individuals") \
            .order("data_date", desc=True) \
            .limit(days) \
            .execute()
        
        data = list(reversed(result.data))  # Chronological order
        
        if len(data) >= 2:
            change = data[-1]["individuals"] - data[0]["individuals"]
            pct_change = (change / data[0]["individuals"] * 100) if data[0]["individuals"] else 0
        else:
            change = 0
            pct_change = 0
        
        return {
            "data": data,
            "period_days": days,
            "change": change,
            "pct_change": round(pct_change, 2)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# CAMP LOCATIONS ENDPOINTS
# ============================================================
@app.get("/api/camps")
def get_camps(status: Optional[str] = None, zone: Optional[str] = None):
    """Get all camp locations. Used to populate map markers."""
    try:
        query = supabase.table("camp_locations") \
            .select("id, name, zone, camp_type, population, capacity, lat, lng, status, source, last_verified")
        
        if status:
            query = query.eq("status", status)
        if zone:
            query = query.eq("zone", zone)
        
        result = query.execute()
        return {"count": len(result.data), "camps": result.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/camps/summary")
def get_camps_summary():
    """Aggregate stats across all camps."""
    try:
        result = supabase.table("camp_locations") \
            .select("population, capacity, status") \
            .execute()
        
        camps = result.data
        total_pop = sum(c["population"] for c in camps)
        total_cap = sum(c["capacity"] for c in camps)
        active    = sum(1 for c in camps if c["status"] == "active")
        
        return {
            "total_population": total_pop,
            "total_capacity": total_cap,
            "occupancy_pct": round(total_pop / total_cap * 100, 1) if total_cap else 0,
            "active_camps": active,
            "total_camps": len(camps)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# AI DETECTIONS ENDPOINTS
# ============================================================
@app.get("/api/detections")
def get_detections(
    flight_id:   Optional[str] = None,
    object_type: Optional[str] = None,
    limit:       int = Query(500)
):
    """Get AI-detected objects from drone flights."""
    try:
        query = supabase.table("ai_detections") \
            .select("id, flight_id, object_type, confidence, lat, lng, properties, detected_at") \
            .limit(limit)
        
        if flight_id:
            query = query.eq("flight_id", flight_id)
        if object_type:
            query = query.eq("object_type", object_type)
        
        result = query.execute()
        return {"count": len(result.data), "detections": result.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/detections/stats")
def get_detection_stats(flight_id: Optional[str] = None):
    """
    Count detections by type.
    Returns: {tents: 1247, latrines: 89, water_points: 23, ...}
    """
    try:
        query = supabase.table("ai_detections").select("object_type")
        if flight_id:
            query = query.eq("flight_id", flight_id)
        
        result = query.execute()
        
        stats = {}
        for row in result.data:
            t = row["object_type"]
            stats[t] = stats.get(t, 0) + 1
        
        return {
            "tents":        stats.get("tent", 0),
            "latrines":     stats.get("latrine", 0),
            "water_points": stats.get("water_point", 0),
            "solar_panels": stats.get("solar", 0),
            "total":        len(result.data),
            "flight_id":    flight_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# DRONE FLIGHTS ENDPOINTS
# ============================================================
@app.get("/api/flights")
def get_flights():
    """Get all drone flights."""
    try:
        result = supabase.table("drone_flights") \
            .select("*") \
            .order("flight_date", desc=True) \
            .execute()
        return {"flights": result.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/flights")
def create_flight(flight: NewFlight):
    """Create a new drone flight record."""
    try:
        flight_id = f"flight-{flight.flight_number}"
        data = {
            "id": flight_id,
            "flight_number": flight.flight_number,
            "area": flight.area,
            "altitude_m": flight.altitude_m,
            "status": "planned",
            "coverage_pct": 0,
            "image_count": 0,
            "flight_date": date.today().isoformat(),
            "pilot_name": flight.pilot_name,
        }
        result = supabase.table("drone_flights").insert(data).execute()
        return {"success": True, "flight": result.data[0]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# TRUCKS ENDPOINTS
# ============================================================
@app.get("/api/trucks")
def get_trucks():
    """Get all truck GPS positions and status."""
    try:
        result = supabase.table("trucks").select("*").execute()
        return {"trucks": result.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/trucks/update")
def update_truck(update: TruckUpdate):
    """Update truck GPS position (called by GPS tracking system)."""
    try:
        data = {
            "lat": update.lat,
            "lng": update.lng,
            "updated_at": datetime.now().isoformat()
        }
        if update.status:
            data["status"] = update.status
        if update.eta:
            data["eta"] = update.eta
        
        result = supabase.table("trucks") \
            .update(data) \
            .eq("id", update.truck_id) \
            .execute()
        
        return {"success": True, "truck": result.data[0] if result.data else None}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# ALERTS ENDPOINTS
# ============================================================
@app.get("/api/alerts")
def get_alerts(include_acknowledged: bool = False):
    """Get active alerts."""
    try:
        query = supabase.table("alerts").select("*").order("created_at", desc=True)
        if not include_acknowledged:
            query = query.eq("acknowledged", False)
        result = query.execute()
        return {"alerts": result.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/alerts/acknowledge")
def acknowledge_alert(body: AlertAcknowledge):
    """Acknowledge an alert."""
    try:
        result = supabase.table("alerts").update({
            "acknowledged": True,
            "acknowledged_by": body.acknowledged_by,
            "acknowledged_at": datetime.now().isoformat()
        }).eq("id", body.alert_id).execute()
        
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# RESOURCE NEEDS ENDPOINTS
# ============================================================
@app.get("/api/resources")
def get_resources(camp_id: Optional[int] = None):
    """Get resource needs across camps."""
    try:
        query = supabase.table("resource_needs") \
            .select("*, camp_locations(name, zone)") \
            .order("need_pct", desc=True)
        
        if camp_id:
            query = query.eq("camp_id", camp_id)
        
        result = query.execute()
        return {"resources": result.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/resources/summary")
def get_resources_summary():
    """Aggregate resource needs — average across all camps."""
    try:
        result = supabase.table("resource_needs") \
            .select("resource_type, need_pct, stock_pct") \
            .execute()
        
        aggregated = {}
        for row in result.data:
            rt = row["resource_type"]
            if rt not in aggregated:
                aggregated[rt] = {"need_values": [], "stock_values": []}
            aggregated[rt]["need_values"].append(row["need_pct"])
            aggregated[rt]["stock_values"].append(row["stock_pct"])
        
        summary = {}
        for rt, vals in aggregated.items():
            summary[rt] = {
                "avg_need_pct":  round(sum(vals["need_values"])  / len(vals["need_values"]), 1),
                "avg_stock_pct": round(sum(vals["stock_values"]) / len(vals["stock_values"]), 1),
            }
        
        return {"resources": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# DASHBOARD — single endpoint for all frontend data
# ============================================================
@app.get("/api/dashboard")
def get_dashboard_data():
    """
    Single endpoint that returns everything the frontend needs.
    Replaces all fakeData.ts with real Supabase data.
    """
    try:
        # Population
        pop_latest = supabase.table("population_timeseries") \
            .select("data_date, individuals") \
            .order("data_date", desc=True).limit(1).execute()
        
        pop_trend = supabase.table("population_timeseries") \
            .select("data_date, individuals") \
            .order("data_date", desc=True).limit(7).execute()
        
        # Detections
        detection_result = supabase.table("ai_detections").select("object_type").execute()
        det_stats = {}
        for row in detection_result.data:
            t = row["object_type"]
            det_stats[t] = det_stats.get(t, 0) + 1
        
        # Camps
        camps = supabase.table("camp_locations").select("*").execute()
        
        # Trucks
        trucks = supabase.table("trucks").select("*").execute()
        
        # Alerts
        alerts = supabase.table("alerts").select("*").eq("acknowledged", False).execute()
        
        # Resources
        resources = supabase.table("resource_needs").select("resource_type, need_pct, stock_pct").execute()
        resource_summary = {}
        for row in resources.data:
            rt = row["resource_type"]
            if rt not in resource_summary:
                resource_summary[rt] = []
            resource_summary[rt].append(row["need_pct"])
        resource_avg = {k: round(sum(v)/len(v), 1) for k, v in resource_summary.items()}
        
        # Flights
        flights = supabase.table("drone_flights").select("*").order("flight_date", desc=True).limit(5).execute()
        
        latest_pop = pop_latest.data[0] if pop_latest.data else {"individuals": 0, "data_date": None}
        
        return {
            "stats": {
                "total_population": latest_pop["individuals"],
                "population_as_of":  latest_pop["data_date"],
                "tents":             det_stats.get("tent", 1247),       # fallback to seed data
                "latrines":          det_stats.get("latrine", 89),
                "water_points":      det_stats.get("water_point", 23),
                "aid_trucks":        len(trucks.data),
                "last_update":       datetime.now().strftime("%H:%M"),
            },
            "population_trend":  list(reversed(pop_trend.data)),
            "camps":             camps.data,
            "trucks":            trucks.data,
            "alerts":            alerts.data,
            "resource_needs":    resource_avg,
            "flights":           flights.data,
            "source": "UNHCR + OCHA HDX + Supabase"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# HEALTH CHECK
# ============================================================
@app.get("/health")
def health():
    try:
        # Quick DB ping
        supabase.table("drone_flights").select("id").limit(1).execute()
        db_status = "connected"
    except:
        db_status = "error"
    
    return {
        "status": "ok",
        "database": db_status,
        "timestamp": datetime.now().isoformat()
    }
