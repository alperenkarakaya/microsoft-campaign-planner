# Project Audit — Influencer ROI Hunter v2

_Generated 2026-06-18. Source of truth for project intent: `README.md`._

This audit ranks every issue found across backend, frontend, database, auth, AI
integrations, infra and tooling. Items are tagged with a stable ID (e.g. `C1`,
`H3`) referenced from `FIX_REPORT.md`.

Status legend: ✅ fixed · 🟡 partially addressed · ⬜ open (tracked in `ROADMAP.md`).

---

## Critical

| ID | Area | Issue | Status |
|----|------|-------|--------|
| C1 | Backend / scalability | **Blocking the async event loop.** `utils/ai_detector.py` and `utils/brand_matcher.py` call the *synchronous* `google-generativeai` client (`_gemini_generate`) directly from `async def` handlers. Inside `POST /brands/discover` this happens in a per-influencer loop (3 Gemini calls × N influencers), each blocking 1–10 s. The entire Uvicorn worker is frozen for the whole request, so one discovery call stalls every other user (login, dashboard, health). At any real concurrency the service is unusable. | ✅ |
| C2 | Auth / security | **`get_current_user` crashes on malformed tokens and ignores `is_active`.** `int(user_id)` raises `ValueError` (→ HTTP 500, not 401) when `sub` is non-numeric, and a deactivated user (`is_active=False`) still authenticates fully. | ✅ |
| C3 | Auth / security | **Weak/placeholder JWT secret with silent fallback.** `SECRET_KEY` defaults to a hardcoded string; the committed `.env` even ships `JWT_SECRET_KEY=your-...` placeholder. Tokens are forgeable. There is no fail-fast in production and the token TTL is hardcoded to 30 min in `routers/auth.py`, ignoring the `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` env var. | ✅ |
| C4 | Auth / robustness | **bcrypt 72-byte limit unguarded.** `utils/security.py` uses the raw `bcrypt` lib. Any password longer than 72 bytes raises `ValueError` → HTTP 500 on both register and login instead of a clean validation error. No password-strength/length policy at all. | ✅ |

## High

| ID | Area | Issue | Status |
|----|------|-------|--------|
| H1 | Testing | **Zero test coverage.** `backend/tests/` contains only empty package dirs (`test_api`, `test_services`, `test_utils`) and an `__init__.py`. README claims "minimal coverage" — it is actually none. No CI safety net for ROI math, auth, or CSV parsing. | ✅ |
| H2 | Backend / performance | **Redis cache is dead code.** `utils/youtube_cache.py` is never imported anywhere. Every discovery hits the YouTube Data API uncached (search + channels + playlistItems + videos per channel), burning quota and adding seconds of latency. README claims YouTube calls are "Cached in Redis". | ✅ |
| H3 | Backend / API contract | **`min_engagement_rate` accepted but ignored.** `InfluencerDiscoveryRequest.min_engagement_rate` is in the schema and the frontend sends it, but `POST /brands/discover` never applies it. Silent no-op → misleading UX. | ✅ |
| H4 | Backend / correctness | **Unvalidated discovery inputs.** `max_results`, `num_posts`, follower bounds have no constraints. `num_posts=0` makes reach/revenue collapse to 0 and divide-adjacent math misbehave; `max_results=100000` can fan out to thousands of API calls. | ✅ |
| H5 | Backend / robustness | **Discovery swallows errors with `print` and per-row commits.** The per-influencer loop uses bare `except Exception` + `print(...)` (no logger), and commits to the DB up to 3× per influencer. A failure mid-loop leaves partial writes; logs are invisible in production. | ✅ |
| H6 | Pydantic v2 / deprecations | Deprecated APIs throughout: `.dict()` (campaigns/brands/influencers routers), `from_orm()` (`routers/influencers.py`), `class Config` (all schemas), and `Query(..., regex=)` (campaigns CSV import). These emit warnings now and break on the next major bump. | ✅ |
| H7 | Frontend / UX | **No global error/loading boundaries; 30-min hard logout.** On token expiry the axios interceptor does `window.location.href='/login'` (full reload, loses state). No React error boundary, no toast system — failed mutations only `console.error`. Token lifetime is 30 min with no refresh, so active users get bounced mid-task. | 🟡 |

