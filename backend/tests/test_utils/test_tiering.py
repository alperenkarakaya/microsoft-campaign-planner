"""Tests for Phase 4 tiering logic (Model C: trust-only tier).

Covers:
  - S / A / B tier boundaries driven by audience trust ONLY
  - Sponsorship does NOT affect tier assignment
  - Sponsorship readiness label is populated independently
  - Reliability gate behavior (active/dormant/inactive)
  - Missing layers => untiered with reason
  - Follower count never influences tier
  - Readiness flag computation
"""

from utils.tiering import (
    compute_readiness,
    compute_intrinsic_tier,
    compose_creator_intelligence,
)


# ---------------------------------------------------------------------------
# Fixtures: representative enrichment signals + analysis blobs
# ---------------------------------------------------------------------------

def _make_signals(
    *,
    last_upload_days_ago=10.0,
    recent_view_cv=0.25,
    like_to_view_ratio=0.06,
    comment_to_view_ratio=0.008,
    subscriber_count=50_000,
):
    """Minimal Phase-1 enrichment_signals blob."""
    return {
        "upload_cadence": {
            "cadence_days_median": 7.0,
            "cadence_days_mean": 8.0,
            "last_upload_days_ago": last_upload_days_ago,
        },
        "view_consistency": {
            "recent_view_median": 15_000,
            "recent_view_cv": recent_view_cv,
            "sample_size": 10,
        },
        "engagement_depth": {
            "like_to_view_ratio": like_to_view_ratio,
            "comment_to_view_ratio": comment_to_view_ratio,
            "sample_size": 10,
        },
        "subscriber_count": subscriber_count,
        "video_count": 200,
    }


def _make_trust(score=75.0, confidence="high", status="analyzed"):
    return {
        "status": status,
        "composite_trust_score": score,
        "confidence": confidence,
        "community_trust_depth": {"score": score},
        "authority": {"score": score * 0.8},
    }


def _make_sponsorship(
    score=70.0,
    confidence="high",
    status="analyzed",
    maturity_label="mature",
    sponsored_ratio=0.30,
):
    return {
        "status": status,
        "composite_sponsorship_score": score,
        "confidence": confidence,
        "maturity": {
            "label": maturity_label,
            "score": 80.0,
            "sponsored_ratio": sponsored_ratio,
        },
        "quality": {"score": 65.0, "repeat_sponsors": ["brand_a"]},
        "integration_style": {"style": "native", "score": 70.0},
        "authenticity": {"score": 65.0},
    }


def _make_influencer(business_email="creator@example.com", talent_agency=False):
    return {
        "business_email": business_email,
        "talent_agency": talent_agency,
    }


# ---------------------------------------------------------------------------
# Readiness / Reliability gate tests
# ---------------------------------------------------------------------------

class TestReadiness:

    def test_active_reachable_creator(self):
        signals = _make_signals(last_upload_days_ago=5.0)
        inf = _make_influencer(business_email="a@b.com")
        r = compute_readiness(signals, inf)
        assert r["is_active"] is True
        assert r["is_reachable"] is True
        assert r["gate_passed"] is True
        assert "active" in r["flags"]
        assert "reachable" in r["flags"]

    def test_dormant_creator_fails_gate(self):
        signals = _make_signals(last_upload_days_ago=120.0)
        inf = _make_influencer()
        r = compute_readiness(signals, inf)
        assert r["is_active"] is False
        assert r["gate_passed"] is False
        assert "dormant" in r["flags"]

    def test_inactive_creator_fails_gate(self):
        signals = _make_signals(last_upload_days_ago=200.0)
        r = compute_readiness(signals)
        assert r["is_active"] is False
        assert r["gate_passed"] is False
        assert "inactive" in r["flags"]

    def test_no_signals_fails_gate(self):
        r = compute_readiness(None, _make_influencer())
        assert r["gate_passed"] is False
        assert "no_enrichment_signals" in r["flags"]

    def test_no_email_marks_not_reachable(self):
        signals = _make_signals()
        inf = _make_influencer(business_email=None)
        r = compute_readiness(signals, inf)
        assert r["is_reachable"] is False
        assert "not_reachable" in r["flags"]

    def test_agency_managed_flag(self):
        signals = _make_signals()
        inf = _make_influencer(talent_agency=True)
        r = compute_readiness(signals, inf)
        assert r["is_agency_managed"] is True
        assert "agency_managed" in r["flags"]

    def test_view_stability_stable(self):
        signals = _make_signals(recent_view_cv=0.20)
        r = compute_readiness(signals)
        assert r["view_stability"] == "stable"
        assert "view_stable" in r["flags"]

    def test_view_stability_volatile(self):
        signals = _make_signals(recent_view_cv=0.90)
        r = compute_readiness(signals)
        assert r["view_stability"] == "volatile"
        assert "view_volatile" in r["flags"]

    def test_view_stability_moderate(self):
        signals = _make_signals(recent_view_cv=0.55)
        r = compute_readiness(signals)
        assert r["view_stability"] == "moderate"


