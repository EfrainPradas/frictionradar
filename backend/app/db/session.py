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

# Ascendia database engine (read-only cross-project)
ascendia_engine = None
AscendiaSessionLocal = None

if settings.ASCENDIA_DATABASE_URL:
    ascendia_engine = create_engine(
        settings.ASCENDIA_DATABASE_URL,
        pool_pre_ping=True,
        max_overflow=5,
        pool_size=2,
    )
    AscendiaSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=ascendia_engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_ascendia_db():
    if not AscendiaSessionLocal:
        return None
    db = AscendiaSessionLocal()
    try:
        return db
    finally:
        db.close()
