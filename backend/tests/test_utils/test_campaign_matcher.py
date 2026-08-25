"""Tests for utils.ai.campaign_matcher — deterministic Campaign Match Score."""

from utils.ai.campaign_matcher import compute_campaign_match


def _intelligence(trust_score=75.0, tier="S", confidence="high", gate_passed=True,
                   sponsorship_score=70.0, sponsorship_label="mature"):
    return {
        "trust_score": trust_score,
        "tier": tier,
        "confidence": confidence,
        "readiness": {"gate_passed": gate_passed},
        "sponsorship_score": sponsorship_score,
        "sponsorship_readiness": {"label": sponsorship_label},
    }


def _brand(preferred_categories=("gaming",), target_countries=("US",), target_aov=40.0, sponsorship_pref=None):
    return {
        "name": "TestBrand",
        "preferred_categories": list(preferred_categories),
        "target_countries": list(target_countries),
        "target_aov": target_aov,
        "sponsorship_pref": sponsorship_pref,
    }


def test_match_score_reuses_trust_score_never_recomputes_it():
    intelligence = _intelligence(trust_score=82.0)
    result = compute_campaign_match(
        followers_count=50_000, platform="youtube",
        influencer_category="gaming", influencer_country="US",
        enrichment_signals=None, intelligence=intelligence,
        brand_profile=_brand(), campaign_budget=5000.0,
    )
    # trust_component must be a straight passthrough of intelligence["trust_score"]
    assert result["trust_component"] == 82.0


def test_category_and_geographic_fit_full_match_scores_high():
    result = compute_campaign_match(
        followers_count=50_000, platform="youtube",
        influencer_category="Gaming & Tech", influencer_country="US",
        enrichment_signals=None, intelligence=_intelligence(),
        brand_profile=_brand(preferred_categories=("gaming",), target_countries=("US",)),
        campaign_budget=5000.0,
    )
    assert result["category_fit"] == 100.0
    assert result["geographic_fit"] == 100.0
    assert result["match_score"] is not None
    assert 0 <= result["match_score"] <= 100


def test_category_mismatch_scores_low():
    result = compute_campaign_match(
        followers_count=50_000, platform="youtube",
        influencer_category="cooking", influencer_country="TR",
        enrichment_signals=None, intelligence=_intelligence(),
        brand_profile=_brand(preferred_categories=("gaming",), target_countries=("US",)),
        campaign_budget=5000.0,
    )
    assert result["category_fit"] < 50.0
    assert result["geographic_fit"] < 50.0


def test_missing_intelligence_never_fabricates_trust_component():
    """When trust hasn't been computed for a creator, trust_component and
    sponsorship_component stay None rather than being guessed."""
    intelligence = {
        "trust_score": None, "tier": None, "confidence": "low",
        "readiness": {"gate_passed": False},
        "sponsorship_score": None, "sponsorship_readiness": {"label": None},
    }
    result = compute_campaign_match(
        followers_count=10_000, platform="youtube",
        influencer_category=None, influencer_country=None,
        enrichment_signals=None, intelligence=intelligence,
        brand_profile=_brand(preferred_categories=(), target_countries=()),
        campaign_budget=None,
    )
    assert result["trust_component"] is None
    assert result["sponsorship_component"] is None
    assert result["risk_level"] == "unknown"


def test_reliability_gate_failure_marks_high_risk():
    intelligence = _intelligence(trust_score=80.0, gate_passed=False)
    result = compute_campaign_match(
        followers_count=50_000, platform="youtube",
        influencer_category="gaming", influencer_country="US",
        enrichment_signals=None, intelligence=intelligence,
        brand_profile=_brand(), campaign_budget=5000.0,
    )
    assert result["risk_level"] == "high"
    assert any("RISK" in r for r in result["reasons"])


def test_sponsorship_preference_match_boosts_component():
    matching = compute_campaign_match(
        followers_count=50_000, platform="youtube",
        influencer_category="gaming", influencer_country="US",
        enrichment_signals=None,
        intelligence=_intelligence(sponsorship_score=60.0, sponsorship_label="mature"),
        brand_profile=_brand(sponsorship_pref="mature"), campaign_budget=5000.0,
    )
    mismatching = compute_campaign_match(
        followers_count=50_000, platform="youtube",
        influencer_category="gaming", influencer_country="US",
        enrichment_signals=None,
        intelligence=_intelligence(sponsorship_score=60.0, sponsorship_label="saturated"),
        brand_profile=_brand(sponsorship_pref="mature"), campaign_budget=5000.0,
    )
    assert matching["sponsorship_component"] > mismatching["sponsorship_component"]


def test_budget_fit_penalizes_expensive_creator():
    cheap = compute_campaign_match(
        followers_count=5_000, platform="youtube",
        influencer_category="gaming", influencer_country="US",
        enrichment_signals=None, intelligence=_intelligence(),
        brand_profile=_brand(), campaign_budget=100_000.0,
    )
    expensive = compute_campaign_match(
        followers_count=5_000, platform="youtube",
        influencer_category="gaming", influencer_country="US",
        enrichment_signals=None, intelligence=_intelligence(),
        brand_profile=_brand(), campaign_budget=1.0,
    )
    assert cheap["budget_fit"] > expensive["budget_fit"]


def test_why_sentence_is_generated_and_reflects_risk():
    result = compute_campaign_match(
        followers_count=50_000, platform="youtube",
        influencer_category="gaming", influencer_country="US",
        enrichment_signals=None, intelligence=_intelligence(),
        brand_profile=_brand(), campaign_budget=5000.0,
    )
    assert result["why"]
    assert "Strong candidate" in result["why"]