# ---------------------------------------------------------------------------
# Intrinsic tier tests (Model C: trust-only)
# ---------------------------------------------------------------------------

class TestIntrinsicTier:

    def test_tier_s_high_trust_reachable_active(self):
        """S-tier: high trust + reachable + active. Sponsorship irrelevant."""
        readiness = compute_readiness(
            _make_signals(),
            _make_influencer(business_email="a@b.com"),
        )
        result = compute_intrinsic_tier(
            _make_trust(score=80.0),
            _make_sponsorship(score=75.0),
            readiness,
        )
        assert result["tier"] == "S"
        assert result["tier_label"] == "Priority Partner"
        assert result["confidence"] in ("high", "medium")
        assert result["trust_score"] == 80.0
        assert result["sponsorship_score"] == 75.0

    def test_sponsorship_does_not_gate_s_tier(self):
        """Trust=60, sponsorship=30, reachable, active => S (not A).

        Under Model C, sponsorship no longer gates tier assignment.
        """
        readiness = compute_readiness(
            _make_signals(),
            _make_influencer(business_email="a@b.com"),
        )
        result = compute_intrinsic_tier(
            _make_trust(score=60.0),
            _make_sponsorship(score=30.0),
            readiness,
        )
        assert result["tier"] == "S"

    def test_sponsorship_does_not_change_s_tier(self):
        """Trust=60, sponsorship=90, reachable, active => S (same as low sponsorship)."""
        readiness = compute_readiness(
            _make_signals(),
            _make_influencer(business_email="a@b.com"),
        )
        result = compute_intrinsic_tier(
            _make_trust(score=60.0),
            _make_sponsorship(score=90.0),
            readiness,
        )
        assert result["tier"] == "S"

    def test_sponsorship_cannot_promote_to_s(self):
        """Trust=45, sponsorship=90 => A (sponsorship can't promote to S)."""
        readiness = compute_readiness(
            _make_signals(),
            _make_influencer(business_email="a@b.com"),
        )
        result = compute_intrinsic_tier(
            _make_trust(score=45.0),
            _make_sponsorship(score=90.0),
            readiness,
        )
        assert result["tier"] == "A"

    def test_low_trust_always_b_regardless_of_sponsorship(self):
        """Trust=35, sponsorship=90 => B (low trust = B regardless)."""
        readiness = compute_readiness(
            _make_signals(),
            _make_influencer(business_email="a@b.com"),
        )
        result = compute_intrinsic_tier(
            _make_trust(score=35.0),
            _make_sponsorship(score=90.0),
            readiness,
        )
        assert result["tier"] == "B"

    def test_tier_a_high_trust_not_reachable(self):
        """A-tier: strong trust but not reachable."""
        readiness = compute_readiness(
            _make_signals(),
            _make_influencer(business_email=None),  # not reachable
        )
        result = compute_intrinsic_tier(
            _make_trust(score=75.0),
            _make_sponsorship(score=80.0),
            readiness,
        )
        assert result["tier"] == "A"

    def test_tier_a_moderate_trust(self):
        """A-tier: moderate trust (38-58 range)."""
        readiness = compute_readiness(
            _make_signals(),
            _make_influencer(),
        )
        result = compute_intrinsic_tier(
            _make_trust(score=50.0),
            _make_sponsorship(score=70.0),
            readiness,
        )
        assert result["tier"] == "A"

    def test_tier_b_low_trust(self):
        """B-tier: shallow community trust."""
        readiness = compute_readiness(
            _make_signals(),
            _make_influencer(),
        )
        result = compute_intrinsic_tier(
            _make_trust(score=25.0),
            _make_sponsorship(score=20.0),
            readiness,
        )
        assert result["tier"] == "B"
        assert result["tier_label"] == "Commodity / Nurture"

    def test_reliability_gate_caps_to_b(self):
        """If reliability gate fails, tier is capped at B even with high trust."""
        readiness = compute_readiness(
            _make_signals(last_upload_days_ago=150.0),
            _make_influencer(),
        )
        assert readiness["gate_passed"] is False

        result = compute_intrinsic_tier(
            _make_trust(score=85.0),
            _make_sponsorship(score=80.0),
            readiness,
        )
        assert result["tier"] == "B"
        assert "capped" in (result["override_reason"] or "").lower()

    def test_untiered_when_trust_missing(self):
        """Missing trust => untiered with reason."""
        readiness = compute_readiness(None, _make_influencer())
        result = compute_intrinsic_tier(None, None, readiness)
        assert result["tier"] is None
        assert result["tier_label"] == "Untiered"
        assert "trust" in result["tier_explanation"].lower()
        assert result["confidence"] == "low"

    def test_untiered_when_trust_unanalyzed(self):
        """Unanalyzed trust status => treated as missing."""
        readiness = compute_readiness(_make_signals(), _make_influencer())
        result = compute_intrinsic_tier(
            _make_trust(status="unanalyzed"),
            _make_sponsorship(score=80.0),
            readiness,
        )
        assert result["tier"] is None
        assert "trust" in result["tier_explanation"].lower()

    def test_follower_count_does_not_influence_tier(self):
        """Verify follower count is NOT used in tiering.

        A creator with 1K followers and high trust should tier
        identically to one with 10M followers and the same trust score.
        """
        readiness_small = compute_readiness(
            _make_signals(subscriber_count=1_000),
            _make_influencer(),
        )
        readiness_large = compute_readiness(
            _make_signals(subscriber_count=10_000_000),
            _make_influencer(),
        )

        result_small = compute_intrinsic_tier(
            _make_trust(score=80.0),
            _make_sponsorship(score=75.0),
            readiness_small,
        )
        result_large = compute_intrinsic_tier(
            _make_trust(score=80.0),
            _make_sponsorship(score=75.0),
            readiness_large,
        )

        assert result_small["tier"] == result_large["tier"]
        assert result_small["tier"] == "S"

    def test_tier_explanation_mentions_trust_not_sponsorship(self):
        """Tier explanation should reference trust, not sponsorship."""
        readiness = compute_readiness(
            _make_signals(),
            _make_influencer(business_email="a@b.com"),
        )
        result = compute_intrinsic_tier(
            _make_trust(score=65.0),
            _make_sponsorship(score=80.0),
            readiness,
        )
        assert result["tier"] == "S"
        explanation = result["tier_explanation"].lower()
        assert "trust" in explanation
        # Explanation should say tier is independent of sponsorship
        assert "independent" in explanation or "authority" in explanation

    def test_no_marginal_a_demotion(self):
        """Model C removed marginal-A demotion. Trust=42 => A (not B)."""
        readiness = compute_readiness(
            _make_signals(),
            _make_influencer(),
        )
        result = compute_intrinsic_tier(
            _make_trust(score=42.0),
            _make_sponsorship(score=40.0),
            readiness,
        )
        # Under trust-only model, 42.0 is in mid-range [38, 58) => A
        assert result["tier"] == "A"
        assert "marginal" not in (result["tier_explanation"] or "").lower()


