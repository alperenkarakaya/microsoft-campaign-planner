from pydantic import BaseModel, EmailStr, Field, ConfigDict
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple, Literal

CampaignStatus = Literal["planning", "active", "completed", "cancelled"]


# User
class UserBase(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=50)

class UserCreate(UserBase):
    # bcrypt only hashes the first 72 bytes, so cap length to avoid silent truncation surprises.
    password: str = Field(min_length=8, max_length=72)

class UserResponse(UserBase):
    id: int
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Influencer
class InfluencerBase(BaseModel):
    platform: str
    platform_id: str
    username: str
    display_name: str

class InfluencerCreate(InfluencerBase):
    followers_count: int
    engagement_rate: float
    category: Optional[str] = None
    country: Optional[str] = None

class InfluencerResponse(InfluencerBase):
    id: int
    followers_count: int
    engagement_rate: float
    fake_follower_percentage: float
    verified: bool
    last_updated: datetime

    model_config = ConfigDict(from_attributes=True)


# Campaign
class CampaignBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    budget: float = Field(gt=0)
    start_date: datetime

class CampaignCreate(CampaignBase):
    influencer_id: int

class CampaignUpdate(BaseModel):
    views: Optional[int] = Field(default=None, ge=0)
    likes: Optional[int] = Field(default=None, ge=0)
    comments: Optional[int] = Field(default=None, ge=0)
    shares: Optional[int] = Field(default=None, ge=0)
    clicks: Optional[int] = Field(default=None, ge=0)
    conversions: Optional[int] = Field(default=None, ge=0)
    revenue: Optional[float] = Field(default=None, ge=0)
    status: Optional[CampaignStatus] = None

class CampaignResponse(CampaignBase):
    id: int
    owner_id: int
    influencer_id: int
    end_date: Optional[datetime] = None
    status: str
    views: int
    likes: int
    comments: int
    shares: int
    clicks: int
    conversions: int
    revenue: float
    roi_percentage: float
    cpm: float
    cpc: float
    cpa: float
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Auth
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None


# Brand profile
class BrandProfileCreate(BaseModel):
    name: str
    aggressive_score: float = 5.0
    creative_score: float = 5.0
    humorous_score: float = 5.0
    professional_score: float = 5.0
    edgy_score: float = 5.0
    target_age_min: int = 18
    target_age_max: int = 45
    target_gender: str = "all"
    target_countries: List[str] = ["US"]
    min_followers: int = 10000
    max_followers: int = 10000000
    preferred_categories: List[str] = []
    budget_range_min: Optional[float] = None
    budget_range_max: Optional[float] = None
    target_aov: Optional[float] = None  # average order value (USD), powers revenue prediction


class BrandProfileResponse(BaseModel):
    id: int
    name: str
    aggressive_score: float
    creative_score: float
    humorous_score: float
    professional_score: float
    edgy_score: float
    target_age_min: int
    target_age_max: int
    target_gender: str
    target_countries: List[str]
    min_followers: int
    max_followers: int
    preferred_categories: List[str]
    budget_range_min: Optional[float] = None
    budget_range_max: Optional[float] = None
    target_aov: Optional[float] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Discovery / prediction
class InfluencerDiscoveryRequest(BaseModel):
    brand_profile_id: int
    search_query: Optional[str] = Field(default=None, max_length=200)
    # YouTube search caps at 50 results per page; bound fan-out to protect quota.
    max_results: int = Field(default=20, ge=1, le=50)

    # Optional manual overrides; default to brand profile values if absent.
    min_subscribers: Optional[int] = Field(default=None, ge=0)
    max_subscribers: Optional[int] = Field(default=None, ge=0)
    min_engagement_rate: Optional[float] = Field(default=None, ge=0)
    min_view_ratio: Optional[float] = Field(default=3.0, ge=0)
    num_posts: int = Field(default=1, ge=1, le=10)


class CampaignPredictionPayload(BaseModel):
    """Grounded prediction range. Mirrors utils.benchmarks.CampaignPrediction.to_dict()."""
    predicted_reach: Tuple[int, int]
    predicted_clicks: Tuple[int, int]
    predicted_conversions: Tuple[float, float]
    predicted_revenue: Tuple[float, float]
    predicted_cost: Tuple[float, float]
    predicted_roi_percentage: Tuple[float, float]
    confidence: str
    inputs: Dict[str, Any]
    source: str
    disclaimer: str


