# Influencer ROI Hunter v2 — Creator Trust & Partnership Intelligence

> **Note for AI assistants (Claude web, etc.):** This README is the canonical entry point for understanding this project. Read it end-to-end before answering questions or proposing changes.

---

## 1. What this project is

**Influencer ROI Hunter** is a creator intelligence platform for gaming & technology influencer marketing agencies. It evaluates YouTube creators on **audience trust, community depth, sponsorship readiness, and partnership potential** — not follower counts.

The system answers two independent questions for every creator:

1. **How valuable is this creator's audience?** → Trust score + Tier (S / A / B)
2. **How ready is this creator for brand partnerships?** → Sponsorship maturity label (mature / emerging / unproven / saturated)

On top of that intrinsic Creator Trust Intelligence, an **AI Campaign Intelligence** layer answers a third,
campaign-specific question — *"For THIS brand, THIS campaign, and THIS budget, which creators should we
partner with, why, how should we brief them, and what did we learn after running it?"* See §13.

### Core philosophy

- **Trust before reach.** A 150K-subscriber creator with a loyal, engaged audience outranks a 1M-subscriber channel with passive viewers.
- **Deterministic backbone, LLM augments.** Every score starts from measured YouTube signals. AI (Gemini) only adjusts within deterministic bounds and records an `override_reason`. Missing data lowers confidence — it never fabricates a number.
- **Sponsorship readiness is a label, not a gate.** A creator with no sponsorship history but a deeply engaged audience is still Tier S. The maturity label tells the outreach team *how* to approach them, not *whether* to.

### What it is NOT

This is not another Modash, HypeAuditor, or CreatorIQ. It does not compete on creator discovery at scale. It starts from a **curated roster** of hand-vetted creators and builds deep intelligence on each one.

---

## 2. High-level architecture

```
┌──────────────┐         ┌────────────────┐         ┌──────────────┐
│  Frontend    │  HTTP   │   Backend API  │  SQL    │  PostgreSQL  │
│  React + Vite│ ──────▶ │   FastAPI      │ ──────▶ │              │
│  TypeScript  │         │   Python 3.11+ │         └──────────────┘
└──────────────┘         │                │         ┌──────────────┐
                         │                │ ──────▶ │    Redis     │
                         └───────┬────────┘         │   (cache)    │
                                 │                  └──────────────┘
                                 │ HTTP
                  ┌──────────────┴───────────────┐
                  ▼                              ▼
          ┌───────────────┐            ┌──────────────────┐
          │ YouTube Data  │            │  Google Gemini   │
          │   API v3      │            │  (LLM analysis)  │
          └───────────────┘            └──────────────────┘
```

### Intelligence pipeline (six phases)

```
Roster XLSX ──▶ Phase 0: Ingest ──▶ Phase 1: Deterministic Signals
                (121 creators)       (view stats, engagement, cadence,
                                      sponsorship detection, reply rate)
                                            │
                                            ▼
                                    Phase 2: Trust Scoring
                                    (community depth + authority,
                                     deterministic backbone + Gemini)
                                            │
                                            ▼
                                    Phase 3: Sponsorship Analysis
                                    (maturity, quality, integration,
                                     authenticity)
                                            │
                                            ▼
                                    Phase 4: Tiering (S/A/B)
                                    (trust-only, sponsorship = label)
                                            │
                                            ▼
                                    Phase 5: Brand-Fit Overlay
                                    (optional, per-brand, secondary)
                                            │
                                            ▼
                                    Phase 6: Orchestration
                                    (background pipeline, run-state)
                                            │
                                            ▼
                                    AI Campaign Intelligence layer
                                    (additive — matching, briefs, content,
                                     execution, performance, reporting;
                                     see §13. Never recomputes Trust/Tier.)
```

---

## 3. Repository layout

