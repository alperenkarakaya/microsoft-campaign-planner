import os
import json
import asyncio
import logging
from typing import Dict, List, Optional

import google.generativeai as genai
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from utils.benchmarks import cpm_benchmark, CPMBenchmark


logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.5-flash"

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


class GeminiUnavailable(Exception):
    """Raised when Gemini fails after retries or returns unparseable output."""


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(Exception),
)
def _gemini_generate(prompt: str) -> str:
    """Call Gemini with exponential backoff. Raises on persistent failure."""
    model = genai.GenerativeModel(GEMINI_MODEL)
    response = model.generate_content(prompt)
    return response.text.strip()


def categorize_influencer(follower_count: int) -> str:
    """Display label only; do not use this to gate filters or pricing."""
    if follower_count < 100_000:
        return "micro"
    if follower_count < 1_000_000:
        return "macro"
    return "mega"


def unanalyzed_response(reason: str) -> Dict:
    """Returned when AI is unavailable. Score is below the 40 cutoff so the
    influencer is excluded from recommendations rather than surfacing as a fake match."""
    return {
        "status": "unanalyzed",
        "overall_match_score": 0.0,
        "original_match_score": 0.0,
        "content_style_match": 0.0,
        "audience_match": 0.0,
        "engagement_quality": 0.0,
        "brand_safety": 0.0,
        "ai_summary": f"AI analysis unavailable: {reason}",
        "content_tone": "unknown",
        "top_themes": [],
        "quality_flags": ["ai_unavailable"],
        "override_reason": None,
    }


async def analyze_influencer_brand_fit(
    brand_profile: Dict,
    influencer_data: Dict,
    recent_videos: List[Dict],
) -> Dict:
    """Score an influencer's fit to a brand using Gemini.

    Returns a dict with: overall_match_score, original_match_score, four sub-scores,
    ai_summary, content_tone, top_themes, quality_flags, override_reason, status.

    Does NOT return ROI or CPM estimates — those are produced by
    utils.benchmarks.predict_campaign_outcome() so the math stays auditable.
    """
    if not GEMINI_API_KEY:
        return unanalyzed_response("GEMINI_API_KEY not set")

    if recent_videos:
        avg_views = sum(v["views"] for v in recent_videos) / len(recent_videos)
        avg_engagement = sum(v["engagement_rate"] for v in recent_videos) / len(recent_videos)
        video_samples = "\n".join(
            f"- {v['title']}\n  Views: {int(v['views']):,}, Engagement: {v['engagement_rate']:.2f}%"
            for v in recent_videos[:5]
        )
    else:
        avg_views = 0
        avg_engagement = 0
        video_samples = "No recent videos"

    view_ratio = influencer_data.get("view_ratio", 0)
    sub_count = max(int(influencer_data.get("subscriber_count", 0)), 1)

    prompt = f"""
You are an influencer marketing analyst. Score how well this YouTube channel fits the brand.

BRAND PROFILE:
- Name: {brand_profile['name']}
- Aggressiveness: {brand_profile['aggressive_score']}/10
- Creativity: {brand_profile['creative_score']}/10
- Humor: {brand_profile['humorous_score']}/10
- Professionalism: {brand_profile['professional_score']}/10
- Edginess: {brand_profile['edgy_score']}/10
- Target age: {brand_profile['target_age_min']}-{brand_profile['target_age_max']}

INFLUENCER METRICS:
- Channel: {influencer_data['title']}
- Subscribers: {sub_count:,}
- Total videos: {int(influencer_data.get('video_count', 0))}
- Lifetime views: {int(influencer_data.get('view_count', 0)):,}
- View/sub ratio: {view_ratio:.2f}% (healthy > 5%)
- Avg recent video views: {int(avg_views):,} ({(avg_views/sub_count*100):.1f}% of subs)
- Avg recent engagement: {avg_engagement:.2f}%

RECENT VIDEOS:
{video_samples}

Return ONLY valid JSON with this exact shape:
{{
  "overall_match_score": 0-100,
  "content_style_match": 0-100,
  "audience_match": 0-100,
  "engagement_quality": 0-100,
  "brand_safety": 0-100,
  "content_tone": "aggressive|friendly|professional|humorous|edgy",
  "top_themes": ["theme1", "theme2"],
  "ai_summary": "2-3 sentences in Turkish on fit and channel quality",
  "quality_flags": ["any of: low_view_ratio, dead_channel, good_engagement"]
}}
""".strip()

    try:
        # Offload the blocking (synchronous) Gemini SDK call to a worker thread so
        # the async event loop stays free during discovery's per-influencer loop.
        text = await asyncio.to_thread(_gemini_generate, prompt)
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        result = json.loads(text.strip())
    except json.JSONDecodeError as e:
        logger.warning("Gemini returned non-JSON output: %s", e)
        return unanalyzed_response("non-JSON response from AI")
    except Exception as e:
        logger.warning("Gemini analysis failed after retries: %s: %s", type(e).__name__, e)
        return unanalyzed_response(str(e)[:120])

    for key in ("overall_match_score", "content_style_match", "audience_match",
                "engagement_quality", "brand_safety"):
        if key not in result or not isinstance(result[key], (int, float)):
            return unanalyzed_response(f"missing/invalid field: {key}")
        result[key] = max(0.0, min(100.0, float(result[key])))

    original = result["overall_match_score"]
    capped = original
    override_reasons = []

    if view_ratio < 5.0:
        new_cap = 40.0
        if capped > new_cap:
            capped = new_cap
            override_reasons.append(f"view_ratio={view_ratio:.1f}% < 5% (low_view_ratio)")
    if avg_engagement < 2.0:
        new_cap = 50.0
        if capped > new_cap:
            capped = new_cap
            override_reasons.append(f"avg_engagement={avg_engagement:.2f}% < 2%")
    if avg_views > 0 and avg_views < sub_count * 0.03:
        new_cap = 30.0
        if capped > new_cap:
            capped = new_cap
            override_reasons.append("recent avg views < 3% of subs (dead_channel)")

    result["original_match_score"] = original
    result["overall_match_score"] = capped
    result["override_reason"] = "; ".join(override_reasons) if override_reasons else None
    result["status"] = "analyzed"
    result.setdefault("quality_flags", [])
    result.setdefault("top_themes", [])
    result.setdefault("content_tone", "unknown")
    result.setdefault("ai_summary", "")

    return result


