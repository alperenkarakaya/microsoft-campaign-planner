import os
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import engine, Base
from routers import influencers, campaigns, auth, analytics, brands, roster, enrichment, campaign_intelligence


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("influencer_roi_hunter")

ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Alembic owns the schema in production (`alembic upgrade head`). For local
    # dev / tests we auto-create tables so a fresh checkout runs without setup.
    if ENVIRONMENT != "production":
        Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Influencer ROI Hunter API",
    description="Influencer kampanya analiz ve ROI hesaplama sistemi",
    version="2.0.0",
    lifespan=lifespan,
)


# CORS_ORIGINS is a comma-separated list of allowed origins. Falls back to the
# local Vite dev server so a fresh checkout keeps working without extra setup.
_cors_raw = os.getenv("CORS_ORIGINS") or os.getenv("FRONTEND_URL") or "http://localhost:3000,http://localhost:3001"
try:
    _parsed = json.loads(_cors_raw)
    cors_origins = [_parsed] if isinstance(_parsed, str) else list(_parsed)
except (json.JSONDecodeError, TypeError):
    cors_origins = [o.strip() for o in _cors_raw.split(",") if o.strip()]

logger.info("CORS allowed origins: %s", cors_origins)

# Auth is via Authorization: Bearer header (not cookies), so credentials mode is
# unnecessary; disabling it keeps the policy tight.
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(influencers.router, prefix="/api/v1/influencers", tags=["Influencers"])
app.include_router(campaigns.router, prefix="/api/v1/campaigns", tags=["Campaigns"])
app.include_router(analytics.router, prefix="/api/v1/analytics", tags=["Analytics"])
app.include_router(brands.router, prefix="/api/v1/brands", tags=["Brand Discovery"])
app.include_router(roster.router, prefix="/api/v1/roster", tags=["Roster Intelligence"])
app.include_router(enrichment.router, prefix="/api/v1/enrichment", tags=["Enrichment Pipeline"])
# AI Campaign Intelligence layer — same prefix as campaigns.router (a second
# router mounted at /api/v1/campaigns) so campaigns.py itself stays untouched.
app.include_router(campaign_intelligence.router, prefix="/api/v1/campaigns", tags=["Campaign Intelligence"])
app.include_router(campaign_intelligence.assistant_router, prefix="/api/v1/assistant", tags=["AI Assistant"])



@app.get("/")
async def root():
    return {
        "message": "Influencer ROI Hunter API v2",
        "status": "running",
        "docs": "/docs"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "influencer-roi-hunter"}