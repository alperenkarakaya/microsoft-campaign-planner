from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, JSON, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    campaigns = relationship("Campaign", back_populates="owner")

class Influencer(Base):
    __tablename__ = "influencers"

    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String, index=True)  # youtube, instagram, tiktok
    platform_id = Column(String, unique=True, index=True)
    username = Column(String, index=True)
    display_name = Column(String)
    followers_count = Column(Integer)
    engagement_rate = Column(Float)
    category = Column(String)
    country = Column(String)
    avatar_url = Column(String, nullable=True)
    bio = Column(String, nullable=True)
    verified = Column(Boolean, default=False)
    fake_follower_percentage = Column(Float, default=0.0)
    last_updated = Column(DateTime, default=datetime.utcnow)
    platform_metadata = Column(JSON, nullable=True)

    # Roster fields (Phase 0): populated by roster_importer from the curated
    # spreadsheet. source_handle is the @handle as it appears in the roster.
    source_handle = Column(String, nullable=True, index=True)
    business_email = Column(String, nullable=True)
    talent_agency = Column(Boolean, nullable=True)

    # Enrichment signals (Phase 1): deterministic signals computed by
    # utils/signals.py, stored as a JSON blob (mirrors InfluencerAnalysis.
    # predicted_outcome pattern). Schema documented in signals.py.
    enrichment_signals = Column(JSON, nullable=True)

    # Phase 6 — enrichment orchestration run-state tracking.
    # last_enriched_at: timestamp of last successful full-pipeline enrichment.
    # enrichment_status: "pending" | "running" | "completed" | "partial" | "failed"
    # enrichment_error: error message on last failure (None on success).
    last_enriched_at = Column(DateTime, nullable=True)
    enrichment_status = Column(String, nullable=True)
    enrichment_error = Column(Text, nullable=True)

    campaigns = relationship("Campaign", back_populates="influencer")

