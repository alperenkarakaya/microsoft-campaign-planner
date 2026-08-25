"""
Community Trust Depth + Authority scorer (Phase 2).

Produces a composite Trust sub-score breakdown that is INDEPENDENT of follower
size.  The architecture mirrors brand_matcher.py:

  1. Deterministic layer sets floor/cap from Phase-1 signals (comment/like-to-view
     depth, view consistency/variance, creator reply-rate).
  2. LLM (Gemini) adjusts WITHIN bounds — judges comment authenticity (spam/emoji-
     only/duplicate ratio, substance, sentiment) and parasocial bond (past-video
     references, questions, loyalty markers).
  3. Every cap/floor/adjustment is recorded in an `override_reason` audit string.

Failure rules (ai_detector.py pattern):
  - Missing inputs  → deterministic-only result with lowered confidence.
  - LLM down        → deterministic-only result with lowered confidence.
  - NEVER fabricate  → None / "unknown" on total failure, never a synthetic number.

Output shape (stored as InfluencerAnalysis.trust_breakdown JSON):
  {
    "status": "analyzed" | "deterministic_only" | "unanalyzed",
    "community_trust_depth": { ... sub-score with range + source },
    "authority": { ... sub-score with range + source },
    "composite_trust_score": float (0-100),
    "confidence": "high" | "medium" | "low",
    "source": str,
    "override_reason": str | None,
    "computed_at": str (ISO timestamp),
  }
"""

import asyncio
import json
import logging
import os
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

SOURCE = "Phase-1 deterministic signals + Gemini comment-quality analysis"
SOURCE_DETERMINISTIC_ONLY = "Phase-1 deterministic signals (LLM unavailable)"

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
# Deterministic scoring helpers
# ---------------------------------------------------------------------------

def _deterministic_community_trust(
    signals: Dict[str, Any],
) -> Dict[str, Any]:
    """Compute community trust depth from Phase-1 deterministic signals.

    Returns a dict with:
      - score: float 0-100 (deterministic baseline)
      - floor: float — minimum the composite may take
      - cap: float — maximum the composite may take
      - components: dict of individual signal contributions
      - reasons: list of adjustment reasons
    """
    components = {}
    reasons: List[str] = []
    points = 0.0
    max_points = 0.0

    # --- Like-to-view depth (weight: 30 points) ---
    engagement = signals.get("engagement_depth") or {}
    ltv = engagement.get("like_to_view_ratio")
    if ltv is not None:
        max_points += 30
        # YouTube healthy range: 3-7% like/view
        if ltv >= 0.07:
            pts = 30.0
        elif ltv >= 0.04:
            pts = 22.0
        elif ltv >= 0.02:
            pts = 15.0
        elif ltv >= 0.01:
            pts = 8.0
        else:
            pts = 3.0
        points += pts
        components["like_to_view"] = {"value": ltv, "points": pts, "max": 30}
    else:
        components["like_to_view"] = {"value": None, "points": 0, "max": 0}
        reasons.append("like_to_view_ratio unavailable")

    # --- Comment-to-view depth (weight: 20 points) ---
    ctv = engagement.get("comment_to_view_ratio")
    if ctv is not None:
        max_points += 20
        # YouTube healthy range: 0.3-1% comment/view
        if ctv >= 0.01:
            pts = 20.0
        elif ctv >= 0.005:
            pts = 14.0
        elif ctv >= 0.002:
            pts = 8.0
        elif ctv >= 0.001:
            pts = 4.0
        else:
            pts = 1.0
        points += pts
        components["comment_to_view"] = {"value": ctv, "points": pts, "max": 20}
    else:
        components["comment_to_view"] = {"value": None, "points": 0, "max": 0}
        reasons.append("comment_to_view_ratio unavailable")

    # --- View consistency / low variance (weight: 30 points) ---
    vc = signals.get("view_consistency") or {}
    cv = vc.get("recent_view_cv")
    if cv is not None:
        max_points += 30
        # Lower CV = more consistent = more loyal audience
        if cv <= 0.15:
            pts = 30.0
        elif cv <= 0.30:
            pts = 24.0
        elif cv <= 0.50:
            pts = 16.0
        elif cv <= 0.80:
            pts = 8.0
        else:
            pts = 3.0
        points += pts
        components["view_consistency"] = {"cv": cv, "points": pts, "max": 30}
    else:
        components["view_consistency"] = {"cv": None, "points": 0, "max": 0}
        reasons.append("view_consistency_cv unavailable")

    # --- Sample size penalty (weight: 20 points) ---
    sample_size = engagement.get("sample_size", 0)
    vc_sample = vc.get("sample_size", 0)
    effective_sample = min(sample_size, vc_sample) if sample_size and vc_sample else max(sample_size, vc_sample)
    if effective_sample > 0:
        max_points += 20
        if effective_sample >= 8:
            pts = 20.0
        elif effective_sample >= 5:
            pts = 14.0
        elif effective_sample >= 3:
            pts = 8.0
        else:
            pts = 4.0
        points += pts
        components["sample_size"] = {"value": effective_sample, "points": pts, "max": 20}
    else:
        components["sample_size"] = {"value": 0, "points": 0, "max": 0}
        reasons.append("no video samples available")

    # Normalize to 0-100 scale
    if max_points > 0:
        score = round((points / max_points) * 100, 1)
    else:
        score = None

    # Floor and cap for the LLM adjustment.
    # The deterministic score sets a +-20 band around itself.
    if score is not None:
        floor = max(0.0, score - 20.0)
        cap = min(100.0, score + 20.0)
    else:
        floor = 0.0
        cap = 100.0

    return {
        "score": score,
        "floor": floor,
        "cap": cap,
        "components": components,
        "reasons": reasons,
    }


