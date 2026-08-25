# AI Changelog

Chronological log of autonomous changes. Newest first.

---

## 2026-06-18 — Autonomous CTO audit + hardening pass

**Scope.** Full audit, fixed all Critical + most High/Medium issues, added the first
real test suite, wired one previously-dead AI feature, produced project docs.

### Backend
- **C1** Offloaded all synchronous Gemini calls to `asyncio.to_thread` (no longer blocks
  the event loop during discovery). — `utils/brand_matcher.py`, `utils/ai_detector.py`
- **C2** Hardened `get_current_user`: malformed token → 401 (not 500), `is_active` enforced,
  timezone-aware expiry. — `utils/security.py`
- **C3** Centralized JWT config; weak/placeholder secret is fatal in production; removed
  hardcoded 30-min TTL. — `utils/security.py`, `routers/auth.py`
- **C4** bcrypt 72-byte truncation + password/username length policy. — `utils/security.py`, `schemas.py`
- **Bug** Fixed `predict_campaign_outcome` `TypeError` when `median_recent_views` missing
  (was silently dropping low-data influencers). — `utils/benchmarks.py`
- **H2** Rewrote + wired Redis cache for YouTube recent-videos (fail-safe). — `utils/youtube_cache.py`, `utils/youtube_discovery.py`
- **H3** Enforced `min_engagement_rate` in discovery. — `routers/brands.py`
- **H4** Input validation on discovery + campaign schemas. — `schemas.py`
- **H5** Discovery: logging + rollback-on-failure + single commit/iteration. — `routers/brands.py`
- **H6** Removed Pydantic v2 / SQLAlchemy 2.0 deprecations. — routers, `schemas.py`, `database.py`
- **M1** `pool_pre_ping` + `pool_recycle`. — `database.py`
- **M2** `create_all` dev-only; Alembic owns prod schema. — `main.py`
- **M3** App-wide logging; removed `print()` from discovery/cache. — `main.py`, `utils/*`
- **M4** Fixed top/worst performer list overlap. — `routers/analytics.py`
- **M5** Recommendation tier JSON uses `estimated_cost`. — `routers/brands.py`
- **L4** New `GET /campaigns/{id}/ai-analysis` (post-campaign AI insights). — `routers/campaigns.py`
- **L5** CORS `allow_credentials=False` (bearer-only). — `main.py`

### Frontend
- **H7** Added `ErrorBoundary` around all routes. — `components/ErrorBoundary.tsx`, `App.tsx`
- Added `campaignsAPI.aiAnalysis`. — `lib/api.ts`

### Tests (new)
- `tests/conftest.py` (offline SQLite + TestClient + authed-client fixtures).
- 34 tests: benchmarks, CSV parsers, security, ROI math, auth flow, campaign CRUD,
  ownership isolation, dashboard aggregation, AI-analysis gating.

### Docs (new)
- `docs/PROJECT_AUDIT.md`, `docs/FIX_REPORT.md`, `docs/GAP_ANALYSIS.md`,
  `docs/ROADMAP.md`, this changelog.
- `backend/.env.example`, `frontend/.env.example`.

### Validation
- `pytest`: **34 passed**.
- `npm run build`: green.
- App import under `DeprecationWarning`→error: clean.
