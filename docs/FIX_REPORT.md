# Fix Report — Influencer ROI Hunter v2

_Session 2026-06-18. Each entry: **What / Why / Impact / Risks.** IDs map to `PROJECT_AUDIT.md`._

Validation baseline established before any change:
- Backend imports clean: `27 routes`.
- Frontend `npm run build`: green.

Final validation after all changes:
- Backend: **34 tests pass** (`pytest`), app imports with `DeprecationWarning`→error.
- Frontend: `npm run build` green.

---

## C1 — Async event loop no longer blocked by Gemini

**What.** Wrapped every synchronous `google-generativeai` call in `asyncio.to_thread(...)`
inside `utils/brand_matcher.py` (`analyze_influencer_brand_fit`, `generate_campaign_strategy`)
and `utils/ai_detector.py` (`detect_fake_followers`, `analyze_campaign_performance`).

**Why.** These `async def` functions called the blocking SDK directly; in the
`POST /brands/discover` per-influencer loop that froze the entire Uvicorn worker
for the whole request (3 Gemini calls × N influencers, seconds each).

**Impact.** The event loop stays responsive during discovery; other requests
(login, dashboard, health) are no longer starved. Latency of a single discovery
is unchanged, but concurrency is restored.

**Risks.** Thread-pool default size (min(32, cpu+4)) bounds parallel Gemini calls;
acceptable for current load. No behavior change to outputs.

## C2 — `get_current_user` hardened

**What.** `int(sub)` wrapped in try/except (→401 not 500), added `is_active` check
(disabled users get 403), timezone-aware token expiry.

**Why.** Malformed tokens raised `ValueError`→HTTP 500; deactivated accounts still authenticated.

**Impact.** Auth failures return correct 401/403. Verified by `test_malformed_token_returns_401_not_500`.

**Risks.** None; stricter only.

## C3 — JWT secret + token lifetime centralized

**What.** `utils/security.py` now reads `JWT_SECRET_KEY` (falls back to legacy `SECRET_KEY`),
`JWT_ALGORITHM`, `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`. Known weak/placeholder secrets are
**fatal in production** and warn in dev. `routers/auth.py` stopped hardcoding a 30-min TTL.

**Why.** Forgeable tokens from a shipped placeholder secret; TTL ignored configuration.

**Impact.** Production refuses to boot with an insecure secret. Token lifetime is now
configurable in one place.

**Risks.** Deployments **must** set `JWT_SECRET_KEY` in production (documented in `.env.example`).

## C4 — bcrypt 72-byte limit + password policy

**What.** `_truncate()` clamps passwords to 72 bytes for both hash and verify;
`verify_password` swallows malformed-hash errors. Schema enforces password 8–72 chars,
username 3–50.

**Why.** Passwords >72 bytes raised `ValueError`→HTTP 500 on register/login.

**Impact.** No crash on long inputs; weak/short passwords rejected with 422.
Verified by `test_password_over_72_bytes_does_not_crash` and `test_short_password_rejected`.

**Risks.** Existing hashes remain valid (bcrypt already only used first 72 bytes).

## (bug found via tests) — `predict_campaign_outcome` crash on missing views

**What.** `has_real_views = median_recent_views and ...` returned `None` (not `False`)
when views were absent, so `sum([...])` raised `TypeError`. Coerced all three flags with `bool()`.

**Why.** Discovery's broad `except` swallowed this, silently dropping every
low-data influencer from results — a quiet correctness loss in the core feature.

**Impact.** Low-confidence predictions now compute correctly. Verified by
`test_prediction_low_confidence_without_views_or_aov`.

**Risks.** None; pure logic fix.

## H1 — Real test suite added

**What.** Added `tests/conftest.py` (offline SQLite + TestClient fixtures) and 34 tests
across `test_utils` (benchmarks, CSV parsers), `test_services` (security, ROI), and
`test_api` (auth, campaigns, ownership isolation, dashboard, AI-analysis).

**Why.** Coverage was zero despite README claiming "minimal".

**Impact.** Core ROI math, auth, and tenancy now have a regression net. The suite
already caught one real bug (above).

**Risks.** bcrypt makes the suite ~22s; acceptable.

## H2 — Redis cache wired in

**What.** Rewrote `utils/youtube_cache.py` to be lazy + fail-safe (no-op if Redis down)
and wired `get_cached_videos`/`cache_videos` into `youtube_discovery.get_channel_recent_videos`.

**Why.** The cache module was dead code; every discovery hit YouTube uncached, burning quota.

**Impact.** Repeat lookups of a channel's recent videos are served from Redis (24h TTL),
cutting API calls and latency. Works without Redis (degrades to direct calls).

**Risks.** Stale video stats for up to 24h — acceptable for discovery.

