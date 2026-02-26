# Refugee Camp GIS Dashboard — Backend

FastAPI + Supabase backend serving real UNHCR + OCHA HDX data.

## Setup (5 steps)

### Step 1 — Run SQL schema in Supabase
1. Go to supabase.com → your project → SQL Editor
2. Click "New Query"  
3. Paste the entire contents of `schema.sql`
4. Click "Run"
5. You should see "Schema created successfully!"

### Step 2 — Get your service_role key
1. Supabase → Settings → API
2. Copy the `service_role` key (NOT the anon key)
3. Open `.env.example` → copy it to `.env`
4. Paste your service_role key as `SUPABASE_SERVICE_KEY`

### Step 3 — Install Python dependencies
```bash
pip install -r requirements.txt
```

### Step 4 — Load UNHCR data into Supabase
Place your CSV files in this folder:
- `csv` — UNHCR timeseries (data_date;individuals)
- `Population` — UNHCR demographics

Then run:
```bash
python load_unhcr_data.py
```

You should see 996 rows loaded into `population_timeseries`.

### Step 5 — Start the API server
```bash
uvicorn main:app --reload --port 8000
```

Open: http://localhost:8000/docs — interactive API explorer

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/dashboard` | All dashboard data in one call |
| GET | `/api/population/latest` | Latest population count |
| GET | `/api/population/trend?days=30` | Population trend chart data |
| GET | `/api/population/timeseries` | Full UNHCR timeseries |
| GET | `/api/camps` | All camp locations |
| GET | `/api/detections/stats` | AI detection counts |
| GET | `/api/trucks` | Live truck positions |
| GET | `/api/alerts` | Active alerts |
| POST | `/api/alerts/acknowledge` | Acknowledge an alert |
| POST | `/api/flights` | Create new drone flight |
| GET | `/health` | Health check |

---

## Connect Frontend to Backend

Add to your frontend `.env`:
```
VITE_API_URL=http://localhost:8000
```

Copy `apiClient.ts` to `src/data/apiClient.ts` in your frontend project.

Then in your Zustand store, replace fake data calls with:
```typescript
import { getDashboardData } from '../data/apiClient'

// In your store's loadData action:
const data = await getDashboardData()
set({ stats: data.stats, trucks: data.trucks, ... })
```

---

## Deploy to Vercel

1. Push this folder to a GitHub repo
2. Go to vercel.com → New Project → import your repo  
3. Set these environment variables in Vercel:
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_KEY`
   - `OCHA_API_KEY`
4. Deploy — your API will be at `https://your-project.vercel.app`
5. Update frontend `.env`: `VITE_API_URL=https://your-project.vercel.app`

## File Structure

```
refugee-backend/
├── main.py              ← FastAPI app (all endpoints)
├── load_unhcr_data.py   ← One-time data loader script
├── schema.sql           ← Run this in Supabase SQL Editor
├── apiClient.ts         ← Copy to frontend src/data/
├── requirements.txt     ← Python dependencies
├── .env.example         ← Copy to .env, fill in keys
└── README.md
```
