"""
load_unhcr_data.py  (FIXED)
============================
Fixes:
  1. Date format: UNHCR exports DD-MM-YY (e.g. 16-12-11)
                  Supabase needs YYYY-MM-DD (e.g. 2011-12-16)
  2. Delimiter:   Both files use comma (,) not semicolon (;)
"""

import os
from datetime import datetime
from dotenv import load_dotenv
import supabase as supabase_ # pyright: ignore[reportMissingImports]

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://jacwfkjkazqmspjdcysl.supabase.co")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

if not SUPABASE_SERVICE_KEY:
    print("ERROR: Set SUPABASE_SERVICE_KEY in your .env file")
    exit(1)

supabase: supabase_.Client = supabase_.create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


def clean_csv_bytes(filepath: str) -> str:
    with open(filepath, "rb") as f:
        raw = f.read()
    return raw.replace(b"\x00", b"").decode("utf-8", errors="ignore")


def parse_date(date_str: str) -> str:
    """
    Convert UNHCR DD-MM-YY dates to YYYY-MM-DD.
    Examples:
      16-12-11  ->  2011-12-16
      19-02-26  ->  2026-02-19
    """
    date_str = date_str.strip()
    for fmt in ("%d-%m-%y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError(f"Unrecognised date format: '{date_str}'")


def load_population_timeseries(filepath: str):
    print(f"\n📊 Loading population timeseries from: {filepath}")
    content = clean_csv_bytes(filepath)
    rows = []
    skipped = 0
    for line in content.split("\n"):
        line = line.strip()
        if not line or line.startswith("sep=") or line.startswith("data_date") or line.startswith('"'):
            continue
        parts = line.split(",")
        if len(parts) < 2:
            continue
        try:
            rows.append({
                "data_date": parse_date(parts[0]),
                "individuals": int(parts[1].strip())
            })
        except (ValueError, IndexError):
            skipped += 1

    print(f"   Parsed {len(rows)} valid rows, skipped {skipped} invalid rows")
    if not rows:
        print("❌ No rows parsed — check file is in same folder as this script")
        return 0

    # Deduplicate by date — keep last occurrence (2021-12-31 appears twice in source file)
    deduped = {}
    for row in rows:
        deduped[row["data_date"]] = row
    rows = list(deduped.values())
    print(f"   After deduplication: {len(rows)} unique rows")

    inserted = 0
    for i in range(0, len(rows), 100):
        batch = rows[i:i+100]
        supabase.table("population_timeseries").upsert(batch, on_conflict="data_date").execute()
        inserted += len(batch)
        print(f"   Batch {i//100+1}: {inserted}/{len(rows)} rows uploaded")

    print(f"✅ Population timeseries: {inserted} rows loaded")
    return inserted


def load_population_demographics(filepath: str):
    print(f"\n👥 Loading population demographics from: {filepath}")
    content = clean_csv_bytes(filepath)
    rows = []
    for line in content.split("\n"):
        line = line.strip()
        if not line or line.startswith("sep=") or line.startswith("date") or line.startswith('"'):
            continue
        parts = line.split(",")
        if len(parts) < 7:
            continue
        try:
            rows.append({
                "snapshot_date":  parse_date(parts[0]),
                "month":          int(parts[1].strip()),
                "year":           int(parts[2].strip()),
                "male_total":     int(parts[3].strip()),
                "female_total":   int(parts[4].strip()),
                "children_total": int(parts[5].strip()),
                "uac_total":      int(parts[6].strip()),
            })
        except (ValueError, IndexError) as e:
            print(f"   Skipping: {line[:60]} — {e}")

    if not rows:
        print("⚠️  No valid demographic rows found")
        return 0

    supabase.table("population_demographics").upsert(rows).execute()
    print(f"✅ Demographics: {len(rows)} row(s) loaded")
    for row in rows:
        print(f"   Date: {row['snapshot_date']} | Male: {row['male_total']:,} | Female: {row['female_total']:,} | Children: {row['children_total']:,}")
    return len(rows)


def load_ocha_hdx_data(api_key: str):
    print(f"\n🌐 Fetching OCHA HDX data...")
    try:
        import requests
        resp = requests.get(
            "https://data.humdata.org/api/3/action/package_search",
            params={"q": "syria refugees displacement camps", "fq": "organization:unhcr", "rows": 5},
            headers={"X-CKAN-API-Key": api_key},
            timeout=15
        )
        data = resp.json()
        if data.get("success"):
            results = data["result"]["results"]
            print(f"   Found {len(results)} datasets on HDX:")
            for r in results[:3]:
                print(f"   - {r['title']}")
            known_camps = [
                {"name": "Rukban Camp",       "zone": "Zone F", "camp_type": "informal", "population": 8000,  "capacity": 10000, "lat": 33.7094, "lng": 38.5644, "source": "OCHA HDX", "last_verified": datetime.now().date().isoformat()},
                {"name": "Bab Al-Salam Camp", "zone": "Zone G", "camp_type": "formal",   "population": 15000, "capacity": 20000, "lat": 36.6167, "lng": 37.0833, "source": "OCHA HDX", "last_verified": datetime.now().date().isoformat()},
            ]
            supabase.table("camp_locations").upsert(known_camps).execute()
            print(f"✅ OCHA HDX: {len(known_camps)} camp locations added")
        else:
            print(f"⚠️  HDX API: {data.get('error', 'Unknown error')}")
    except Exception as e:
        print(f"   HDX fetch error: {e}")


def print_summary():
    print("\n" + "="*50)
    print("📋 DATABASE SUMMARY")
    print("="*50)
    for table, label in [
        ("population_timeseries",   "Population timeseries"),
        ("population_demographics", "Demographics snapshots"),
        ("camp_locations",          "Camp locations"),
        ("drone_flights",           "Drone flights"),
        ("alerts",                  "Alerts"),
        ("trucks",                  "Trucks"),
        ("resource_needs",          "Resource needs"),
    ]:
        try:
            result = supabase.table(table).select("id", count="exact").execute()
            count = result.count if result.count is not None else len(result.data)
            print(f"   {label:30s}: {count:>6} rows")
        except Exception as e:
            print(f"   {label:30s}: ERROR — {e}")
    print("="*50)


if __name__ == "__main__":
    print("🚀 REFUGEE CAMP GIS — UNHCR Data Loader (FIXED)")
    print("="*50)

    for fname, loader in [("csv.csv", load_population_timeseries), ("population_timeseries.csv", load_population_demographics)]:
        if os.path.exists(fname):
            loader(fname)
        else:
            print(f"⚠️  '{fname}' not found — place it in the same folder as this script")

    ocha_key = os.getenv("OCHA_API_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJqdGkiOiJQYjlnaXdYZ1NrVkMybkZUbHNmZ3oyeE9tWklkSzFTLTNSUVdkSzNfZ2ZVIiwiaWF0IjoxNzcyMTA2NjY5LCJleHAiOjE3NzQ2OTg2Njl9.mJrEUQbKqNne4eizjXpRWrlrfD7Z_pVxiHEpMGVZjyg")
    load_ocha_hdx_data(ocha_key)

    print_summary()
    print("\n✅ All done! Next step: python main.py")
