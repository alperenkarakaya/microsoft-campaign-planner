"""
AI Performance Analyst.

Reads ONLY stored actuals (Campaign + CampaignCreator + CampaignMatch rows
already committed to the DB) and produces three grounded sections:
  - what_happened: a factual summary of the real numbers.
  - why: compares creators against each other / against their match data,
    using only numbers actually present.
  - what_next: actionable, tied to what was actually observed.

Any section that would require data not on file renders "Insufficient data"
— this module never invents a number. Gemini, when available, is used only
to phrase the three sections in prose; it is given the exact computed
numbers and instructed not to add anything beyond them. Without Gemini, a
deterministic prose template covers the same ground.
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


INSUFFICIENT = "Insufficient data."


def _deterministic_sections(
    campaign_name: str,
    creators_with_actuals: List[Dict[str, Any]],
    performance: Dict[str, Any],
) -> Dict[str, str]:
    if not creators_with_actuals:
        return {
            "what_happened": INSUFFICIENT + " No creator has recorded actuals for this campaign yet.",
            "why": INSUFFICIENT,
            "what_next": "Enter actuals (views, clicks, conversions, revenue) for at least one creator to unlock analysis.",
        }

    n = len(creators_with_actuals)
    total_views = performance.get("views")
    total_revenue = performance.get("revenue")
    roi = performance.get("roi_percentage")

    what_parts = [f"{n} creator(s) in '{campaign_name}' have recorded actuals."]
    if total_views is not None:
        what_parts.append(f"Combined views: {total_views:,}.")
    if total_revenue is not None:
        what_parts.append(f"Combined revenue: ${total_revenue:,.2f}.")
    if roi is not None:
        what_parts.append(f"Blended ROI: {roi:.1f}%.")
    what_happened = " ".join(what_parts)

    # Rank by ROI where we have both revenue and spend for a creator.
    ranked = [
        c for c in creators_with_actuals
        if c.get("roi_percentage") is not None
    ]
    ranked.sort(key=lambda c: c["roi_percentage"], reverse=True)

    if len(ranked) >= 2:
        best, worst = ranked[0], ranked[-1]
        why = (
            f"{best['display_name']} led on ROI ({best['roi_percentage']:.1f}%), "
            f"while {worst['display_name']} trailed ({worst['roi_percentage']:.1f}%). "
        )
        if best.get("trust_score") is not None and worst.get("trust_score") is not None:
            if best["trust_score"] > worst["trust_score"]:
                why += "The stronger performer also had the higher Trust Score, consistent with trust-before-reach."
            else:
                why += "Trust Score did not predict the ROI gap here — reach or content fit may explain it instead."
        why_text = why
    elif len(ranked) == 1:
        why_text = f"Only {ranked[0]['display_name']} has enough data (revenue + spend) to compute ROI; no comparison is possible yet."
    else:
        why_text = INSUFFICIENT + " No creator has both revenue and spend recorded, so ROI cannot be compared."

    if ranked:
        top = ranked[0]
        what_next = (
            f"{top['display_name']} is outperforming on ROI — consider expanding this partnership "
            f"or reallocating budget toward similar-profile creators."
        )
        if len(ranked) >= 2:
            bottom = ranked[-1]
            what_next += (
                f" Review {bottom['display_name']}'s content/CTA before renewing — "
                f"ROI is trailing the campaign average."
            )
    else:
        what_next = "Record revenue and spend per creator to generate optimization recommendations."

    return {"what_happened": what_happened, "why": why_text, "what_next": what_next}


async def analyze_campaign_performance(
    *,
    campaign_name: str,
    creators_with_actuals: List[Dict[str, Any]],
    performance: Dict[str, Any],
) -> Dict[str, Any]:
    """Returns {"what_happened", "why", "what_next", "source"}.

    creators_with_actuals: list of dicts with display_name, views, clicks,
    conversions, revenue, spend, roi_percentage (any may be None),
    trust_score, match_score — ONLY creators with at least one recorded actual.
    performance: the aggregate CampaignPerformanceResponse-shaped dict.
    """
    deterministic = _deterministic_sections(campaign_name, creators_with_actuals, performance)

    if not GEMINI_API_KEY or not creators_with_actuals:
        deterministic["source"] = "deterministic"
        return deterministic

    prompt = f"""
You are a campaign performance analyst. Rephrase the following FACTS into
three short sections (what_happened, why, what_next). Do NOT add any number,
name, or claim that is not already present in the facts below. If a fact is
"Insufficient data", keep saying so — do not guess.

FACTS:
what_happened: {deterministic['what_happened']}
why: {deterministic['why']}
what_next: {deterministic['what_next']}

Return ONLY valid JSON: {{"what_happened": "string", "why": "string", "what_next": "string"}}
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
        for key in ("what_happened", "why", "what_next"):
            if key not in result or not isinstance(result[key], str):
                raise ValueError(f"missing field {key}")
        result["source"] = "gemini"
        return result
    except Exception as e:
        logger.warning("Performance analyst: Gemini phrasing failed, using deterministic: %s: %s",
                        type(e).__name__, e)
        deterministic["source"] = "deterministic"
        return deterministic