class InfluencerMatchResult(BaseModel):
    influencer_id: int
    username: str
    display_name: str
    followers_count: int
    overall_match_score: float
    content_style_match: float
    audience_match: float
    engagement_quality: float
    brand_safety: float
    ai_summary: str
    category: str  # display label only: "micro" | "macro" | "mega"
    engagement_rate: float
    content_tone: str

    cpm_benchmark: Tuple[float, float]
    median_recent_views: Optional[int] = None
    fake_follower_percentage: Optional[float] = None
    quality_flags: List[str] = []
    predicted_outcome: Optional[CampaignPredictionPayload] = None


# Trust breakdown (Phase 2)
class TrustSubScore(BaseModel):
    """Sub-score within the trust breakdown (community or authority)."""
    score: Optional[float] = None
    deterministic_baseline: Optional[float] = None
    floor: Optional[float] = None
    cap: Optional[float] = None
    components: Optional[Dict[str, Any]] = None
    # LLM fields (None when LLM unavailable)
    llm_comment_authenticity: Optional[float] = None
    llm_spam_ratio: Optional[float] = None
    llm_substantive_ratio: Optional[float] = None
    llm_parasocial_bond: Optional[float] = None
    llm_past_video_references: Optional[float] = None
    llm_loyalty_markers: Optional[float] = None


class TrustBreakdown(BaseModel):
    """Trust score breakdown stored as InfluencerAnalysis.trust_breakdown JSON."""
    status: str  # "analyzed" | "deterministic_only" | "unanalyzed"
    community_trust_depth: Optional[TrustSubScore] = None
    authority: Optional[TrustSubScore] = None
    composite_trust_score: Optional[float] = None
    confidence: str  # "high" | "medium" | "low"
    source: str
    override_reason: Optional[str] = None
    computed_at: Optional[str] = None


# Sponsorship profile (Phase 3)
class SponsorshipMaturity(BaseModel):
    label: Optional[str] = None  # "unproven" | "emerging" | "mature" | "saturated" | "unknown"
    score: Optional[float] = None
    sponsored_ratio: Optional[float] = None
    sponsored_count: int = 0
    total_checked: int = 0
    reason: Optional[str] = None


class SponsorshipQuality(BaseModel):
    score: Optional[float] = None
    repeat_sponsors: List[str] = []
    unique_sponsors: int = 0
    sponsor_diversity: Optional[float] = None


class SponsorshipIntegrationStyle(BaseModel):
    style: Optional[str] = None  # "native" | "read_out" | "mixed" | "unknown"
    score: Optional[float] = None
    floor: Optional[float] = None
    cap: Optional[float] = None
    notes: str = ""


class SponsorshipAuthenticity(BaseModel):
    score: Optional[float] = None
    floor: Optional[float] = None
    cap: Optional[float] = None
    sentiment_sponsored: Optional[float] = None
    sentiment_organic: Optional[float] = None
    sentiment_gap: Optional[float] = None
    audience_welcomes_sponsors: Optional[bool] = None
    notes: str = ""


class SponsorshipProfile(BaseModel):
    """Sponsorship profile stored as InfluencerAnalysis.sponsorship_profile JSON."""
    status: str  # "analyzed" | "deterministic_only" | "unanalyzed"
    maturity: Optional[SponsorshipMaturity] = None
    quality: Optional[SponsorshipQuality] = None
    integration_style: Optional[SponsorshipIntegrationStyle] = None
    authenticity: Optional[SponsorshipAuthenticity] = None
    composite_sponsorship_score: Optional[float] = None
    confidence: str  # "high" | "medium" | "low"
    source: str
    override_reason: Optional[str] = None
    computed_at: Optional[str] = None


class CampaignRecommendation(BaseModel):
    brand_profile_name: str
    recommended_influencers: List[InfluencerMatchResult]
    recommended_budget: Tuple[float, float]
    projected_total_reach: Tuple[int, int]
    predicted_total_revenue: Optional[Tuple[float, float]] = None
    predicted_total_roi_percentage: Optional[Tuple[float, float]] = None
    campaign_strategy: str
    breakdown: Dict[str, Any]
    disclaimer: str = (
        "Predictions combine the influencer's measured recent performance with "
        "industry benchmarks (CTR, CVR, CPM). Replace with actuals after the "
        "campaign runs to recompute true ROI."
    )


