import glob
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse

from app.api.routers import (
    companies,
    signals,
    scoring,
    hypothesis,
    collection,
    health,
    analysis,
    hiring,
    careers_v2,
    validation,
    dashboard,
    pipeline,
)
from app.core.logging import setup_logging

# Enable structured logging
setup_logging()

app = FastAPI(
    title="Friction Radar API",
    description="API for analyzing companies and detecting operational friction",
    version="0.4.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health
app.include_router(health.router, prefix="/health", tags=["Health"])

# Core data
app.include_router(companies.router, prefix="/api/v1/companies", tags=["Companies"])

# Signals (nested under companies)
app.include_router(signals.router, prefix="/api/v1", tags=["Signals"])

# Collection
app.include_router(collection.router, prefix="/api/v1", tags=["Collection"])

# Intelligence layer
app.include_router(scoring.router, prefix="/api/v1", tags=["Scoring"])
app.include_router(hypothesis.router, prefix="/api/v1", tags=["Hypothesis"])

# Analysis orchestration
app.include_router(analysis.router, prefix="/api/v1", tags=["Analysis"])

# Hiring Intelligence
app.include_router(hiring.router, prefix="/api/v1", tags=["Hiring"])

# Careers V2 Pipeline
app.include_router(careers_v2.router, prefix="/api/v2", tags=["Careers V2"])

# Validation
app.include_router(validation.router, prefix="/api/v1", tags=["Validation"])

# Dashboard (bulk stats)
app.include_router(dashboard.router, prefix="/api/v1", tags=["Dashboard"])

# Commercial Pipeline (internal review workflow)
app.include_router(pipeline.router, prefix="/api/v1", tags=["Pipeline"])


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")


@app.get("/heatmap", include_in_schema=False)
def heatmap_latest():
    """Serve the most recent friction_heatmap_*.html from output/."""
    files = sorted(glob.glob(os.path.join("output", "friction_heatmap_*.html")))
    if not files:
        raise HTTPException(
            status_code=404,
            detail="No heatmap found. Run: python scripts/gen_friction_heatmap.py",
        )
    return FileResponse(files[-1], media_type="text/html")
