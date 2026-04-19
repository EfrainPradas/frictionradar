"""
Migration runner for Friction Radar.
Runs a specified SQL file (or schema.sql by default) against the configured DATABASE_URL.
"""
import os
import sys
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv(os.path.join("backend", ".env"))

DB_URL = os.environ.get("DATABASE_URL")
if not DB_URL:
    print("Error: DATABASE_URL not set.")
    sys.exit(1)

sql_file = sys.argv[1] if len(sys.argv) > 1 else os.path.join("infra", "supabase", "schema.sql")

engine = create_engine(DB_URL, isolation_level="AUTOCOMMIT")

with open(sql_file, "r", encoding="utf-8") as f:
    sql_script = f.read()

with engine.connect() as conn:
    print(f"Executing: {sql_file}")
    conn.execute(text(sql_script))
    print("Done! Migration successful.")