# ---------------------------------------------------------------------------
# Roster Intelligence (Phase 4 + Phase 5)
# ---------------------------------------------------------------------------

class ReadinessFlags(BaseModel):
    """Reliability/readiness gate — qualification flags, not a ranker."""
    is_active: Optional[bool] = None
    is_reachable: Optional[bool] = None
    is_agency_managed: Optional[bool] = None
    view_stability: Optional[str] = None  # "stable" | "moderate" | "volatile"
    flags: List[str] = []
    gate_passed: bool = False
    gate_reason: Optional[str] = None


class SponsorshipReadiness(BaseModel):
    """Sponsorship readiness label — answers 'How ready is this creator for
    brand partnerships?' independently from the intrinsic quality tier."""
    label: Optional[str] = None  # "mature" | "emerging" | "unproven" | "saturated" | "unknown"
    score: Optional[float] = None
    explanation: Optional[str] = None
    outreach_implication: Optional[str] = None


class CreatorIntelligence(BaseModel):
    """Composed creator-intelligence view: intrinsic tier + layers."""
    tier: Optional[str] = None  # "S" | "A" | "B" | null (untiered)
    tier_label: str = "Untiered"
    tier_explanation: str = ""
    confidence: str = "low"
    readiness: ReadinessFlags
    trust_score: Optional[float] = None
    sponsorship_score: Optional[float] = None
    sponsorship_readiness: Optional[SponsorshipReadiness] = None
    override_reason: Optional[str] = None


class RosterCreatorResponse(BaseModel):
    """Single creator in the roster intelligence response."""
    influencer_id: int
    username: str
    display_name: str
    followers_count: int
    platform: str
    intelligence: CreatorIntelligence
    trust_breakdown: Optional[Dict[str, Any]] = None
    sponsorship_profile: Optional[Dict[str, Any]] = None
    # Sponsorship readiness (Model C) — top-level for prominence
    sponsorship_readiness: Optional[SponsorshipReadiness] = None
    # Brand-fit overlay (Phase 5) — present only when brand_profile_id is supplied
    brand_fit: Optional[Dict[str, Any]] = None
    # Campaign potential (Phase 5, demoted) — secondary industry-benchmark estimate
    campaign_potential: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


class RosterIntelligenceResponse(BaseModel):
    """Response for the roster intelligence endpoint."""
    creators: List[RosterCreatorResponse]
    total: int
    sort_order: str = "intrinsic_quality"
    sort_description: str = (
        "Sorted by intrinsic audience trust (tier), then trust score, "
        "then sponsorship readiness. NOT by follower count."
    )
    brand_profile_id: Optional[int] = None
    disclaimer: Optional[str] = None


# ---------------------------------------------------------------------------
# Enrichment pipeline (Phase 6)
# ---------------------------------------------------------------------------

class EnrichmentTriggerResponse(BaseModel):
    """Response from POST /enrichment/trigger."""
    job_id: str
    status: str  # "queued"
    message: str


class EnrichmentCreatorStatus(BaseModel):
    """Per-creator enrichment status (lightweight)."""
    influencer_id: int
    handle: Optional[str] = None
    enrichment_status: Optional[str] = None
    last_enriched_at: Optional[str] = None
    enrichment_error: Optional[str] = None


class EnrichmentStatusResponse(BaseModel):
    """Overview of enrichment state across the roster."""
    total_resolved: int
    never_enriched: int
    completed: int
    partial: int
    failed: int
    running: int
    creators: List[EnrichmentCreatorStatus]
    latest_job: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# AI Campaign Intelligence layer (additive)
#
# This layer sits ON TOP of the existing Campaign/Influencer/BrandProfile
# model. It never recomputes Trust Score (utils.trust_scorer) or Tier
# (utils.tiering) — it consumes them as inputs. Missing data renders as
# "Insufficient data" rather than being fabricated, mirroring the
# predicted_outcome vs actuals discipline already established in benchmarks.py.
# ---------------------------------------------------------------------------

