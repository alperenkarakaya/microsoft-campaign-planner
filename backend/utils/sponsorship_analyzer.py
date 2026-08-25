"""
Sponsorship Authenticity analyzer (Phase 3).

Produces a sponsorship profile breakdown from Phase-1 sponsorship detection
signals plus LLM analysis of integration style and sentiment.

Architecture mirrors brand_matcher.py:
  1. Deterministic layer: cadence (maturity), repeat-sponsor detection (quality),
     saturation ratio — all from Phase-1 signals.
  2. LLM layer: integration style (native vs read-out) over video descriptions,
     and sponsored-vs-organic sentiment comparison.
  3. Every cap/floor/adjustment recorded in override_reason.

Failure rules (ai_detector.py pattern):
  - Missing inputs / LLM-down  => deterministic-only with lowered confidence.
  - NEVER fabricate a value.

Output shape (stored as InfluencerAnalysis.sponsorship_profile JSON):
  {
    "status": "analyzed" | "deterministic_only" | "unanalyzed",
    "maturity": { ... },
    "quality": { ... },
    "integration_style": { ... },
    "authenticity": { ... },
    "composite_sponsorship_score": float (0-100),
    "confidence": str,
    "source": str,
    "override_reason": str | None,
    "computed_at": str (ISO),
  }
"""

import asyncio
import json
import logging
import os
import re
from collections import Counter
from datetime import datetime, timezone
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

SOURCE = "Phase-1 sponsorship signals + Gemini integration/sentiment analysis"
SOURCE_DETERMINISTIC_ONLY = "Phase-1 sponsorship signals (LLM unavailable)"

# ---------------------------------------------------------------------------
# Gemini call (brand_matcher pattern)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Deterministic: Maturity
# ---------------------------------------------------------------------------

def _compute_maturity(
    signals: Dict[str, Any],
    videos: List[Dict],
) -> Dict[str, Any]:
    """Derive sponsorship maturity from Phase-1 sponsorship detection.

    Categories:
      - "unproven": no sponsorship signals detected
      - "emerging": 1-2 sponsored videos out of sample
      - "mature": healthy regular sponsorship (20-60% of videos)
      - "saturated": >60% sponsored — ad fatigue / trust erosion risk
    """
    spons = signals.get("sponsorship_detection") or {}
    total = spons.get("total_videos_checked", 0)
    sponsored_count = spons.get("videos_with_description_signals", 0)
    paid_placement_count = spons.get("videos_with_paid_placement_flag", 0)

    # Use the higher of description signals vs paid placement flag
    effective_sponsored = max(sponsored_count, paid_placement_count)

    if total == 0:
        return {
            "label": "unknown",
            "score": None,
            "sponsored_ratio": None,
            "sponsored_count": 0,
            "total_checked": 0,
            "reason": "no videos checked for sponsorship",
        }

    ratio = effective_sponsored / total

    if effective_sponsored == 0:
        label = "unproven"
        score = 30.0  # Not bad, just unproven
    elif ratio <= 0.15:
        label = "emerging"
        score = 50.0
    elif ratio <= 0.40:
        label = "mature"
        score = 80.0  # Sweet spot
    elif ratio <= 0.60:
        label = "mature"
        score = 65.0  # Starting to get heavy
    else:
        label = "saturated"
        score = 25.0  # Trust erosion risk

    return {
        "label": label,
        "score": score,
        "sponsored_ratio": round(ratio, 3),
        "sponsored_count": effective_sponsored,
        "total_checked": total,
        "reason": None,
    }


# ---------------------------------------------------------------------------
# Deterministic: Quality (repeat-sponsor + diversity)
# ---------------------------------------------------------------------------

# Common brand/sponsor domain patterns to extract from descriptions
_BRAND_PATTERNS = [
    # "use code BRAND" patterns
    re.compile(r"(?:use|with)\s+code\s+['\"]?(\w+)['\"]?", re.IGNORECASE),
    # "sponsored by BRAND" patterns
    re.compile(r"sponsored\s+by\s+(\w+)", re.IGNORECASE),
    # "thanks to BRAND" patterns
    re.compile(r"thanks\s+to\s+(\w+)\s+for", re.IGNORECASE),
    # Common affiliate domains
    re.compile(r"https?://(?:www\.)?(\w+\.(?:com|co|gg|io|tv))", re.IGNORECASE),
]