def estimate_cpm_range(
    platform: str,
    follower_count: int,
    region: Optional[str],
) -> CPMBenchmark:
    """Single source of CPM truth. Replaces the old hardcoded tier dict."""
    tier = categorize_influencer(follower_count)
    return cpm_benchmark(platform, tier, region)


async def generate_campaign_strategy(brand_profile, top_influencers: List[Dict]) -> str:
    """Gemini-generated strategy paragraph. Best-effort; returns a fallback string on error."""
    if not GEMINI_API_KEY:
        return "Campaign strategy generation requires GEMINI_API_KEY."

    try:
        influencer_summary = "\n".join(
            f"- {inf['display_name']} ({inf['category']}): {inf['followers_count']:,} followers, "
            f"match {inf['overall_match_score']:.1f}%, tone: {inf['content_tone']}"
            for inf in top_influencers[:5]
        )
        prompt = f"""
Sen bir influencer marketing stratejistisin. Aşağıdaki bilgilere göre kampanya stratejisi öner.

MARKA: {brand_profile.name}
- Agresiflik: {brand_profile.aggressive_score}/10
- Yaratıcılık: {brand_profile.creative_score}/10
- Mizah: {brand_profile.humorous_score}/10
- Profesyonellik: {brand_profile.professional_score}/10

ÖNERİLEN INFLUENCER'LAR:
{influencer_summary}

Maksimum 400 kelime ile:
1. Kampanya stratejisi
2. İçerik formatı (video türü, süre, tone)
3. Yayın takvimi
4. Başarı metrikleri
5. Risk faktörleri

Türkçe, profesyonel bir dille yaz.
""".strip()
        return await asyncio.to_thread(_gemini_generate, prompt)
    except Exception as e:
        logger.warning("Strategy generation failed after retries: %s: %s", type(e).__name__, e)
        return f"Kampanya stratejisi oluşturulamadı: {str(e)[:100]}"
