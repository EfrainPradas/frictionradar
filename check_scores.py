import os

os.environ["DATABASE_URL"] = (
    "postgresql://postgres:Pr%40d4.2026.**@db.jfazmprkjzefnhauzqbn.supabase.co:5432/postgres"
)
import sys

sys.path.insert(0, "C:/Ubuntu/home/efraiprada/frictionradar/backend")

from sqlalchemy import create_engine, text

engine = create_engine(os.environ["DATABASE_URL"])

print("=== Actual DB columns ===")
with engine.connect() as conn:
    result = conn.execute(
        text("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'friction_scores'
        ORDER BY ordinal_position
    """)
    )
    for row in result:
        print(f"  {row[0]}: {row[1]}")

print("\n=== Latest scores for Nike ===")
with engine.connect() as conn:
    result = conn.execute(
        text("""
        SELECT * FROM friction_scores 
        WHERE company_id = '43dd96ab-c1ee-453b-a3c0-9a255fdd1197'
        ORDER BY computed_at DESC LIMIT 3
    """)
    )
    for row in result:
        print(f"  {row}")