```
influencer-roi-hunter/
├── README.md                       ← you are here
├── docker-compose.yml              ← Postgres + Redis + backend
├── docs/                           ← audit, roadmap, gap analysis
│
├── backend/                        ← FastAPI service
│   ├── main.py                     ← app factory, router wiring, CORS
│   ├── database.py                 ← SQLAlchemy engine + SessionLocal
│   ├── models.py                   ← all ORM models (Influencer, InfluencerAnalysis, etc.)
│   ├── schemas.py                  ← all Pydantic request/response schemas
│   ├── ingest_roster.py            ← CLI: import → resolve → enrich pipeline
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── alembic.ini
│   ├── alembic/versions/           ← 5 migrations (0001–0005)
│   ├── pytest.ini
│   ├── tests/                      ← 259 offline tests
│   │
│   ├── routers/                    ← HTTP endpoints (mounted under /api/v1)
│   │   ├── auth.py                 ← /auth/register, /auth/login
│   │   ├── influencers.py          ← /influencers CRUD
│   │   ├── campaigns.py            ← /campaigns CRUD + ROI metrics
│   │   ├── analytics.py            ← /analytics aggregate stats
│   │   ├── brands.py               ← /brands brand profiles + AI discovery
│   │   ├── roster.py               ← /roster/intelligence — creator intelligence endpoint
│   │   ├── enrichment.py           ← /enrichment/trigger, /enrichment/status
│   │   └── campaign_intelligence.py← AI Campaign Intelligence layer (§13); also exports
│   │                                  assistant_router → /assistant/query. Mounted at the
│   │                                  SAME /campaigns prefix as campaigns.py (2nd router).
│   │
│   └── utils/                      ← service & intelligence modules
│       ├── security.py             ← JWT, password hashing
│       ├── roster_importer.py      ← spreadsheet parser + DB upsert + handle resolver
│       ├── signals.py              ← Phase 1: deterministic YouTube signals
│       ├── trust_scorer.py         ← Phase 2: community trust depth + authority
│       ├── sponsorship_analyzer.py ← Phase 3: maturity, quality, integration, authenticity
│       ├── tiering.py              ← Phase 4: S/A/B tier + readiness + sponsorship_readiness
│       ├── enrichment_pipeline.py  ← Phase 6: orchestration, batch processing
│       ├── brand_matcher.py        ← Gemini brand-fit scoring (secondary layer)
│       ├── benchmarks.py           ← CPM/CTR/CVR tables + campaign prediction (secondary)
│       ├── ai_detector.py          ← fake-follower detection
│       ├── csv_importers.py        ← YouTube Studio / Shopify / Stripe parsers
│       ├── youtube_api.py          ← YouTube Data API v3 client
│       ├── youtube_cache.py        ← Redis cache for YouTube calls + comments
│       ├── youtube_discovery.py    ← keyword/category-based channel search
│       └── ai/                     ← AI Campaign Intelligence services (§13)
│           ├── campaign_analyzer.py    ← NL/structured campaign brief parsing
│           ├── campaign_matcher.py     ← Campaign Match Score (consumes Trust Score, never recomputes it)
│           ├── brief_generator.py      ← personalized-per-creator AI campaign briefs
│           ├── content_generator.py    ← Content Studio generation
│           ├── performance_analyst.py  ← grounded what/why/what-next, no fabrication
│           ├── report_generator.py     ← 13-section campaign report (pure composition)
│           └── assistant.py            ← single-turn grounded AI Partnership Assistant
│
└── frontend/                       ← Vite + React + TypeScript
    ├── package.json
    ├── vite.config.ts
    └── src/
        ├── App.tsx                 ← router, providers
        ├── pages/
        │   ├── RosterPage.tsx      ← creator intelligence table (main agency view)
        │   ├── CreatorDetailPage.tsx← full creator profile + explainability + Campaign Intelligence section
        │   ├── DashboardPage.tsx   ← campaign aggregate stats + AI Opportunities
        │   ├── InfluencersPage.tsx  ← basic influencer library
        │   ├── InfluencerDiscoveryPage.tsx ← AI-powered brand-fit discovery
        │   ├── CampaignsPage.tsx   ← campaign management
        │   ├── CampaignFormPage.tsx
        │   ├── CampaignDetailPage.tsx      ← legacy single-creator ROI view + link to intelligence
        │   ├── CampaignIntelligencePage.tsx← AI Matches / Shortlist / Briefs / Content / Performance / Report tabs
        │   ├── ContentStudioPage.tsx← standalone Content Studio
        │   ├── AIAssistantPage.tsx  ← AI Partnership Assistant
        │   ├── BrandProfilesPage.tsx
        │   ├── BrandProfileFormPage.tsx
        │   ├── AnalyticsPage.tsx
        │   ├── LoginPage.tsx
        │   └── RegisterPage.tsx
        ├── components/
        │   ├── Navbar.tsx
        │   ├── ProtectedRoute.tsx
        │   ├── ErrorBoundary.tsx
        │   ├── StatsCard.tsx
        │   ├── InfluencerCard.tsx
        │   └── CampaignCard.tsx
        ├── store/
        │   ├── authStore.ts        ← Zustand: auth state
        │   └── campaignStore.ts    ← Zustand: campaign state
        └── lib/
            ├── api.ts              ← Axios instance + all endpoint wrappers
            └── types.ts            ← shared TS types (including roster + campaign intelligence)
```

