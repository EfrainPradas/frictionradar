"""Run the schema migration."""
from dotenv import load_dotenv
load_dotenv("backend/.env")
import sys
sys.path.insert(0, "backend")
from app.db.session import engine
from sqlalchemy import text

sql = open("infra/supabase/schema_part4_fix.sql").read()
with engine.begin() as conn:
    conn.execute(text(sql))
    print("Migration complete!")
    r = conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name"))
    for row in r:
        print(" ", row[0])
