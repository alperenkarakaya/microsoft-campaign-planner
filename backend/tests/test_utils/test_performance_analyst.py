"""utils.ai.performance_analyst — grounded, no-fabrication analysis."""

import pytest

from utils.ai.performance_analyst import analyze_campaign_performance


@pytest.mark.asyncio
async def test_no_actuals_returns_insufficient_data():
    result = await analyze_campaign_performance(
        campaign_name="Empty Campaign", creators_with_actuals=[], performance={},
    )
    assert result["source"] == "deterministic"
    assert "Insufficient data" in result["what_happened"]
    assert "Insufficient data" in result["why"]


@pytest.mark.asyncio
async def test_two_creators_compares_roi_without_fabricating():
    creators = [
        {"display_name": "Alice", "roi_percentage": 150.0, "trust_score": 80.0},
        {"display_name": "Bob", "roi_percentage": 50.0, "trust_score": 40.0},
    ]
    performance = {"views": 500_000, "revenue": 10_000.0, "roi_percentage": 100.0}
    result = await analyze_campaign_performance(
        campaign_name="Test Campaign", creators_with_actuals=creators, performance=performance,
    )
    assert result["source"] == "deterministic"
    assert "Alice" in result["why"]
    assert "Bob" in result["why"]
    assert "Alice" in result["what_next"]


@pytest.mark.asyncio
async def test_single_creator_no_comparison_claimed():
    creators = [{"display_name": "Solo", "roi_percentage": 120.0, "trust_score": 70.0}]
    result = await analyze_campaign_performance(
        campaign_name="Test", creators_with_actuals=creators, performance={"roi_percentage": 120.0},
    )
    # Must not claim a comparison it can't make with only one creator.
    assert "only" in result["why"].lower()
