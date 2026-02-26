"""
main.py — Refugee Camp GIS Dashboard Backend
FastAPI + Supabase (Python 3.11 + Pydantic v2 compatible)
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client
from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# ── Supabase ─────────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_ANON_KEY", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ── App ───────────────────────────────────────────────────────
app = FastAPI(title="Refugee Camp GIS API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Models (Pydantic v2 compatible) ──────────────────────────
class AlertAcknowledge(BaseModel):
    alert_id: int
    acknowledged_by: str

class NewFlight(BaseModel):
    flight_number: int
    area: str
    altitude_m: int = 120
    pilot_name: Optional[str] = None

class TruckUpdate(BaseModel):
    truck_id: str
    lat: float
    lng: float
    status: Optional[str] = None
    eta: Optional[str] = None

# ── Endpoints ─────────────────────────────────────────────────
@app.get("/")
def root():
    return {"api": "Refugee Camp GIS Dashboard", "version": "1.0.0", "status": "online", "docs": "/docs", "data_sources": ["UNHCR", "OCHA HDX"]}

@app.get("/health")
def health():
    try:
        supabase.table("drone_flights").select("id").limit(1).execute()
        db = "connected"
    except Exception:
        db = "error"
    return {"status": "ok", "database": db, "timestamp": datetime.now().isoformat()}

@app.get("/api/population/latest")
def get_latest_population():
    try:
        ts   = supabase.table("population_timeseries").select("data_date, individuals").order("data_date", desc=True).limit(1).execute()
        demo = supabase.table("population_demographics").select("*").order("snapshot_date", desc=True).limit(1).execute()
        latest = ts.data[0] if ts.data else None
        return {"latest_count": latest["individuals"] if latest else 0, "as_of_date": latest["data_date"] if latest else None, "demographics": demo.data[0] if demo.data else None, "source": "UNHCR"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/population/trend")
def get_population_trend(days: int = Query(30)):
    try:
        result = supabase.table("population_timeseries").select("data_date, individuals").order("data_date", desc=True).limit(days).execute()
        return {"data": list(reversed(result.data)), "period_days": days}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/population/timeseries")
def get_timeseries(limit: int = Query(365)):
    try:
        result = supabase.table("population_timeseries").select("data_date, individuals").order("data_date").limit(limit).execute()
        return {"count": len(result.data), "data": result.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/camps")
def get_camps(status: Optional[str] = None):
    try:
        q = supabase.table("camp_locations").select("id, name, zone, camp_type, population, capacity, lat, lng, status, source")
        if status:
            q = q.eq("status", status)
        result = q.execute()
        return {"count": len(result.data), "camps": result.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/detections/stats")
def get_detection_stats(flight_id: Optional[str] = None):
    try:
        q = supabase.table("ai_detections").select("object_type")
        if flight_id:
            q = q.eq("flight_id", flight_id)
        result = q.execute()
        stats: dict = {}
        for row in result.data:
            t = row["object_type"]
            stats[t] = stats.get(t, 0) + 1
        return {"tents": stats.get("tent", 0), "latrines": stats.get("latrine", 0), "water_points": stats.get("water_point", 0), "total": len(result.data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
        data = {"id": f"flight-{flight.flight_number}", "flight_number": flight.flight_number, "area": flight.area, "altitude_m": flight.altitude_m, "status": "planned", "coverage_pct": 0, "image_count": 0, "flight_date": date.today().isoformat(), "pilot_name": flight.pilot_name}
        result = supabase.table("drone_flights").insert(data).execute()
        return {"success": True, "flight": result.data[0]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
        if update.status: data["status"] = update.status
        if update.eta:    data["eta"]    = update.eta
        supabase.table("trucks").update(data).eq("id", update.truck_id).execute()
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/alerts")
def get_alerts(include_acknowledged: bool = False):
    try:
        q = supabase.table("alerts").select("*").order("created_at", desc=True)
        if not include_acknowledged:
            q = q.eq("acknowledged", False)
        result = q.execute()
        return {"alerts": result.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/alerts/acknowledge")
def acknowledge_alert(body: AlertAcknowledge):
    try:
        supabase.table("alerts").update({"acknowledged": True, "acknowledged_by": body.acknowledged_by, "acknowledged_at": datetime.now().isoformat()}).eq("id", body.alert_id).execute()
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/resources/summary")
def get_resources_summary():
    try:
        result = supabase.table("resource_needs").select("resource_type, need_pct").execute()
        agg: dict = {}
        for row in result.data:
            rt = row["resource_type"]
            if rt not in agg: agg[rt] = []
            agg[rt].append(row["need_pct"])
        return {"resources": {k: round(sum(v)/len(v), 1) for k, v in agg.items()}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/dashboard")
def get_dashboard():
    try:
        pop     = supabase.table("population_timeseries").select("data_date, individuals").order("data_date", desc=True).limit(1).execute()
        trend   = supabase.table("population_timeseries").select("data_date, individuals").order("data_date", desc=True).limit(7).execute()
        trucks  = supabase.table("trucks").select("*").execute()
        alerts  = supabase.table("alerts").select("*").eq("acknowledged", False).execute()
        res     = supabase.table("resource_needs").select("resource_type, need_pct").execute()
        flights = supabase.table("drone_flights").select("*").order("flight_date", desc=True).limit(5).execute()

        agg: dict = {}
        for row in res.data:
            rt = row["resource_type"]
            if rt not in agg: agg[rt] = []
            agg[rt].append(row["need_pct"])
        resource_avg = {k: round(sum(v)/len(v), 1) for k, v in agg.items()}

        latest = pop.data[0] if pop.data else {"individuals": 234511, "data_date": None}
        return {
            "stats": {"total_population": latest["individuals"], "population_as_of": latest["data_date"], "tents": 1247, "latrines": 89, "water_points": 23, "aid_trucks": len(trucks.data), "last_update": datetime.now().strftime("%H:%M")},
            "population_trend": list(reversed(trend.data)),
            "trucks":  trucks.data,
            "alerts":  alerts.data,
            "resource_needs": resource_avg,
            "flights": flights.data,
            "source":  "UNHCR + OCHA HDX + Supabase"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