---

## 4. Tech stack

### Backend
- **FastAPI** 0.104 + **Uvicorn**
- **SQLAlchemy** 2.0 + **Alembic** (4 migrations)
- **PostgreSQL** 15 (primary store), **Redis** 7 (YouTube + comment cache)
- **Pydantic** 2.5 for request/response validation
- **python-jose** + **passlib[bcrypt]** for auth
- **google-generativeai** 0.8 (Gemini 2.5 Flash)
- **httpx** for YouTube API calls
- **openpyxl** for roster spreadsheet parsing
- **tenacity** for retry logic on Gemini calls

### Frontend
- **React** 18 + **Vite** 5 + **TypeScript** 5
- **react-router-dom** 6
- **zustand** 4 for client state
- **axios** for HTTP
- Inline JavaScript styles (no CSS framework)

---

## 5. Data model

### Core intelligence models

```
Influencer
  ├── source_handle          (from roster spreadsheet)
  ├── business_email         (from roster)
  ├── talent_agency          (bool, from roster)
  ├── enrichment_signals     (JSON — Phase 1 deterministic signals)
  ├── enrichment_status      (pending/running/completed/partial/failed)
  └── last_enriched_at

InfluencerAnalysis
  ├── trust_breakdown        (JSON — Phase 2, community + authority scores)
  ├── sponsorship_profile    (JSON — Phase 3, maturity + quality + integration)
  ├── brand_profile_id       (NULL for intrinsic, FK for brand-specific)
  └── analyzed_at
```

### Tiering (Model C — computed on read, not stored)

| Tier | Criteria | Meaning |
|------|----------|---------|
| **S** | Trust ≥ 58 + reachable + active | Priority Partner — high audience trust |
| **A** | Trust ≥ 38 | High-Potential — moderate trust |
| **B** | Trust < 38 or gate-failed | Commodity / Nurture |

Sponsorship maturity is a **separate label**, never gates the tier:
- `mature` — regular sponsorship with repeat brands
- `emerging` — early sponsorship experience
- `unproven` — no sponsorship signals detected
- `saturated` — high ad density, ad-fatigue risk

---

## 6. API surface

| Prefix | Router | Purpose |
|--------|--------|---------|
| `/auth` | `auth.py` | Register, login, JWT |
| `/influencers` | `influencers.py` | CRUD on influencer records |
| `/campaigns` | `campaigns.py` | CRUD + ROI metrics + CSV import |
| `/analytics` | `analytics.py` | Dashboard aggregate stats |
| `/brands` | `brands.py` | Brand profiles + AI discovery |
| `/roster` | `roster.py` | **Creator intelligence** — the primary endpoint |
| `/enrichment` | `enrichment.py` | Trigger/monitor batch enrichment |
| `/campaigns/{id}/ai/*`, `/campaigns/{id}/matches`, `/shortlist`, `/creators`, `/brief`, `/content/generate`, `/performance`, `/report` | `campaign_intelligence.py` | **AI Campaign Intelligence** — see §13 |
| `/assistant` | `campaign_intelligence.py` (`assistant_router`) | Single-turn grounded AI Partnership Assistant |