# ---------------------------------------------------------------------------
# Sponsorship readiness label tests
# ---------------------------------------------------------------------------

class TestSponsorshipReadiness:

    def test_mature_label(self):
        """Mature sponsorship profile produces correct readiness label."""
        readiness = compute_readiness(_make_signals(), _make_influencer())
        result = compute_intrinsic_tier(
            _make_trust(score=60.0),
            _make_sponsorship(score=70.0, maturity_label="mature", sponsored_ratio=0.30),
            readiness,
        )
        sr = result["sponsorship_readiness"]
        assert sr["label"] == "mature"
        assert sr["score"] == 70.0
        assert "professional proposal" in sr["outreach_implication"].lower()
        assert "mature" in sr["explanation"].lower()

    def test_unproven_label(self):
        """Unproven sponsorship produces correct readiness label."""
        readiness = compute_readiness(_make_signals(), _make_influencer())
        result = compute_intrinsic_tier(
            _make_trust(score=60.0),
            _make_sponsorship(score=30.0, maturity_label="unproven"),
            readiness,
        )
        sr = result["sponsorship_readiness"]
        assert sr["label"] == "unproven"
        assert "discovery" in sr["outreach_implication"].lower()

    def test_emerging_label(self):
        """Emerging sponsorship produces correct readiness label."""
        readiness = compute_readiness(_make_signals(), _make_influencer())
        result = compute_intrinsic_tier(
            _make_trust(score=60.0),
            _make_sponsorship(score=50.0, maturity_label="emerging", sponsored_ratio=0.10),
            readiness,
        )
        sr = result["sponsorship_readiness"]
        assert sr["label"] == "emerging"
        assert "growth partnership" in sr["outreach_implication"].lower()

    def test_saturated_label(self):
        """Saturated sponsorship produces correct readiness label."""
        readiness = compute_readiness(_make_signals(), _make_influencer())
        result = compute_intrinsic_tier(
            _make_trust(score=60.0),
            _make_sponsorship(score=25.0, maturity_label="saturated", sponsored_ratio=0.70),
            readiness,
        )
        sr = result["sponsorship_readiness"]
        assert sr["label"] == "saturated"
        assert "differentiate" in sr["outreach_implication"].lower()

    def test_no_sponsorship_profile(self):
        """Missing sponsorship profile produces unknown readiness."""
        readiness = compute_readiness(_make_signals(), _make_influencer())
        result = compute_intrinsic_tier(
            _make_trust(score=60.0),
            None,
            readiness,
        )
        sr = result["sponsorship_readiness"]
        assert sr["label"] is None
        assert sr["score"] is None
        assert "could not be assessed" in sr["explanation"].lower()

    def test_readiness_independent_of_tier(self):
        """Sponsorship readiness label does not depend on tier assignment."""
        readiness = compute_readiness(_make_signals(), _make_influencer())
        # B-tier creator with mature sponsorship
        result = compute_intrinsic_tier(
            _make_trust(score=30.0),
            _make_sponsorship(score=80.0, maturity_label="mature"),
            readiness,
        )
        assert result["tier"] == "B"
        sr = result["sponsorship_readiness"]
        assert sr["label"] == "mature"
        assert sr["score"] == 80.0


