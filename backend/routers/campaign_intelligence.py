"""
AI Campaign Intelligence endpoints (additive layer on top of campaigns.py).

Mounted at the SAME prefix as routers/campaigns.py (/api/v1/campaigns) so URLs
read naturally (POST /campaigns/{id}/ai/match-creators, etc.) — a second
router under one prefix, so campaigns.py itself is untouched.

Every endpoint here composes on top of the existing intelligence pipeline
(utils.tiering.compose_creator_intelligence) rather than recomputing trust or
sponsorship data, per CLAUDE.md's "Intelligence Pipeline" philosophy.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from database import get_db
from models import (
    AIInsight,
    BrandProfile,
    Campaign,
    CampaignBrief,
    CampaignCreator,
    CampaignMatch,
    CampaignTask,
    CreatorContent,
    Influencer,
    InfluencerAnalysis,
    User,
)
from schemas import (
    AIInsightItem,
    AssistantQueryRequest,
    AssistantQueryResponse,
    BriefGenerateRequest,
    CampaignAnalyzeRequest,
    CampaignBriefResponse,
    CampaignBriefUnderstanding,
    CampaignCreatorResponse,
    CampaignCreatorUpdate,
    CampaignMatchListResponse,
    CampaignMatchRequest,
    CampaignMatchResult,
    CampaignPerformanceResponse,
    CampaignReportResponse,
    CampaignTaskCreate,
    CampaignTaskResponse,
    CampaignTaskUpdate,
    ContentGenerateRequest,
    CreatorContentResponse,
    CreatorPerformance,
    PerformanceAnalysisResponse,
    ShortlistRequest,
    CAMPAIGN_TASK_TYPES,
)
from utils.security import get_current_user
from utils.tiering import compose_creator_intelligence
from utils.ai.campaign_analyzer import analyze_campaign_brief
from utils.ai.campaign_matcher import compute_campaign_match
from utils.ai.brief_generator import generate_campaign_brief
from utils.ai.content_generator import generate_content
from utils.ai.performance_analyst import analyze_campaign_performance
from utils.ai.report_generator import build_report

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _get_owned_campaign(db: Session, campaign_id: int, user: User) -> Campaign:
    campaign = db.query(Campaign).filter(
        Campaign.id == campaign_id, Campaign.owner_id == user.id,
    ).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


def _get_owned_brand_profile(db: Session, brand_profile_id: int, user: User) -> BrandProfile:
    bp = db.query(BrandProfile).filter(
        BrandProfile.id == brand_profile_id, BrandProfile.user_id == user.id,
    ).first()
    if not bp:
        raise HTTPException(status_code=404, detail="Brand profile not found")
    return bp


def _compose_intelligence(db: Session, influencer: Influencer) -> Dict[str, Any]:
    """Mirrors routers/roster.py's composition: latest analysis row with
    trust/sponsorship data (falling back to any row) + Phase-1 signals."""
    analysis = (
        db.query(InfluencerAnalysis)
        .filter(InfluencerAnalysis.influencer_id == influencer.id)
        .order_by(InfluencerAnalysis.analyzed_at.desc())
        .all()
    )
    chosen: Optional[InfluencerAnalysis] = None
    fallback: Optional[InfluencerAnalysis] = None
    for a in analysis:
        if fallback is None:
            fallback = a
        if a.trust_breakdown or a.sponsorship_profile:
            chosen = a
            break
    chosen = chosen or fallback

    trust_breakdown = chosen.trust_breakdown if chosen else None
    sponsorship_profile = chosen.sponsorship_profile if chosen else None

    return compose_creator_intelligence(
        enrichment_signals=influencer.enrichment_signals,
        trust_breakdown=trust_breakdown,
        sponsorship_profile=sponsorship_profile,
        influencer={
            "business_email": influencer.business_email,
            "talent_agency": influencer.talent_agency,
        },
    )


def _brand_profile_dict(bp: BrandProfile, sponsorship_pref: Optional[str] = None) -> Dict[str, Any]:
    return {
        "name": bp.name,
        "preferred_categories": bp.preferred_categories or [],
        "target_countries": bp.target_countries or [],
        "target_aov": bp.target_aov,
        "sponsorship_pref": sponsorship_pref,
    }


def _creator_content_style(db: Session, influencer_id: int) -> Dict[str, Optional[Any]]:
    row = (
        db.query(InfluencerAnalysis)
        .filter(InfluencerAnalysis.influencer_id == influencer_id)
        .order_by(InfluencerAnalysis.analyzed_at.desc())
        .first()
    )
    return {
        "content_tone": row.content_tone if row else None,
        "top_video_themes": row.top_video_themes if row else None,
    }


def _serialize_creator(cc: CampaignCreator, inf: Influencer, match: Optional[CampaignMatch]) -> Dict[str, Any]:
    return {
        "id": cc.id,
        "campaign_id": cc.campaign_id,
        "influencer_id": cc.influencer_id,
        "username": inf.username,
        "display_name": inf.display_name,
        "status": cc.status,
        "recommended_role": cc.recommended_role,
        "notes": cc.notes,
        "match_score": match.match_score if match else None,
        "trust_score": match.trust_component if match else None,
        "tier": None,
        "views": cc.views,
        "engagement": cc.engagement,
        "clicks": cc.clicks,
        "conversions": cc.conversions,
        "revenue": cc.revenue,
        "spend": cc.spend,
        "added_at": cc.added_at,
        "updated_at": cc.updated_at,
    }


def _roi_percentage(revenue: Optional[float], spend: Optional[float]) -> Optional[float]:
    if revenue is None or spend is None or spend <= 0:
        return None
    return round(((revenue - spend) / spend) * 100, 1)


# ---------------------------------------------------------------------------
# AI Campaign Builder
# ---------------------------------------------------------------------------

@router.post("/{campaign_id}/ai/analyze", response_model=CampaignBriefUnderstanding)
async def analyze_campaign(
    campaign_id: int,
    request: CampaignAnalyzeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Parse natural language and/or structured input into a stored campaign
    understanding. Structured fields always win over anything extracted from
    raw_input; user can freely edit the result afterward via the same endpoint."""
    campaign = _get_owned_campaign(db, campaign_id, current_user)

    overrides = {
        "objective": request.objective,
        "target_audience": request.target_audience,
        "geography": request.geography,
        "category": request.category,
        "budget": request.budget,
        "trust_profile_pref": request.trust_profile_pref,
        "sponsorship_pref": request.sponsorship_pref,
        "kpis": request.kpis,
    }
    understanding = await analyze_campaign_brief(raw_input=request.raw_input, overrides=overrides)

    campaign.ai_campaign_brief = understanding
    db.commit()
    db.refresh(campaign)
    return understanding


# ---------------------------------------------------------------------------
# AI Creator Matching
# ---------------------------------------------------------------------------

@router.post("/{campaign_id}/ai/match-creators", response_model=CampaignMatchListResponse)
async def match_creators(
    campaign_id: int,
    request: CampaignMatchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Compute Campaign Match Score for the roster against this campaign +
    brand profile, upserting one CampaignMatch row per creator. Trust Score is
    read from stored intelligence, never recomputed here."""
    campaign = _get_owned_campaign(db, campaign_id, current_user)
    brand_profile = _get_owned_brand_profile(db, request.brand_profile_id, current_user)

    brief = campaign.ai_campaign_brief or {}
    brand_dict = _brand_profile_dict(brand_profile, sponsorship_pref=brief.get("sponsorship_pref"))
    campaign_budget = brief.get("budget") or campaign.budget

    influencers = db.query(Influencer).all()
    results: List[Dict[str, Any]] = []

    for inf in influencers:
        intelligence = _compose_intelligence(db, inf)
        if request.min_trust_score is not None:
            ts = intelligence.get("trust_score")
            if ts is None or ts < request.min_trust_score:
                continue

        match = compute_campaign_match(
            followers_count=inf.followers_count or 0,
            platform=inf.platform or "youtube",
            influencer_category=inf.category,
            influencer_country=inf.country,
            enrichment_signals=inf.enrichment_signals,
            intelligence=intelligence,
            brand_profile=brand_dict,
            campaign_budget=campaign_budget,
        )

        existing = db.query(CampaignMatch).filter(
            CampaignMatch.campaign_id == campaign_id,
            CampaignMatch.influencer_id == inf.id,
        ).first()
        if existing:
            for k in (
                "match_score", "audience_fit", "brand_fit", "category_fit",
                "geographic_fit", "budget_fit", "trust_component",
                "sponsorship_component", "risk_level", "reasons",
                "recommended_role", "confidence", "estimated_reach", "source",
            ):
                setattr(existing, k, match[k])
            existing.estimated_cost_low = match["estimated_cost_low"]
            existing.estimated_cost_high = match["estimated_cost_high"]
            existing.computed_at = datetime.utcnow()
            row = existing
        else:
            row = CampaignMatch(
                campaign_id=campaign_id,
                influencer_id=inf.id,
                match_score=match["match_score"],
                audience_fit=match["audience_fit"],
                brand_fit=match["brand_fit"],
                category_fit=match["category_fit"],
                geographic_fit=match["geographic_fit"],
                budget_fit=match["budget_fit"],
                trust_component=match["trust_component"],
                sponsorship_component=match["sponsorship_component"],
                risk_level=match["risk_level"],
                reasons=match["reasons"],
                recommended_role=match["recommended_role"],
                confidence=match["confidence"],
                estimated_reach=match["estimated_reach"],
                estimated_cost_low=match["estimated_cost_low"],
                estimated_cost_high=match["estimated_cost_high"],
                source=match["source"],
            )
            db.add(row)
        db.flush()

        results.append({
            "influencer_id": inf.id,
            "username": inf.username,
            "display_name": inf.display_name,
            "followers_count": inf.followers_count or 0,
            "tier": intelligence.get("tier"),
            "trust_score": intelligence.get("trust_score"),
            "sponsorship_maturity": (intelligence.get("sponsorship_readiness") or {}).get("label"),
            "match_score": match["match_score"],
            "audience_fit": match["audience_fit"],
            "brand_fit": match["brand_fit"],
            "category_fit": match["category_fit"],
            "geographic_fit": match["geographic_fit"],
            "budget_fit": match["budget_fit"],
            "trust_component": match["trust_component"],
            "sponsorship_component": match["sponsorship_component"],
            "risk_level": match["risk_level"],
            "reasons": match["reasons"],
            "why": match["why"],
            "recommended_role": match["recommended_role"],
            "confidence": match["confidence"],
            "estimated_reach": match["estimated_reach"],
            "estimated_cost": (match["estimated_cost_low"], match["estimated_cost_high"]),
            "computed_at": match["computed_at"],
        })

    db.commit()

    results.sort(key=lambda r: r["match_score"] or 0.0, reverse=True)
    results = results[: request.limit]

    return {
        "campaign_id": campaign_id,
        "brand_profile_id": request.brand_profile_id,
        "matches": results,
        "total": len(results),
    }


@router.get("/{campaign_id}/matches", response_model=CampaignMatchListResponse)
async def list_matches(
    campaign_id: int,
    tier: Optional[str] = Query(default=None),
    risk_level: Optional[str] = Query(default=None),
    sponsorship_maturity: Optional[str] = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List previously computed matches (run POST .../ai/match-creators first)."""
    campaign = _get_owned_campaign(db, campaign_id, current_user)

    matches = (
        db.query(CampaignMatch)
        .filter(CampaignMatch.campaign_id == campaign_id)
        .order_by(CampaignMatch.match_score.desc().nullslast())
        .all()
    )

    results: List[Dict[str, Any]] = []
    for m in matches:
        inf = db.query(Influencer).filter(Influencer.id == m.influencer_id).first()
        if not inf:
            continue
        if risk_level and m.risk_level != risk_level:
            continue
        intelligence = _compose_intelligence(db, inf)
        if tier and intelligence.get("tier") != tier:
            continue
        sponsorship_label = (intelligence.get("sponsorship_readiness") or {}).get("label")
        if sponsorship_maturity and sponsorship_label != sponsorship_maturity:
            continue

        results.append({
            "influencer_id": inf.id,
            "username": inf.username,
            "display_name": inf.display_name,
            "followers_count": inf.followers_count or 0,
            "tier": intelligence.get("tier"),
            "trust_score": intelligence.get("trust_score"),
            "sponsorship_maturity": sponsorship_label,
            "match_score": m.match_score,
            "audience_fit": m.audience_fit,
            "brand_fit": m.brand_fit,
            "category_fit": m.category_fit,
            "geographic_fit": m.geographic_fit,
            "budget_fit": m.budget_fit,
            "trust_component": m.trust_component,
            "sponsorship_component": m.sponsorship_component,
            "risk_level": m.risk_level,
            "reasons": m.reasons or [],
            "why": "; ".join(m.reasons or []),
            "recommended_role": m.recommended_role,
            "confidence": m.confidence,
            "estimated_reach": m.estimated_reach,
            "estimated_cost": (
                (m.estimated_cost_low, m.estimated_cost_high)
                if m.estimated_cost_low is not None and m.estimated_cost_high is not None else None
            ),
            "computed_at": m.computed_at.isoformat() if m.computed_at else None,
        })

    total = len(results)
    page = results[skip: skip + limit]

    return {
        "campaign_id": campaign_id,
        "brand_profile_id": None,
        "matches": page,
        "total": total,
    }


# ---------------------------------------------------------------------------
# Shortlist / Execution
# ---------------------------------------------------------------------------

@router.post("/{campaign_id}/shortlist", response_model=List[CampaignCreatorResponse], status_code=status.HTTP_201_CREATED)
async def shortlist_creators(
    campaign_id: int,
    request: ShortlistRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    campaign = _get_owned_campaign(db, campaign_id, current_user)

    out: List[Dict[str, Any]] = []
    for inf_id in request.influencer_ids:
        inf = db.query(Influencer).filter(Influencer.id == inf_id).first()
        if not inf:
            raise HTTPException(status_code=404, detail=f"Influencer {inf_id} not found")

        cc = db.query(CampaignCreator).filter(
            CampaignCreator.campaign_id == campaign_id,
            CampaignCreator.influencer_id == inf_id,
        ).first()
        if cc:
            if cc.status == "matched":
                cc.status = "shortlisted"
        else:
            match = db.query(CampaignMatch).filter(
                CampaignMatch.campaign_id == campaign_id,
                CampaignMatch.influencer_id == inf_id,
            ).first()
            cc = CampaignCreator(
                campaign_id=campaign_id,
                influencer_id=inf_id,
                status="shortlisted",
                recommended_role=match.recommended_role if match else None,
            )
            db.add(cc)
        db.flush()
        db.refresh(cc)

        match = db.query(CampaignMatch).filter(
            CampaignMatch.campaign_id == campaign_id,
            CampaignMatch.influencer_id == inf_id,
        ).first()
        out.append(_serialize_creator(cc, inf, match))

    db.commit()
    return out


@router.get("/{campaign_id}/creators", response_model=List[CampaignCreatorResponse])
async def list_campaign_creators(
    campaign_id: int,
    status_filter: Optional[str] = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    campaign = _get_owned_campaign(db, campaign_id, current_user)
    q = db.query(CampaignCreator).filter(CampaignCreator.campaign_id == campaign_id)
    if status_filter:
        q = q.filter(CampaignCreator.status == status_filter)
    rows = q.order_by(CampaignCreator.added_at.asc()).all()

    out = []
    for cc in rows:
        inf = db.query(Influencer).filter(Influencer.id == cc.influencer_id).first()
        if not inf:
            continue
        match = db.query(CampaignMatch).filter(
            CampaignMatch.campaign_id == campaign_id,
            CampaignMatch.influencer_id == cc.influencer_id,
        ).first()
        out.append(_serialize_creator(cc, inf, match))
    return out


_VALID_STATUSES = {
    "matched", "shortlisted", "contracted", "briefed", "content_creation",
    "review", "live", "completed", "removed",
}


@router.patch("/{campaign_id}/creators/{influencer_id}", response_model=CampaignCreatorResponse)
async def update_campaign_creator(
    campaign_id: int,
    influencer_id: int,
    update: CampaignCreatorUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    campaign = _get_owned_campaign(db, campaign_id, current_user)
    cc = db.query(CampaignCreator).filter(
        CampaignCreator.campaign_id == campaign_id,
        CampaignCreator.influencer_id == influencer_id,
    ).first()
    if not cc:
        raise HTTPException(status_code=404, detail="Creator not attached to this campaign")

    if update.status is not None:
        if update.status not in _VALID_STATUSES:
            raise HTTPException(status_code=422, detail=f"Invalid status. Must be one of {sorted(_VALID_STATUSES)}")
        cc.status = update.status

    for field in ("recommended_role", "notes", "views", "engagement", "clicks", "conversions", "revenue", "spend"):
        value = getattr(update, field)
        if value is not None:
            setattr(cc, field, value)

    db.commit()
    db.refresh(cc)

    inf = db.query(Influencer).filter(Influencer.id == influencer_id).first()
    match = db.query(CampaignMatch).filter(
        CampaignMatch.campaign_id == campaign_id, CampaignMatch.influencer_id == influencer_id,
    ).first()
    return _serialize_creator(cc, inf, match)


@router.post("/{campaign_id}/creators/{influencer_id}/tasks", response_model=CampaignTaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    campaign_id: int,
    influencer_id: int,
    task: CampaignTaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    campaign = _get_owned_campaign(db, campaign_id, current_user)
    if task.task_type not in CAMPAIGN_TASK_TYPES:
        raise HTTPException(status_code=422, detail=f"task_type must be one of {CAMPAIGN_TASK_TYPES}")

    cc = db.query(CampaignCreator).filter(
        CampaignCreator.campaign_id == campaign_id,
        CampaignCreator.influencer_id == influencer_id,
    ).first()
    if not cc:
        raise HTTPException(status_code=404, detail="Creator not attached to this campaign")

    row = CampaignTask(
        campaign_creator_id=cc.id,
        task_type=task.task_type,
        status=task.status,
        deadline=task.deadline,
        notes=task.notes,
        completed_at=datetime.utcnow() if task.status == "done" else None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    is_overdue = (
        row.status != "done"
        and row.deadline is not None
        and row.deadline < datetime.utcnow()
    )
    return {**row.__dict__, "is_overdue": is_overdue}


@router.get("/{campaign_id}/creators/{influencer_id}/tasks", response_model=List[CampaignTaskResponse])
async def list_tasks(
    campaign_id: int,
    influencer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    campaign = _get_owned_campaign(db, campaign_id, current_user)
    cc = db.query(CampaignCreator).filter(
        CampaignCreator.campaign_id == campaign_id,
        CampaignCreator.influencer_id == influencer_id,
    ).first()
    if not cc:
        raise HTTPException(status_code=404, detail="Creator not attached to this campaign")

    rows = db.query(CampaignTask).filter(CampaignTask.campaign_creator_id == cc.id).all()
    now = datetime.utcnow()
    out = []
    for r in rows:
        is_overdue = r.status != "done" and r.deadline is not None and r.deadline < now
        out.append({**r.__dict__, "is_overdue": is_overdue})
    return out


# ---------------------------------------------------------------------------
# AI Brief + Content Studio
# ---------------------------------------------------------------------------

@router.post("/{campaign_id}/brief", response_model=List[CampaignBriefResponse])
async def generate_briefs(
    campaign_id: int,
    request: BriefGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    campaign = _get_owned_campaign(db, campaign_id, current_user)
    brief_ctx = campaign.ai_campaign_brief or {}

    # Best-effort brand context: the most recently used brand profile for this
    # user (briefs need brand tone/name; campaigns don't carry a brand FK).
    brand_profile = (
        db.query(BrandProfile)
        .filter(BrandProfile.user_id == current_user.id)
        .order_by(BrandProfile.created_at.desc())
        .first()
    )
    brand_dict = _brand_profile_dict(brand_profile) if brand_profile else {"name": campaign.name}

    out = []
    for inf_id in request.influencer_ids:
        inf = db.query(Influencer).filter(Influencer.id == inf_id).first()
        if not inf:
            raise HTTPException(status_code=404, detail=f"Influencer {inf_id} not found")

        intelligence = _compose_intelligence(db, inf)
        style = _creator_content_style(db, inf_id)
        sponsorship_label = (intelligence.get("sponsorship_readiness") or {}).get("label")

        generated = await generate_campaign_brief(
            brand_profile=brand_dict,
            campaign_objective=brief_ctx.get("objective"),
            creator_display_name=inf.display_name,
            creator_category=inf.category,
            content_tone=style["content_tone"],
            top_video_themes=style["top_video_themes"],
            sponsorship_label=sponsorship_label,
            tier=intelligence.get("tier"),
        )

        row = db.query(CampaignBrief).filter(
            CampaignBrief.campaign_id == campaign_id, CampaignBrief.influencer_id == inf_id,
        ).first()
        if not row:
            row = CampaignBrief(campaign_id=campaign_id, influencer_id=inf_id)
            db.add(row)

        row.objective = generated["objective"]
        row.key_message = generated["key_message"]
        row.content_format = generated["content_format"]
        row.creative_direction = generated["creative_direction"]
        row.hook = generated["hook"]
        row.talking_points = generated["talking_points"]
        row.cta = generated["cta"]
        row.dos = generated["dos"]
        row.donts = generated["donts"]
        row.required_disclosures = generated["required_disclosures"]
        row.deliverables = generated["deliverables"]
        row.source = generated["source"]
        row.generated_at = datetime.utcnow()
        db.flush()
        db.refresh(row)

        out.append({
            "campaign_id": campaign_id,
            "influencer_id": inf_id,
            "username": inf.username,
            "display_name": inf.display_name,
            "objective": row.objective,
            "key_message": row.key_message,
            "content_format": row.content_format,
            "creative_direction": row.creative_direction,
            "hook": row.hook,
            "talking_points": row.talking_points or [],
            "cta": row.cta,
            "dos": row.dos or [],
            "donts": row.donts or [],
            "required_disclosures": row.required_disclosures,
            "deadline": row.deadline,
            "deliverables": row.deliverables or [],
            "source": row.source,
            "generated_at": row.generated_at,
        })

    db.commit()
    return out


@router.get("/{campaign_id}/brief/{influencer_id}", response_model=CampaignBriefResponse)
async def get_brief(
    campaign_id: int,
    influencer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    campaign = _get_owned_campaign(db, campaign_id, current_user)
    row = db.query(CampaignBrief).filter(
        CampaignBrief.campaign_id == campaign_id, CampaignBrief.influencer_id == influencer_id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="No brief generated yet for this creator")
    inf = db.query(Influencer).filter(Influencer.id == influencer_id).first()
    return {
        "campaign_id": campaign_id,
        "influencer_id": influencer_id,
        "username": inf.username if inf else None,
        "display_name": inf.display_name if inf else None,
        "objective": row.objective,
        "key_message": row.key_message,
        "content_format": row.content_format,
        "creative_direction": row.creative_direction,
        "hook": row.hook,
        "talking_points": row.talking_points or [],
        "cta": row.cta,
        "dos": row.dos or [],
        "donts": row.donts or [],
        "required_disclosures": row.required_disclosures,
        "deadline": row.deadline,
        "deliverables": row.deliverables or [],
        "source": row.source,
        "generated_at": row.generated_at,
    }


@router.post("/content/generate", response_model=CreatorContentResponse, status_code=status.HTTP_201_CREATED)
async def generate_creator_content(
    request: ContentGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    inf = db.query(Influencer).filter(Influencer.id == request.influencer_id).first()
    if not inf:
        raise HTTPException(status_code=404, detail="Influencer not found")

    brand_name = None
    if request.campaign_id is not None:
        campaign = _get_owned_campaign(db, request.campaign_id, current_user)
        brand_name = campaign.name

    style = _creator_content_style(db, request.influencer_id)

    generated = await generate_content(
        content_type=request.content_type,
        creator_display_name=inf.display_name,
        creator_category=inf.category,
        content_tone=style["content_tone"],
        brand_name=brand_name,
        extra_instructions=request.extra_instructions,
    )

    row = CreatorContent(
        influencer_id=request.influencer_id,
        campaign_id=request.campaign_id,
        content_type=request.content_type,
        caption=generated.get("caption"),
        title=generated.get("title"),
        description=generated.get("description"),
        hook=generated.get("hook"),
        video_concept=generated.get("video_concept"),
        script_outline=generated.get("script_outline"),
        cta=generated.get("cta"),
        hashtags=generated.get("hashtags"),
        talking_points=generated.get("talking_points"),
        source=generated.get("source"),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "id": row.id,
        "influencer_id": row.influencer_id,
        "campaign_id": row.campaign_id,
        "content_type": row.content_type,
        "caption": row.caption,
        "title": row.title,
        "description": row.description,
        "hook": row.hook,
        "video_concept": row.video_concept,
        "script_outline": row.script_outline,
        "cta": row.cta,
        "hashtags": row.hashtags or [],
        "talking_points": row.talking_points or [],
        "source": row.source,
        "generated_at": row.generated_at,
    }


# ---------------------------------------------------------------------------
# Performance + AI Analyst + Report
# ---------------------------------------------------------------------------

def _compute_performance(db: Session, campaign: Campaign) -> Dict[str, Any]:
    creators = db.query(CampaignCreator).filter(CampaignCreator.campaign_id == campaign.id).all()

    per_creator: List[Dict[str, Any]] = []
    has_any = False
    has_full = True

    total_views = total_engagement = total_clicks = total_conversions = 0
    total_revenue = total_spend = 0.0
    any_views = any_clicks = any_conversions = any_revenue = any_spend = False

    for cc in creators:
        inf = db.query(Influencer).filter(Influencer.id == cc.influencer_id).first()
        if not inf:
            continue
        match = db.query(CampaignMatch).filter(
            CampaignMatch.campaign_id == campaign.id, CampaignMatch.influencer_id == cc.influencer_id,
        ).first()
        has_actuals = any(
            v is not None for v in (cc.views, cc.engagement, cc.clicks, cc.conversions, cc.revenue, cc.spend)
        )
        if has_actuals:
            has_any = True
        else:
            has_full = False

        roi = _roi_percentage(cc.revenue, cc.spend)
        per_creator.append({
            "influencer_id": inf.id,
            "username": inf.username,
            "display_name": inf.display_name,
            "views": cc.views,
            "engagement": cc.engagement,
            "clicks": cc.clicks,
            "conversions": cc.conversions,
            "revenue": cc.revenue,
            "spend": cc.spend,
            "roi_percentage": roi,
            "match_score": match.match_score if match else None,
            "trust_score": match.trust_component if match else None,
            "has_actuals": has_actuals,
        })

        if cc.views is not None:
            total_views += cc.views
            any_views = True
        if cc.engagement is not None:
            total_engagement += cc.engagement
        if cc.clicks is not None:
            total_clicks += cc.clicks
            any_clicks = True
        if cc.conversions is not None:
            total_conversions += cc.conversions
            any_conversions = True
        if cc.revenue is not None:
            total_revenue += cc.revenue
            any_revenue = True
        if cc.spend is not None:
            total_spend += cc.spend
            any_spend = True

    ctr = round((total_clicks / total_views) * 100, 2) if any_views and any_clicks and total_views > 0 else None
    cvr = round((total_conversions / total_clicks) * 100, 2) if any_clicks and any_conversions and total_clicks > 0 else None
    roi_percentage = _roi_percentage(total_revenue if any_revenue else None, total_spend if any_spend else None)
    cpm = round((total_spend / total_views) * 1000, 2) if any_spend and any_views and total_views > 0 else None
    cpc = round(total_spend / total_clicks, 2) if any_spend and any_clicks and total_clicks > 0 else None
    cpa = round(total_spend / total_conversions, 2) if any_spend and any_conversions and total_conversions > 0 else None

    if not creators:
        completeness = "none"
    elif has_full:
        completeness = "full"
    elif has_any:
        completeness = "partial"
    else:
        completeness = "none"

    return {
        "campaign_id": campaign.id,
        "reach": total_views if any_views else None,
        "views": total_views if any_views else None,
        "engagement": total_engagement if any_views else None,
        "clicks": total_clicks if any_clicks else None,
        "ctr": ctr,
        "conversions": total_conversions if any_conversions else None,
        "cvr": cvr,
        "revenue": total_revenue if any_revenue else None,
        "spend": total_spend if any_spend else None,
        "roi_percentage": roi_percentage,
        "cpm": cpm,
        "cpc": cpc,
        "cpa": cpa,
        "per_creator": per_creator,
        "data_completeness": completeness,
        "note": None if creators else "No creators attached to this campaign yet.",
    }


@router.get("/{campaign_id}/performance", response_model=CampaignPerformanceResponse)
async def get_performance(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    campaign = _get_owned_campaign(db, campaign_id, current_user)
    return _compute_performance(db, campaign)


@router.post("/{campaign_id}/ai/analyze-performance", response_model=PerformanceAnalysisResponse)
async def analyze_performance(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    campaign = _get_owned_campaign(db, campaign_id, current_user)
    performance = _compute_performance(db, campaign)
    creators_with_actuals = [c for c in performance["per_creator"] if c["has_actuals"]]

    result = await analyze_campaign_performance(
        campaign_name=campaign.name,
        creators_with_actuals=creators_with_actuals,
        performance=performance,
    )

    insights: List[AIInsight] = []
    for insight_type in ("what_happened", "why", "what_next"):
        row = AIInsight(
            campaign_id=campaign_id,
            insight_type=insight_type,
            content=result[insight_type],
            data_snapshot=performance,
        )
        db.add(row)
        insights.append(row)
    db.commit()
    for row in insights:
        db.refresh(row)

    return {
        "campaign_id": campaign_id,
        "what_happened": result["what_happened"],
        "why": result["why"],
        "what_next": result["what_next"],
        "insights": insights,
        "source": result["source"],
    }


@router.get("/{campaign_id}/report", response_model=CampaignReportResponse)
async def get_report(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    campaign = _get_owned_campaign(db, campaign_id, current_user)

    creators = db.query(CampaignCreator).filter(CampaignCreator.campaign_id == campaign_id).all()
    shortlisted = []
    creator_intelligence = []
    for cc in creators:
        inf = db.query(Influencer).filter(Influencer.id == cc.influencer_id).first()
        if not inf:
            continue
        shortlisted.append({"influencer_id": inf.id, "display_name": inf.display_name, "status": cc.status})
        creator_intelligence.append({
            "influencer_id": inf.id,
            "display_name": inf.display_name,
            "intelligence": _compose_intelligence(db, inf),
        })

    performance = _compute_performance(db, campaign)

    insights = (
        db.query(AIInsight)
        .filter(AIInsight.campaign_id == campaign_id)
        .order_by(AIInsight.generated_at.desc())
        .limit(9)
        .all()
    )
    insight_dicts = [{"insight_type": i.insight_type, "content": i.content} for i in insights]

    report = build_report(
        campaign_name=campaign.name,
        campaign_status=campaign.status,
        ai_campaign_brief=campaign.ai_campaign_brief,
        shortlisted_creators=shortlisted,
        creator_intelligence=creator_intelligence,
        performance=performance,
        creator_performance=performance["per_creator"],
        insights=insight_dicts,
    )

    return {
        "campaign_id": campaign_id,
        "generated_at": datetime.now(timezone.utc),
        **report,
    }


# ---------------------------------------------------------------------------
# AI Partnership Assistant (single-turn, grounded)
# ---------------------------------------------------------------------------

assistant_router = APIRouter()


@assistant_router.post("/query", response_model=AssistantQueryResponse)
async def assistant_query(
    request: AssistantQueryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from utils.ai.assistant import answer_query

    context: Dict[str, Any] = {"campaigns": [], "creators": []}

    if request.campaign_id is not None:
        campaign = _get_owned_campaign(db, request.campaign_id, current_user)
        performance = _compute_performance(db, campaign)
        context["campaigns"].append({
            "id": campaign.id,
            "name": campaign.name,
            "status": campaign.status,
            "budget": campaign.budget,
            "ai_campaign_brief": campaign.ai_campaign_brief,
            "performance": performance,
        })
        matches = (
            db.query(CampaignMatch)
            .filter(CampaignMatch.campaign_id == campaign.id)
            .order_by(CampaignMatch.match_score.desc().nullslast())
            .limit(15)
            .all()
        )
        for m in matches:
            inf = db.query(Influencer).filter(Influencer.id == m.influencer_id).first()
            if inf:
                context["creators"].append({
                    "influencer_id": inf.id,
                    "display_name": inf.display_name,
                    "match_score": m.match_score,
                    "trust_score": m.trust_component,
                    "risk_level": m.risk_level,
                    "reasons": m.reasons,
                })
    else:
        campaigns = (
            db.query(Campaign)
            .filter(Campaign.owner_id == current_user.id)
            .order_by(Campaign.created_at.desc())
            .limit(10)
            .all()
        )
        for c in campaigns:
            context["campaigns"].append({"id": c.id, "name": c.name, "status": c.status, "roi_percentage": c.roi_percentage})

        top_influencers = db.query(Influencer).limit(30).all()
        for inf in top_influencers:
            intelligence = _compose_intelligence(db, inf)
            if intelligence.get("tier"):
                context["creators"].append({
                    "influencer_id": inf.id,
                    "display_name": inf.display_name,
                    "tier": intelligence.get("tier"),
                    "trust_score": intelligence.get("trust_score"),
                })

    result = await answer_query(query=request.query, context=context)
    return {"answer": result["answer"], "grounded_on": context, "source": result["source"]}