def _extract_sponsor_names(descriptions: List[str]) -> List[str]:
    """Best-effort extraction of sponsor/brand names from video descriptions."""
    names = []
    for desc in descriptions:
        if not desc:
            continue
        for pat in _BRAND_PATTERNS:
            matches = pat.findall(desc)
            for m in matches:
                name = m.strip().lower()
                # Filter out generic/noise words and self-promotion
                # domains that are NOT brand sponsors.
                if name and len(name) > 2 and name not in {
                    "the", "for", "and", "www", "com", "https",
                    "your", "our", "bit", "goo",
                    # Social platforms
                    "youtube.com", "youtu.be",
                    "twitter.com", "x.com",
                    "instagram.com", "facebook.com",
                    "tiktok.com", "threads.net", "bsky.app",
                    "tumblr.com",
                    # Video / streaming
                    "twitch.tv", "trovo.live", "kick.com",
                    # Community / messaging
                    "discord.com", "discord.gg", "discordapp.com",
                    "reddit.com",
                    # Donation / tipping
                    "patreon.com", "ko-fi.com",
                    "paypal.com", "paypal.me",
                    "cashapp.com", "venmo.com",
                    "streamlabs.com", "streamelements.com",
                    "throne.com",
                    # Link aggregators
                    "linktr.ee", "linktree.com",
                    # Merch / creator storefronts
                    "teespring.com", "redbubble.com", "spreadshop.com",
                    # Gaming storefronts
                    "steamcommunity.com", "store.steampowered.com",
                    # Art / portfolio
                    "deviantart.com",
                }:
                    names.append(name)
    return names


def _compute_quality(
    signals: Dict[str, Any],
    videos: List[Dict],
) -> Dict[str, Any]:
    """Detect repeat sponsors and sponsor diversity.

    Repeat sponsor = same brand/code/domain appears across 2+ videos.
    High diversity = many different sponsors (not locked into one).
    """
    spons = signals.get("sponsorship_detection") or {}
    hits = spons.get("hits", [])

    if not hits and not videos:
        return {
            "score": None,
            "repeat_sponsors": [],
            "unique_sponsors": 0,
            "sponsor_diversity": None,
            "reason": "no sponsorship data to analyze",
        }

    # Gather descriptions from sponsored videos
    sponsored_descriptions = []
    hit_video_ids = {h.get("video_id") for h in hits}
    for v in videos:
        vid = v.get("video_id", "")
        if vid in hit_video_ids or v.get("paid_product_placement"):
            sponsored_descriptions.append(v.get("description", ""))

    # Also check all video descriptions for brand references
    all_descriptions = [v.get("description", "") for v in videos]
    sponsor_names = _extract_sponsor_names(all_descriptions)

    if not sponsor_names:
        # No extractable sponsors — return deterministic baseline
        has_any_sponsorship = len(hits) > 0
        return {
            "score": 40.0 if has_any_sponsorship else None,
            "repeat_sponsors": [],
            "unique_sponsors": 0,
            "sponsor_diversity": None,
            "reason": "sponsorship detected but no sponsor names extractable",
        }

    counter = Counter(sponsor_names)
    repeat = [name for name, count in counter.items() if count >= 2]
    unique = len(set(sponsor_names))

    # Score: repeat sponsors are very positive (brand came back = it worked)
    points = 0.0
    max_pts = 100.0

    # Repeat sponsor bonus (0-50 points)
    if len(repeat) >= 3:
        points += 50.0
    elif len(repeat) >= 2:
        points += 40.0
    elif len(repeat) >= 1:
        points += 30.0
    else:
        points += 10.0

    # Diversity bonus (0-30 points)
    if unique >= 5:
        points += 30.0
    elif unique >= 3:
        points += 20.0
    elif unique >= 2:
        points += 12.0
    else:
        points += 5.0

    # Ratio of repeat to total (0-20 points) — moderate repeat is healthy
    repeat_ratio = len(repeat) / unique if unique > 0 else 0
    if 0.2 <= repeat_ratio <= 0.5:
        points += 20.0  # Sweet spot
    elif repeat_ratio > 0.5:
        points += 10.0  # Too concentrated
    else:
        points += 5.0

    score = round(min(points, max_pts), 1)

    return {
        "score": score,
        "repeat_sponsors": repeat[:10],
        "unique_sponsors": unique,
        "sponsor_diversity": round(unique / max(len(sponsor_names), 1), 3),
        "reason": None,
    }


