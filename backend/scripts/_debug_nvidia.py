"""Ad-hoc: inspect companies that look misclassified."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal
from app.models.company import Company

db = SessionLocal()
names = ["nvidia", "amd", "intel", "qualcomm", "cypress", "sun microsystem",
         "sciencesoft", "crowdstrike", "openedge", "control4", "roberhalf",
         "semiconductor"]

for kw in names:
    rows = db.query(Company).filter(Company.name.ilike(f"%{kw}%")).all()
    for c in rows:
        print(f"  name={c.name!r:45s} domain={c.domain!r:35s} industry={c.industry!r:45s} sector={c.inferred_sector!r:30s} source={c.inferred_sector_source!r}")

db.close()
