"""Quick test: run the full pipeline for one company that previously had 0 signals."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "backend"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / "backend" / ".env")

from app.db.session import SessionLocal
from app.services.collection_orchestrator import run_collection_for_company, extract_careers_evidence
from app.models.company import Company
from app.models.collection_run import CollectionRun
from app.schemas.company import CompanyCreate
from app.services import company_service
from app.services.scoring_engine import compute_and_persist_score
from uuid import uuid4
from datetime import datetime, timezone

# Test with Bluehost (had 0 signals)
TEST_DOMAIN = "bluehost.com"
TEST_NAME = "Bluehost"

db = SessionLocal()
try:
    company = company_service.find_by_domain(db, TEST_DOMAIN)
    if not company:
        company = company_service.create_company(
            db,
            CompanyCreate(name=TEST_NAME, domain=TEST_DOMAIN, source_added_from="test"),
        )
    print(f"Company: {company.name} (id={company.id})")

    # Run sync collectors
    run = CollectionRun(
        company_id=company.id,
        collector_type="test",
        status="pending",
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    result = run_collection_for_company(db, company.id, run.id)
    print(f"Sync collection: {result}")

    # Run Playwright extraction
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        open_pos = loop.run_until_complete(
            extract_careers_evidence(db, company.id, TEST_DOMAIN)
        )
        print(f"Playwright: open_positions={open_pos}")
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except:
            pass
        loop.close()

    # Count signals
    from app.models.company_signal import CompanySignal
    signals = db.query(CompanySignal).filter(CompanySignal.company_id == company.id).all()
    print(f"Total signals: {len(signals)}")
    for s in signals:
        print(f"  [{s.source_type}] {s.signal_type}: {s.signal_text[:80]}")

    # Score
    score = compute_and_persist_score(db, company.id, open_positions_count=open_pos)
    print(f"Friction score: {score.total_score} ({score.dominant_friction_type})")

except Exception as e:
    import traceback
    traceback.print_exc()
finally:
    db.close()
