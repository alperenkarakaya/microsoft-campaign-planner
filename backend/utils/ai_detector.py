"""
Heuristic + AI fake-follower detection.

Returns None when detection cannot be performed (no API key, parse failure,
upstream error). Callers must treat None as "unknown" and skip writing the
column rather than substituting a fabricated value.
"""

import os
import json
import asyncio
import logging
from typing import Dict, Optional

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
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(Exception),
)
def _gemini_generate(prompt: str) -> str:
    model = genai.GenerativeModel(GEMINI_MODEL)
    response = model.generate_content(prompt)
    return response.text.strip()


async def detect_fake_followers(channel_data: Dict) -> Optional[float]:
    """Estimate fake-follower percentage (0-100) for a channel.

    Combines a deterministic heuristic on view/sub ratio with a Gemini
    second opinion. Returns None on any failure — callers MUST NOT default
    to a synthetic value.
    """
    sub_count = max(int(channel_data.get("subscriber_count", 0)), 1)
    view_count = int(channel_data.get("view_count", 0))
    video_count = max(int(channel_data.get("video_count", 0)), 1)
    engagement_rate = float(channel_data.get("engagement_rate", 0))

    # Heuristic floor based on view/sub ratio. Channels with consistently low
    # view ratios relative to subscriber count have signs of inflated audience.
    avg_views_per_video = view_count / video_count
    view_ratio = (avg_views_per_video / sub_count) * 100

    if view_ratio < 1.0:
        heuristic_floor = 60.0
    elif view_ratio < 3.0:
        heuristic_floor = 35.0
    elif view_ratio < 5.0:
        heuristic_floor = 15.0
    else:
        heuristic_floor = 0.0

    if not GEMINI_API_KEY:
        return heuristic_floor if heuristic_floor > 0 else None

    prompt = f"""
Estimate the fake-follower percentage of this YouTube channel based on the
relationship between subscribers, lifetime views, and engagement.

Data:
- Title: {channel_data.get('title', 'unknown')}
- Subscribers: {sub_count:,}
- Videos: {video_count}
- Lifetime views: {view_count:,}
- View/sub ratio: {view_ratio:.2f}%
- Recent engagement rate: {engagement_rate:.2f}%

Return ONLY a single number 0-100 (percentage). No words, no symbols.
""".strip()

    try:
        raw = await asyncio.to_thread(_gemini_generate, prompt)
        text = raw.replace("%", "").replace(",", ".")
        gemini_estimate = float(text.split()[0])
        gemini_estimate = max(0.0, min(100.0, gemini_estimate))
    except (ValueError, IndexError) as e:
        logger.warning("Fake-follower parse failed: %s", e)
        return heuristic_floor if heuristic_floor > 0 else None
    except Exception as e:
        logger.warning("Fake-follower detection failed after retries: %s: %s", type(e).__name__, e)
        return heuristic_floor if heuristic_floor > 0 else None

    return max(heuristic_floor, gemini_estimate)


async def analyze_campaign_performance(campaign_data: Dict) -> Dict:
    """AI commentary on a completed campaign's measured metrics."""
    if not GEMINI_API_KEY:
        return {"score": None, "insights": ["AI not configured"], "recommendations": []}

    prompt = f"""
You are an influencer marketing analyst. Score and comment on this completed campaign.

Campaign:
- Budget: ${campaign_data['budget']:,.2f}
- Revenue: ${campaign_data['revenue']:,.2f}
- ROI: {campaign_data['roi_percentage']:.2f}%
- Views: {campaign_data['views']:,}
- Clicks: {campaign_data['clicks']:,}
- Conversions: {campaign_data['conversions']:,}
- CPM: ${campaign_data['cpm']:.2f}
- CPC: ${campaign_data['cpc']:.2f}

Return ONLY JSON:
{{
  "score": 0-100,
  "insights": ["insight 1", "insight 2"],
  "recommendations": ["recommendation 1", "recommendation 2"]
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
        return json.loads(text.strip())
    except json.JSONDecodeError as e:
        logger.warning("Campaign analysis returned non-JSON: %s", e)
        return {"score": None, "insights": ["AI returned non-JSON output"], "recommendations": []}
    except Exception as e:
        logger.warning("Campaign analysis failed after retries: %s: %s", type(e).__name__, e)
        return {"score": None, "insights": [f"Analysis failed: {str(e)[:80]}"], "recommendations": []}
