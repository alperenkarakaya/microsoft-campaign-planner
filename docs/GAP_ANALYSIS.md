# Product Gap Analysis — Implementation vs. README Vision

_2026-06-18. Compares what the README promises against what the code actually does._

The product's stated job (README §1): help brands **discover → analyze → plan/track →
measure ROI → get AI recommendations** for influencers. Below, each pillar is rated and
the concrete gaps listed.

Legend: 🟢 solid · 🟡 partial · 🔴 missing/weak.

---

## 1. Influencer discovery — 🟡

**Have.** Real YouTube Data API search with tiered filter relaxation, median-recent-views
view ratio (resistant to viral outliers), dead-channel detection, Redis caching (now wired),
subscriber/engagement/view-ratio filters.

**Gaps.**
- 🔴 **Single platform.** Instagram/TikTok are modeled but not implemented. The whole
  discovery/stats path is YouTube-only. (Honest in README; still the #1 product gap.)
- 🟡 **No persistence/browse of discovered influencers as a saved list.** Discovery
  recomputes from scratch each call; there's no "saved shortlist" or favoriting.
- 🟡 **Search is keyword-only.** No filtering by country/language/topic taxonomy beyond
  the brand's `preferred_categories` join.
- 🔴 **No dedup/ranking across repeated searches** for the same brand profile over time.

## 2. Recommendation quality — 🟡

**Have.** Gemini 0–100 fit scoring across 4 axes with backend score caps + audit trail
(`original_match_score`, `override_reason`), tiering (micro/macro/mega), AI campaign
strategy text, "skip influencers we couldn't analyze" integrity rule.

**Gaps.**
- 🟡 **No explanation of *why* a score was capped surfaced in the UI** (data exists in
  `override_reason` but isn't a first-class UI element).
- 🟡 **Brand-identity axes (aggressive/creative/…) feed only the prompt**, not any
  deterministic scoring — fully LLM-dependent, no fallback ranking when Gemini is down.
- 🔴 **No feedback loop.** User can't accept/reject recommendations to improve future ones.

## 3. ROI prediction quality — 🟢

**Have.** This is the strongest area. `benchmarks.py` produces grounded **ranges** (never
point estimates), cites a `source`, tiers `confidence` by how many real inputs are present,
and the post-campaign path recomputes true ROI from actuals. Now test-covered.

**Gaps.**
- 🟡 **CTR/CVR/CPM benchmarks are static constants.** No per-brand calibration from the
  brand's own historical campaigns even when that data exists.
- 🟡 **AOV is the only brand-supplied funnel input.** No margin/COGS, so "revenue" ≠ profit
  in predictions (net profit only appears post-actuals on the dashboard).

## 4. Analytics quality — 🟡

**Have.** Dashboard aggregates (budget/revenue/net profit/avg ROI filtered to measurable
campaigns), top/worst performers (now non-overlapping), influencer ROI ranking.

**Gaps.**
- 🔴 **No time-series / trends.** Everything is a point-in-time aggregate; no per-month or
  per-campaign-timeline charts.
- 🔴 **No comparison/benchmarking** of a campaign's actuals vs. its original prediction
  (the data to do this is stored in `InfluencerAnalysis.predicted_outcome`).
- 🟡 **Frontend uses raw `useEffect` fetching;** `@tanstack/react-query` is a dependency
  but unused — no caching/retry/stale handling for analytics.

## 5. Campaign tracking — 🟡

**Have.** CRUD, status lifecycle (planning/active/completed/cancelled, now validated),
manual actuals via PATCH, CSV import (YouTube Studio / Shopify / Stripe).

**Gaps.**
- 🔴 **No first-party click tracking** (`/r/{token}` UTM redirector is deferred in README).
  Clicks are only ever manually entered → CPC/CPA quality depends on the user.
- 🔴 **No webhooks** for Shopify/Stripe push (deferred).
- 🟡 **No multi-influencer campaigns.** `Campaign` has a single `influencer_id`, but
  recommendations are built for a *portfolio* — there's a model/feature mismatch.
- 🟡 **No campaign ↔ recommendation link.** You can't create a campaign directly from a
  discovery result; you re-enter everything.

## 6. Reporting — 🔴

**Gaps.**
- 🔴 No exportable report (PDF/CSV) of a campaign or discovery run.
- 🔴 No shareable client-facing summary.

## 7. AI insights — 🟡

**Have.** Fit analysis, fake-follower detection, campaign strategy text, and (newly wired)
post-campaign `ai-analysis` endpoint.

**Gaps.**
- 🟡 **AI insights not surfaced as a cohesive "insights" surface** in the UI yet
  (endpoint exists, no dedicated panel).
- 🔴 **No prediction-vs-actual AI narrative** ("you expected X, got Y, here's why").

## 8. Dashboard usefulness — 🟡

**Have.** KPI cards, performance lists, rankings.

**Gaps.**
- 🟡 Static numbers; no drill-down, no trends, no alerts (e.g., "campaign underperforming
  vs. prediction").
- 🟡 No empty-state guidance for new users (what to do first).

---

## Highest-leverage gaps (feed into ROADMAP)
1. **Prediction-vs-actual comparison** — the data already exists; pure value-add. (P1)
2. **Create campaign from discovery result** — closes the core funnel. (P1)
3. **react-query adoption + typed API client** — quality/perf foundation. (P1)
4. **First-party click tracker `/r/{token}`** — unlocks honest CPC/CPA. (P2)
5. **Multi-influencer campaigns** — aligns model with the portfolio recommendation. (P2)
6. **Reporting/export** — client-facing deliverable. (P2)
7. **Second platform (Instagram/TikTok)** — biggest scope, biggest TAM. (P3)