class CampaignBriefUnderstanding(BaseModel):
    """AI-parsed (or manually supplied) understanding of a campaign.
    Stored as Campaign.ai_campaign_brief."""
    objective: Optional[str] = None
    target_audience: Optional[str] = None
    geography: Optional[List[str]] = None
    category: Optional[List[str]] = None
    budget: Optional[float] = None
    trust_profile_pref: Optional[str] = None  # e.g. "high-trust over high-reach"
    sponsorship_pref: Optional[str] = None    # e.g. "mature" | "emerging" | "any"
    kpis: Optional[List[str]] = None
    raw_input: Optional[str] = None
    source: str = "manual"  # "gemini" | "manual" | "deterministic_fallback"


class CampaignAnalyzeRequest(BaseModel):
    """Either free-text natural language, or structured overrides, or both.
    Structured fields win over anything Gemini extracts from raw_input."""
    raw_input: Optional[str] = Field(default=None, max_length=4000)
    objective: Optional[str] = None
    target_audience: Optional[str] = None
    geography: Optional[List[str]] = None
    category: Optional[List[str]] = None
    budget: Optional[float] = Field(default=None, ge=0)
    trust_profile_pref: Optional[str] = None
    sponsorship_pref: Optional[str] = None
    kpis: Optional[List[str]] = None


class CampaignMatchRequest(BaseModel):
    brand_profile_id: int
    limit: int = Field(default=50, ge=1, le=200)
    min_trust_score: Optional[float] = Field(default=None, ge=0, le=100)


class CampaignMatchResult(BaseModel):
    """One creator's Campaign Match Score. SEPARATE from Trust Score — both
    are always shown together, never merged into one number."""
    influencer_id: int
    username: str
    display_name: str
    followers_count: int
    tier: Optional[str] = None
    trust_score: Optional[float] = None
    sponsorship_maturity: Optional[str] = None
    match_score: Optional[float] = None
    audience_fit: Optional[float] = None
    brand_fit: Optional[float] = None
    category_fit: Optional[float] = None
    geographic_fit: Optional[float] = None
    budget_fit: Optional[float] = None
    trust_component: Optional[float] = None
    sponsorship_component: Optional[float] = None
    risk_level: Optional[str] = None
    reasons: List[str] = []
    why: str = ""
    recommended_role: Optional[str] = None
    confidence: Optional[str] = None
    estimated_reach: Optional[int] = None
    estimated_cost: Optional[Tuple[float, float]] = None
    computed_at: Optional[str] = None


class CampaignMatchListResponse(BaseModel):
    campaign_id: int
    brand_profile_id: Optional[int] = None
    matches: List[CampaignMatchResult]
    total: int
    disclaimer: str = (
        "Campaign Match Score is a per-campaign fit estimate. It does NOT "
        "replace or recompute Trust Score, which reflects intrinsic audience "
        "quality independent of any campaign."
    )


class ShortlistRequest(BaseModel):
    influencer_ids: List[int] = Field(min_length=1)


class CampaignCreatorResponse(BaseModel):
    id: int
    campaign_id: int
    influencer_id: int
    username: str
    display_name: str
    status: str
    recommended_role: Optional[str] = None
    notes: Optional[str] = None
    match_score: Optional[float] = None
    trust_score: Optional[float] = None
    tier: Optional[str] = None
    views: Optional[int] = None
    engagement: Optional[int] = None
    clicks: Optional[int] = None
    conversions: Optional[int] = None
    revenue: Optional[float] = None
    spend: Optional[float] = None
    added_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class CampaignCreatorUpdate(BaseModel):
    status: Optional[str] = None
    recommended_role: Optional[str] = None
    notes: Optional[str] = None
    views: Optional[int] = Field(default=None, ge=0)
    engagement: Optional[int] = Field(default=None, ge=0)
    clicks: Optional[int] = Field(default=None, ge=0)
    conversions: Optional[int] = Field(default=None, ge=0)
    revenue: Optional[float] = Field(default=None, ge=0)
    spend: Optional[float] = Field(default=None, ge=0)


CAMPAIGN_TASK_TYPES = (
    "brief_sent", "brief_approved", "content_draft", "content_submitted",
    "content_approved", "publish_scheduled", "published", "performance_tracking",
)


class CampaignTaskCreate(BaseModel):
    task_type: str
    status: str = "pending"
    deadline: Optional[datetime] = None
    notes: Optional[str] = None


class CampaignTaskUpdate(BaseModel):
    status: Optional[str] = None
    deadline: Optional[datetime] = None
    notes: Optional[str] = None