# ---------------------------------------------------------------------------
# Composition function tests
# ---------------------------------------------------------------------------

class TestComposeCreatorIntelligence:

    def test_full_composition(self):
        result = compose_creator_intelligence(
            enrichment_signals=_make_signals(),
            trust_breakdown=_make_trust(score=80.0),
            sponsorship_profile=_make_sponsorship(score=75.0),
            influencer=_make_influencer(),
        )
        assert result["tier"] == "S"
        assert "readiness" in result
        assert result["readiness"]["gate_passed"] is True
        assert "sponsorship_readiness" in result
        assert result["sponsorship_readiness"]["label"] == "mature"

    def test_no_data_composition(self):
        result = compose_creator_intelligence(
            enrichment_signals=None,
            trust_breakdown=None,
            sponsorship_profile=None,
            influencer=None,
        )
        assert result["tier"] is None
        assert result["readiness"]["gate_passed"] is False
        assert result["sponsorship_readiness"]["label"] is None

    def test_partial_data_no_fabrication(self):
        """With only signals (no trust/sponsorship), should be untiered."""
        result = compose_creator_intelligence(
            enrichment_signals=_make_signals(),
            trust_breakdown=None,
            sponsorship_profile=None,
            influencer=_make_influencer(),
        )
        assert result["tier"] is None
        assert result["trust_score"] is None
        assert result["sponsorship_score"] is None


