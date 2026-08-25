"""Tests for the roster intelligence endpoint (Phase 4 + Phase 5).

Covers:
  - Composition from stored DB rows (mock data with stored JSON)
  - Sorting by intrinsic quality, not followers
  - brand_profile_id adds brand-fit overlay and campaign-potential
  - Missing layers => untiered with reason
  - Auth required
"""

from datetime import datetime

from models import (
    BrandProfile,
    Influencer,
    InfluencerAnalysis,
    User,
)
from database import get_db
import database


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_influencer(
    db,
    *,
    username="creator1",
    display_name="Creator One",
    followers_count=50_000,
    platform_id="UC_test_1",
    business_email="creator@example.com",
    talent_agency=False,
    enrichment_signals=None,
):
    """Insert an Influencer row and return it."""
    inf = Influencer(
        platform="youtube",
        platform_id=platform_id,
        username=username,
        display_name=display_name,
        followers_count=followers_count,
        engagement_rate=5.0,
        category="gaming",
        country="US",
        business_email=business_email,
        talent_agency=talent_agency,
        enrichment_signals=enrichment_signals,
    )
    db.add(inf)
    db.flush()
    db.refresh(inf)
    return inf


def _seed_analysis(
    db,
    influencer_id,
    *,
    brand_profile_id=None,
    trust_breakdown=None,
    sponsorship_profile=None,
    overall_match_score=None,
    original_match_score=None,
    override_reason=None,
):
    """Insert an InfluencerAnalysis row."""
    a = InfluencerAnalysis(
        influencer_id=influencer_id,
        brand_profile_id=brand_profile_id,
        trust_breakdown=trust_breakdown,
        sponsorship_profile=sponsorship_profile,
        overall_match_score=overall_match_score or 0.0,
        original_match_score=original_match_score,
        override_reason=override_reason,
        content_style_match_score=60.0,
        audience_match_score=55.0,
        engagement_quality_score=70.0,
        brand_safety_score=80.0,
        ai_analysis_summary="Test analysis",
        content_tone="friendly",
        top_video_themes=["gaming"],
    )
    db.add(a)
    db.flush()
    db.refresh(a)
    return a


def _make_signals(last_upload_days_ago=10.0, cv=0.25):
    return {
        "upload_cadence": {
            "cadence_days_median": 7.0,
            "cadence_days_mean": 8.0,
            "last_upload_days_ago": last_upload_days_ago,
        },
        "view_consistency": {
            "recent_view_median": 15_000,
            "recent_view_cv": cv,
            "sample_size": 10,
        },
        "engagement_depth": {
            "like_to_view_ratio": 0.06,
            "comment_to_view_ratio": 0.008,
            "sample_size": 10,
        },
        "subscriber_count": 50_000,
    }


def _make_trust(score=75.0, status="analyzed", confidence="high"):
    return {
        "status": status,
        "composite_trust_score": score,
        "confidence": confidence,
        "community_trust_depth": {"score": score},
        "authority": {"score": score * 0.8},
    }


def _make_sponsorship(score=70.0, status="analyzed", confidence="high", maturity_label="mature"):
    return {
        "status": status,
        "composite_sponsorship_score": score,
        "confidence": confidence,
        "maturity": {"label": maturity_label, "score": 80.0, "sponsored_ratio": 0.30},
        "quality": {"score": 65.0, "repeat_sponsors": ["brand_a"]},
    }


def _seed_brand_profile(db, user_id, name="TestBrand"):
    bp = BrandProfile(
        user_id=user_id,
        name=name,
        aggressive_score=5.0,
        creative_score=5.0,
        humorous_score=5.0,
        professional_score=5.0,
        edgy_score=5.0,
        target_age_min=18,
        target_age_max=35,
        target_countries=["US"],
        preferred_categories=["gaming"],
        target_aov=40.0,
    )
    db.add(bp)
    db.flush()
    db.refresh(bp)
    return bp