def _deterministic_authority(
    signals: Dict[str, Any],
) -> Dict[str, Any]:
    """Compute authority / parasocial bond from deterministic signals.

    Signals and weights (summing to 100 points):
      - Reply rate: 35 pts — rewards engagement but doesn't dominate.
      - Reply sample size: 10 pts — proportional to reply weight.
      - Comment depth (comment_to_view_ratio): 30 pts — community engagement.
      - View ratio (median_recent_views / subscriber_count): 25 pts — does the
        audience actually watch?
    """
    components = {}
    reasons: List[str] = []
    points = 0.0
    max_points = 0.0

    reply_data = signals.get("creator_reply_rate")
    if reply_data is not None and isinstance(reply_data, dict):
        reply_rate = reply_data.get("reply_rate")
        if reply_rate is not None:
            max_points += 35
            # Reply rates: >20% is outstanding, 5-20% is good, <5% is low
            if reply_rate >= 0.20:
                pts = 35.0
            elif reply_rate >= 0.10:
                pts = 26.0
            elif reply_rate >= 0.05:
                pts = 18.0
            elif reply_rate >= 0.02:
                pts = 9.0
            else:
                pts = 3.0
            points += pts
            components["reply_rate"] = {"value": reply_rate, "points": pts, "max": 35}

            # Bonus for sufficient sample size
            threads = reply_data.get("total_threads_sampled", 0)
            max_points += 10
            if threads >= 50:
                pts2 = 10.0
            elif threads >= 20:
                pts2 = 7.0
            elif threads >= 10:
                pts2 = 4.0
            else:
                pts2 = 2.0
            points += pts2
            components["reply_sample_size"] = {"value": threads, "points": pts2, "max": 10}
        else:
            components["reply_rate"] = {"value": None, "points": 0, "max": 0}
            reasons.append("reply_rate value missing in reply data")
    else:
        components["reply_rate"] = {"value": None, "points": 0, "max": 0}
        components["reply_sample_size"] = {"value": 0, "points": 0, "max": 0}
        reasons.append("creator_reply_rate unavailable (comments disabled or quota)")

    # Comment-to-view depth also contributes to authority (community engagement)
    engagement = signals.get("engagement_depth") or {}
    ctv = engagement.get("comment_to_view_ratio")
    if ctv is not None:
        max_points += 30
        if ctv >= 0.01:
            pts = 30.0
        elif ctv >= 0.005:
            pts = 21.0
        elif ctv >= 0.002:
            pts = 12.0
        else:
            pts = 4.0
        points += pts
        components["comment_depth_authority"] = {"value": ctv, "points": pts, "max": 30}
    else:
        components["comment_depth_authority"] = {"value": None, "points": 0, "max": 0}

    # View ratio: median_recent_views / subscriber_count — measures whether
    # the audience actually watches, independent of reply behavior.
    vc = signals.get("view_consistency") or {}
    recent_view_median = vc.get("recent_view_median")
    subscriber_count = signals.get("subscriber_count")
    if recent_view_median is not None and subscriber_count and subscriber_count > 0:
        view_ratio = recent_view_median / subscriber_count
        max_points += 25
        if view_ratio >= 0.15:
            pts = 25.0
        elif view_ratio >= 0.10:
            pts = 20.0
        elif view_ratio >= 0.05:
            pts = 14.0
        elif view_ratio >= 0.03:
            pts = 8.0
        else:
            pts = 3.0
        points += pts
        components["view_ratio"] = {
            "value": round(view_ratio, 4),
            "points": pts,
            "max": 25,
        }
    else:
        components["view_ratio"] = {"value": None, "points": 0, "max": 0}
        if subscriber_count is None or subscriber_count == 0:
            reasons.append("subscriber_count unavailable for view_ratio")
        elif recent_view_median is None:
            reasons.append("recent_view_median unavailable for view_ratio")

    if max_points > 0:
        score = round((points / max_points) * 100, 1)
    else:
        score = None

    if score is not None:
        floor = max(0.0, score - 20.0)
        cap = min(100.0, score + 20.0)
    else:
        floor = 0.0
        cap = 100.0

    return {
        "score": score,
        "floor": floor,
        "cap": cap,
        "components": components,
        "reasons": reasons,
    }


