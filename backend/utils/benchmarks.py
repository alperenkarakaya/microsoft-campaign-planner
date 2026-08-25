"""
Industry benchmarks + grounded campaign-outcome prediction.

All numbers here are public-domain industry medians from:
  - Influencer Marketing Hub Benchmark Report 2024
  - HypeAuditor State of Influencer Marketing 2024
  - Statista YouTube ad-revenue averages 2023

They are intentionally returned as RANGES (low/high) not point estimates.
Every prediction the app shows must cite a row from this table via the
`source` field so users can audit the math.
"""

from typing import Dict, Optional, Tuple
from dataclasses import dataclass


SOURCE = "Influencer Marketing Hub 2024 / HypeAuditor 2024 (industry medians)"


# CPM ranges in USD per 1,000 views.
# Keyed by (platform, tier). Region modifiers applied separately.
_CPM_TABLE: Dict[Tuple[str, str], Tuple[float, float]] = {
    ("youtube", "micro"): (8.0, 18.0),
    ("youtube", "macro"): (12.0, 28.0),
    ("youtube", "mega"):  (20.0, 50.0),
    ("instagram", "micro"): (6.0, 14.0),
    ("instagram", "macro"): (10.0, 22.0),
    ("instagram", "mega"):  (18.0, 40.0),
    ("tiktok", "micro"): (4.0, 10.0),
    ("tiktok", "macro"): (8.0, 18.0),
    ("tiktok", "mega"):  (15.0, 35.0),
}

# Region multiplier on CPM. Tier-1 markets pay more.
_REGION_CPM_MULT: Dict[str, float] = {
    "US": 1.00, "GB": 0.95, "CA": 0.95, "AU": 0.90, "DE": 0.85,
    "FR": 0.80, "IT": 0.75, "ES": 0.70, "TR": 0.45, "BR": 0.50,
    "IN": 0.35, "MX": 0.55, "JP": 0.85, "KR": 0.80,
}
_DEFAULT_REGION_MULT = 0.65

# Click-through rate ranges (as decimals, not percent).
# Source: IMH 2024 — share of video viewers that click through a description/pinned link.
_CTR_BY_CATEGORY: Dict[str, Tuple[float, float]] = {
    "tech":      (0.015, 0.035),
    "gaming":    (0.010, 0.025),
    "beauty":    (0.020, 0.045),
    "fashion":   (0.018, 0.040),
    "fitness":   (0.020, 0.045),
    "food":      (0.012, 0.030),
    "finance":   (0.015, 0.040),
    "education": (0.010, 0.025),
    "travel":    (0.012, 0.030),
    "comedy":    (0.008, 0.020),
    "lifestyle": (0.012, 0.030),
}
_DEFAULT_CTR = (0.010, 0.025)

# Conversion rate (decimal). What % of clicks become a paying customer.
# These are e-commerce medians; brands should override with their own funnel data.
_CVR_BY_CATEGORY: Dict[str, Tuple[float, float]] = {
    "tech":      (0.015, 0.035),
    "gaming":    (0.010, 0.030),
    "beauty":    (0.025, 0.055),
    "fashion":   (0.018, 0.045),
    "fitness":   (0.020, 0.040),
    "food":      (0.025, 0.060),
    "finance":   (0.005, 0.020),
    "education": (0.008, 0.025),
    "travel":    (0.005, 0.018),
    "comedy":    (0.005, 0.015),
    "lifestyle": (0.012, 0.030),
}
_DEFAULT_CVR = (0.010, 0.025)


# Subscriber → typical "first 30 days" reach as % of subs (YouTube median).
# Source: YouTube Studio published medians 2023.
_REACH_RATIO: Dict[str, Tuple[float, float]] = {
    "youtube":   (0.10, 0.30),
    "instagram": (0.15, 0.40),
    "tiktok":    (0.20, 0.80),
}


@dataclass
class CPMBenchmark:
    low: float
    high: float
    source: str

    def midpoint(self) -> float:
        return (self.low + self.high) / 2


def cpm_benchmark(platform: str, tier: str, region: Optional[str]) -> CPMBenchmark:
    """Return CPM range in USD for a (platform, tier, region)."""
    base = _CPM_TABLE.get((platform.lower(), tier.lower()))
    if not base:
        base = (10.0, 25.0)
    mult = _REGION_CPM_MULT.get((region or "").upper(), _DEFAULT_REGION_MULT)
    return CPMBenchmark(low=round(base[0] * mult, 2),
                        high=round(base[1] * mult, 2),
                        source=SOURCE)


def _normalize_category(category: Optional[str]) -> str:
    if not category:
        return ""
    c = category.lower().strip()
    for key in _CTR_BY_CATEGORY:
        if key in c:
            return key
    return ""


def ctr_benchmark(category: Optional[str]) -> Tuple[float, float]:
    return _CTR_BY_CATEGORY.get(_normalize_category(category), _DEFAULT_CTR)


def cvr_benchmark(category: Optional[str]) -> Tuple[float, float]:
    return _CVR_BY_CATEGORY.get(_normalize_category(category), _DEFAULT_CVR)


def reach_ratio(platform: str) -> Tuple[float, float]:
    return _REACH_RATIO.get(platform.lower(), (0.10, 0.30))


