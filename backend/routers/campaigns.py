from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query
from sqlalchemy.orm import Session
from typing import List

from database import get_db
from schemas import CampaignCreate, CampaignUpdate, CampaignResponse
from models import Campaign, User, Influencer
from utils.security import get_current_user
from utils.csv_importers import (
    parse_youtube_studio_csv,
    parse_shopify_orders_csv,
    parse_stripe_payouts_csv,
)
from utils.ai_detector import analyze_campaign_performance

router = APIRouter()

def calculate_roi(campaign: Campaign) -> Campaign:
    """Recompute ROI / CPM / CPC / CPA from the current actuals.

    Reset all four to 0 first, then conditionally compute. Otherwise stale values
    from a previous update persist when an actual gets cleared back to 0.
    """
    campaign.roi_percentage = 0.0
    campaign.cpm = 0.0
    campaign.cpc = 0.0
    campaign.cpa = 0.0

    if campaign.budget and campaign.budget > 0:
        campaign.roi_percentage = ((campaign.revenue - campaign.budget) / campaign.budget) * 100
        if campaign.views and campaign.views > 0:
            campaign.cpm = (campaign.budget / campaign.views) * 1000
        if campaign.clicks and campaign.clicks > 0:
            campaign.cpc = campaign.budget / campaign.clicks
        if campaign.conversions and campaign.conversions > 0:
            campaign.cpa = campaign.budget / campaign.conversions

    return campaign

@router.post("/", response_model=CampaignResponse, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    campaign:  CampaignCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Influencer kontrolü
    influencer = db.query(Influencer).filter(Influencer.id == campaign.influencer_id).first()
    if not influencer:
        raise HTTPException(status_code=404, detail="Influencer not found")
    
    # Yeni kampanya oluştur
    db_campaign = Campaign(
        **campaign.model_dump(),
        owner_id=current_user.id
    )
    
    db.add(db_campaign)
    db.commit()
    db.refresh(db_campaign)
    
    return db_campaign

@router.get("/", response_model=List[CampaignResponse])
async def list_campaigns(
    skip: int = 0,
    limit: int = 20,
    status: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Campaign).filter(Campaign.owner_id == current_user.id)
    
    if status:
        query = query.filter(Campaign.status == status)
    
    campaigns = query.offset(skip).limit(limit).all()
    return campaigns

@router.get("/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    campaign = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.owner_id == current_user.id
    ).first()
    
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    return campaign

@router.patch("/{campaign_id}", response_model=CampaignResponse)
async def update_campaign(
    campaign_id: int,
    campaign_update: CampaignUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    campaign = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.owner_id == current_user.id
    ).first()
    
    if not campaign: 
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    # Update fields
    update_data = campaign_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(campaign, field, value)
    
    # ROI hesapla
    campaign = calculate_roi(campaign)
    
    db.commit()
    db.refresh(campaign)
    
    return campaign

@router.post("/{campaign_id}/import-csv", response_model=CampaignResponse)
async def import_campaign_csv(
    campaign_id: int,
    file: UploadFile = File(...),
    format: str = Query(..., pattern="^(youtube_studio|shopify_orders|stripe_payouts)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Import measured actuals from a CSV export.

    Supported formats:
      - youtube_studio: video performance export (Views, Likes, Comments).
      - shopify_orders: orders export (one row per order, line totals → revenue).
      - stripe_payouts: payouts export (gross → revenue).

    Updates the campaign in place and recomputes ROI/CPM/CPC/CPA.
    """
    campaign = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.owner_id == current_user.id,
    ).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    raw = await file.read()
    try:
        if format == "youtube_studio":
            metrics = parse_youtube_studio_csv(raw)
        elif format == "shopify_orders":
            metrics = parse_shopify_orders_csv(raw)
        else:
            metrics = parse_stripe_payouts_csv(raw)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"CSV parse error: {e}")

    for field, value in metrics.items():
        if value is not None and hasattr(campaign, field):
            setattr(campaign, field, value)

    calculate_roi(campaign)
    db.commit()
    db.refresh(campaign)
    return campaign


@router.get("/{campaign_id}/ai-analysis")
async def get_campaign_ai_analysis(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """AI commentary (score, insights, recommendations) on a measured campaign.

    Requires recorded actuals — analysing a campaign with default-zero metrics
    produces no useful signal, so we ask the user to enter actuals first.
    """
    campaign = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.owner_id == current_user.id,
    ).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if not (campaign.revenue or campaign.views):
        raise HTTPException(
            status_code=400,
            detail="No measured metrics yet. Enter actuals or import a CSV first.",
        )

    return await analyze_campaign_performance({
        "budget": campaign.budget or 0.0,
        "revenue": campaign.revenue or 0.0,
        "roi_percentage": campaign.roi_percentage or 0.0,
        "views": campaign.views or 0,
        "clicks": campaign.clicks or 0,
        "conversions": campaign.conversions or 0,
        "cpm": campaign.cpm or 0.0,
        "cpc": campaign.cpc or 0.0,
    })


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    campaign = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.owner_id == current_user.id
    ).first()
    
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    db.delete(campaign)
    db.commit()
    
    return None