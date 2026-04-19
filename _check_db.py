"""Quick DB health check."""
from dotenv import load_dotenv
load_dotenv("C:/Ubuntu/home/efraiprada/frictionradar/backend/.env")
import sys
sys.path.insert(0, "C:/Ubuntu/home/efraiprada/frictionradar/backend")
from app.db.session import SessionLocal
from sqlalchemy import text

db = SessionLocal()
try:
    r = db.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name"))
    tables = [row[0] for row in r]
    print("Tables:", tables)

    for tbl in ["companies", "company_signals", "company_job_roles", "hiring_patterns",
                "friction_scores", "opportunity_hypotheses", "collection_runs"]:
        try:
            r = db.execute(text(f"SELECT COUNT(*) FROM {tbl}"))
            print(f"  {tbl}: {r.scalar()} rows")
        except Exception as e:
            db.rollback()
            print(f"  {tbl}: MISSING ({e})")
except Exception as e:
    print("DB ERROR:", e)
finally:
    db.close()
