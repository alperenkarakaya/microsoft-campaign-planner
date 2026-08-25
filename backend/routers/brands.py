from datetime import datetime
from typing import List, Dict

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session

from database import get_db
from schemas import (
    BrandProfileCreate,
    BrandProfileResponse,
    InfluencerDiscoveryRequest,
    CampaignRecommendation,
)
from models import (
    BrandProfile,
    User,
    Influencer,
    InfluencerAnalysis,
    InfluencerRecommendation,
)
from utils.security import get_current_user
from utils.youtube_discovery import search_youtube_influencers, get_channel_recent_videos, YouTubeDiscoveryError
from utils.youtube_api import YouTubeAPIError
from utils.brand_matcher import (
    analyze_influencer_brand_fit,
    categorize_influencer,
    estimate_cpm_range,
    generate_campaign_strategy,
)
from utils.benchmarks import predict_campaign_outcome
from utils.ai_detector import detect_fake_followers


import logging
logger = logging.getLogger(__name__)


router = APIRouter()


@router.post("/profiles", response_model=BrandProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_brand_profile(
    profile: BrandProfileCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db_profile = BrandProfile(**profile.model_dump(), user_id=current_user.id)
    db.add(db_profile)
    db.commit()
    db.refresh(db_profile)
    return db_profile


@router.get("/profiles", response_model=List[BrandProfileResponse])
async def list_brand_profiles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(BrandProfile).filter(BrandProfile.user_id == current_user.id).all()


@router.get("/profiles/{profile_id}", response_model=BrandProfileResponse)
async def get_brand_profile(
    profile_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    profile = db.query(BrandProfile).filter(
        BrandProfile.id == profile_id,
        BrandProfile.user_id == current_user.id,
    ).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Brand profile not found")
    return profile


@router.post("/discover", response_model=CampaignRecommendation)
async def discover_influencers(
    request: InfluencerDiscoveryRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Discover, score, and predict outcomes for influencers matching a brand profile.

    Pipeline:
      1. YouTube Data API → real channel stats + median recent video views.
      2. Gemini → 0-100 fit scores (style, audience, engagement, brand safety).
      3. Heuristic + Gemini → fake-follower estimate.
      4. benchmarks.predict_campaign_outcome → grounded reach/clicks/conversions/revenue/ROI ranges.

    Influencers without successful AI analysis are excluded — there is no
    fabricated baseline score.
    """
    brand_profile = db.query(BrandProfile).filter(
        BrandProfile.id == request.brand_profile_id,
        BrandProfile.user_id == current_user.id,
    ).first()
    if not brand_profile:
        raise HTTPException(status_code=404, detail="Brand profile not found")

    search_query = request.search_query or " ".join(
        brand_profile.preferred_categories or ["content creator", "influencer"]
    )

    min_subs = request.min_subscribers or brand_profile.min_followers
    max_subs = request.max_subscribers or brand_profile.max_followers
    min_view_ratio = request.min_view_ratio if request.min_view_ratio is not None else 3.0

    try:
        youtube_results = await search_youtube_influencers(
            query=search_query,
            min_subscribers=min_subs,
            max_subscribers=max_subs,
            max_results=request.max_results,
            min_view_ratio=min_view_ratio,
        )
    except (YouTubeDiscoveryError, YouTubeAPIError) as e:
        logger.warning("YouTube discovery failed: %s", e)
        raise HTTPException(
            status_code=503,
            detail=f"YouTube data unavailable: {str(e)[:200]}",
        )
    except Exception as e:
        logger.exception("Unexpected discovery failure")
        raise HTTPException(status_code=500, detail="YouTube search failed. Please try again.")

    if not youtube_results:
        raise HTTPException(
            status_code=404,
            detail=f"No influencers found for '{search_query}'. Try different keywords.",
        )

    # Brand profile dict for the AI prompt (avoid passing the SA instance).
    brand_dict = {
        "name": brand_profile.name,
        "aggressive_score": brand_profile.aggressive_score,
        "creative_score": brand_profile.creative_score,
        "humorous_score": brand_profile.humorous_score,
        "professional_score": brand_profile.professional_score,
        "edgy_score": brand_profile.edgy_score,
        "target_age_min": brand_profile.target_age_min,
        "target_age_max": brand_profile.target_age_max,
    }

    # Region for CPM benchmark — first target country, fallback to channel country.
    target_region = (
        (brand_profile.target_countries or [None])[0]
        if brand_profile.target_countries else None
    )

    matched_influencers: List[Dict] = []

    for yt in youtube_results:
        try:
            recent_videos = await get_channel_recent_videos(yt["channel_id"], max_videos=10)

            ai = await analyze_influencer_brand_fit(
                brand_profile=brand_dict,
                influencer_data=yt,
                recent_videos=recent_videos,
            )

            if ai.get("status") != "analyzed":
                # AI failed — skip rather than surface a fake match.
                continue
            if ai["overall_match_score"] < 40:
                continue

            existing = db.query(Influencer).filter(
                Influencer.platform_id == yt["channel_id"]
            ).first()

            if recent_videos:
                total_engagement = sum(v["likes"] + v["comments"] for v in recent_videos)
                total_views = sum(v["views"] for v in recent_videos)
                video_engagement_rate = (
                    round((total_engagement / total_views) * 100, 2)
                    if total_views > 0 else 0.0
                )
            else:
                video_engagement_rate = 0.0

            # Honour the optional engagement-rate floor from the discovery request.
            if (
                request.min_engagement_rate is not None
                and video_engagement_rate < request.min_engagement_rate
            ):
                continue

            if not existing:
                existing = Influencer(
                    platform="youtube",
                    platform_id=yt["channel_id"],
                    username=yt["username"],
                    display_name=yt["title"],
                    followers_count=yt["subscriber_count"],
                    engagement_rate=video_engagement_rate,
                    category=", ".join(brand_profile.preferred_categories or []),
                    country=yt.get("country") or target_region,
                    avatar_url=yt["thumbnail"],
                    bio=yt["description"][:500] if yt.get("description") else None,
                    verified=yt["subscriber_count"] > 100_000,
                    platform_metadata=yt,
                    last_updated=datetime.utcnow(),
                )
                db.add(existing)
                # flush (not commit) to assign the PK; one commit per iteration below.
                db.flush()
                db.refresh(existing)
            else:
                existing.followers_count = yt["subscriber_count"]
                existing.engagement_rate = video_engagement_rate
                existing.last_updated = datetime.utcnow()

            fake_pct = await detect_fake_followers({
                "title": yt["title"],
                "subscriber_count": yt["subscriber_count"],
                "video_count": yt["video_count"],
                "view_count": yt["view_count"],
                "engagement_rate": video_engagement_rate,
            })
            if fake_pct is not None:
                existing.fake_follower_percentage = fake_pct

            tier = categorize_influencer(yt["subscriber_count"])
            cpm = estimate_cpm_range("youtube", yt["subscriber_count"], target_region)
            median_recent_views = yt.get("median_recent_views")

            prediction = predict_campaign_outcome(
                platform="youtube",
                tier=tier,
                category=(brand_profile.preferred_categories or [None])[0],
                region=target_region,
                median_recent_views=median_recent_views,
                follower_count=yt["subscriber_count"],
                target_aov=brand_profile.target_aov,
                num_posts=request.num_posts,
            )
            prediction_dict = prediction.to_dict()

            analysis = InfluencerAnalysis(
                influencer_id=existing.id,
                brand_profile_id=brand_profile.id,
                content_style_match_score=ai["content_style_match"],
                audience_match_score=ai["audience_match"],
                engagement_quality_score=ai["engagement_quality"],
                brand_safety_score=ai["brand_safety"],
                overall_match_score=ai["overall_match_score"],
                original_match_score=ai.get("original_match_score"),
                override_reason=ai.get("override_reason"),
                ai_analysis_summary=ai["ai_summary"],
                top_video_themes=ai.get("top_themes", []),
                content_tone=ai["content_tone"],
                quality_flags=ai.get("quality_flags", []),
                predicted_outcome=prediction_dict,
                cpm_benchmark_low=cpm.low,
                cpm_benchmark_high=cpm.high,
            )
            db.add(analysis)
            db.commit()

            matched_influencers.append({
                "influencer_id": existing.id,
                "username": existing.username,
                "display_name": existing.display_name,
                "followers_count": existing.followers_count,
                "overall_match_score": ai["overall_match_score"],
                "content_style_match": ai["content_style_match"],
                "audience_match": ai["audience_match"],
                "engagement_quality": ai["engagement_quality"],
                "brand_safety": ai["brand_safety"],
                "ai_summary": ai["ai_summary"],
                "category": tier,
                "engagement_rate": existing.engagement_rate,
                "content_tone": ai["content_tone"],
                "cpm_benchmark": (cpm.low, cpm.high),
                "median_recent_views": median_recent_views,
                "fake_follower_percentage": fake_pct,
                "quality_flags": ai.get("quality_flags", []),
                "predicted_outcome": prediction_dict,
            })

        except Exception:
            # One bad influencer must not abort the whole discovery. Roll back any
            # partial writes from this iteration and move on.
            db.rollback()
            logger.exception("Error analyzing channel %s", yt.get("title", "unknown"))
            continue

    if not matched_influencers:
        raise HTTPException(
            status_code=404,
            detail="No suitable influencers found. Try relaxing your criteria.",
        )

    matched_influencers.sort(key=lambda x: x["overall_match_score"], reverse=True)
    top = matched_influencers[:20]

    # Aggregate campaign envelope from per-influencer prediction ranges.
    budget_low = sum(inf["predicted_outcome"]["predicted_cost"][0] for inf in top)
    budget_high = sum(inf["predicted_outcome"]["predicted_cost"][1] for inf in top)
    reach_low = sum(inf["predicted_outcome"]["predicted_reach"][0] for inf in top)
    reach_high = sum(inf["predicted_outcome"]["predicted_reach"][1] for inf in top)

    has_aov = brand_profile.target_aov is not None and brand_profile.target_aov > 0
    if has_aov:
        revenue_low = sum(inf["predicted_outcome"]["predicted_revenue"][0] for inf in top)
        revenue_high = sum(inf["predicted_outcome"]["predicted_revenue"][1] for inf in top)
        if budget_low > 0:
            roi_low = ((revenue_low - budget_high) / budget_high) * 100
            roi_high = ((revenue_high - budget_low) / budget_low) * 100
        else:
            roi_low = roi_high = 0.0
        predicted_total_revenue = (round(revenue_low, 2), round(revenue_high, 2))
        predicted_total_roi = (round(roi_low, 1), round(roi_high, 1))
    else:
        predicted_total_revenue = None
        predicted_total_roi = None

    campaign_strategy = await generate_campaign_strategy(
        brand_profile=brand_profile, top_influencers=top
    )

    recommendation = InfluencerRecommendation(
        brand_profile_id=brand_profile.id,
        micro_influencers=[
            {"id": inf["influencer_id"], "score": inf["overall_match_score"],
             "estimated_cost": inf["predicted_outcome"]["predicted_cost"]}
            for inf in top if inf["category"] == "micro"
        ],
        macro_influencers=[
            {"id": inf["influencer_id"], "score": inf["overall_match_score"],
             "estimated_cost": inf["predicted_outcome"]["predicted_cost"]}
            for inf in top if inf["category"] == "macro"
        ],
        mega_influencers=[
            {"id": inf["influencer_id"], "score": inf["overall_match_score"],
             "estimated_cost": inf["predicted_outcome"]["predicted_cost"]}
            for inf in top if inf["category"] == "mega"
        ],
        recommended_budget_low=round(budget_low, 2),
        recommended_budget_high=round(budget_high, 2),
        projected_total_reach_low=reach_low,
        projected_total_reach_high=reach_high,
        predicted_total_revenue_low=predicted_total_revenue[0] if predicted_total_revenue else None,
        predicted_total_revenue_high=predicted_total_revenue[1] if predicted_total_revenue else None,
        predicted_total_roi_low=predicted_total_roi[0] if predicted_total_roi else None,
        predicted_total_roi_high=predicted_total_roi[1] if predicted_total_roi else None,
        campaign_strategy=campaign_strategy,
    )
    db.add(recommendation)
    db.commit()

    return {
        "brand_profile_name": brand_profile.name,
        "recommended_influencers": top,
        "recommended_budget": (round(budget_low, 2), round(budget_high, 2)),
        "projected_total_reach": (reach_low, reach_high),
        "predicted_total_revenue": predicted_total_revenue,
        "predicted_total_roi_percentage": predicted_total_roi,
        "campaign_strategy": campaign_strategy,
        "breakdown": {
            "micro_count": sum(1 for i in top if i["category"] == "micro"),
            "macro_count": sum(1 for i in top if i["category"] == "macro"),
            "mega_count": sum(1 for i in top if i["category"] == "mega"),
            "avg_match_score": round(
                sum(i["overall_match_score"] for i in top) / len(top), 2
            ),
            "aov_provided": has_aov,
        },
    }


@router.get("/recommendations/{brand_profile_id}")
async def get_recommendations(
    brand_profile_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(InfluencerRecommendation).filter(
        InfluencerRecommendation.brand_profile_id == brand_profile_id
    ).order_by(InfluencerRecommendation.created_at.desc()).limit(5).all()