# ---------------------------------------------------------------------------
# LLM: Integration style + Authenticity
# ---------------------------------------------------------------------------

def _build_sponsorship_prompt(
    sponsored_descriptions: List[str],
    organic_descriptions: List[str],
    sponsored_comments: Optional[List[Dict]] = None,
    organic_comments: Optional[List[Dict]] = None,
) -> str:
    """Build Gemini prompt for integration style and sentiment analysis."""
    sponsored_samples = "\n---\n".join(
        d[:500] for d in sponsored_descriptions[:5]
    ) or "(none available)"

    organic_samples = "\n---\n".join(
        d[:500] for d in organic_descriptions[:5]
    ) or "(none available)"

    # Comment samples if available
    sp_comments_text = ""
    org_comments_text = ""
    if sponsored_comments:
        sp_comments_text = "\n".join(
            f"- {c.get('text', '')[:150]}" for c in sponsored_comments[:15]
        )
    if organic_comments:
        org_comments_text = "\n".join(
            f"- {c.get('text', '')[:150]}" for c in organic_comments[:15]
        )

    comment_section = ""
    if sp_comments_text or org_comments_text:
        comment_section = f"""
COMMENTS ON SPONSORED VIDEOS:
{sp_comments_text or "(none available)"}

COMMENTS ON ORGANIC VIDEOS:
{org_comments_text or "(none available)"}
"""

    return f"""
You are analyzing a YouTube creator's sponsorship integration quality and audience reception.

SPONSORED VIDEO DESCRIPTIONS (up to 5):
{sponsored_samples}

ORGANIC (NON-SPONSORED) VIDEO DESCRIPTIONS (up to 5):
{organic_samples}
{comment_section}
Analyze and return ONLY valid JSON with this exact shape:
{{
  "integration_style": "native" | "read_out" | "mixed" | "unknown",
  "integration_quality_score": 0-100,
  "integration_notes": "1-2 sentences on how naturally sponsors are integrated",
  "sentiment_sponsored": -1.0 to 1.0,
  "sentiment_organic": -1.0 to 1.0,
  "sentiment_gap": -2.0 to 2.0,
  "audience_welcomes_sponsors": true | false | null,
  "authenticity_score": 0-100,
  "authenticity_notes": "1-2 sentences on whether fans seem to welcome or reject sponsorships"
}}

Definitions:
- integration_style: "native" means sponsor is woven into content naturally; "read_out" means clearly scripted ad segment; "mixed" means varies across videos
- integration_quality_score: 0-100 how well the creator integrates sponsors
- sentiment_sponsored: average audience sentiment on sponsored videos (-1 negative to +1 positive)
- sentiment_organic: average audience sentiment on organic videos
- sentiment_gap: sentiment_organic - sentiment_sponsored (positive = fans dislike sponsored content)
- audience_welcomes_sponsors: do fans seem to positively receive sponsored content?
- authenticity_score: 0-100 overall sponsorship authenticity
""".strip()


async def _llm_sponsorship_analysis(
    sponsored_descriptions: List[str],
    organic_descriptions: List[str],
    sponsored_comments: Optional[List[Dict]] = None,
    organic_comments: Optional[List[Dict]] = None,
) -> Optional[Dict[str, Any]]:
    """Run Gemini sponsorship analysis. Returns None on failure."""
    if not GEMINI_API_KEY:
        return None

    if not sponsored_descriptions and not organic_descriptions:
        return None

    prompt = _build_sponsorship_prompt(
        sponsored_descriptions,
        organic_descriptions,
        sponsored_comments,
        organic_comments,
    )

    try:
        text = await asyncio.to_thread(_gemini_generate, prompt)
        # Defensive JSON parse (brand_matcher pattern)
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        result = json.loads(text.strip())
    except json.JSONDecodeError as e:
        logger.warning("Sponsorship analyzer: Gemini returned non-JSON: %s", e)
        return None
    except Exception as e:
        logger.warning("Sponsorship analyzer: Gemini failed: %s: %s",
                       type(e).__name__, e)
        return None

    # Validate required fields
    for key in ("integration_quality_score", "authenticity_score"):
        if key not in result or not isinstance(result[key], (int, float)):
            logger.warning("Sponsorship analyzer: missing/invalid field: %s", key)
            return None

    # Clamp scores
    for key in ("integration_quality_score", "authenticity_score"):
        result[key] = max(0.0, min(100.0, float(result[key])))

    for key in ("sentiment_sponsored", "sentiment_organic"):
        if key in result and isinstance(result[key], (int, float)):
            result[key] = max(-1.0, min(1.0, float(result[key])))

    if "sentiment_gap" in result and isinstance(result["sentiment_gap"], (int, float)):
        result["sentiment_gap"] = max(-2.0, min(2.0, float(result["sentiment_gap"])))

    # Normalize integration_style
    valid_styles = {"native", "read_out", "mixed", "unknown"}
    if result.get("integration_style") not in valid_styles:
        result["integration_style"] = "unknown"

    return result


