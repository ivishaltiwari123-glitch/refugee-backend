-- ============================================================
-- REFUGEE CAMP GIS DASHBOARD — SUPABASE SCHEMA
-- Run this entire file in Supabase → SQL Editor → New Query
-- ============================================================

-- Enable PostGIS extension (Supabase has this built-in)
CREATE EXTENSION IF NOT EXISTS postgis;

-- ============================================================
-- TABLE 1: population_timeseries
-- Source: UNHCR CSV (data_date, individuals)
-- ============================================================
CREATE TABLE IF NOT EXISTS population_timeseries (
  id          SERIAL PRIMARY KEY,
  data_date   DATE NOT NULL UNIQUE,
  individuals INTEGER NOT NULL,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- TABLE 2: population_demographics
-- Source: UNHCR Population file (latest snapshot)
-- ============================================================
CREATE TABLE IF NOT EXISTS population_demographics (
  id              SERIAL PRIMARY KEY,
  snapshot_date   DATE NOT NULL,
  month           INTEGER,
  year            INTEGER,
  male_total      INTEGER,
  female_total    INTEGER,
  children_total  INTEGER,
  uac_total       INTEGER,  -- Unaccompanied children
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- TABLE 3: camp_locations
-- Source: OCHA HDX + manual entry
-- PostGIS geometry column for map rendering
-- ============================================================
CREATE TABLE IF NOT EXISTS camp_locations (
  id            SERIAL PRIMARY KEY,
  name          TEXT NOT NULL,
  zone          TEXT,                    -- Zone A, B, C etc
  camp_type     TEXT DEFAULT 'formal',   -- formal, informal, transit
  population    INTEGER DEFAULT 0,
  capacity      INTEGER DEFAULT 0,
  status        TEXT DEFAULT 'active',   -- active, closed, emergency
  location      GEOMETRY(POINT, 4326),   -- PostGIS point (lng, lat)
  lat           FLOAT,
  lng           FLOAT,
  source        TEXT DEFAULT 'OCHA HDX',
  last_verified DATE,
  created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- Spatial index for fast map queries
CREATE INDEX IF NOT EXISTS camp_locations_gist ON camp_locations USING GIST(location);

-- ============================================================
-- TABLE 4: ai_detections
-- Source: Drone image AI processing (YOLOv8 output)
-- Stores individual detected objects (tents, latrines, etc.)
-- ============================================================
CREATE TABLE IF NOT EXISTS ai_detections (
  id              SERIAL PRIMARY KEY,
  flight_id       TEXT NOT NULL,         -- e.g. 'flight-47'
  object_type     TEXT NOT NULL,         -- tent, latrine, water_point, solar, road
  confidence      FLOAT,                 -- AI confidence 0-1
  location        GEOMETRY(POINT, 4326),
  lat             FLOAT,
  lng             FLOAT,
  properties      JSONB DEFAULT '{}',    -- flexible extra data
  detected_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ai_detections_gist ON ai_detections USING GIST(location);
CREATE INDEX IF NOT EXISTS ai_detections_type ON ai_detections(object_type);
CREATE INDEX IF NOT EXISTS ai_detections_flight ON ai_detections(flight_id);

-- ============================================================
-- TABLE 5: drone_flights
-- Source: Dashboard "New Flight" button
-- ============================================================
CREATE TABLE IF NOT EXISTS drone_flights (
  id            TEXT PRIMARY KEY,        -- e.g. 'flight-47'
  flight_number INTEGER NOT NULL,
  area          TEXT,
  altitude_m    INTEGER DEFAULT 120,
  status        TEXT DEFAULT 'completed', -- planned, in-progress, completed, failed
  coverage_pct  FLOAT,
  image_count   INTEGER DEFAULT 0,
  flight_date   DATE DEFAULT CURRENT_DATE,
  pilot_name    TEXT,
  created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- TABLE 6: resource_needs
-- Source: Field reports + calculated from detections
-- ============================================================
CREATE TABLE IF NOT EXISTS resource_needs (
  id            SERIAL PRIMARY KEY,
  camp_id       INTEGER REFERENCES camp_locations(id),
  resource_type TEXT NOT NULL,           -- water, food, medical, shelter, fuel
  need_pct      FLOAT NOT NULL,          -- 0-100, higher = more urgent
  stock_pct     FLOAT,                   -- current stock level
  recorded_at   TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- TABLE 7: alerts
-- Source: System-generated + field reports
-- ============================================================
CREATE TABLE IF NOT EXISTS alerts (
  id              SERIAL PRIMARY KEY,
  severity        TEXT NOT NULL,         -- critical, warning, info
  zone            TEXT,
  message         TEXT NOT NULL,
  acknowledged    BOOLEAN DEFAULT FALSE,
  acknowledged_by TEXT,
  acknowledged_at TIMESTAMPTZ,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- TABLE 8: trucks
-- Source: GPS tracking system
-- ============================================================
CREATE TABLE IF NOT EXISTS trucks (
  id          TEXT PRIMARY KEY,          -- T1, T2, T3
  name        TEXT NOT NULL,
  status      TEXT DEFAULT 'idle',       -- en-route, delivering, returning, idle
  cargo       TEXT,
  lat         FLOAT,
  lng         FLOAT,
  eta         TEXT,
  updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- ROW LEVEL SECURITY (RLS) — Allow public read, restrict writes
-- ============================================================
ALTER TABLE population_timeseries   ENABLE ROW LEVEL SECURITY;
ALTER TABLE population_demographics ENABLE ROW LEVEL SECURITY;
ALTER TABLE camp_locations          ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_detections           ENABLE ROW LEVEL SECURITY;
ALTER TABLE drone_flights           ENABLE ROW LEVEL SECURITY;
ALTER TABLE resource_needs          ENABLE ROW LEVEL SECURITY;
ALTER TABLE alerts                  ENABLE ROW LEVEL SECURITY;
ALTER TABLE trucks                  ENABLE ROW LEVEL SECURITY;

-- Public read access (anon key can read)
CREATE POLICY "Public read population_timeseries"   ON population_timeseries   FOR SELECT USING (true);
CREATE POLICY "Public read population_demographics" ON population_demographics FOR SELECT USING (true);
CREATE POLICY "Public read camp_locations"          ON camp_locations          FOR SELECT USING (true);
CREATE POLICY "Public read ai_detections"           ON ai_detections           FOR SELECT USING (true);
CREATE POLICY "Public read drone_flights"           ON drone_flights           FOR SELECT USING (true);
CREATE POLICY "Public read resource_needs"          ON resource_needs          FOR SELECT USING (true);
CREATE POLICY "Public read alerts"                  ON alerts                  FOR SELECT USING (true);
CREATE POLICY "Public read trucks"                  ON trucks                  FOR SELECT USING (true);

-- Service role can write (backend only)
CREATE POLICY "Service write population_timeseries"   ON population_timeseries   FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service write population_demographics" ON population_demographics FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service write camp_locations"          ON camp_locations          FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service write ai_detections"           ON ai_detections           FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service write drone_flights"           ON drone_flights           FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service write resource_needs"          ON resource_needs          FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service write alerts"                  ON alerts                  FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service write trucks"                  ON trucks                  FOR ALL USING (auth.role() = 'service_role');

-- ============================================================
-- SEED: Initial drone flights
-- ============================================================
INSERT INTO drone_flights (id, flight_number, area, altitude_m, status, coverage_pct, image_count, flight_date)
VALUES
  ('flight-47', 47, 'North + Central', 120, 'completed', 94, 847, CURRENT_DATE),
  ('flight-46', 46, 'South Zone',      120, 'completed', 88, 612, CURRENT_DATE - 1),
  ('flight-45', 45, 'East + Central',  150, 'completed', 91, 734, CURRENT_DATE - 2),
  ('flight-44', 44, 'West Zone',       100, 'completed', 79, 521, CURRENT_DATE - 3)
ON CONFLICT (id) DO NOTHING;

-- ============================================================
-- SEED: Initial trucks
-- ============================================================
INSERT INTO trucks (id, name, status, cargo, lat, lng, eta)
VALUES
  ('T1', 'Truck Alpha',   'en-route',   'Water + Food', 33.52, 36.28, '14:45'),
  ('T2', 'Truck Bravo',   'delivering', 'Medical',      33.49, 36.33, '15:10'),
  ('T3', 'Truck Charlie', 'returning',  'Empty',        33.54, 36.35, '16:00')
ON CONFLICT (id) DO NOTHING;

-- ============================================================
-- SEED: Initial alerts
-- ============================================================
INSERT INTO alerts (severity, zone, message)
VALUES
  ('critical', 'Zone A', 'Overcrowding — 340% capacity'),
  ('critical', 'Zone C', 'Water supply critically low'),
  ('warning',  'Zone B', 'Latrine capacity at 85%')
;

-- ============================================================
-- SEED: Camp locations (Syria region, from OCHA data)
-- ============================================================
INSERT INTO camp_locations (name, zone, camp_type, population, capacity, lat, lng, location, last_verified)
VALUES
  ('Al-Zaatari North Block', 'Zone A', 'formal', 2840, 2000, 33.515, 36.285, ST_SetSRID(ST_MakePoint(36.285, 33.515), 4326), CURRENT_DATE),
  ('Al-Zaatari South Block', 'Zone B', 'formal', 1920, 2500, 33.492, 36.298, ST_SetSRID(ST_MakePoint(36.298, 33.492), 4326), CURRENT_DATE),
  ('Central Water Station',  'Zone C', 'formal',  340,    0, 33.505, 36.310, ST_SetSRID(ST_MakePoint(36.310, 33.505), 4326), CURRENT_DATE),
  ('East Medical Post',      'Zone D', 'formal',  620,  800, 33.498, 36.325, ST_SetSRID(ST_MakePoint(36.325, 33.498), 4326), CURRENT_DATE),
  ('West Transit Zone',      'Zone E', 'transit', 527,  600, 33.520, 36.270, ST_SetSRID(ST_MakePoint(36.270, 33.520), 4326), CURRENT_DATE)
ON CONFLICT DO NOTHING;

-- ============================================================
-- SEED: Resource needs
-- ============================================================
INSERT INTO resource_needs (camp_id, resource_type, need_pct, stock_pct)
VALUES
  (1, 'water',   67, 33),
  (1, 'food',    45, 55),
  (1, 'medical', 12, 88),
  (2, 'water',   55, 45),
  (2, 'food',    38, 62)
;

-- Done! Check your tables:
SELECT 'Schema created successfully!' AS status;
SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;
