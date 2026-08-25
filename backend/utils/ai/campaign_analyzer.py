"""
AI Campaign Builder — parses a natural-language campaign description (and/or
structured overrides) into the structured understanding stored on
Campaign.ai_campaign_brief (see schemas.CampaignBriefUnderstanding).

Structured fields the caller supplies always win over anything extracted from
free text. Without GEMINI_API_KEY, raw_input is stored as-is and every
other field stays None (manual entry required) rather than being guessed.
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

_FIELDS = [
    "objective", "target_audience", "geography", "category", "budget",
    "trust_profile_pref", "sponsorship_pref", "kpis",
]


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


async def _extract_from_text(raw_input: str) -> Optional[Dict[str, Any]]:
    if not GEMINI_API_KEY:
        return None
    prompt = f"""
Extract a structured campaign brief from this description. Use null for
anything not stated — do not guess or invent values.

DESCRIPTION:
{raw_input}

Return ONLY valid JSON with this exact shape:
{{
  "objective": "string or null",
  "target_audience": "string or null",
  "geography": ["string"] or null,
  "category": ["string"] or null,
  "budget": number or null,
  "trust_profile_pref": "string or null (e.g. 'high-trust over high-reach')",
  "sponsorship_pref": "mature|emerging|unproven|any or null",
  "kpis": ["string"] or null
}}
""".strip()
    try:
        text = await asyncio.to_thread(_gemini_generate, prompt)
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        result = json.loads(text.strip())
        return {k: result.get(k) for k in _FIELDS}
    except Exception as e:
        logger.warning("Campaign analyzer: Gemini extraction failed: %s: %s", type(e).__name__, e)
        return None


async def analyze_campaign_brief(
    *,
    raw_input: Optional[str],
    overrides: Dict[str, Any],
) -> Dict[str, Any]:
    """overrides is the structured request fields (already dict, may contain
    None values for unset fields) — these always win over extracted text."""
    extracted: Dict[str, Any] = {}
    source = "manual"

    if raw_input:
        gemini_result = await _extract_from_text(raw_input)
        if gemini_result is not None:
            extracted = gemini_result
            source = "gemini"
        else:
            source = "deterministic_fallback"

    merged = dict(extracted)
    has_overrides = any(v is not None for v in overrides.values())
    for k, v in overrides.items():
        if v is not None:
            merged[k] = v

    if has_overrides and source == "gemini":
        source = "gemini+manual_overrides"
    elif has_overrides:
        source = "manual"

    merged["raw_input"] = raw_input
    merged["source"] = source
    for f in _FIELDS:
        merged.setdefault(f, None)
    return merged