# ---------------------------------------------------------------------------
# LLM comment quality analysis
# ---------------------------------------------------------------------------

def _build_comment_quality_prompt(comments: List[Dict]) -> str:
    """Build a Gemini prompt for comment authenticity + parasocial analysis."""
    # Sample up to 30 comments for cost efficiency
    sampled = comments[:30]
    comment_text = "\n".join(
        f"- [{c.get('author', 'anon')}]: {c.get('text', '')[:200]}"
        for c in sampled
    )

    return f"""
You are analyzing YouTube comments for community trust signals. Evaluate these comments from a creator's recent videos.

COMMENTS ({len(sampled)} sampled):
{comment_text}

Analyze and return ONLY valid JSON with this exact shape:
{{
  "spam_ratio": 0.0-1.0,
  "emoji_only_ratio": 0.0-1.0,
  "duplicate_ratio": 0.0-1.0,
  "substantive_ratio": 0.0-1.0,
  "avg_sentiment": -1.0 to 1.0,
  "comment_authenticity_score": 0-100,
  "past_video_references": 0-100,
  "questions_asked": 0-100,
  "loyalty_markers": 0-100,
  "parasocial_bond_score": 0-100,
  "analysis_notes": "1-2 sentences on community quality"
}}

Definitions:
- spam_ratio: fraction of comments that are spam/bot-like
- emoji_only_ratio: fraction that are just emojis with no substance
- duplicate_ratio: fraction that are near-duplicates of each other
- substantive_ratio: fraction with genuine, thoughtful engagement
- avg_sentiment: overall sentiment (-1 negative, 0 neutral, +1 positive)
- comment_authenticity_score: 0-100 overall authenticity of the comment section
- past_video_references: 0-100 how much commenters reference creator's past content
- questions_asked: 0-100 how often commenters ask genuine questions to the creator
- loyalty_markers: 0-100 signs of returning viewers (e.g., "been watching since...", "as always")
- parasocial_bond_score: 0-100 overall strength of the creator-audience bond
""".strip()


async def _llm_comment_analysis(
    comments: List[Dict],
) -> Optional[Dict[str, Any]]:
    """Run Gemini comment quality analysis. Returns None on failure."""
    if not GEMINI_API_KEY:
        return None

    if not comments:
        return None

    prompt = _build_comment_quality_prompt(comments)

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
        logger.warning("Trust scorer: Gemini returned non-JSON: %s", e)
        return None
    except Exception as e:
        logger.warning("Trust scorer: Gemini failed after retries: %s: %s",
                       type(e).__name__, e)
        return None

    # Validate required fields
    required_numeric = [
        "comment_authenticity_score", "parasocial_bond_score",
        "spam_ratio", "substantive_ratio",
    ]
    for key in required_numeric:
        if key not in result or not isinstance(result[key], (int, float)):
            logger.warning("Trust scorer: missing/invalid LLM field: %s", key)
            return None

    # Clamp scores
    for key in ("comment_authenticity_score", "parasocial_bond_score",
                "past_video_references", "questions_asked", "loyalty_markers"):
        if key in result and isinstance(result[key], (int, float)):
            result[key] = max(0.0, min(100.0, float(result[key])))

    for key in ("spam_ratio", "emoji_only_ratio", "duplicate_ratio", "substantive_ratio"):
        if key in result and isinstance(result[key], (int, float)):
            result[key] = max(0.0, min(1.0, float(result[key])))

    if "avg_sentiment" in result and isinstance(result["avg_sentiment"], (int, float)):
        result["avg_sentiment"] = max(-1.0, min(1.0, float(result["avg_sentiment"])))

    return result


# ---------------------------------------------------------------------------
# Composite Trust Score
# ---------------------------------------------------------------------------

def _compute_confidence(
    det_community: Dict,
    det_authority: Dict,
    llm_result: Optional[Dict],
) -> str:
    """Determine confidence tier based on data availability."""
    has_community = det_community["score"] is not None
    has_authority = det_authority["score"] is not None
    has_llm = llm_result is not None

    if has_community and has_authority and has_llm:
        return "high"
    elif has_community and (has_authority or has_llm):
        return "medium"
    else:
        return "low"


def unanalyzed_trust_response(reason: str) -> Dict[str, Any]:
    """Returned when trust cannot be computed at all. Never fabricates."""
    return {
        "status": "unanalyzed",
        "community_trust_depth": None,
        "authority": None,
        "composite_trust_score": None,
        "confidence": "low",
        "source": SOURCE_DETERMINISTIC_ONLY,
        "override_reason": f"unanalyzed: {reason}",
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }


