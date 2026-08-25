"""
AI Creator Matching (Campaign Match Score).

Produces a per-campaign fit score for one creator, SEPARATE from — and never
recomputing — that creator's intrinsic Trust Score. Trust Score answers "how
good is this creator's audience, in general?" (utils.trust_scorer /
utils.tiering). Campaign Match Score answers "how well does THIS creator fit
THIS brand's THIS campaign?" Both are always surfaced together, never merged.

Deterministic weighted components (weights sum to 100, renormalized over
whichever components have data — same discipline as trust_scorer.py):

  - trust_component      30  — passthrough of intelligence["trust_score"]
  - category_fit         20  — brand.preferred_categories vs influencer.category
  - budget_fit            15  — estimated single-creator cost vs campaign budget
  - sponsorship_component 15  — intelligence sponsorship score, adjusted by
                                 whether it matches the brand's stated preference
  - geographic_fit        10  — brand.target_countries vs influencer.country
  - audience_fit           10  — from stored audience_demographics (Gemini),
                                 None when no demographic data is on file

Reach/cost estimates reuse utils.benchmarks.predict_campaign_outcome — the
same grounded prediction already used by brand_matcher/roster — rather than
reinventing CPM math.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from utils.benchmarks import predict_campaign_outcome

WEIGHTS = {
    "trust_component": 30.0,
    "category_fit": 20.0,
    "budget_fit": 15.0,
    "sponsorship_component": 15.0,
    "geographic_fit": 10.0,
    "audience_fit": 10.0,
}


def _category_fit(preferred_categories: Optional[List[str]], influencer_category: Optional[str]) -> Optional[float]:
    if not preferred_categories:
        return None
    if not influencer_category:
        return 50.0  # brand has a preference, creator's category is unknown
    cat_lower = influencer_category.lower()
    for pref in preferred_categories:
        if pref and pref.lower() in cat_lower:
            return 100.0
    return 20.0  # no textual overlap; single free-text category field is coarse


def _geographic_fit(target_countries: Optional[List[str]], influencer_country: Optional[str]) -> Optional[float]:
    if not target_countries:
        return None
    if not influencer_country:
        return 50.0
    if influencer_country.upper() in [c.upper() for c in target_countries]:
        return 100.0
    return 30.0


_SPONSORSHIP_PREF_MATCH_BONUS = 15.0
_SPONSORSHIP_PREF_MISMATCH_PENALTY = 10.0


def _sponsorship_component(
    sponsorship_score: Optional[float],
    sponsorship_label: Optional[str],
    sponsorship_pref: Optional[str],
) -> Optional[float]:
    if sponsorship_score is None:
        return None
    score = sponsorship_score
    if sponsorship_pref and sponsorship_label:
        if sponsorship_pref.lower() == sponsorship_label.lower():
            score = min(100.0, score + _SPONSORSHIP_PREF_MATCH_BONUS)
        elif sponsorship_pref.lower() == "any":
            pass
        else:
            score = max(0.0, score - _SPONSORSHIP_PREF_MISMATCH_PENALTY)
    return round(score, 1)


def _budget_fit(
    campaign_budget: Optional[float],
    estimated_cost_low: Optional[float],
    estimated_cost_high: Optional[float],
) -> Optional[float]:
    if campaign_budget is None or campaign_budget <= 0:
        return None
    if estimated_cost_low is None or estimated_cost_high is None:
        return None
    midpoint = (estimated_cost_low + estimated_cost_high) / 2
    if midpoint <= 0:
        return None
    ratio = midpoint / campaign_budget
    if ratio <= 0.5:
        return 100.0
    if ratio <= 1.0:
        return 70.0
    if ratio <= 1.5:
        return 40.0
    return 15.0


def _audience_fit(audience_demographics: Optional[Dict[str, Any]], brand_profile: Dict[str, Any]) -> Optional[float]:
    """Only scored when real demographic data (from a prior Gemini brand-fit
    analysis) is stored. Never fabricated from follower count alone."""
    if not audience_demographics:
        return None
    # audience_demographics is a free-form Gemini JSON blob (see brand_matcher's
    # discover() output shape); without a stable schema we can only give a
    # conservative neutral score confirming data exists, not a synthetic fit number.
    return 60.0


def _risk_level(
    trust_score: Optional[float],
    trust_confidence: Optional[str],
    gate_passed: bool,
    sponsorship_label: Optional[str],
) -> str:
    if trust_score is None:
        return "unknown"
    if not gate_passed or trust_score < 30:
        return "high"
    if trust_confidence == "low" or sponsorship_label == "saturated":
        return "medium"
    return "low"


def _build_reasons(
    trust_score: Optional[float],
    tier: Optional[str],
    category_fit: Optional[float],
    geographic_fit: Optional[float],
    budget_fit: Optional[float],
    sponsorship_label: Optional[str],
    sponsorship_component: Optional[float],
    audience_fit: Optional[float],
    risk_level: str,
) -> List[str]:
    reasons: List[str] = []
    if trust_score is not None:
        if trust_score >= 58:
            reasons.append(f"high community trust ({trust_score:.0f}/100, tier {tier or '?'})")
        elif trust_score >= 38:
            reasons.append(f"moderate community trust ({trust_score:.0f}/100)")
        else:
            reasons.append(f"low community trust ({trust_score:.0f}/100)")
    else:
        reasons.append("trust score not yet computed for this creator")

    if category_fit is not None and category_fit >= 100:
        reasons.append("category matches the brand's preferred categories")
    elif category_fit is not None and category_fit <= 30:
        reasons.append("category does not clearly overlap the brand's preferences")

    if geographic_fit is not None and geographic_fit >= 100:
        reasons.append("audience geography matches the brand's target markets")
    elif geographic_fit is not None and geographic_fit <= 40:
        reasons.append("creator's country is outside the brand's target geography")

    if sponsorship_label:
        reasons.append(f"sponsorship maturity: {sponsorship_label}")

    if budget_fit is not None and budget_fit >= 70:
        reasons.append("estimated cost fits comfortably within the campaign budget")
    elif budget_fit is not None and budget_fit <= 40:
        reasons.append("estimated cost is high relative to the campaign budget")

    if audience_fit is not None:
        reasons.append("audience demographic data is on file for this creator")

    if risk_level == "high":
        reasons.append("RISK: reliability gate failed or very low trust — vet before contacting")
    elif risk_level == "medium":
        reasons.append("RISK: moderate — review sponsorship saturation / confidence before contacting")

    return reasons


def _build_why(reasons: List[str], risk_level: str) -> str:
    positives = [r for r in reasons if not r.startswith("RISK")]
    negatives = [r for r in reasons if r.startswith("RISK")]
    lead = "Strong candidate" if risk_level in ("low", "unknown") else "Candidate with caveats"
    body = "; ".join(positives[:4]) if positives else "insufficient data to characterize fit"
    sentence = f"{lead}: {body}."
    if negatives:
        sentence += " " + " ".join(negatives)
    return sentence


def compute_campaign_match(
    *,
    followers_count: int,
    platform: str,
    influencer_category: Optional[str],
    influencer_country: Optional[str],
    enrichment_signals: Optional[Dict[str, Any]],
    intelligence: Dict[str, Any],
    brand_profile: Dict[str, Any],
    campaign_budget: Optional[float],
    audience_demographics: Optional[Dict[str, Any]] = None,
    num_posts: int = 1,
) -> Dict[str, Any]:
    """Compute the Campaign Match Score for one (campaign, creator) pair.

    `intelligence` is the output of utils.tiering.compose_creator_intelligence()
    — this function reads trust_score/sponsorship_score/tier/readiness from it
    but never recomputes them.
    """
    trust_score = intelligence.get("trust_score")
    trust_confidence = intelligence.get("confidence")
    tier = intelligence.get("tier")
    readiness = intelligence.get("readiness") or {}
    gate_passed = bool(readiness.get("gate_passed"))
    sponsorship_score = intelligence.get("sponsorship_score")
    sponsorship_readiness = intelligence.get("sponsorship_readiness") or {}
    sponsorship_label = sponsorship_readiness.get("label")

    category_fit = _category_fit(brand_profile.get("preferred_categories"), influencer_category)
    geographic_fit = _geographic_fit(brand_profile.get("target_countries"), influencer_country)
    sponsorship_pref = brand_profile.get("sponsorship_pref")
    sponsorship_component = _sponsorship_component(sponsorship_score, sponsorship_label, sponsorship_pref)
    audience_fit_score = _audience_fit(audience_demographics, brand_profile)

    # Grounded reach/cost estimate — reuses the same prediction infra used
    # elsewhere in the app (brand_matcher discovery, roster campaign_potential).
    median_views = None
    if enrichment_signals:
        vc = enrichment_signals.get("view_consistency") or {}
        median_views = vc.get("recent_view_median")

    category_for_pred = (brand_profile.get("preferred_categories") or [None])[0]
    region_for_pred = (brand_profile.get("target_countries") or [None])[0]

    prediction = predict_campaign_outcome(
        platform=platform or "youtube",
        tier=tier.lower() if tier else "micro",
        category=category_for_pred,
        region=region_for_pred,
        median_recent_views=median_views,
        follower_count=followers_count or 0,
        target_aov=brand_profile.get("target_aov"),
        num_posts=num_posts,
    )
    estimated_reach = int((prediction.predicted_reach_low + prediction.predicted_reach_high) / 2)
    estimated_cost_low = round(prediction.predicted_cost_low, 2)
    estimated_cost_high = round(prediction.predicted_cost_high, 2)

    budget_fit = _budget_fit(campaign_budget, estimated_cost_low, estimated_cost_high)

    components = {
        "trust_component": trust_score,
        "category_fit": category_fit,
        "budget_fit": budget_fit,
        "sponsorship_component": sponsorship_component,
        "geographic_fit": geographic_fit,
        "audience_fit": audience_fit_score,
    }

    available = {k: v for k, v in components.items() if v is not None}
    if available:
        total_weight = sum(WEIGHTS[k] for k in available)
        match_score = round(
            sum(v * (WEIGHTS[k] / total_weight) for k, v in available.items()), 1
        )
        confidence = "high" if len(available) >= 5 else ("medium" if len(available) >= 3 else "low")
    else:
        match_score = None
        confidence = "low"

    risk_level = _risk_level(trust_score, trust_confidence, gate_passed, sponsorship_label)

    reasons = _build_reasons(
        trust_score, tier, category_fit, geographic_fit, budget_fit,
        sponsorship_label, sponsorship_component, audience_fit_score, risk_level,
    )
    why = _build_why(reasons, risk_level)

    recommended_role = None
    if tier == "S":
        recommended_role = "Lead partner — flagship content"
    elif tier == "A":
        recommended_role = "Growth partner — test campaign"
    elif tier == "B":
        recommended_role = "Supporting / volume placement"

    return {
        "match_score": match_score,
        "audience_fit": audience_fit_score,
        "brand_fit": category_fit,  # category overlap is the closest deterministic proxy to "brand fit" without an LLM pass
        "category_fit": category_fit,
        "geographic_fit": geographic_fit,
        "budget_fit": budget_fit,
        "trust_component": trust_score,
        "sponsorship_component": sponsorship_component,
        "risk_level": risk_level,
        "reasons": reasons,
        "why": why,
        "recommended_role": recommended_role,
        "confidence": confidence,
        "estimated_reach": estimated_reach,
        "estimated_cost_low": estimated_cost_low,
        "estimated_cost_high": estimated_cost_high,
        "source": "deterministic (trust/sponsorship from stored intelligence, reach/cost from benchmarks.py)",
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }
