# Roadmap — Influencer ROI Hunter

_2026-06-18. Priorities: **P0** critical · **P1** high value · **P2** growth · **P3** scale._

Effort: S ≈ <½ day · M ≈ 1–2 days · L ≈ 3–5 days · XL ≈ >1 week.
Status: ✅ done this session · ⬜ open.

---

## P0 — Critical (correctness, security, stability)

| Task | Business impact | Complexity | Effort | Dependencies | Status |
|------|-----------------|-----------|--------|--------------|--------|
| Unblock async event loop (Gemini in threads) | Service usable under concurrency | Med | M | — | ✅ |
| Auth hardening (`is_active`, 401 not 500, JWT secret fail-fast) | Prevents account takeover & 500s | Low | S | — | ✅ |
| bcrypt 72-byte + password policy | No crashes on register/login | Low | S | — | ✅ |
| Discovery prediction crash on missing views | Stops silent loss of results | Low | S | — | ✅ |
| Input validation (discovery, campaigns) | Blocks degenerate/abusive payloads | Low | S | — | ✅ |
| Test suite + CI gate | Regression safety net | Med | M | — | ✅ |
| Wire CI (GitHub Actions: pytest + frontend build) | Keeps green permanently | Low | S | test suite | ✅ |
| Run `alembic upgrade head` in deploy/compose | Prod schema correctness | Low | S | M2 | ✅ |

## P1 — High value (core product depth)

| Task | Business impact | Complexity | Effort | Dependencies | Status |
|------|-----------------|-----------|--------|--------------|--------|
| **Prediction-vs-actual comparison** (store prediction on campaign create, show variance + AI narrative) | Proves the product's core promise | Med | M | actuals flow, `predicted_outcome` | ⬜ |
| **Create campaign from a discovery result** (carry influencer + prediction) | Closes discovery→campaign funnel | Med | M | discovery, campaigns | ⬜ |
| **Adopt react-query + typed API client** (replace `useEffect` + `any`) | Caching, retries, fewer bugs | Med | M | — | ⬜ |
| **Surface AI insights panel** (use new `/ai-analysis`) | Visible AI value | Low | S | ✅ endpoint | ⬜ |
| **Token refresh / silent re-auth + toast system** | No mid-task logout; better error UX | Med | M | H7 | ⬜ |
| **Recommendation explainability** (show `override_reason`, confidence badges) | Trust in scores | Low | S | — | ⬜ |

## P2 — Growth (new capabilities)

| Task | Business impact | Complexity | Effort | Dependencies | Status |
|------|-----------------|-----------|--------|--------------|--------|
| **First-party click tracker `/r/{token}`** | Honest CPC/CPA without platform APIs | Med | M | campaigns | ⬜ |
| **Shopify/Stripe webhooks** | Auto actuals, less manual entry | Med | L | CSV importers | ⬜ |
| **Multi-influencer campaigns** (campaign↔influencer join table) | Matches portfolio recommendations | High | L | schema migration | ⬜ |
| **Reporting/export** (PDF/CSV of campaign or discovery) | Client-facing deliverable | Med | M | analytics | ⬜ |
| **Time-series analytics** (trends, per-month ROI) | Deeper insight, retention | Med | M | actuals over time | ⬜ |
| **Per-brand benchmark calibration** (use brand's own history for CTR/CVR) | Sharper predictions | High | L | enough historical data | ⬜ |

## P3 — Scale (enterprise & ops)

| Task | Business impact | Complexity | Effort | Dependencies | Status |
|------|-----------------|-----------|--------|--------------|--------|
| **Rate limiting** (per-user, esp. discovery/Gemini) | Cost control, abuse prevention | Med | M | — | ⬜ |
| **Background jobs** (discovery as async task + status polling) | Long discoveries don't hold HTTP conns | High | L | task queue (RQ/Celery/arq) | ⬜ |
| **Observability** (structured request logs, metrics, tracing, Sentry) | Production debuggability | Med | M | logging ✅ | ⬜ |
| **Second platform: Instagram/TikTok** | Expands TAM significantly | High | XL | platform API keys | ⬜ |
| **Production Docker target** (no `--reload`, gunicorn workers, run migrations) | Deployability | Low | S | M2/M8 | ⬜ |
| **Secrets rotation + vault** (move keys out of `.env`) | Security posture | Med | M | — | ⬜ |

---

## Sequencing recommendation
1. Finish P0 tail: **CI + migrate-on-deploy** (cheap, locks in this session's gains).
2. P1 funnel pair: **create-campaign-from-discovery** + **prediction-vs-actual** — together
   they make the product tell a complete, provable story.
3. P1 platform polish: **react-query/typed client** + **AI insights panel** + **toasts**.
4. Then P2 tracking depth (click tracker, webhooks, multi-influencer).
5. P3 when multi-tenant scale or enterprise deals demand it.