### Key endpoint: `GET /roster/intelligence`

Returns the composed creator-intelligence view sorted by intrinsic quality.

Query params:
- `brand_profile_id` (optional) — adds brand-fit overlay + campaign potential
- `skip` / `limit` — pagination

Response per creator:
- `intelligence`: tier, tier_label, tier_explanation, trust_score, confidence, readiness flags
- `sponsorship_readiness`: label, score, explanation, outreach_implication
- `trust_breakdown`: community trust depth + authority component scores
- `sponsorship_profile`: maturity, quality, integration style, authenticity

---

## 7. Trust scoring system

### Signals (Phase 1 — deterministic, high confidence)

| Signal | What it measures | Source |
|--------|-----------------|--------|
| Like-to-view ratio | Audience approval depth | YouTube video stats (median) |
| Comment-to-view ratio | Audience engagement depth | YouTube video stats (median) |
| View consistency (CV) | Loyal base vs algorithm spikes | Coefficient of variation of recent views |
| View ratio (views/subs) | Audience actually watches | Median views / subscriber count |
| Upload cadence | Publishing consistency | Days between uploads (median) |
| Creator reply rate | Community interaction | commentThreads API sample |
| Sponsorship detection | Brand deal indicators | Description parsing + paidProductPlacement |

### Community Trust Depth (65% of composite)

| Component | Weight | What high means |
|-----------|--------|-----------------|
| Like/View ratio | 25pt | Consistent audience approval (≥4%) |
| Comment/View ratio | 30pt | Deep engagement, not passive viewing (≥0.20%) |
| View consistency CV | 30pt | Loyal subscriber-driven base (CV ≤ 0.30) |
| Sample size | 15pt | Sufficient data to trust the signal |

### Authority (35% of composite)

| Component | Weight | What high means |
|-----------|--------|-----------------|
| Reply rate | 25pt | Creator engages with community |
| Reply sample size | 10pt | Sufficient data |
| Comment depth | 30pt | Active discussion in comments |
| View ratio | 25pt | Audience watches, not just subscribes |

When Gemini is available, LLM comment-authenticity and parasocial-bond scores adjust within ±20 of the deterministic baseline. When unavailable, the system degrades to deterministic-only with lowered confidence.

---

## 8. Recommendation engine

Every creator receives a decision, not just a score:

| Recommendation | Criteria |
|---|---|
| **Strong Buy** | Trust ≥ 65 + mature/emerging sponsorship + zero risks |
| **Buy** | Trust ≥ 58, or trust ≥ 65 with risks |
| **Watchlist** | Trust 38–58 |
| **Avoid** | Trust < 38 |

Risk flags: `volatile_audience` (CV > 0.8), `dormant` (no upload 60+ days), `ad_fatigue` (saturated), `weak_community` (trust < 40), `low_view_ratio` (< 5%).

---

## 9. Running locally

### With Docker (recommended)

```bash
docker compose up --build
```

Brings up Postgres (5432), Redis (6379), and FastAPI backend (8000).

```bash
cd frontend && npm install && npm run dev    # http://localhost:3000
```

### Apply migrations

```bash
cd backend
alembic upgrade head    # applies 0001–0005
```

### Import and enrich the roster

```bash
cd backend

# Step 1 — Import spreadsheet (offline):
python ingest_roster.py import "../YouTube _ Gaming and technology _ English Speaking (USA_EU) _ alperenweb.xlsx"

# Step 2 — Resolve @handles to YouTube channel IDs (needs YOUTUBE_API_KEY):
python ingest_roster.py resolve

# Step 3 — Full pipeline: signals + trust + sponsorship (needs YOUTUBE_API_KEY, optionally GEMINI_API_KEY):
python ingest_roster.py pipeline

# Or all in one:
python ingest_roster.py all "../YouTube _ Gaming and technology _ English Speaking (USA_EU) _ alperenweb.xlsx"
```

