from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from database import get_db
from models import Campaign, User, Influencer
from utils.security import get_current_user

router = APIRouter()


# Statuses whose ROI is meaningful. "planning" rows have revenue=0 by default
# and would otherwise drag the dashboard average down to -100%.
_MEASURABLE_STATUSES = ("active", "completed")


@router.get("/dashboard")
async def get_dashboard_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Aggregate dashboard for the current user."""
    campaigns = db.query(Campaign).filter(Campaign.owner_id == current_user.id).all()

    total_campaigns = len(campaigns)
    total_budget = sum(c.budget for c in campaigns)
    total_revenue = sum(c.revenue for c in campaigns)

    measurable = [c for c in campaigns if c.status in _MEASURABLE_STATUSES and c.budget > 0]
    avg_roi = (
        sum(c.roi_percentage for c in measurable) / len(measurable)
        if measurable else 0.0
    )

    active_campaigns = sum(1 for c in campaigns if c.status == "active")
    completed_campaigns = sum(1 for c in campaigns if c.status == "completed")

    return {
        "total_campaigns": total_campaigns,
        "active_campaigns": active_campaigns,
        "completed_campaigns": completed_campaigns,
        "measurable_campaigns": len(measurable),
        "total_budget": total_budget,
        "total_revenue": total_revenue,
        "net_profit": total_revenue - total_budget,
        "avg_roi_percentage": round(avg_roi, 2),
        "total_views": sum(c.views for c in campaigns),
        "total_clicks": sum(c.clicks for c in campaigns),
        "total_conversions": sum(c.conversions for c in campaigns),
    }


@router.get("/campaigns/performance")
async def get_campaign_performance(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Top and worst performers — measured campaigns only.

    A campaign with default zero metrics isn't "worst performing", it just hasn't
    been measured. Filter to campaigns where revenue or views have been recorded.
    """
    measured = db.query(Campaign).filter(
        Campaign.owner_id == current_user.id,
        Campaign.status.in_(_MEASURABLE_STATUSES),
        (Campaign.revenue > 0) | (Campaign.views > 0),
    ).order_by(Campaign.roi_percentage.desc()).all()

    top_campaigns = measured[:5]
    # Worst performers are drawn only from campaigns NOT already shown as top, so
    # the same campaign never appears in both lists (overlap when 5 < n <= 10).
    remaining = measured[5:]
    worst_campaigns = list(reversed(remaining[-5:])) if remaining else []

    def _serialize(c):
        return {
            "id": c.id,
            "name": c.name,
            "roi": c.roi_percentage,
            "revenue": c.revenue,
            "budget": c.budget,
        }

    return {
        "top_performers": [_serialize(c) for c in top_campaigns],
        "worst_performers": [_serialize(c) for c in worst_campaigns],
    }


@router.get("/influencers/ranking")
async def get_influencer_ranking(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Influencers ranked by avg ROI across the user's measured campaigns."""
    results = db.query(
        Influencer,
        func.avg(Campaign.roi_percentage).label("avg_roi"),
        func.count(Campaign.id).label("campaign_count"),
    ).join(Campaign).filter(
        Campaign.owner_id == current_user.id,
        Campaign.status.in_(_MEASURABLE_STATUSES),
        Campaign.budget > 0,
    ).group_by(Influencer.id).order_by(func.avg(Campaign.roi_percentage).desc()).all()

    return [
        {
            "influencer_id": inf.id,
            "username": inf.username,
            "display_name": inf.display_name,
            "platform": inf.platform,
            "avg_roi": round(float(avg_roi), 2),
            "campaign_count": campaign_count,
            "followers": inf.followers_count,
            "engagement_rate": inf.engagement_rate,
        }
        for inf, avg_roi, campaign_count in results
    ]