# ---------------------------------------------------------------------------
# Composite Sponsorship Score
# ---------------------------------------------------------------------------

def _classify_videos(
    signals: Dict[str, Any],
    videos: List[Dict],
) -> tuple:
    """Split videos into sponsored and organic based on Phase-1 signals.

    Returns (sponsored_videos, organic_videos).
    """
    spons = signals.get("sponsorship_detection") or {}
    hits = spons.get("hits", [])
    hit_ids = {h.get("video_id") for h in hits}

    sponsored = []
    organic = []
    for v in videos:
        vid = v.get("video_id", "")
        is_sponsored = (
            vid in hit_ids
            or v.get("paid_product_placement") is True
        )
        if is_sponsored:
            sponsored.append(v)
        else:
            organic.append(v)

    return sponsored, organic


def unanalyzed_sponsorship_response(reason: str) -> Dict[str, Any]:
    """Returned when sponsorship cannot be analyzed. Never fabricates."""
    return {
        "status": "unanalyzed",
        "maturity": None,
        "quality": None,
        "integration_style": None,
        "authenticity": None,
        "composite_sponsorship_score": None,
        "confidence": "low",
        "source": SOURCE_DETERMINISTIC_ONLY,
        "override_reason": f"unanalyzed: {reason}",
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }


async def compute_sponsorship_profile(
    signals: Dict[str, Any],
    videos: List[Dict],
    sponsored_comments: Optional[List[Dict]] = None,
    organic_comments: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
    """Compute the sponsorship profile breakdown.

    Args:
        signals: The enrichment_signals JSON blob from Phase 1.
        videos: List of recent video dicts (from youtube_discovery or cache).
        sponsored_comments: Optional comments from sponsored videos.
        organic_comments: Optional comments from organic videos.

    Returns:
        Sponsorship profile dict for InfluencerAnalysis.sponsorship_profile.
    """
    if not signals:
        return unanalyzed_sponsorship_response("no enrichment signals available")

    override_reasons: List[str] = []

    # --- Step 1: Deterministic layer ---
    maturity = _compute_maturity(signals, videos)
    quality = _compute_quality(signals, videos)

    if maturity.get("reason"):
        override_reasons.append(f"maturity: {maturity['reason']}")
    if quality.get("reason"):
        override_reasons.append(f"quality: {quality['reason']}")

    # --- Step 2: LLM layer (integration style + authenticity) ---
    sponsored_videos, organic_videos = _classify_videos(signals, videos)
    sponsored_descs = [v.get("description", "") for v in sponsored_videos]
    organic_descs = [v.get("description", "") for v in organic_videos]

    llm_result = await _llm_sponsorship_analysis(
        sponsored_descs,
        organic_descs,
        sponsored_comments,
        organic_comments,
    )

    # Integration style sub-score
    integration_style_data: Dict[str, Any]
    if llm_result is not None:
        # Set deterministic bounds on integration score
        det_floor = 20.0
        det_cap = 90.0

        # If maturity is "saturated", cap integration quality
        if maturity.get("label") == "saturated":
            det_cap = 60.0
            override_reasons.append(
                "integration_style: cap reduced to 60 due to saturation"
            )
        # If maturity is "unproven", floor integration quality
        if maturity.get("label") == "unproven":
            det_floor = 10.0

        llm_integration = llm_result.get("integration_quality_score", 50.0)
        if llm_integration > det_cap:
            override_reasons.append(
                f"integration_style: LLM score {llm_integration:.1f} "
                f"capped to {det_cap:.1f}"
            )
            llm_integration = det_cap
        elif llm_integration < det_floor:
            override_reasons.append(
                f"integration_style: LLM score {llm_integration:.1f} "
                f"floored to {det_floor:.1f}"
            )
            llm_integration = det_floor

        integration_style_data = {
            "style": llm_result.get("integration_style", "unknown"),
            "score": round(llm_integration, 1),
            "floor": det_floor,
            "cap": det_cap,
            "notes": llm_result.get("integration_notes", ""),
        }
    else:
        override_reasons.append("integration_style: LLM unavailable, scored as unknown")
        integration_style_data = {
            "style": "unknown",
            "score": None,
            "floor": None,
            "cap": None,
            "notes": "LLM unavailable for integration analysis",
        }

    # Authenticity sub-score
    authenticity_data: Dict[str, Any]
    if llm_result is not None:
        # Deterministic bounds on authenticity: maturity-based
        auth_floor = 15.0
        auth_cap = 95.0

        if maturity.get("label") == "saturated":
            auth_cap = 55.0
            override_reasons.append(
                "authenticity: cap reduced to 55 due to saturation"
            )

        llm_auth = llm_result.get("authenticity_score", 50.0)
        if llm_auth > auth_cap:
            override_reasons.append(
                f"authenticity: LLM score {llm_auth:.1f} capped to {auth_cap:.1f}"
            )
            llm_auth = auth_cap
        elif llm_auth < auth_floor:
            override_reasons.append(
                f"authenticity: LLM score {llm_auth:.1f} floored to {auth_floor:.1f}"
            )
            llm_auth = auth_floor

        authenticity_data = {
            "score": round(llm_auth, 1),
            "floor": auth_floor,
            "cap": auth_cap,
            "sentiment_sponsored": llm_result.get("sentiment_sponsored"),
            "sentiment_organic": llm_result.get("sentiment_organic"),
            "sentiment_gap": llm_result.get("sentiment_gap"),
            "audience_welcomes_sponsors": llm_result.get("audience_welcomes_sponsors"),
            "notes": llm_result.get("authenticity_notes", ""),
        }
    else:
        override_reasons.append("authenticity: LLM unavailable, no sentiment comparison")
        authenticity_data = {
            "score": None,
            "floor": None,
            "cap": None,
            "sentiment_sponsored": None,
            "sentiment_organic": None,
            "sentiment_gap": None,
            "audience_welcomes_sponsors": None,
            "notes": "LLM unavailable for authenticity analysis",
        }

    # --- Step 3: Composite score ---
    # Weights: maturity 25%, quality 25%, integration 25%, authenticity 25%
    available_scores = []
    weights = []

    if maturity.get("score") is not None:
        available_scores.append(maturity["score"])
        weights.append(0.25)
    if quality.get("score") is not None:
        available_scores.append(quality["score"])
        weights.append(0.25)
    if integration_style_data.get("score") is not None:
        available_scores.append(integration_style_data["score"])
        weights.append(0.25)
    if authenticity_data.get("score") is not None:
        available_scores.append(authenticity_data["score"])
        weights.append(0.25)

    if available_scores:
        total_weight = sum(weights)
        composite = sum(s * (w / total_weight)
                        for s, w in zip(available_scores, weights))
        composite = round(composite, 1)
    else:
        composite = None

    # Confidence
    has_det = maturity.get("score") is not None or quality.get("score") is not None
    has_llm = llm_result is not None
    n_scores = len(available_scores)

    if n_scores >= 3 and has_llm:
        confidence = "high"
    elif n_scores >= 2:
        confidence = "medium"
    elif n_scores >= 1:
        confidence = "low"
    else:
        confidence = "low"

    # Status
    if composite is None:
        status = "unanalyzed"
    elif llm_result is not None:
        status = "analyzed"
    else:
        status = "deterministic_only"

    source = SOURCE if llm_result else SOURCE_DETERMINISTIC_ONLY

    return {
        "status": status,
        "maturity": maturity,
        "quality": {
            "score": quality.get("score"),
            "repeat_sponsors": quality.get("repeat_sponsors", []),
            "unique_sponsors": quality.get("unique_sponsors", 0),
            "sponsor_diversity": quality.get("sponsor_diversity"),
        },
        "integration_style": integration_style_data,
        "authenticity": authenticity_data,
        "composite_sponsorship_score": composite,
        "confidence": confidence,
        "source": source,
        "override_reason": "; ".join(override_reasons) if override_reasons else None,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }
