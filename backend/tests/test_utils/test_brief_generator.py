"""utils.ai.brief_generator — deterministic fallback path (no GEMINI_API_KEY)."""

import pytest

from utils.ai.brief_generator import generate_campaign_brief, _REQUIRED_FIELDS


@pytest.mark.asyncio
async def test_fallback_brief_is_always_complete_and_personalized():
    brand = {"name": "Acme", "aggressive_score": 5, "creative_score": 5,
             "humorous_score": 5, "professional_score": 5, "edgy_score": 5}

    gaming_brief = await generate_campaign_brief(
        brand_profile=brand, campaign_objective="Launch awareness",
        creator_display_name="Gamer One", creator_category="gaming",
        sponsorship_label="mature",
    )
    beauty_brief = await generate_campaign_brief(
        brand_profile=brand, campaign_objective="Launch awareness",
        creator_display_name="Beauty One", creator_category="beauty",
        sponsorship_label="unproven",
    )

    for field in _REQUIRED_FIELDS:
        assert field in gaming_brief and gaming_brief[field]

    assert gaming_brief["source"] == "deterministic_template"
    # Personalized per creator category/sponsorship maturity — not a copy-paste template.
    assert gaming_brief["content_format"] != beauty_brief["content_format"]
