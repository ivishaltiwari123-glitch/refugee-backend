"""
main.py — Refugee Camp GIS Dashboard Backend
FastAPI + Supabase (Vercel-compatible)
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client
from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime
import os

# load_dotenv only locally — Vercel uses env vars directly
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# ── Supabase setup ───────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_ANON_KEY", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in environment variables")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ── App setup ────────────────────────────────────────────────
app = FastAPI(
    title="Refugee Camp GIS API",
    description="Backend powered by UNHCR + OCHA data",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Models ───────────────────────────────────────────────────
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

# ── Root ─────────────────────────────────────────────────────
@app.get("/")
def root():
    return {
        "api": "Refugee Camp GIS Dashboard",
        "version": "1.0.0",
        "status": "online",
        "docs": "/docs",
        "data_sources": ["UNHCR", "OCHA HDX"]
    }

# ── Health ───────────────────────────────────────────────────
@app.get("/health")
def health():
    try:
        supabase.table("drone_flights").select("id").limit(1).execute()
        db_status = "connected"
    except Exception:
        db_status = "error"
    return {"status": "ok", "database": db_status, "timestamp": datetime.now().isoformat()}

# ── Population ───────────────────────────────────────────────
@app.get("/api/population/latest")
def get_latest_population():
    try:
        ts = supabase.table("population_timeseries").select("data_date, individuals").order("data_date", desc=True).limit(1).execute()
        demo = supabase.table("population_demographics").select("*").order("snapshot_date", desc=True).limit(1).execute()
        latest_ts = ts.data[0] if ts.data else None
        return {
            "latest_count": latest_ts["individuals"] if latest_ts else 0,
            "as_of_date": latest_ts["data_date"] if latest_ts else None,
            "demographics": demo.data[0] if demo.data else None,
            "source": "UNHCR"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/population/trend")
def get_population_trend(days: int = Query(30)):
    try:
        result = supabase.table("population_timeseries").select("data_date, individuals").order("data_date", desc=True).limit(days).execute()
        data = list(reversed(result.data))
        return {"data": data, "period_days": days}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/population/timeseries")
def get_population_timeseries(limit: int = Query(365)):
    try:
        result = supabase.table("population_timeseries").select("data_date, individuals").order("data_date", desc=False).limit(limit).execute()
        return {"count": len(result.data), "data": result.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Camps ────────────────────────────────────────────────────
@app.get("/api/camps")
def get_camps(status: Optional[str] = None):
    try:
        query = supabase.table("camp_locations").select("id, name, zone, camp_type, population, capacity, lat, lng, status, source")
        if status:
            query = query.eq("status", status)
        result = query.execute()
        return {"count": len(result.data), "camps": result.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Detections ───────────────────────────────────────────────
@app.get("/api/detections/stats")
def get_detection_stats(flight_id: Optional[str] = None):
    try:
        query = supabase.table("ai_detections").select("object_type")
        if flight_id:
            query = query.eq("flight_id", flight_id)
        result = query.execute()
        stats: dict = {}
        for row in result.data:
            t = row["object_type"]
            stats[t] = stats.get(t, 0) + 1
        return {"tents": stats.get("tent", 0), "latrines": stats.get("latrine", 0), "water_points": stats.get("water_point", 0), "total": len(result.data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Flights ──────────────────────────────────────────────────
@app.get("/api/flights")
def get_flights():
    try:
        result = supabase.table("drone_flights").select("*").order("flight_date", desc=True).execute()
        return {"flights": result.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/flights")
def create_flight(flight: NewFlight):
    try:
        data = {
            "id": f"flight-{flight.flight_number}",
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

# ── Trucks ───────────────────────────────────────────────────
@app.get("/api/trucks")
def get_trucks():
    try:
        result = supabase.table("trucks").select("*").execute()
        return {"trucks": result.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/trucks/update")
def update_truck(update: TruckUpdate):
    try:
        data: dict = {"lat": update.lat, "lng": update.lng, "updated_at": datetime.now().isoformat()}
        if update.status:
            data["status"] = update.status
        if update.eta:
            data["eta"] = update.eta
        result = supabase.table("trucks").update(data).eq("id", update.truck_id).execute()
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Alerts ───────────────────────────────────────────────────
@app.get("/api/alerts")
def get_alerts(include_acknowledged: bool = False):
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
    try:
        supabase.table("alerts").update({
            "acknowledged": True,
            "acknowledged_by": body.acknowledged_by,
            "acknowledged_at": datetime.now().isoformat()
        }).eq("id", body.alert_id).execute()
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Resources ────────────────────────────────────────────────
@app.get("/api/resources/summary")
def get_resources_summary():
    try:
        result = supabase.table("resource_needs").select("resource_type, need_pct, stock_pct").execute()
        aggregated: dict = {}
        for row in result.data:
            rt = row["resource_type"]
            if rt not in aggregated:
                aggregated[rt] = []
            aggregated[rt].append(row["need_pct"])
        summary = {k: round(sum(v)/len(v), 1) for k, v in aggregated.items()}
        return {"resources": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Dashboard (single call for frontend) ─────────────────────
@app.get("/api/dashboard")
def get_dashboard_data():
    try:
        pop = supabase.table("population_timeseries").select("data_date, individuals").order("data_date", desc=True).limit(1).execute()
        pop_trend = supabase.table("population_timeseries").select("data_date, individuals").order("data_date", desc=True).limit(7).execute()
        trucks = supabase.table("trucks").select("*").execute()
        alerts = supabase.table("alerts").select("*").eq("acknowledged", False).execute()
        resources = supabase.table("resource_needs").select("resource_type, need_pct").execute()
        flights = supabase.table("drone_flights").select("*").order("flight_date", desc=True).limit(5).execute()

        resource_summary: dict = {}
        for row in resources.data:
            rt = row["resource_type"]
            if rt not in resource_summary:
                resource_summary[rt] = []
            resource_summary[rt].append(row["need_pct"])
        resource_avg = {k: round(sum(v)/len(v), 1) for k, v in resource_summary.items()}

        latest_pop = pop.data[0] if pop.data else {"individuals": 234511, "data_date": None}

        return {
            "stats": {
                "total_population": latest_pop["individuals"],
                "population_as_of": latest_pop["data_date"],
                "tents": 1247,
                "latrines": 89,
                "water_points": 23,
                "aid_trucks": len(trucks.data),
                "last_update": datetime.now().strftime("%H:%M"),
            },
            "population_trend": list(reversed(pop_trend.data)),
            "trucks": trucks.data,
            "alerts": alerts.data,
            "resource_needs": resource_avg,
            "flights": flights.data,
            "source": "UNHCR + OCHA HDX + Supabase"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