async def compute_trust_score(
    signals: Dict[str, Any],
    comments: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
    """Compute the composite Trust sub-score breakdown.

    Args:
        signals: The enrichment_signals JSON blob from Phase 1
                 (Influencer.enrichment_signals).
        comments: Optional list of comment dicts with 'author' and 'text' keys.
                  When None or empty, the LLM layer is skipped and confidence
                  is lowered.

    Returns:
        Trust breakdown dict suitable for InfluencerAnalysis.trust_breakdown.
    """
    if not signals:
        return unanalyzed_trust_response("no enrichment signals available")

    # --- Step 1: Deterministic layer ---
    det_community = _deterministic_community_trust(signals)
    det_authority = _deterministic_authority(signals)

    override_reasons: List[str] = []
    override_reasons.extend(det_community["reasons"])
    override_reasons.extend(det_authority["reasons"])

    # --- Step 2: LLM adjustment (within deterministic bounds) ---
    llm_result = None
    if comments:
        llm_result = await _llm_comment_analysis(comments)

    community_score = det_community["score"]
    authority_score = det_authority["score"]

    if llm_result is not None:
        # LLM adjusts community trust WITHIN deterministic bounds
        llm_authenticity = llm_result.get("comment_authenticity_score", 50.0)
        if community_score is not None:
            adjusted_community = (community_score * 0.6) + (llm_authenticity * 0.4)
            # Cap/floor enforcement
            if adjusted_community > det_community["cap"]:
                override_reasons.append(
                    f"community_trust: LLM-adjusted {adjusted_community:.1f} "
                    f"capped to {det_community['cap']:.1f}"
                )
                adjusted_community = det_community["cap"]
            elif adjusted_community < det_community["floor"]:
                override_reasons.append(
                    f"community_trust: LLM-adjusted {adjusted_community:.1f} "
                    f"floored to {det_community['floor']:.1f}"
                )
                adjusted_community = det_community["floor"]
            else:
                override_reasons.append(
                    f"community_trust: LLM-adjusted from {community_score:.1f} "
                    f"to {adjusted_community:.1f} (within [{det_community['floor']:.1f}, "
                    f"{det_community['cap']:.1f}])"
                )
            community_score = round(adjusted_community, 1)
        else:
            # No deterministic baseline — LLM provides initial estimate but
            # with conservative bounds (30-70) since we have no grounding
            community_score = max(30.0, min(70.0, llm_authenticity))
            override_reasons.append(
                f"community_trust: no deterministic baseline; LLM-only "
                f"clamped to [30, 70] = {community_score:.1f}"
            )

        # LLM adjusts authority WITHIN deterministic bounds
        llm_parasocial = llm_result.get("parasocial_bond_score", 50.0)
        if authority_score is not None:
            adjusted_authority = (authority_score * 0.6) + (llm_parasocial * 0.4)
            if adjusted_authority > det_authority["cap"]:
                override_reasons.append(
                    f"authority: LLM-adjusted {adjusted_authority:.1f} "
                    f"capped to {det_authority['cap']:.1f}"
                )
                adjusted_authority = det_authority["cap"]
            elif adjusted_authority < det_authority["floor"]:
                override_reasons.append(
                    f"authority: LLM-adjusted {adjusted_authority:.1f} "
                    f"floored to {det_authority['floor']:.1f}"
                )
                adjusted_authority = det_authority["floor"]
            else:
                override_reasons.append(
                    f"authority: LLM-adjusted from {authority_score:.1f} "
                    f"to {adjusted_authority:.1f} (within [{det_authority['floor']:.1f}, "
                    f"{det_authority['cap']:.1f}])"
                )
            authority_score = round(adjusted_authority, 1)
        else:
            authority_score = max(30.0, min(70.0, llm_parasocial))
            override_reasons.append(
                f"authority: no deterministic baseline; LLM-only "
                f"clamped to [30, 70] = {authority_score:.1f}"
            )
    else:
        if comments is not None and len(comments) == 0:
            override_reasons.append("LLM skipped: no comments provided")
        elif comments is None:
            override_reasons.append("LLM skipped: comments not fetched")
        else:
            override_reasons.append("LLM failed: using deterministic-only scores")

    # --- Step 3: Composite score ---
    # Community Trust Depth is the FOUNDATION (weight 65%), Authority is 35%
    available_scores = []
    weights = []
    if community_score is not None:
        available_scores.append(community_score)
        weights.append(0.65)
    if authority_score is not None:
        available_scores.append(authority_score)
        weights.append(0.35)

    if available_scores:
        # Normalize weights to sum to 1.0
        total_weight = sum(weights)
        composite = sum(s * (w / total_weight)
                        for s, w in zip(available_scores, weights))
        composite = round(composite, 1)
    else:
        composite = None

    confidence = _compute_confidence(det_community, det_authority, llm_result)

    # Determine status
    if composite is None:
        status = "unanalyzed"
    elif llm_result is not None:
        status = "analyzed"
    else:
        status = "deterministic_only"

    source = SOURCE if llm_result else SOURCE_DETERMINISTIC_ONLY

    return {
        "status": status,
        "community_trust_depth": {
            "score": community_score,
            "deterministic_baseline": det_community["score"],
            "floor": det_community["floor"],
            "cap": det_community["cap"],
            "components": det_community["components"],
            "llm_comment_authenticity": (
                llm_result.get("comment_authenticity_score") if llm_result else None
            ),
            "llm_spam_ratio": (
                llm_result.get("spam_ratio") if llm_result else None
            ),
            "llm_substantive_ratio": (
                llm_result.get("substantive_ratio") if llm_result else None
            ),
        },
        "authority": {
            "score": authority_score,
            "deterministic_baseline": det_authority["score"],
            "floor": det_authority["floor"],
            "cap": det_authority["cap"],
            "components": det_authority["components"],
            "llm_parasocial_bond": (
                llm_result.get("parasocial_bond_score") if llm_result else None
            ),
            "llm_past_video_references": (
                llm_result.get("past_video_references") if llm_result else None
            ),
            "llm_loyalty_markers": (
                llm_result.get("loyalty_markers") if llm_result else None
            ),
        },
        "composite_trust_score": composite,
        "confidence": confidence,
        "source": source,
        "override_reason": "; ".join(override_reasons) if override_reasons else None,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }
