from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from database import get_db
from schemas import InfluencerCreate, InfluencerResponse
from models import Influencer, User
from utils.security import get_current_user
from utils.youtube_api import get_youtube_channel_data, YouTubeAPIError
from utils.ai_detector import detect_fake_followers

router = APIRouter()

@router.post("", response_model=InfluencerResponse, status_code=status.HTTP_201_CREATED)
async def create_influencer(
    influencer: InfluencerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Platform ID kontrolü
    existing = db.query(Influencer).filter(
        Influencer. platform_id == influencer.platform_id,
        Influencer.platform == influencer.platform
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Influencer already exists")
    
    # Yeni influencer oluştur
    db_influencer = Influencer(**influencer.model_dump())
    db.add(db_influencer)
    db.commit()
    db.refresh(db_influencer)
    
    return db_influencer

@router.get("", response_model=List[InfluencerResponse])
async def list_influencers(
    skip: int = 0,
    limit: int = 20,
    platform: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Influencer)
    
    if platform: 
        query = query.filter(Influencer.platform == platform)
    
    influencers = query.offset(skip).limit(limit).all()
    return influencers

@router.get("/{influencer_id}", response_model=InfluencerResponse)
async def get_influencer(
    influencer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    influencer = db.query(Influencer).filter(Influencer.id == influencer_id).first()
    
    if not influencer:
        raise HTTPException(status_code=404, detail="Influencer not found")
    
    return influencer

@router.post("/youtube/fetch")
async def fetch_youtube_channel(
    channel_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """YouTube API'den kanal bilgilerini çek ve influencer olarak kaydet"""
    
    try:
        # YouTube API'den veri çek
        channel_data = await get_youtube_channel_data(channel_id)
        
        # AI ile sahte takipçi analizi
        fake_percentage = await detect_fake_followers(channel_data)
        
        influencer = Influencer(
            platform="youtube",
            platform_id=channel_id,
            username=channel_data["username"],
            display_name=channel_data["title"],
            followers_count=channel_data["subscriber_count"],
            engagement_rate=channel_data["engagement_rate"],
            category=channel_data.get("category"),
            country=channel_data.get("country"),
            avatar_url=channel_data.get("thumbnail"),
            verified=channel_data.get("verified", False),
            fake_follower_percentage=fake_percentage if fake_percentage is not None else 0.0,
            platform_metadata=channel_data,
        )
        
        db.add(influencer)
        db.commit()
        db.refresh(influencer)
        
        return {
            "message": "YouTube channel fetched successfully",
            "influencer": InfluencerResponse.model_validate(influencer)
        }
        
    except YouTubeAPIError as e:
        raise HTTPException(status_code=503, detail=f"YouTube data unavailable: {str(e)[:200]}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))