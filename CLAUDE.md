# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Backend

```bash
cd backend
pip install -r requirements.txt
pytest                                           # run all 259 tests (offline, SQLite)
pytest tests/test_api/test_auth.py              # single file
pytest tests/test_api/test_auth.py::test_login  # single test
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
alembic upgrade head
```

### Frontend

```bash
cd frontend
npm install
npm run dev      # Vite dev server on port 3000, proxies /api to :8000
npm run build    # TypeScript check + Vite build
npm run lint     # ESLint, zero warnings allowed
```

### Docker (full stack)

```bash
docker compose up --build    # Postgres 15 + Redis 7 + FastAPI backend
# Then separately: cd frontend && npm run dev
```

### Roster CLI (data ingestion)

```bash
cd backend
python ingest_roster.py import <xlsx>   # parse spreadsheet → upsert Influencer rows
python ingest_roster.py resolve         # @handle → YouTube channel_id
python ingest_roster.py pipeline        # run Phases 1-3 enrichment
python ingest_roster.py all <xlsx>      # import + resolve + pipeline in one shot
```

## Architecture

### High-Level

```
Frontend (React/Vite :3000)
  → Axios with Bearer JWT
    → FastAPI backend (:8000)
      → PostgreSQL (ORM + Alembic migrations)
      → Redis (YouTube API response cache, 24h TTL)
      → YouTube Data API v3 (channel stats, videos, comments)
      → Google Gemini 2.5 Flash (trust scoring adjustment, brand-fit)
```

### Backend Structure

All routes are mounted under `/api/v1`. Seven routers in `backend/routers/`:

| Router | Prefix | Purpose |
|--------|--------|---------|
| `auth.py` | `/auth` | JWT register/login/me |
| `influencers.py` | `/influencers` | Creator CRUD |
| `campaigns.py` | `/campaigns` | Campaign management + ROI calc |
| `analytics.py` | `/analytics` | Dashboard aggregates |
| `brands.py` | `/brands` | Brand profiles + Gemini-powered discovery |
| `roster.py` | `/roster` | **Primary endpoint** — trust-ranked creator intelligence |
| `enrichment.py` | `/enrichment` | Batch enrichment pipeline trigger + status polling |
| `campaign_intelligence.py` | `/campaigns` (2nd router, same prefix as `campaigns.py`) + exports `assistant_router` at `/assistant` | **AI Campaign Intelligence** — matching, shortlist, briefs, content, tasks, performance, AI analyst, report, assistant. Additive on top of the single-influencer `Campaign` model; never recomputes Trust Score or Tier — consumes `utils.tiering.compose_creator_intelligence()` as an input. See `utils/ai/`. |

`main.py` uses a lifespan context manager. In non-production environments it auto-creates tables via `Base.metadata.create_all()`; in production, Alembic owns the schema.

### Intelligence Pipeline (the core product)

Enrichment runs in phases, each storing results as JSON blobs on the ORM models:

1. **Signals** (`utils/signals.py`) — deterministic YouTube API metrics: view consistency (CV), like/comment ratios, upload cadence, reply rate, sponsorship detection. Stored on `Influencer.enrichment_signals`. Never fabricates; missing data → `None`.

2. **Trust Scoring** (`utils/trust_scorer.py`) — two-layer: deterministic weighted score (Community Trust 65% + Authority 35%) ± optional Gemini adjustment (±20 pts). Stored on `InfluencerAnalysis.trust_breakdown` where `brand_profile_id IS NULL` (intrinsic row).

3. **Sponsorship Analysis** (`utils/sponsorship_analyzer.py`) — maturity label (mature/emerging/unproven/saturated), integration quality, authenticity. Stored on `InfluencerAnalysis.sponsorship_profile`.

4. **Tiering** (`utils/tiering.py`) — S (trust ≥ 58 + active + reachable) / A (trust ≥ 38) / B (else). Readiness flags (is_active, is_reachable, view_stability) qualify the tier but do not rank.

5. **Brand-Fit Overlay** (`utils/brand_matcher.py`) — optional per-brand pass; creates a second `InfluencerAnalysis` row where `brand_profile_id = <FK>` (non-null).

6. **Orchestration** (`utils/enrichment_pipeline.py`) — `enrich_batch()` runs Phases 1-3 per creator. Called from `POST /enrichment/trigger` as a FastAPI `BackgroundTask`.

7. **AI Campaign Intelligence** (`utils/ai/`) — additive layer consumed by `routers/campaign_intelligence.py`: `campaign_analyzer.py` (NL campaign brief parsing), `campaign_matcher.py` (Campaign Match Score — reads trust/sponsorship from step 4's composed intelligence, never recomputes them), `brief_generator.py` / `content_generator.py` (personalized-per-creator generation), `performance_analyst.py` (grounded what/why/what-next from real `CampaignCreator` actuals only), `report_generator.py` (pure composition), `assistant.py` (single-turn grounded Q&A). Same degrade-without-Gemini discipline as steps 2-3.

### Key Data Model Decisions

- `InfluencerAnalysis` has a **nullable `brand_profile_id`**: NULL rows are intrinsic (trust/sponsorship), non-NULL rows are brand-specific overlays. Query accordingly.
- Enrichment state tracked on `Influencer.enrichment_status` (pending → running → completed/partial/failed).
- All JSON blobs (`enrichment_signals`, `trust_breakdown`, `sponsorship_profile`, `predicted_outcome`) use TEXT columns — schema changes don't require migrations.
- `Influencer.source_handle` / `business_email` / `talent_agency` are roster-import fields (Phase 0).

### Frontend Structure

- **State:** Zustand stores in `src/store/` — `authStore.ts` (token in localStorage, 401 interceptor auto-redirects) and `campaignStore.ts`.
- **API layer:** `src/lib/api.ts` — single Axios instance with request/response interceptors; all endpoint functions exported from here.
- **Auth guard:** `ProtectedRoute.tsx` wraps all authenticated routes.
- **Primary page:** `RosterPage.tsx` — creator table with tier/filter/sort/CSV export, links to `CreatorDetailPage.tsx` for full intelligence drill-down.
- **Types:** `src/lib/types.ts` — `RosterCreator`, `CreatorIntelligence`, `SponsorshipReadiness`, `PredictedOutcome` are the key composite interfaces matching `/roster/intelligence` response.

### Test Environment

Tests use SQLite (no Postgres required, no API keys). `conftest.py` recreates the schema before each test. CI runs `pytest -q` with `ENVIRONMENT=test`.

## Environment Variables

Copy `backend/.env.example` to `backend/.env`. Key vars:

| Variable | Required | Notes |
|----------|----------|-------|
| `DATABASE_URL` | Yes | Postgres in prod, SQLite for tests |
| `JWT_SECRET_KEY` | Yes | Fatal in production if weak |
| `YOUTUBE_API_KEY` | Yes for enrichment | Not needed for tests |
| `GEMINI_API_KEY` | No | Graceful degradation to deterministic-only if absent |
| `CORS_ORIGINS` | Yes | Comma-separated or JSON list |
| `ENVIRONMENT` | Yes | `production` disables auto table creation |

Frontend: copy `frontend/.env.example` to `frontend/.env` and set `VITE_API_URL=http://localhost:8000/api/v1`.

## Known Issues (from docs/)

- `asyncio.run()` inside `BackgroundTask` is unsafe for multi-worker Uvicorn/Gunicorn deploys.
- A-tier is over-populated; trust thresholds may need calibration after LLM comment-quality recalibration.
- Alembic `alembic.ini` references `influencer_db` but Docker/app uses `influencer_roi_db` — override via `DATABASE_URL` env var.
- AI Partnership Assistant (`utils/ai/assistant.py`) is single-turn — no persisted multi-turn chat history or tool-calling agent loop.
- No `PerformanceSnapshot` time-series table — campaign performance is computed live from `CampaignCreator` actuals, so there's no historical trend view yet.
- `npm run lint` fails on a fresh checkout regardless of code changes — no ESLint config file exists in `frontend/`. Use `npm run build` (tsc + vite) as the reliable frontend check.

## Suggested Reading Order

For understanding the core scoring logic: `utils/signals.py` → `utils/trust_scorer.py` → `utils/tiering.py` → `utils/sponsorship_analyzer.py` → `utils/enrichment_pipeline.py` → `routers/roster.py` → `frontend/src/pages/RosterPage.tsx`

For understanding the AI Campaign Intelligence layer built on top of it: `utils/ai/campaign_matcher.py` → `routers/campaign_intelligence.py` → `frontend/src/pages/CampaignIntelligencePage.tsx`