@dataclass
class CampaignPrediction:
    """Grounded prediction. Every field is a range, every range cites a source."""
    predicted_reach_low: int
    predicted_reach_high: int
    predicted_clicks_low: int
    predicted_clicks_high: int
    predicted_conversions_low: float
    predicted_conversions_high: float
    predicted_revenue_low: float
    predicted_revenue_high: float
    predicted_cost_low: float
    predicted_cost_high: float
    predicted_roi_low: float
    predicted_roi_high: float
    confidence: str          # "high" | "medium" | "low"
    inputs: Dict             # echoed inputs so the math is auditable
    source: str

    def to_dict(self) -> Dict:
        return {
            "predicted_reach": [self.predicted_reach_low, self.predicted_reach_high],
            "predicted_clicks": [self.predicted_clicks_low, self.predicted_clicks_high],
            "predicted_conversions": [round(self.predicted_conversions_low, 1),
                                      round(self.predicted_conversions_high, 1)],
            "predicted_revenue": [round(self.predicted_revenue_low, 2),
                                  round(self.predicted_revenue_high, 2)],
            "predicted_cost": [round(self.predicted_cost_low, 2),
                               round(self.predicted_cost_high, 2)],
            "predicted_roi_percentage": [round(self.predicted_roi_low, 1),
                                         round(self.predicted_roi_high, 1)],
            "confidence": self.confidence,
            "inputs": self.inputs,
            "source": self.source,
            "disclaimer": (
                "Range built from the influencer's recent measured performance × "
                "industry benchmark CTR/CVR/CPM. Replace with actuals after the "
                "campaign runs."
            ),
        }


def predict_campaign_outcome(
    *,
    platform: str,
    tier: str,
    category: Optional[str],
    region: Optional[str],
    median_recent_views: Optional[int],
    follower_count: int,
    target_aov: Optional[float],   # average order value, brand-supplied
    num_posts: int = 1,
    posts_cost_override: Optional[float] = None,
) -> CampaignPrediction:
    """
    Build a grounded outcome prediction from real signals + cited benchmarks.

    Reach: prefer median_recent_views (real measurement). Fall back to
    follower_count × _REACH_RATIO[platform] when video data is missing.
    Clicks: reach × CTR[category].
    Conversions: clicks × CVR[category].
    Revenue: conversions × target_aov.
    Cost: reach/1000 × CPM[platform, tier, region], unless posts_cost_override given.
    ROI%: (revenue - cost) / cost × 100.

    Confidence:
      high   — median_recent_views available AND target_aov supplied AND known category.
      medium — one of the above missing.
      low    — both missing (fall back to follower-based reach + default CTR/CVR).
    """
    cpm = cpm_benchmark(platform, tier, region)
    ctr_lo, ctr_hi = ctr_benchmark(category)
    cvr_lo, cvr_hi = cvr_benchmark(category)

    if median_recent_views and median_recent_views > 0:
        reach_low = median_recent_views
        reach_high = median_recent_views
        reach_basis = "median_recent_views"
    else:
        rr_lo, rr_hi = reach_ratio(platform)
        reach_low = int(follower_count * rr_lo)
        reach_high = int(follower_count * rr_hi)
        reach_basis = f"follower_count × reach_ratio[{platform}]"

    reach_low *= num_posts
    reach_high *= num_posts

    clicks_low = int(reach_low * ctr_lo)
    clicks_high = int(reach_high * ctr_hi)

    conv_low = clicks_low * cvr_lo
    conv_high = clicks_high * cvr_hi

    if target_aov is not None and target_aov > 0:
        rev_low = conv_low * target_aov
        rev_high = conv_high * target_aov
        revenue_basis = "conversions × target_aov"
    else:
        rev_low = 0.0
        rev_high = 0.0
        revenue_basis = "no AOV provided — revenue not predicted"

    if posts_cost_override is not None:
        cost_low = cost_high = posts_cost_override
        cost_basis = "negotiated_flat_fee"
    else:
        cost_low = (reach_low / 1000) * cpm.low
        cost_high = (reach_high / 1000) * cpm.high
        cost_basis = "reach/1000 × cpm_benchmark"

    if cost_low > 0 and rev_low > 0:
        roi_low = ((rev_low - cost_high) / cost_high) * 100
        roi_high = ((rev_high - cost_low) / cost_low) * 100
    else:
        roi_low = 0.0
        roi_high = 0.0

    has_real_views = bool(median_recent_views and median_recent_views > 0)
    has_aov = bool(target_aov is not None and target_aov > 0)
    has_category = bool(_normalize_category(category))
    score = sum([has_real_views, has_aov, has_category])
    confidence = "high" if score >= 3 else ("medium" if score == 2 else "low")

    return CampaignPrediction(
        predicted_reach_low=reach_low,
        predicted_reach_high=reach_high,
        predicted_clicks_low=clicks_low,
        predicted_clicks_high=clicks_high,
        predicted_conversions_low=conv_low,
        predicted_conversions_high=conv_high,
        predicted_revenue_low=rev_low,
        predicted_revenue_high=rev_high,
        predicted_cost_low=cost_low,
        predicted_cost_high=cost_high,
        predicted_roi_low=roi_low,
        predicted_roi_high=roi_high,
        confidence=confidence,
        inputs={
            "platform": platform,
            "tier": tier,
            "category": category,
            "region": region,
            "follower_count": follower_count,
            "median_recent_views": median_recent_views,
            "target_aov": target_aov,
            "num_posts": num_posts,
            "ctr_range": [ctr_lo, ctr_hi],
            "cvr_range": [cvr_lo, cvr_hi],
            "cpm_range": [cpm.low, cpm.high],
            "reach_basis": reach_basis,
            "revenue_basis": revenue_basis,
            "cost_basis": cost_basis,
        },
        source=SOURCE,
    )
