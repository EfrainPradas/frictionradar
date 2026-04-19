import os

os.environ["DATABASE_URL"] = (
    "postgresql://postgres:Pr%40d4.2026.**@db.jfazmprkjzefnhauzqbn.supabase.co:5432/postgres"
)
import sys

sys.path.insert(0, "C:/Ubuntu/home/efraiprada/frictionradar/backend")

from sqlalchemy import create_engine, text

engine = create_engine(os.environ["DATABASE_URL"])

# Delete all scores for Nike except the 8.0 one
with engine.connect() as conn:
    conn.execute(
        text("""
        DELETE FROM friction_scores 
        WHERE company_id = '43dd96ab-c1ee-453b-a3c0-9a255fdd1197'
        AND total_score != 8.0
    """)
    )
    conn.commit()
    print("Deleted old scores")

# Verify only 8.0 remains
with engine.connect() as conn:
    result = conn.execute(
        text("""
        SELECT total_score, dominant_friction_type, computed_at 
        FROM friction_scores 
        WHERE company_id = '43dd96ab-c1ee-453b-a3c0-9a255fdd1197'
        ORDER BY computed_at DESC
    """)
    )
    print("\nRemaining scores:")
    for row in result:
        print(f"  Score: {row[0]}, Type: {row[1]}, Time: {row[2]}")
