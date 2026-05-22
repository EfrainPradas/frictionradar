import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Friction Radar"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/friction_radar")

    # Ascendia database (cross-project read-only for candidate intelligence)
    ASCENDIA_DATABASE_URL: str | None = os.getenv("ASCENDIA_DATABASE_URL")
    ASCENDIA_SUPABASE_URL: str | None = os.getenv("ASCENDIA_SUPABASE_URL")
    ASCENDIA_SUPABASE_KEY: str | None = os.getenv("ASCENDIA_SUPABASE_KEY")

    # Supabase (for REST ops if needed, although we use SQLAlchemy direct for now)
    SUPABASE_URL: str | None = os.getenv("SUPABASE_URL")
    SUPABASE_KEY: str | None = os.getenv("SUPABASE_KEY")
    SUPABASE_SECRET_KEY: str | None = os.getenv("SUPABASE_SECRET_KEY")

    # Security
    FRICTIONRADAR_API_KEY: str = os.getenv("FRICTIONRADAR_API_KEY", "")
    FRICTIONRADAR_VERIFY_SSL: str = os.getenv("FRICTIONRADAR_VERIFY_SSL", "true")
    ALLOWED_ORIGINS: str = os.getenv("ALLOWED_ORIGINS", "")

    DEFAULT_USER_AGENT: str = os.getenv(
        "DEFAULT_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    )

    model_config = {
        "env_file": ".env",
        "case_sensitive": True,
        "extra": "ignore"
    }

settings = Settings()
