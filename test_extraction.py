import asyncio
import sys
import os
import time

os.environ["DATABASE_URL"] = (
    "postgresql://postgres:Pr%40d4.2026.**@db.jfazmprkjzefnhauzqbn.supabase.co:5432/postgres"
)

sys.path.insert(0, "C:/Ubuntu/home/efraiprada/frictionradar/backend")

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

from app.db.session import SessionLocal

db = SessionLocal()

from app.models.company import Company

company = db.query(Company).filter(Company.domain == "nike.com").first()

if company:
    print(f"Company: {company.name} ({company.id})")

    response = client.post(f"/api/v1/companies/{company.id}/collect")
    print(f"Collection response: {response.status_code}")

    # Wait for background task to complete
    print("Waiting for extraction...")
    time.sleep(15)

    # Check signals
    from app.models.company_signal import CompanySignal

    signals = (
        db.query(CompanySignal).filter(CompanySignal.company_id == company.id).all()
    )

    print(f"\nTotal signals: {len(signals)}")
    hybrid = [s for s in signals if s.source_type == "hybrid_careers_v2"]
    print(f"hybrid_careers_v2 signals: {len(hybrid)}")
    for s in hybrid:
        print(f"  - {s.signal_type}: {s.signal_text[:80]}")

db.close()
