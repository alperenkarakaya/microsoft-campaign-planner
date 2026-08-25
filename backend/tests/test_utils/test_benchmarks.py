"""Tests for the grounded prediction math — the product's core asset."""

from utils import benchmarks as b


def test_cpm_region_multiplier_applied():
    us = b.cpm_benchmark("youtube", "micro", "US")
    tr = b.cpm_benchmark("youtube", "micro", "TR")
    assert us.low == 8.0 and us.high == 18.0
    # TR multiplier is 0.45.
    assert tr.low < us.low and tr.high < us.high
    assert round(tr.low, 2) == round(8.0 * 0.45, 2)


def test_cpm_unknown_region_uses_default_multiplier():
    bench = b.cpm_benchmark("youtube", "macro", "ZZ")
    assert round(bench.low, 2) == round(12.0 * b._DEFAULT_REGION_MULT, 2)


def test_category_normalization_substring_match():
    assert b._normalize_category("Tech Reviews") == "tech"
    assert b._normalize_category("Beauty & Makeup") == "beauty"
    assert b._normalize_category("totally unknown") == ""
    assert b._normalize_category(None) == ""


def test_prediction_high_confidence_with_all_inputs():
    p = b.predict_campaign_outcome(
        platform="youtube", tier="micro", category="tech", region="US",
        median_recent_views=50_000, follower_count=80_000,
        target_aov=40.0, num_posts=1,
    )
    d = p.to_dict()
    assert d["confidence"] == "high"
    # Reach is anchored to measured median views, not followers.
    assert d["predicted_reach"] == [50_000, 50_000]
    assert d["predicted_revenue"][1] > 0
    assert d["predicted_cost"][0] > 0
    assert d["source"]


def test_prediction_low_confidence_without_views_or_aov():
    p = b.predict_campaign_outcome(
        platform="youtube", tier="micro", category=None, region=None,
        median_recent_views=None, follower_count=80_000,
        target_aov=None, num_posts=1,
    )
    d = p.to_dict()
    assert d["confidence"] == "low"
    # No AOV → revenue is not fabricated.
    assert d["predicted_revenue"] == [0.0, 0.0]
    # Falls back to follower-based reach band (low < high).
    assert d["predicted_reach"][0] < d["predicted_reach"][1]


def test_prediction_num_posts_scales_reach():
    one = b.predict_campaign_outcome(
        platform="youtube", tier="macro", category="tech", region="US",
        median_recent_views=10_000, follower_count=500_000,
        target_aov=50.0, num_posts=1,
    ).to_dict()
    three = b.predict_campaign_outcome(
        platform="youtube", tier="macro", category="tech", region="US",
        median_recent_views=10_000, follower_count=500_000,
        target_aov=50.0, num_posts=3,
    ).to_dict()
    assert three["predicted_reach"][0] == one["predicted_reach"][0] * 3


def test_roi_only_when_revenue_and_cost_positive():
    no_aov = b.predict_campaign_outcome(
        platform="youtube", tier="mega", category="finance", region="US",
        median_recent_views=1_000_000, follower_count=2_000_000,
        target_aov=None, num_posts=1,
    ).to_dict()
    assert no_aov["predicted_roi_percentage"] == [0.0, 0.0]
