from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

# Usually Supabase handles pool sizing nicely with connection pooler port (6543)
# We will use the standard engine setup.
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    max_overflow=10,
    pool_size=5
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