## Medium

| ID | Area | Issue | Status |
|----|------|-------|--------|
| M1 | DB / connections | `create_engine` has no `pool_pre_ping`/`pool_recycle`. After Postgres idle-timeouts the first query of a stale connection throws `OperationalError`. | ✅ |
| M2 | Schema management | **Dual source of truth.** `main.py` lifespan calls `Base.metadata.create_all()` *and* Alembic migrations exist. `create_all` silently creates tables that drift from migrations (e.g. server defaults) and masks missing-migration bugs. | ✅ |
| M3 | Backend / logging | `youtube_discovery.py` uses `print()` with emoji throughout instead of the `logging` module; not configurable, pollutes stdout, no levels. No app-wide logging config exists. | ✅ |
| M4 | Analytics / correctness | In `get_campaign_performance`, when `5 < len(measured) <= 10` the `worst_performers` slice (`measured[-5:]`) overlaps the `top_performers` slice (`measured[:5]`), so the same campaign appears in both lists. | ✅ |
| M5 | Backend / model mismatch | `InfluencerRecommendation` rows are written with a `cost_range` key in the tier JSON, but the model docstring/legacy readers expect `estimated_cost`. Inconsistent JSON shape across writes. | ✅ |
| M6 | Config | `.env` mixes two competing conventions (`SECRET_KEY`+`ALGORITHM`+`ACCESS_TOKEN_EXPIRE_MINUTES` vs `JWT_SECRET_KEY`+`JWT_ALGORITHM`+`JWT_ACCESS_TOKEN_EXPIRE_MINUTES`) and leaves live-looking API keys plus commented spare keys in the file. No `.env.example`. | 🟡 |
| M7 | Frontend / types | `campaignsAPI`, `influencersAPI`, `brandsAPI` use `data: any`; responses are untyped (`response.data` as `any`). The strong types in `types.ts` aren't enforced at call sites. | ⬜ |
| M8 | Docker | Backend container runs `--reload` (a dev server) as its compose command and bind-mounts the source; there is no production target. Migrations are not run on start (`alembic upgrade head` missing), so a fresh DB relies on `create_all`. | 🟡 |

## Low

| ID | Area | Issue | Status |
|----|------|-------|--------|
| L1 | Repo hygiene | `yapi.txt` scratch notes and a binary `Influencer_ROI_Hunter_Is_Plani_v2.docx` are committed at repo root. `docs/` was empty. | 🟡 |
| L2 | Frontend | `react-query` (`@tanstack/react-query`) is a dependency but there is no `QueryClientProvider` in `App.tsx`; pages fetch with raw `useEffect`. Either wire it or drop the dep. | ⬜ |
| L3 | Backend | `routers/influencers.py` `POST /youtube/fetch` and `utils/youtube_api.py` overlap with the discovery client; two YouTube client code paths to maintain. | ⬜ |
| L4 | Backend | `analyze_campaign_performance` in `ai_detector.py` is implemented but never exposed via any endpoint — useful AI feature left unwired. | 🟡 |
| L5 | Security | CORS uses `allow_credentials=True` but the app authenticates via `Authorization: Bearer` header (not cookies), so credentials mode is unnecessary and slightly widens exposure. | ⬜ |

---

## Cross-cutting observations

- **AI math integrity is good.** `utils/benchmarks.py` is well-designed: ranges not point estimates, cited `source`, confidence tiering, and the "skip influencers we couldn't actually analyze" rule in discovery is the right call. This is the product's strongest asset and should be protected by tests (see H1).
- **Single-platform reality.** Only YouTube is implemented despite `platform` allowing instagram/tiktok. This is honest in the README; treated as a roadmap item, not a bug.
- **Observability gap.** No structured logging config, no request IDs, no metrics, no rate limiting. Fine for MVP, required before multi-tenant scale (see ROADMAP P3).
</content>
</invoke>