## H3 — `min_engagement_rate` now enforced

**What.** Discovery skips influencers whose measured video engagement rate is below
`request.min_engagement_rate`.

**Why.** The field was accepted and sent by the frontend but silently ignored.

**Impact.** The filter does what the UI implies.

**Risks.** Stricter results; defaults unchanged (field optional).

## H4 — Discovery/campaign input validation

**What.** `InfluencerDiscoveryRequest`: `max_results` 1–50, `num_posts` 1–10, non-negative
bounds, `search_query` ≤200 chars. `CampaignUpdate` metrics ≥0 + status restricted to the
4 valid values via `Literal`. `CampaignBase` budget `>0`, name 1–200.

**Why.** Unbounded fan-out and degenerate inputs (`num_posts=0`, negative metrics, bogus status).

**Impact.** Invalid payloads rejected with 422. Verified by 3 campaign tests.

**Risks.** Clients sending out-of-range values now get 422 instead of silent acceptance.

## H5 — Discovery error handling & transactions

**What.** Replaced `print` with `logger.exception`, added `db.rollback()` on per-influencer
failure, switched the new-influencer insert from `commit` to `flush` so each iteration
commits once.

**Why.** Invisible logs, partial writes on mid-loop failure, and excessive commits.

**Impact.** Cleaner transactions, real logs, no orphaned rows on failure.

**Risks.** None.

## H6 — Pydantic v2 / SQLAlchemy 2.0 deprecations removed

**What.** `.dict()`→`.model_dump()`, `from_orm`→`model_validate`, `class Config`→`model_config`,
`Query(regex=)`→`Query(pattern=)`, `declarative_base` import moved to `sqlalchemy.orm`.

**Why.** Deprecation warnings; future hard breaks.

**Impact.** App imports cleanly under `DeprecationWarning`→error.

**Risks.** None.

## H7 — Frontend resilience (partial)

**What.** Added `components/ErrorBoundary.tsx` wrapping all routes.

**Why.** An unhandled render error blanked the whole app; no global error UI existed.

**Impact.** Render failures show a recoverable fallback instead of a white screen.

**Risks.** Does not catch async/data-fetch errors (those still surface per-page). Token-refresh
and a toast system remain open (see ROADMAP P1).

## M1 — DB connection resilience

**What.** `pool_pre_ping=True` + `pool_recycle=1800` for non-SQLite engines.

**Why.** Stale-connection `OperationalError` after Postgres idle timeout.

**Impact.** Dropped connections recovered transparently.

**Risks.** Negligible per-checkout ping overhead.

## M2 — Schema source of truth

**What.** `create_all` now runs only when `ENVIRONMENT != production`; Alembic owns prod schema.

**Why.** Dual source-of-truth let `create_all` mask missing migrations and drift defaults.

**Impact.** Local/test stays zero-setup; production schema is migration-driven.

**Risks.** Production deploys must run `alembic upgrade head` (documented).

## M3 — Logging instead of print

**What.** App-wide `logging.basicConfig` in `main.py`; converted all `print()` in
`youtube_discovery.py` and `youtube_cache.py` to `logging`.

**Why.** Unstructured stdout, no levels.

**Impact.** Configurable via `LOG_LEVEL`; clean stdout.

**Risks.** None.

## M4 — Analytics top/worst overlap fixed

**What.** Worst performers now drawn from `measured[5:]` so they never overlap top-5.

**Why.** When 5 < n ≤ 10 the same campaign appeared in both lists.

**Impact.** Distinct top/worst lists.

**Risks.** None.

## M5 — Recommendation JSON key consistency

**What.** Tier JSON uses `estimated_cost` (matching README) instead of `cost_range`.

**Why.** Write/contract mismatch.

**Impact.** Stored recommendations match the documented shape.

**Risks.** None (no existing reader depended on `cost_range`).

## L4 — AI campaign analysis endpoint exposed

**What.** New `GET /api/v1/campaigns/{id}/ai-analysis` calling the previously-unwired
`analyze_campaign_performance`; requires recorded actuals (400 otherwise). Added
`campaignsAPI.aiAnalysis` on the frontend.

**Why.** A built AI feature was unreachable.

**Impact.** Post-campaign AI insights are now available to the UI. Verified by
`test_ai_analysis_requires_metrics`.

**Risks.** Costs a Gemini call; gated behind "metrics recorded" + auth.

## L5 / M6 — CORS + env hygiene

**What.** `allow_credentials=False` (bearer-only auth needs no cookies); added
`backend/.env.example` and `frontend/.env.example`.

**Why.** Unnecessary credentials mode; no documented env template.

**Impact.** Tighter CORS; reproducible setup.

**Risks.** If cookie auth is added later, re-enable credentials.