class Campaign(Base):
    __tablename__ = "campaigns"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(String, nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"))
    influencer_id = Column(Integer, ForeignKey("influencers.id"))
    
    budget = Column(Float)
    start_date = Column(DateTime)
    end_date = Column(DateTime, nullable=True)
    status = Column(String, default="planning")  # planning, active, completed, cancelled
    
    # Metrikler
    views = Column(Integer, default=0)
    likes = Column(Integer, default=0)
    comments = Column(Integer, default=0)
    shares = Column(Integer, default=0)
    clicks = Column(Integer, default=0)
    conversions = Column(Integer, default=0)
    revenue = Column(Float, default=0.0)
    
    # ROI Hesaplamaları
    roi_percentage = Column(Float, default=0.0)
    cpm = Column(Float, default=0.0)  # Cost Per Mille
    cpc = Column(Float, default=0.0)  # Cost Per Click
    cpa = Column(Float, default=0.0)  # Cost Per Acquisition
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # AI Campaign Intelligence layer (additive). AI-parsed understanding of the
    # campaign (objective, audience, geography, category, budget, trust/sponsorship
    # preference, KPIs). Populated by POST /campaigns/{id}/ai/analyze. Follows the
    # existing "TEXT/JSON blob, no schema churn" convention used elsewhere.
    ai_campaign_brief = Column(JSON, nullable=True)

    owner = relationship("User", back_populates="campaigns")
    influencer = relationship("Influencer", back_populates="campaigns")

# Mevcut models. py'e EKLE: 

class BrandProfile(Base):
    __tablename__ = "brand_profiles"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String, index=True)  # Marka adı
    
    # Marka Kimliği Özellikleri (0-10 skala)
    aggressive_score = Column(Float, default=5.0)  # Agresiflik
    creative_score = Column(Float, default=5.0)    # Yaratıcılık
    humorous_score = Column(Float, default=5.0)    # Mizah
    professional_score = Column(Float, default=5.0) # Profesyonellik
    edgy_score = Column(Float, default=5.0)        # Keskinlik
    
    # Hedef kitle
    target_age_min = Column(Integer, default=18)
    target_age_max = Column(Integer, default=45)
    target_gender = Column(String, default="all")  # male, female, all
    target_countries = Column(JSON)  # ["US", "UK", "TR"]
    
    # Kampanya tercihleri
    min_followers = Column(Integer, default=10000)
    max_followers = Column(Integer, default=10000000)
    preferred_categories = Column(JSON)  # ["Gaming", "Tech", "Comedy"]
    budget_range_min = Column(Float)
    budget_range_max = Column(Float)

    # Average order value (USD). Required for grounded revenue prediction.
    target_aov = Column(Float, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", backref="brand_profiles")


class InfluencerAnalysis(Base):
    __tablename__ = "influencer_analysis"
    
    id = Column(Integer, primary_key=True, index=True)
    influencer_id = Column(Integer, ForeignKey("influencers.id"))
    brand_profile_id = Column(Integer, ForeignKey("brand_profiles.id"))
    
    # AI fit scores (0-100). overall_match_score may be capped by backend rules;
    # original_match_score retains the raw Gemini value for audit.
    content_style_match_score = Column(Float)
    audience_match_score = Column(Float)
    engagement_quality_score = Column(Float)
    brand_safety_score = Column(Float)
    overall_match_score = Column(Float)
    original_match_score = Column(Float, nullable=True)
    override_reason = Column(Text, nullable=True)

    # AI commentary
    ai_analysis_summary = Column(Text)
    top_video_themes = Column(JSON)
    audience_demographics = Column(JSON)
    content_tone = Column(String)
    quality_flags = Column(JSON, nullable=True)

    # Grounded prediction (real signals × cited benchmarks). Stored as the dict
    # produced by utils.benchmarks.predict_campaign_outcome().
    predicted_outcome = Column(JSON, nullable=True)
    cpm_benchmark_low = Column(Float, nullable=True)
    cpm_benchmark_high = Column(Float, nullable=True)

    # Phase 2 — Community Trust Depth + Authority breakdown. JSON blob
    # produced by utils.trust_scorer.compute_trust_score().
    trust_breakdown = Column(JSON, nullable=True)

    # Phase 3 — Sponsorship Authenticity profile. JSON blob produced by
    # utils.sponsorship_analyzer.compute_sponsorship_profile().
    sponsorship_profile = Column(JSON, nullable=True)

    analyzed_at = Column(DateTime, default=datetime.utcnow)
    
    influencer = relationship("Influencer")
    brand_profile = relationship("BrandProfile")


class InfluencerRecommendation(Base):
    __tablename__ = "influencer_recommendations"
    
    id = Column(Integer, primary_key=True, index=True)
    brand_profile_id = Column(Integer, ForeignKey("brand_profiles.id"))
    
    # Önerilen influencer grubu
    micro_influencers = Column(JSON)   # [{"id": 1, "score": 85, "estimated_cost": 5000}, ...]
    macro_influencers = Column(JSON)
    mega_influencers = Column(JSON)
    
    # Recommended campaign envelope. Reach is the projected sum of per-post
    # median recent views; budget is the sum of per-influencer cost ranges.
    recommended_budget_low = Column(Float)
    recommended_budget_high = Column(Float)
    projected_total_reach_low = Column(Integer)
    projected_total_reach_high = Column(Integer)
    predicted_total_revenue_low = Column(Float, nullable=True)
    predicted_total_revenue_high = Column(Float, nullable=True)
    predicted_total_roi_low = Column(Float, nullable=True)
    predicted_total_roi_high = Column(Float, nullable=True)
    campaign_strategy = Column(Text)
    
    created_at = Column(DateTime, default=datetime.utcnow)

    brand_profile = relationship("BrandProfile")


# ---------------------------------------------------------------------------
# AI Campaign Intelligence layer (additive). These models sit ON TOP of the
# existing single-influencer Campaign — they never replace it. They power the
# multi-creator matching / shortlist / brief / content / execution / reporting
# workflow. See CLAUDE.md "Intelligence Pipeline" section for the layering
# philosophy this mirrors (deterministic backbone + optional LLM augmentation,
# missing data never fabricated).
# ---------------------------------------------------------------------------

class CampaignCreator(Base):
    """Join entity: a creator attached to a campaign for the AI-matching /
    shortlist / execution workflow. Independent of Campaign.influencer_id
    (the legacy single-creator field) so existing campaigns are untouched."""
    __tablename__ = "campaign_creators"
    __table_args__ = (UniqueConstraint("campaign_id", "influencer_id", name="uq_campaign_creator"),)

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False, index=True)
    influencer_id = Column(Integer, ForeignKey("influencers.id"), nullable=False, index=True)

    # matched -> shortlisted -> contracted -> briefed -> content_creation ->
    # review -> live -> completed (or removed at any point)
    status = Column(String, default="matched", nullable=False)
    recommended_role = Column(String, nullable=True)
    notes = Column(Text, nullable=True)

    # Per-creator ACTUALS within a multi-creator campaign. Distinct from the
    # legacy Campaign-level metrics (which remain the single-creator source of
    # truth for old campaigns). None until real data is entered — never fabricated.
    views = Column(Integer, nullable=True)
    engagement = Column(Integer, nullable=True)
    clicks = Column(Integer, nullable=True)
    conversions = Column(Integer, nullable=True)
    revenue = Column(Float, nullable=True)
    spend = Column(Float, nullable=True)

    added_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    campaign = relationship("Campaign", backref="campaign_creators")
    influencer = relationship("Influencer")


