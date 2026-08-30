"""
Roster Intelligence endpoint (Phase 4 + Phase 5).

Returns the composed creator-intelligence view from STORED data:
  - Intrinsic tier (S / A / B) + trust_breakdown + sponsorship_profile + readiness flags
  - Sorted by intrinsic quality (NOT followers)
  - Optional ?brand_profile_id= adds brand-fit overlay + demoted campaign-potential

This endpoint reads stored analysis — it does NOT trigger live YouTube/Gemini
enrichment inline. If a creator lacks stored layers, they are returned as
untiered with a reason.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from models import (
    BrandProfile,
    Influencer,
    InfluencerAnalysis,
    User,
)
from schemas import (
    RosterCreatorResponse,
    RosterIntelligenceResponse,
    SponsorshipReadiness,
)
from utils.security import get_current_user
from utils.tiering import compose_creator_intelligence
from utils.brand_matcher import (
    analyze_influencer_brand_fit,
    categorize_influencer,
    estimate_cpm_range,
)
from utils.benchmarks import predict_campaign_outcome


logger = logging.getLogger(__name__)


router = APIRouter()


def _tier_sort_key(creator: Dict[str, Any]) -> tuple:
    """Sort key: intrinsic quality descending.

    Order: S > A > B > untiered.
    Within same tier: higher trust score first (primary sort).
    Sponsorship score is a TIEBREAKER only (secondary sort within same trust).
    Follower count is NEVER part of the sort key.
    """
    intelligence = creator.get("intelligence", {})
    tier = intelligence.get("tier")
    tier_rank = {"S": 3, "A": 2, "B": 1}.get(tier, 0)
    trust_score = intelligence.get("trust_score") or 0.0
    sponsorship_score = intelligence.get("sponsorship_score") or 0.0
    return (tier_rank, trust_score, sponsorship_score)


def _build_campaign_potential(
    influencer: Influencer,
    brand_profile: BrandProfile,
    enrichment_signals: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build the DEMOTED campaign-potential estimate.

    Reuses benchmarks.predict_campaign_outcome and explicitly labels the
    result as a secondary, industry-benchmark estimate (not a per-creator
    forecast).
    """
    tier = categorize_influencer(influencer.followers_count or 0)

    # Extract median recent views from enrichment signals
    median_views: Optional[int] = None
    if enrichment_signals:
        vc = enrichment_signals.get("view_consistency") or {}
        median_views = vc.get("recent_view_median")

    # Region from brand profile
    target_region = (
        (brand_profile.target_countries or [None])[0]
        if brand_profile.target_countries else None
    )
    category = (
        (brand_profile.preferred_categories or [None])[0]
        if brand_profile.preferred_categories else None
    )

    prediction = predict_campaign_outcome(
        platform=influencer.platform or "youtube",
        tier=tier,
        category=category,
        region=target_region,
        median_recent_views=median_views,
        follower_count=influencer.followers_count or 0,
        target_aov=brand_profile.target_aov,
        num_posts=1,
    )
    result = prediction.to_dict()

    # Explicitly label as secondary/demoted
    result["label"] = "SECONDARY ESTIMATE"
    result["disclaimer"] = (
        "This is an industry-benchmark estimate based on aggregate CTR/CVR/CPM "
        "data, NOT a per-creator forecast. It does not account for this "
        "creator's unique audience quality, trust level, or sponsorship "
        "authenticity. Replace with actuals after the campaign runs."
    )

    return result