Pipeline flags: `--force` (re-enrich all), `--limit N`, `--stale-days N`.

### Environment variables

```
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/influencer_roi_db
REDIS_URL=redis://localhost:6379
YOUTUBE_API_KEY=...
GEMINI_API_KEY=...           # optional; system degrades gracefully without it
JWT_SECRET_KEY=...
CORS_ORIGINS=http://localhost:3000
```

### Tests

```bash
cd backend
pytest                       # 259 tests, all offline (no API keys needed)
```

---

## 10. Frontend — Creator Intelligence UI

### Roster Page (`/roster`)

The daily-use agency tool. A sortable, filterable, searchable table of all creators ranked by audience trust.

- **Columns:** Creator, Tier (S/A/B badge), Trust, Community, Authority, Sponsorship Maturity, Recommendation, Risk Flags, Subscribers, Contact
- **Filters:** Tier, Maturity, Search by name, Bookmarked
- **Sort:** Click any column header
- **Expand:** Click a row to see tier explanation, outreach strategy, top signals, risk details, similar creators
- **Export:** CSV export of filtered/sorted creators
- **Bulk select:** Checkbox selection + export selected
- **Bookmarks:** Star toggle, persisted to localStorage

### Creator Detail Page (`/roster/:id`)

Full intelligence profile for a single creator:

- Identity + decision banner (tier, recommendation, maturity, confidence)
- Community Trust Depth breakdown with component scores and visual bars
- Authority breakdown with component scores
- Sponsorship readiness with outreach implication
- Readiness flags (active/reachable/agency/view stability)
- Risk assessment with explanations
- Decision summary: recommendation reasoning, top signals, concerns
- Similar creators (5 closest by trust/community/authority)

---

## 11. Current state

### What works
- Full intelligence pipeline: 121 creators enriched with deterministic signals + trust + sponsorship
- Trust-driven tiering (Model C): S:33, A:77, B:11
- Sponsorship maturity as independent label with outreach implications
- Recommendation engine (Strong Buy / Buy / Watchlist / Avoid)
- Roster intelligence API with full explainability
- Frontend roster table + detail views with filtering, sorting, export
- 259 backend tests (offline, no API keys)
- Redis caching for YouTube API quota conservation
- Graceful degradation when Gemini/Redis unavailable

### Known limitations
- **YouTube only** — Instagram/TikTok modeled but not implemented
- **LLM comment-authenticity prompt needs recalibration** (P1) — scores 90+ for everything, not discriminative
- **A-tier overload** — 77 of 121 creators (64%) in A; requires LLM fix to spread trust distribution
- **No outreach CRM** — deferred by design; the "Approved" column from the spreadsheet is the hook
- **`asyncio.run()` in BackgroundTasks** — must fix before multi-worker production deploy
- **business_email not exposed in roster API response** — frontend can't show/copy emails yet
- **No mobile responsiveness**
- **AI Partnership Assistant is single-turn** (§13) — no persisted multi-turn chat or tool-calling
  agent loop; each question is answered independently from freshly-resolved grounding data
- **No campaign-level PerformanceSnapshot history** — performance is computed live from
  `CampaignCreator` actuals rather than periodic snapshots, so there's no time-series view yet
- **ESLint has no config file in this repo** — `npm run lint` fails on a fresh checkout with
  "ESLint couldn't find a configuration file" regardless of any code change; `npm run build`
  (tsc + vite) is the reliable frontend check until an `eslint.config.js` is added

---

## 12. Scoring validation results

From the production-readiness audit on the live 121-creator roster:

| Signal | Correlation with Trust | Discriminative Power |
|--------|----------------------|---------------------|
| Comment/View ratio | **+0.689 (strong)** | 2.2x top-vs-bottom |
| View CV | **-0.515 (strong)** | 0.66x (lower = better) |
| Like/View ratio | **+0.539 (strong)** | 1.5x |
| View ratio | +0.321 (moderate) | 1.85x |
| Upload cadence | +0.294 (moderate) | 2.3x |
| Reply rate | +0.248 (weak) | — |
| Subscriber count | **-0.172 (weak negative)** | 0.81x (bigger = worse) |
| Sponsorship score | +0.026 (none) | ~1.0x |

**Key finding:** Subscriber count is weakly negatively correlated with trust. Sponsorship history has zero correlation with audience quality. The architecture's decision to exclude both from tier assignment is empirically validated.

---

## 13. AI Campaign Intelligence layer

Built on top of Creator Trust Intelligence — never replaces it. Two scores are always shown
side by side and never merged: **Trust Score** (intrinsic audience quality, from `tiering.py`)
and **Campaign Match Score** (this creator's fit for one specific campaign). A creator can be
"excellent overall, only a moderate fit for this campaign" or the reverse — that distinction is
the point.

### Workflow

```
Brand Profile → Campaign → AI Understanding (POST .../ai/analyze)
             → AI Creator Matching (POST .../ai/match-creators) → Campaign Match Score + "why"
             → Shortlist (POST .../shortlist) → per-creator execution status (matched → … → completed)
             → AI Brief (POST .../brief) → personalized per creator (content style, not a template)
             → Content Studio (POST /content/generate) → captions, titles, hooks, scripts, ...
             → Tasks (POST .../creators/{id}/tasks) → brief_sent → … → performance_tracking, overdue-aware
             → Performance (GET .../performance) → live aggregation from real actuals only
             → AI Analyst (POST .../ai/analyze-performance) → what happened / why / what next, grounded
             → Report (GET .../report) → 13-section campaign report
```

### Campaign Match Score

`utils/ai/campaign_matcher.py` computes a weighted 0-100 score from: Trust Score (30, straight
passthrough — never recomputed), category fit (20), budget fit (15, from `benchmarks.py`'s
grounded cost estimate), sponsorship-preference fit (15), geographic fit (10), audience-fit (10,
only scored when real demographic data is on file). Missing components are excluded and weights
renormalize, exactly like `trust_scorer.py`'s composite calculation. Every match includes a
deterministic `why` sentence and a `risk_level`.

### No-fabrication discipline

Every AI service in `utils/ai/` follows the same rule as the rest of the app: deterministic
backbone, optional Gemini augmentation, graceful degradation without `GEMINI_API_KEY` (unit-
tested — the whole layer runs and passes its tests with no API keys configured), and missing
data renders as `"Insufficient data"` rather than a guess. `performance_analyst.py` only ever
describes numbers that are actually stored on `CampaignCreator`/`Campaign`.

### Frontend entry points

- `/campaigns/:id/intelligence` — tabbed AI Matches / Shortlist / Briefs / Content / Performance / Report (linked from the existing Campaign Detail page)
- `/content-studio` — standalone Content Studio for any roster creator
- `/assistant` — AI Partnership Assistant
- `CreatorDetailPage` — a "Campaign Intelligence" section appears when opened with `?campaign_id=`, directly below the existing "Creator Intelligence" section, so intrinsic quality and campaign-specific fit are never conflated

---

## 14. Suggested reading order

1. This README
2. `backend/utils/signals.py` — the deterministic signal layer
3. `backend/utils/trust_scorer.py` — how trust is computed
4. `backend/utils/tiering.py` — how S/A/B tiers are assigned
5. `backend/utils/sponsorship_analyzer.py` — sponsorship maturity
6. `backend/utils/enrichment_pipeline.py` — how the pipeline orchestrates
7. `backend/routers/roster.py` — the intelligence API endpoint
8. `frontend/src/pages/RosterPage.tsx` — the agency-facing UI
9. `backend/utils/ai/campaign_matcher.py` — Campaign Match Score (§13)
10. `backend/routers/campaign_intelligence.py` — the AI Campaign Intelligence API
11. `frontend/src/pages/CampaignIntelligencePage.tsx` — the agency-facing AI workflow UI