class CampaignMatch(Base):
    """AI Campaign Match Score for one (campaign, influencer) pair. SEPARATE
    from the creator's intrinsic Trust Score (InfluencerAnalysis.trust_breakdown)
    — this table never recomputes trust, it consumes it as an input."""
    __tablename__ = "campaign_matches"
    __table_args__ = (UniqueConstraint("campaign_id", "influencer_id", name="uq_campaign_match"),)

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False, index=True)
    influencer_id = Column(Integer, ForeignKey("influencers.id"), nullable=False, index=True)

    match_score = Column(Float, nullable=True)
    audience_fit = Column(Float, nullable=True)
    brand_fit = Column(Float, nullable=True)
    category_fit = Column(Float, nullable=True)
    geographic_fit = Column(Float, nullable=True)
    budget_fit = Column(Float, nullable=True)
    trust_component = Column(Float, nullable=True)
    sponsorship_component = Column(Float, nullable=True)
    risk_level = Column(String, nullable=True)  # "low" | "medium" | "high" | "unknown"
    reasons = Column(JSON, nullable=True)  # list[str] — the "Why this creator?" bullets
    recommended_role = Column(String, nullable=True)
    confidence = Column(String, nullable=True)  # "high" | "medium" | "low"
    estimated_reach = Column(Integer, nullable=True)
    estimated_cost_low = Column(Float, nullable=True)
    estimated_cost_high = Column(Float, nullable=True)
    source = Column(String, nullable=True)

    computed_at = Column(DateTime, default=datetime.utcnow)

    campaign = relationship("Campaign")
    influencer = relationship("Influencer")


class CampaignBrief(Base):
    """Personalized AI campaign brief for one (campaign, influencer) pair.
    Not a shared template — content_format/creative_direction are meant to
    differ per creator based on their existing content style."""
    __tablename__ = "campaign_briefs"
    __table_args__ = (UniqueConstraint("campaign_id", "influencer_id", name="uq_campaign_brief"),)

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False, index=True)
    influencer_id = Column(Integer, ForeignKey("influencers.id"), nullable=False, index=True)

    objective = Column(Text, nullable=True)
    key_message = Column(Text, nullable=True)
    content_format = Column(String, nullable=True)
    creative_direction = Column(Text, nullable=True)
    hook = Column(Text, nullable=True)
    talking_points = Column(JSON, nullable=True)  # list[str]
    cta = Column(Text, nullable=True)
    dos = Column(JSON, nullable=True)  # list[str]
    donts = Column(JSON, nullable=True)  # list[str]
    required_disclosures = Column(Text, nullable=True)
    deadline = Column(DateTime, nullable=True)
    deliverables = Column(JSON, nullable=True)  # list[str]
    source = Column(String, nullable=True)  # "gemini" | "deterministic_template"

    generated_at = Column(DateTime, default=datetime.utcnow)

    campaign = relationship("Campaign")
    influencer = relationship("Influencer")


class CreatorContent(Base):
    """Content Studio output. Optionally tied to a campaign; always tied to
    the creator whose existing content style informed generation."""
    __tablename__ = "creator_content"

    id = Column(Integer, primary_key=True, index=True)
    influencer_id = Column(Integer, ForeignKey("influencers.id"), nullable=False, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=True, index=True)

    content_type = Column(String, nullable=False)  # "caption" | "youtube_title" | ...
    caption = Column(Text, nullable=True)
    title = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    hook = Column(Text, nullable=True)
    video_concept = Column(Text, nullable=True)
    script_outline = Column(Text, nullable=True)
    cta = Column(Text, nullable=True)
    hashtags = Column(JSON, nullable=True)  # list[str]
    talking_points = Column(JSON, nullable=True)  # list[str]
    source = Column(String, nullable=True)

    generated_at = Column(DateTime, default=datetime.utcnow)

    influencer = relationship("Influencer")
    campaign = relationship("Campaign")


class CampaignTask(Base):
    """Per-creator execution task (brief_sent, content_submitted, ...)."""
    __tablename__ = "campaign_tasks"

    id = Column(Integer, primary_key=True, index=True)
    campaign_creator_id = Column(Integer, ForeignKey("campaign_creators.id"), nullable=False, index=True)

    task_type = Column(String, nullable=False)
    status = Column(String, default="pending", nullable=False)  # pending | done
    deadline = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    campaign_creator = relationship("CampaignCreator", backref="tasks")


class AIInsight(Base):
    """AI Performance Analyst output. Grounded in real Campaign/CampaignCreator
    actuals only — data_snapshot records exactly what numbers backed the text
    so 'insufficient data' claims are auditable, never silently fabricated."""
    __tablename__ = "ai_insights"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False, index=True)

    insight_type = Column(String, nullable=False)  # what_happened | why | what_next | optimization
    content = Column(Text, nullable=False)
    data_snapshot = Column(JSON, nullable=True)

    generated_at = Column(DateTime, default=datetime.utcnow)

    campaign = relationship("Campaign")