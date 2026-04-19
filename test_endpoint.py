import asyncio
import sys
import json
import os

os.environ["DATABASE_URL"] = (
    "postgresql://postgres:Pr%40d4.2026.**@db.jfazmprkjzefnhauzqbn.supabase.co:5432/postgres"
)

sys.path.insert(0, "C:/Ubuntu/home/efraiprada/frictionradar/backend")

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

response = client.post(
    "/api/v2/extract-careers-page",
    json={"domain": "nike.com", "careers_url": "https://careers.nike.com"},
)

print(f"Status: {response.status_code}")

if response.status_code == 200:
    data = response.json()
    ext = data.get("extraction", {})
    print(f"Page type: {ext.get('page_type')}")
    print(f"Open positions: {ext.get('open_positions_count')}")
    print(f"Job cards: {len(ext.get('visible_role_cards', []))}")
    print(f"Hiring areas: {ext.get('visible_hiring_areas', [])[:5]}")
    print(f"Evidence quality: {ext.get('evidence_quality')}")
    print(f"Source of truth: {data.get('source_of_truth')}")
    print(f"Source details: {data.get('source_details')}")
    print(f"DB warning: {data.get('db_warning', 'None')}")

    with open(
        "C:/Ubuntu/home/efraiprada/frictionradar/result_nike.json",
        "w",
        encoding="utf-8",
    ) as f:
        f.write(json.dumps(data, indent=2, ensure_ascii=False))
else:
    print(f"Error: {response.text[:1000]}")