# ---------------------------------------------------------------------------
# Tier boundary edge cases
# ---------------------------------------------------------------------------

class TestTierBoundaries:

    def test_trust_exactly_at_high_threshold(self):
        """Trust score exactly at threshold (58.0) should qualify as high."""
        readiness = compute_readiness(_make_signals(), _make_influencer())
        result = compute_intrinsic_tier(
            _make_trust(score=58.0),
            _make_sponsorship(score=52.0),
            readiness,
        )
        assert result["tier"] == "S"

    def test_trust_just_below_high_threshold(self):
        """Trust score just below threshold should not qualify as S."""
        readiness = compute_readiness(_make_signals(), _make_influencer())
        result = compute_intrinsic_tier(
            _make_trust(score=57.9),
            _make_sponsorship(score=75.0),
            readiness,
        )
        assert result["tier"] != "S"
        # Should be A (mid-range trust)
        assert result["tier"] == "A"

    def test_trust_at_low_boundary(self):
        """Trust below 38 should push to B tier regardless of sponsorship."""
        readiness = compute_readiness(_make_signals(), _make_influencer())
        result = compute_intrinsic_tier(
            _make_trust(score=37.9),
            _make_sponsorship(score=90.0),  # high sponsorship doesn't help
            readiness,
        )
        assert result["tier"] == "B"

    def test_trust_exactly_at_low_boundary(self):
        """Trust score exactly at 38.0 => A tier (mid-range)."""
        readiness = compute_readiness(_make_signals(), _make_influencer())
        result = compute_intrinsic_tier(
            _make_trust(score=38.0),
            _make_sponsorship(score=30.0),
            readiness,
        )
        assert result["tier"] == "A"

    def test_recalibrated_s_tier_trust_only(self):
        """Trust=60, reachable, active => S regardless of sponsorship."""
        readiness = compute_readiness(
            _make_signals(),
            _make_influencer(business_email="a@b.com"),
        )
        result = compute_intrinsic_tier(
            _make_trust(score=60.0),
            _make_sponsorship(score=55.0),
            readiness,
        )
        assert result["tier"] == "S"

    def test_dormant_still_capped_to_b(self):
        """Dormant creator still capped to B regardless of scores."""
        readiness = compute_readiness(
            _make_signals(last_upload_days_ago=150.0),
            _make_influencer(),
        )
        assert readiness["gate_passed"] is False
        result = compute_intrinsic_tier(
            _make_trust(score=80.0),
            _make_sponsorship(score=80.0),
            readiness,
        )
        assert result["tier"] == "B"
        assert "capped" in (result["override_reason"] or "").lower()

    def test_sponsorship_score_still_in_output(self):
        """Verify sponsorship_score is still present in the output dict."""
        readiness = compute_readiness(_make_signals(), _make_influencer())
        result = compute_intrinsic_tier(
            _make_trust(score=60.0),
            _make_sponsorship(score=70.0),
            readiness,
        )
        assert "sponsorship_score" in result
        assert result["sponsorship_score"] == 70.0
