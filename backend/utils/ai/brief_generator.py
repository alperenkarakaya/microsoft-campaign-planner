"""
AI Campaign Brief generator — personalized per creator.

Uses each creator's actual content style (category, content_tone, top video
themes when on file, sponsorship maturity) so the brief differs across
creators rather than being a copy-pasted template. Gemini produces the
creative language; a deterministic template fills every field when Gemini is
unavailable or returns invalid output, so a brief is always produced.
"""

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional

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


_REQUIRED_FIELDS = [
    "objective", "key_message", "content_format", "creative_direction", "hook",
    "talking_points", "cta", "dos", "donts", "required_disclosures", "deliverables",
]


def _deterministic_template(
    *,
    campaign_objective: Optional[str],
    brand_name: str,
    creator_display_name: str,
    creator_category: Optional[str],
    content_tone: Optional[str],
    sponsorship_label: Optional[str],
) -> Dict[str, Any]:
    """Always-available fallback brief. Personalized via the fields we do
    have (category / tone / sponsorship maturity), never a blank template."""
    category = creator_category or "content"
    tone = content_tone or "their established"
    objective = campaign_objective or f"Drive awareness and consideration for {brand_name}"

    if sponsorship_label == "mature":
        format_note = "a fully-integrated sponsored segment, similar to their existing brand deals"
    elif sponsorship_label == "unproven":
        format_note = "a native, low-pressure first collaboration to introduce the partnership"
    else:
        format_note = "an integration that matches their existing content pacing"

    return {
        "objective": objective,
        "key_message": f"{brand_name} fits naturally into {creator_display_name}'s {category} content.",
        "content_format": f"Standard-length {category} video with {format_note}",
        "creative_direction": (
            f"Keep {tone} tone and pacing. Introduce the product where it would "
            f"naturally appear in a normal upload, not as a hard cut-away."
        ),
        "hook": f"Open with the problem {brand_name} solves for a {category} audience, not the product itself.",
        "talking_points": [
            f"Why this matters to a {category} audience",
            "Personal, first-use impression rather than a spec list",
            "One clear differentiator vs. alternatives",
        ],
        "cta": "Link/code in description; verbal mention once mid-video and once at outro.",
        "dos": [
            "Disclose the partnership per FTC/ASA guidelines",
            "Keep the integration in your own voice",
            "Show the product being used, not just described",
        ],
        "donts": [
            "Don't overstate claims not provided by the brand",
            "Don't bury the disclosure at the very end only",
        ],
        "required_disclosures": "#ad / Paid partnership disclosure at video start, per platform policy.",
        "deliverables": ["1x main video integration", "1x pinned comment with link/code"],
    }


def _build_prompt(
    *,
    brand_profile: Dict[str, Any],
    campaign_objective: Optional[str],
    creator_display_name: str,
    creator_category: Optional[str],
    content_tone: Optional[str],
    top_video_themes: Optional[List[str]],
    sponsorship_label: Optional[str],
    tier: Optional[str],
) -> str:
    themes = ", ".join(top_video_themes) if top_video_themes else "unknown"
    return f"""
You are a creator partnerships manager writing a personalized campaign brief.

BRAND: {brand_profile.get('name')}
Tone target — aggressive:{brand_profile.get('aggressive_score')}/10, creative:{brand_profile.get('creative_score')}/10, humorous:{brand_profile.get('humorous_score')}/10, professional:{brand_profile.get('professional_score')}/10, edgy:{brand_profile.get('edgy_score')}/10
CAMPAIGN OBJECTIVE: {campaign_objective or 'awareness and consideration'}

CREATOR: {creator_display_name}
- Content category: {creator_category or 'unknown'}
- Existing content tone: {content_tone or 'unknown'}
- Recent video themes: {themes}
- Sponsorship maturity: {sponsorship_label or 'unknown'}
- Intrinsic quality tier: {tier or 'unknown'}

Write a brief PERSONALIZED to this specific creator's existing style — do not
write a generic template. Return ONLY valid JSON with this exact shape:
{{
  "objective": "string",
  "key_message": "string",
  "content_format": "string — should reflect this creator's typical format",
  "creative_direction": "string",
  "hook": "string",
  "talking_points": ["string", "string", "string"],
  "cta": "string",
  "dos": ["string", "string"],
  "donts": ["string", "string"],
  "required_disclosures": "string",
  "deliverables": ["string"]
}}
""".strip()


async def generate_campaign_brief(
    *,
    brand_profile: Dict[str, Any],
    campaign_objective: Optional[str],
    creator_display_name: str,
    creator_category: Optional[str],
    content_tone: Optional[str] = None,
    top_video_themes: Optional[List[str]] = None,
    sponsorship_label: Optional[str] = None,
    tier: Optional[str] = None,
) -> Dict[str, Any]:
    """Returns a dict with all _REQUIRED_FIELDS populated plus 'source'."""
    fallback = _deterministic_template(
        campaign_objective=campaign_objective,
        brand_name=brand_profile.get("name") or "the brand",
        creator_display_name=creator_display_name,
        creator_category=creator_category,
        content_tone=content_tone,
        sponsorship_label=sponsorship_label,
    )
    fallback["source"] = "deterministic_template"

    if not GEMINI_API_KEY:
        return fallback

    prompt = _build_prompt(
        brand_profile=brand_profile,
        campaign_objective=campaign_objective,
        creator_display_name=creator_display_name,
        creator_category=creator_category,
        content_tone=content_tone,
        top_video_themes=top_video_themes,
        sponsorship_label=sponsorship_label,
        tier=tier,
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
        logger.warning("Brief generator: non-JSON Gemini output: %s", e)
        return fallback
    except Exception as e:
        logger.warning("Brief generator: Gemini failed: %s: %s", type(e).__name__, e)
        return fallback

    for field in _REQUIRED_FIELDS:
        if field not in result:
            logger.warning("Brief generator: missing field %s, using fallback", field)
            return fallback

    result["source"] = "gemini"
    return result