class CampaignTaskResponse(BaseModel):
    id: int
    campaign_creator_id: int
    task_type: str
    status: str
    deadline: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    notes: Optional[str] = None
    is_overdue: bool = False
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BriefGenerateRequest(BaseModel):
    influencer_ids: List[int] = Field(min_length=1)


class CampaignBriefResponse(BaseModel):
    campaign_id: int
    influencer_id: int
    username: Optional[str] = None
    display_name: Optional[str] = None
    objective: Optional[str] = None
    key_message: Optional[str] = None
    content_format: Optional[str] = None
    creative_direction: Optional[str] = None
    hook: Optional[str] = None
    talking_points: List[str] = []
    cta: Optional[str] = None
    dos: List[str] = []
    donts: List[str] = []
    required_disclosures: Optional[str] = None
    deadline: Optional[datetime] = None
    deliverables: List[str] = []
    source: Optional[str] = None
    generated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


ContentType = Literal[
    "caption", "youtube_title", "youtube_description", "short_hook",
    "video_concept", "script_outline", "cta", "hashtags", "talking_points",
]


class ContentGenerateRequest(BaseModel):
    influencer_id: int
    campaign_id: Optional[int] = None
    content_type: ContentType
    extra_instructions: Optional[str] = Field(default=None, max_length=1000)


class CreatorContentResponse(BaseModel):
    id: int
    influencer_id: int
    campaign_id: Optional[int] = None
    content_type: str
    caption: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    hook: Optional[str] = None
    video_concept: Optional[str] = None
    script_outline: Optional[str] = None
    cta: Optional[str] = None
    hashtags: List[str] = []
    talking_points: List[str] = []
    source: Optional[str] = None
    generated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class CreatorPerformance(BaseModel):
    influencer_id: int
    username: str
    display_name: str
    views: Optional[int] = None
    engagement: Optional[int] = None
    clicks: Optional[int] = None
    conversions: Optional[int] = None
    revenue: Optional[float] = None
    spend: Optional[float] = None
    roi_percentage: Optional[float] = None
    match_score: Optional[float] = None
    trust_score: Optional[float] = None
    has_actuals: bool = False


class CampaignPerformanceResponse(BaseModel):
    campaign_id: int
    reach: Optional[int] = None
    views: Optional[int] = None
    engagement: Optional[int] = None
    clicks: Optional[int] = None
    ctr: Optional[float] = None
    conversions: Optional[int] = None
    cvr: Optional[float] = None
    revenue: Optional[float] = None
    spend: Optional[float] = None
    roi_percentage: Optional[float] = None
    cpm: Optional[float] = None
    cpc: Optional[float] = None
    cpa: Optional[float] = None
    per_creator: List[CreatorPerformance] = []
    data_completeness: str = "none"  # "none" | "partial" | "full"
    note: Optional[str] = None


class AIInsightItem(BaseModel):
    insight_type: str
    content: str
    data_snapshot: Optional[Dict[str, Any]] = None
    generated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class PerformanceAnalysisResponse(BaseModel):
    campaign_id: int
    what_happened: str
    why: str
    what_next: str
    insights: List[AIInsightItem] = []
    source: str  # "gemini" | "deterministic"
    disclaimer: str = (
        "Analysis is grounded only in recorded actuals for this campaign. "
        "Metrics that have not been entered are reported as insufficient "
        "data, never estimated."
    )


class CampaignReportResponse(BaseModel):
    campaign_id: int
    executive_summary: str
    campaign_objective: str
    creator_selection: str
    creator_intelligence: List[Dict[str, Any]] = []
    campaign_performance: Optional[CampaignPerformanceResponse] = None
    creator_performance: List[CreatorPerformance] = []
    best_performing_creators: List[Dict[str, Any]] = []
    weakest_performing_creators: List[Dict[str, Any]] = []
    roi_analysis: str
    key_insights: List[str] = []
    risks: List[str] = []
    recommendations: List[str] = []
    next_campaign_strategy: str
    generated_at: datetime


class AssistantQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    campaign_id: Optional[int] = None


class AssistantQueryResponse(BaseModel):
    answer: str
    grounded_on: Dict[str, Any] = {}
    source: str  # "gemini" | "deterministic_fallback"
    disclaimer: str = (
        "Answers are grounded only in data stored in this workspace. The "
        "assistant never invents follower counts, engagement, or campaign results."
    )
