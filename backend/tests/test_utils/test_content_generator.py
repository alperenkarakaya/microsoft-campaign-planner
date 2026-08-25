"""utils.ai.content_generator — deterministic fallback path (no GEMINI_API_KEY)."""

import pytest

from utils.ai.content_generator import generate_content, _FIELD_BY_TYPE


@pytest.mark.asyncio
async def test_every_content_type_produces_its_field():
    for content_type, field in _FIELD_BY_TYPE.items():
        result = await generate_content(
            content_type=content_type,
            creator_display_name="Creator X",
            creator_category="gaming",
            brand_name="Acme",
        )
        assert result.get(field), f"{content_type} did not populate {field}"
        assert result["source"] == "deterministic_template"


@pytest.mark.asyncio
async def test_hashtags_and_talking_points_are_lists():
    hashtags = await generate_content(content_type="hashtags", creator_display_name="C", creator_category="tech")
    assert isinstance(hashtags["hashtags"], list) and hashtags["hashtags"]

    points = await generate_content(content_type="talking_points", creator_display_name="C", creator_category="tech")
    assert isinstance(points["talking_points"], list) and points["talking_points"]