def _get_user_id(auth_client):
    """Extract user ID from the auth client."""
    resp = auth_client.get("/api/v1/auth/me")
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRosterIntelligenceEndpoint:

    def test_requires_auth(self, client):
        r = client.get("/api/v1/roster/intelligence")
        assert r.status_code == 401

    def test_empty_roster(self, auth_client):
        r = auth_client.get("/api/v1/roster/intelligence")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 0
        assert body["creators"] == []
        assert body["sort_order"] == "intrinsic_quality"

    def test_composition_from_stored_data(self, auth_client):
        """Verify the endpoint composes tier from stored trust + sponsorship."""
        db = next(get_db())
        try:
            inf = _seed_influencer(
                db,
                enrichment_signals=_make_signals(),
                business_email="a@b.com",
            )
            _seed_analysis(
                db,
                inf.id,
                trust_breakdown=_make_trust(score=80.0),
                sponsorship_profile=_make_sponsorship(score=75.0),
            )
            db.commit()
            inf_id = inf.id
        finally:
            db.close()

        r = auth_client.get("/api/v1/roster/intelligence")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 1

        creator = body["creators"][0]
        assert creator["influencer_id"] == inf_id
        assert creator["intelligence"]["tier"] == "S"
        assert creator["intelligence"]["readiness"]["gate_passed"] is True
        assert creator["trust_breakdown"] is not None
        assert creator["sponsorship_profile"] is not None
        # No brand-fit without brand_profile_id
        assert creator["brand_fit"] is None
        assert creator["campaign_potential"] is None

    def test_sorting_by_intrinsic_quality_not_followers(self, auth_client):
        """S-tier with fewer followers should rank above B-tier with more."""
        db = next(get_db())
        try:
            # Small creator with high trust/sponsorship
            inf_small = _seed_influencer(
                db,
                username="small_quality",
                display_name="Small Quality",
                followers_count=5_000,
                platform_id="UC_small",
                enrichment_signals=_make_signals(),
                business_email="small@test.com",
            )
            _seed_analysis(
                db,
                inf_small.id,
                trust_breakdown=_make_trust(score=85.0),
                sponsorship_profile=_make_sponsorship(score=80.0),
            )

            # Large creator with low trust/sponsorship
            inf_large = _seed_influencer(
                db,
                username="large_commodity",
                display_name="Large Commodity",
                followers_count=5_000_000,
                platform_id="UC_large",
                enrichment_signals=_make_signals(),
                business_email="large@test.com",
            )
            _seed_analysis(
                db,
                inf_large.id,
                trust_breakdown=_make_trust(score=25.0),
                sponsorship_profile=_make_sponsorship(score=20.0),
            )
            db.commit()
        finally:
            db.close()

        r = auth_client.get("/api/v1/roster/intelligence")
        assert r.status_code == 200
        body = r.json()
        creators = body["creators"]
        assert len(creators) == 2

        # Small quality creator should be first despite fewer followers
        assert creators[0]["username"] == "small_quality"
        assert creators[0]["intelligence"]["tier"] == "S"
        assert creators[1]["username"] == "large_commodity"
        assert creators[1]["intelligence"]["tier"] == "B"

    def test_untiered_when_no_analysis(self, auth_client):
        """Creator with no analysis rows should be untiered."""
        db = next(get_db())
        try:
            _seed_influencer(
                db,
                enrichment_signals=_make_signals(),
                business_email="a@b.com",
            )
            db.commit()
        finally:
            db.close()

        r = auth_client.get("/api/v1/roster/intelligence")
        assert r.status_code == 200
        creator = r.json()["creators"][0]
        assert creator["intelligence"]["tier"] is None
        assert creator["intelligence"]["tier_label"] == "Untiered"

    def test_brand_profile_id_adds_overlay(self, auth_client):
        """When brand_profile_id is provided, brand_fit and campaign_potential appear."""
        user_id = _get_user_id(auth_client)
        db = next(get_db())
        try:
            bp = _seed_brand_profile(db, user_id)
            inf = _seed_influencer(
                db,
                enrichment_signals=_make_signals(),
                business_email="a@b.com",
            )
            inf_id = inf.id
            # Analysis with trust + sponsorship (intrinsic)
            _seed_analysis(
                db,
                inf_id,
                trust_breakdown=_make_trust(score=70.0),
                sponsorship_profile=_make_sponsorship(score=65.0),
            )
            # Brand-specific analysis
            _seed_analysis(
                db,
                inf_id,
                brand_profile_id=bp.id,
                overall_match_score=78.0,
                original_match_score=82.0,
                override_reason="test cap",
            )
            db.commit()
            bp_id = bp.id
        finally:
            db.close()

        r = auth_client.get(f"/api/v1/roster/intelligence?brand_profile_id={bp_id}")
        assert r.status_code == 200
        body = r.json()
        assert body["brand_profile_id"] == bp_id
        assert body["disclaimer"] is not None

        creator = body["creators"][0]
        # Brand-fit overlay present
        assert creator["brand_fit"] is not None
        assert creator["brand_fit"]["overall_match_score"] == 78.0
        assert "SEPARATE" in creator["brand_fit"].get("note", "")

        # Campaign potential present and labeled as secondary
        assert creator["campaign_potential"] is not None
        assert creator["campaign_potential"]["label"] == "SECONDARY ESTIMATE"
        assert "industry-benchmark" in creator["campaign_potential"]["disclaimer"].lower()

        # Intrinsic tier is SEPARATE from brand-fit
        assert creator["intelligence"]["tier"] is not None

    def test_invalid_brand_profile_id_returns_404(self, auth_client):
        r = auth_client.get("/api/v1/roster/intelligence?brand_profile_id=99999")
        assert r.status_code == 404

    def test_brand_fit_missing_shows_note(self, auth_client):
        """When brand_profile_id is given but no brand analysis exists."""
        user_id = _get_user_id(auth_client)
        db = next(get_db())
        try:
            bp = _seed_brand_profile(db, user_id)
            _seed_influencer(
                db,
                enrichment_signals=_make_signals(),
                business_email="a@b.com",
            )
            db.commit()
            bp_id = bp.id
        finally:
            db.close()

        r = auth_client.get(f"/api/v1/roster/intelligence?brand_profile_id={bp_id}")
        assert r.status_code == 200
        creator = r.json()["creators"][0]
        assert creator["brand_fit"]["overall_match_score"] is None
        assert "no brand-fit analysis" in creator["brand_fit"]["note"].lower()

    def test_dormant_creator_capped_at_b(self, auth_client):
        """Dormant creator should be capped at B despite high scores."""
        db = next(get_db())
        try:
            inf = _seed_influencer(
                db,
                enrichment_signals=_make_signals(last_upload_days_ago=150.0),
                business_email="a@b.com",
            )
            _seed_analysis(
                db,
                inf.id,
                trust_breakdown=_make_trust(score=85.0),
                sponsorship_profile=_make_sponsorship(score=80.0),
            )
            db.commit()
        finally:
            db.close()

        r = auth_client.get("/api/v1/roster/intelligence")
        assert r.status_code == 200
        creator = r.json()["creators"][0]
        assert creator["intelligence"]["tier"] == "B"
        assert "capped" in (creator["intelligence"]["override_reason"] or "").lower()

    def test_sponsorship_readiness_in_response(self, auth_client):
        """Verify sponsorship_readiness appears as a top-level field per creator."""
        db = next(get_db())
        try:
            inf = _seed_influencer(
                db,
                enrichment_signals=_make_signals(),
                business_email="a@b.com",
            )
            _seed_analysis(
                db,
                inf.id,
                trust_breakdown=_make_trust(score=70.0),
                sponsorship_profile=_make_sponsorship(score=65.0, maturity_label="mature"),
            )
            db.commit()
        finally:
            db.close()

        r = auth_client.get("/api/v1/roster/intelligence")
        assert r.status_code == 200
        creator = r.json()["creators"][0]

        # Top-level sponsorship_readiness
        sr = creator.get("sponsorship_readiness")
        assert sr is not None
        assert sr["label"] == "mature"
        assert sr["score"] == 65.0
        assert sr["outreach_implication"] is not None
        assert sr["explanation"] is not None

        # Also present inside intelligence
        intel_sr = creator["intelligence"].get("sponsorship_readiness")
        assert intel_sr is not None
        assert intel_sr["label"] == "mature"

    def test_sort_by_trust_not_sponsorship(self, auth_client):
        """Within same tier, creators sort by trust score, not sponsorship."""
        db = next(get_db())
        try:
            # Creator with higher trust but lower sponsorship
            inf_high_trust = _seed_influencer(
                db,
                username="high_trust",
                display_name="High Trust",
                followers_count=50_000,
                platform_id="UC_ht",
                enrichment_signals=_make_signals(),
                business_email="ht@test.com",
            )
            _seed_analysis(
                db,
                inf_high_trust.id,
                trust_breakdown=_make_trust(score=75.0),
                sponsorship_profile=_make_sponsorship(score=30.0),
            )

            # Creator with lower trust but higher sponsorship
            inf_high_spons = _seed_influencer(
                db,
                username="high_spons",
                display_name="High Sponsorship",
                followers_count=50_000,
                platform_id="UC_hs",
                enrichment_signals=_make_signals(),
                business_email="hs@test.com",
            )
            _seed_analysis(
                db,
                inf_high_spons.id,
                trust_breakdown=_make_trust(score=65.0),
                sponsorship_profile=_make_sponsorship(score=90.0),
            )
            db.commit()
        finally:
            db.close()

        r = auth_client.get("/api/v1/roster/intelligence")
        assert r.status_code == 200
        creators = r.json()["creators"]
        assert len(creators) == 2

        # Both are S-tier (trust >= 58, reachable, active)
        # Higher trust (75) should sort first, despite lower sponsorship
        assert creators[0]["username"] == "high_trust"
        assert creators[1]["username"] == "high_spons"

    def test_sort_description_reflects_trust_model(self, auth_client):
        """sort_description should reflect trust-based sorting."""
        r = auth_client.get("/api/v1/roster/intelligence")
        assert r.status_code == 200
        desc = r.json()["sort_description"].lower()
        assert "trust" in desc
        assert "follower" not in desc or "not" in desc