@router.get("/intelligence", response_model=RosterIntelligenceResponse)
async def roster_intelligence(
    brand_profile_id: Optional[int] = Query(
        default=None,
        description=(
            "Optional. When provided, adds a brand-fit overlay and demoted "
            "campaign-potential estimate per creator."
        ),
    ),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return composed creator-intelligence view from stored data.

    Sorted by intrinsic quality (trust + sponsorship tier), NOT by followers.
    Does NOT trigger live enrichment — reads stored analysis only.
    """
    # Validate brand profile if provided
    brand_profile: Optional[BrandProfile] = None
    if brand_profile_id is not None:
        brand_profile = db.query(BrandProfile).filter(
            BrandProfile.id == brand_profile_id,
            BrandProfile.user_id == current_user.id,
        ).first()
        if not brand_profile:
            raise HTTPException(status_code=404, detail="Brand profile not found")

    # Total count across the whole roster (independent of this page's slice) —
    # used by the frontend for "Showing X of {total}" and Next-page enablement.
    total_influencers = db.query(Influencer).count()

    # Fetch this page of influencers
    influencers = db.query(Influencer).offset(skip).limit(limit).all()

    # Pre-fetch the LATEST analysis per influencer (not brand-specific — this is
    # the intrinsic analysis with trust + sponsorship stored).
    # We look for any InfluencerAnalysis row that has trust_breakdown or
    # sponsorship_profile populated (these are stored per-influencer during
    # enrichment, sometimes with a brand_profile_id from discovery).
    influencer_ids = [i.id for i in influencers]
    analyses_by_influencer: Dict[int, InfluencerAnalysis] = {}

    if influencer_ids:
        # Get the most recent analysis per influencer that has trust or sponsorship data.
        # Two passes: first collect rows with trust/sponsorship, then fallback to any row.
        analyses = (
            db.query(InfluencerAnalysis)
            .filter(InfluencerAnalysis.influencer_id.in_(influencer_ids))
            .order_by(InfluencerAnalysis.analyzed_at.desc())
            .all()
        )
        fallback_by_influencer: Dict[int, InfluencerAnalysis] = {}
        for a in analyses:
            # Prefer analysis rows that have trust/sponsorship data
            if a.influencer_id not in analyses_by_influencer:
                if a.trust_breakdown or a.sponsorship_profile:
                    analyses_by_influencer[a.influencer_id] = a
            # Track the most recent row as fallback (regardless of content)
            if a.influencer_id not in fallback_by_influencer:
                fallback_by_influencer[a.influencer_id] = a
        # Fill in any influencers that had analysis rows but none with trust/sponsorship
        for inf_id, fallback in fallback_by_influencer.items():
            if inf_id not in analyses_by_influencer:
                analyses_by_influencer[inf_id] = fallback

    # Brand-fit analysis rows (brand-specific) — only when brand_profile_id given
    brand_fit_by_influencer: Dict[int, InfluencerAnalysis] = {}
    if brand_profile and influencer_ids:
        brand_analyses = (
            db.query(InfluencerAnalysis)
            .filter(
                InfluencerAnalysis.influencer_id.in_(influencer_ids),
                InfluencerAnalysis.brand_profile_id == brand_profile_id,
            )
            .order_by(InfluencerAnalysis.analyzed_at.desc())
            .all()
        )
        for a in brand_analyses:
            if a.influencer_id not in brand_fit_by_influencer:
                brand_fit_by_influencer[a.influencer_id] = a

    # Compose results
    creators: List[Dict[str, Any]] = []
    for inf in influencers:
        analysis = analyses_by_influencer.get(inf.id)

        enrichment_signals = inf.enrichment_signals
        trust_breakdown = analysis.trust_breakdown if analysis else None
        sponsorship_profile = analysis.sponsorship_profile if analysis else None

        # Compose intrinsic intelligence (Phase 4)
        influencer_data = {
            "business_email": inf.business_email,
            "talent_agency": inf.talent_agency,
        }
        intelligence = compose_creator_intelligence(
            enrichment_signals=enrichment_signals,
            trust_breakdown=trust_breakdown,
            sponsorship_profile=sponsorship_profile,
            influencer=influencer_data,
        )

        # Extract sponsorship_readiness for top-level prominence
        sr_data = intelligence.get("sponsorship_readiness")

        creator_dict: Dict[str, Any] = {
            "influencer_id": inf.id,
            "username": inf.username,
            "display_name": inf.display_name,
            "followers_count": inf.followers_count or 0,
            "platform": inf.platform or "youtube",
            "intelligence": intelligence,
            "trust_breakdown": trust_breakdown,
            "sponsorship_profile": sponsorship_profile,
            "sponsorship_readiness": sr_data,
            "brand_fit": None,
            "campaign_potential": None,
        }

        # Phase 5: Brand-fit overlay (SEPARATE from intrinsic tier)
        if brand_profile:
            brand_analysis = brand_fit_by_influencer.get(inf.id)
            if brand_analysis:
                # Compose brand-fit from stored analysis
                creator_dict["brand_fit"] = {
                    "overall_match_score": brand_analysis.overall_match_score,
                    "original_match_score": brand_analysis.original_match_score,
                    "content_style_match": brand_analysis.content_style_match_score,
                    "audience_match": brand_analysis.audience_match_score,
                    "engagement_quality": brand_analysis.engagement_quality_score,
                    "brand_safety": brand_analysis.brand_safety_score,
                    "content_tone": brand_analysis.content_tone,
                    "ai_summary": brand_analysis.ai_analysis_summary,
                    "override_reason": brand_analysis.override_reason,
                    "note": (
                        "Brand-fit is a SEPARATE per-campaign overlay. It does "
                        "not affect the intrinsic tier."
                    ),
                }
            else:
                creator_dict["brand_fit"] = {
                    "overall_match_score": None,
                    "note": (
                        "No brand-fit analysis stored for this creator and brand. "
                        "Run discovery to generate brand-fit scoring."
                    ),
                }

            # Phase 5: Campaign Potential (DEMOTED)
            creator_dict["campaign_potential"] = _build_campaign_potential(
                inf, brand_profile, enrichment_signals,
            )

        creators.append(creator_dict)

    # Sort by intrinsic quality (NOT followers)
    creators.sort(key=_tier_sort_key, reverse=True)

    disclaimer = None
    if brand_profile:
        disclaimer = (
            "Tier reflects intrinsic audience trust ONLY. Sponsorship readiness "
            "is a separate label indicating partnership experience. Brand-fit "
            "and campaign-potential are SECONDARY overlays. Campaign potential "
            "uses industry benchmarks and is NOT a per-creator forecast."
        )

    return {
        "creators": creators,
        "total": total_influencers,
        "sort_order": "intrinsic_quality",
        "sort_description": (
            "Sorted by intrinsic audience trust (tier), then trust score, "
            "then sponsorship readiness. NOT by follower count."
        ),
        "brand_profile_id": brand_profile_id,
        "disclaimer": disclaimer,
    }
