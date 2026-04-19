import sys
import os

os.environ["DATABASE_URL"] = (
    "postgresql://postgres:Pr%40d4.2026.**@db.jfazmprkjzefnhauzqbn.supabase.co:5432/postgres"
)
sys.path.insert(0, "C:/Ubuntu/home/efraiprada/frictionradar/backend")

from fastapi.testclient import TestClient
from main import app
from app.db.session import SessionLocal
from app.models.company import Company

client = TestClient(app)
db = SessionLocal()

company = db.query(Company).filter(Company.domain == "nike.com").first()

if company:
    print(f"Company ID: {company.id}")

    # Trigger scoring via API
    response = client.post(f"/api/v1/companies/{company.id}/score")
    print(f"Score response: {response.status_code}")

    if response.status_code == 200:
        score = response.json()
        print(f"Total score: {score.get('total_score')}")
        print(f"Dominant: {score.get('dominant_friction_type')}")
        print(f"Breakdown: {score.get('scoring_breakdown_json')}")
    else:
        print(f"Error: {response.text}")

db.close()
