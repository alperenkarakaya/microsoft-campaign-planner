"""
Content Studio generator.

Generates one piece of content (caption, title, description, hook, video
concept, script outline, CTA, hashtags, or talking points) for a specific
creator + content_type, using the creator's category/tone as context so
output isn't generic. Same Gemini-with-deterministic-fallback discipline as
brief_generator.py.
"""

import asyncio
import json
import logging
import os
from typing import Any, Dict, Optional

import google.generativeai as genai
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.5-flash"

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


@retry(
    reraise=True,
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=6),
    retry=retry_if_exception_type(Exception),
)
def _gemini_generate(prompt: str) -> str:
    model = genai.GenerativeModel(GEMINI_MODEL)
    response = model.generate_content(prompt)
    return response.text.strip()


# Which output field each content_type fills, and a deterministic fallback text.
_FIELD_BY_TYPE = {
    "caption": "caption",
    "youtube_title": "title",
    "youtube_description": "description",
    "short_hook": "hook",
    "video_concept": "video_concept",
    "script_outline": "script_outline",
    "cta": "cta",
    "hashtags": "hashtags",
    "talking_points": "talking_points",
}


def _deterministic_content(
    content_type: str,
    creator_display_name: str,
    creator_category: Optional[str],
    brand_name: Optional[str],
    extra_instructions: Optional[str],
) -> Dict[str, Any]:
    category = creator_category or "content"
    brand = brand_name or "the brand"
    text_by_type = {
        "caption": f"New {category} video is up — partnered with {brand} on this one. Full thoughts inside.",
        "youtube_title": f"I Tried {brand}'s Latest Product | {creator_display_name}",
        "youtube_description": (
            f"In this video I team up with {brand} to show you how it fits into "
            f"my {category} setup. Thanks to {brand} for sponsoring this video."
        ),
        "short_hook": f"This is the {category} upgrade nobody's talking about yet.",
        "video_concept": f"Day-in-the-life {category} video with {brand} integrated naturally into the routine.",
        "script_outline": (
            "1) Cold open hook (5-10s)\n2) Normal content intro\n"
            f"3) {brand} integration mid-video, framed as personal discovery\n"
            "4) Return to normal content\n5) CTA + outro"
        ),
        "cta": f"Link and code in the description — thanks again to {brand} for making this possible.",
        "hashtags": [f"#{category.replace(' ', '')}", f"#{brand.replace(' ', '')}Partner", "#ad"],
        "talking_points": [
            f"Why {category} creators/viewers should care",
            "First-hand impression, not a spec sheet",
            "One honest caveat to keep it credible",
        ],
    }
    field = _FIELD_BY_TYPE[content_type]
    value = text_by_type[content_type]
    if extra_instructions:
        note = f" (Note: tailor for — {extra_instructions[:200]})"
        if isinstance(value, str):
            value = value + note
    return {field: value, "source": "deterministic_template"}


def _build_prompt(
    content_type: str,
    creator_display_name: str,
    creator_category: Optional[str],
    content_tone: Optional[str],
    brand_name: Optional[str],
    extra_instructions: Optional[str],
) -> str:
    field = _FIELD_BY_TYPE[content_type]
    value_shape = '["string", "string"]' if content_type in ("hashtags", "talking_points") else '"string"'
    json_shape = '{"' + field + '": ' + value_shape + '}'
    return f"""
You are writing {content_type.replace('_', ' ')} for a specific YouTube creator's
sponsored content. Match their existing voice — do not write generically.

CREATOR: {creator_display_name}
- Content category: {creator_category or 'unknown'}
- Existing tone: {content_tone or 'unknown'}
BRAND: {brand_name or 'the brand'}
EXTRA INSTRUCTIONS: {extra_instructions or 'none'}

Return ONLY valid JSON with this exact shape:
{json_shape}
""".strip()


async def generate_content(
    *,
    content_type: str,
    creator_display_name: str,
    creator_category: Optional[str] = None,
    content_tone: Optional[str] = None,
    brand_name: Optional[str] = None,
    extra_instructions: Optional[str] = None,
) -> Dict[str, Any]:
    fallback = _deterministic_content(
        content_type, creator_display_name, creator_category, brand_name, extra_instructions,
    )

    if not GEMINI_API_KEY:
        return fallback

    field = _FIELD_BY_TYPE[content_type]
    prompt = _build_prompt(
        content_type, creator_display_name, creator_category, content_tone,
        brand_name, extra_instructions,
    )

    try:
        text = await asyncio.to_thread(_gemini_generate, prompt)
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        result = json.loads(text.strip())
    except json.JSONDecodeError as e:
        logger.warning("Content generator: non-JSON Gemini output: %s", e)
        return fallback
    except Exception as e:
        logger.warning("Content generator: Gemini failed: %s: %s", type(e).__name__, e)
        return fallback

    if field not in result:
        logger.warning("Content generator: missing field %s, using fallback", field)
        return fallback

    result["source"] = "gemini"
    return result
