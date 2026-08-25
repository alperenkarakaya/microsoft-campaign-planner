"""Tests for the Community Trust Depth + Authority scorer — fully offline.

Gemini is mocked so tests never hit the network. Tests verify:
  (a) deterministic floors/caps hold,
  (b) LLM-down path returns a valid deterministic-only result with lowered confidence,
  (c) override_reason is populated when an adjustment happens,
  (d) no fabricated numbers on failure.
"""

import json
from unittest.mock import patch, MagicMock

import pytest

from utils.trust_scorer import (
    _deterministic_community_trust,
    _deterministic_authority,
    compute_trust_score,
    unanalyzed_trust_response,
)


# ---------------------------------------------------------------------------
# Fixtures: synthetic Phase-1 signal blobs
# ---------------------------------------------------------------------------

def _healthy_signals():
    """A well-performing channel with strong engagement."""
    return {
        "subscriber_count": 100_000,
        "engagement_depth": {
            "like_to_view_ratio": 0.05,
            "comment_to_view_ratio": 0.008,
            "sample_size": 10,
        },
        "view_consistency": {
            "recent_view_cv": 0.20,
            "recent_view_median": 50000,
            "sample_size": 10,
        },
        "creator_reply_rate": {
            "reply_rate": 0.15,
            "total_threads_sampled": 40,
            "creator_replies_found": 6,
            "videos_sampled": 5,
        },
    }


def _weak_signals():
    """A channel with weak engagement indicators."""
    return {
        "subscriber_count": 200_000,
        "engagement_depth": {
            "like_to_view_ratio": 0.008,
            "comment_to_view_ratio": 0.0008,
            "sample_size": 3,
        },
        "view_consistency": {
            "recent_view_cv": 1.2,
            "recent_view_median": 5000,
            "sample_size": 3,
        },
        "creator_reply_rate": {
            "reply_rate": 0.01,
            "total_threads_sampled": 15,
            "creator_replies_found": 0,
            "videos_sampled": 3,
        },
    }


def _minimal_signals():
    """Only view consistency available — everything else missing."""
    return {
        "subscriber_count": 50_000,
        "engagement_depth": {
            "like_to_view_ratio": None,
            "comment_to_view_ratio": None,
            "sample_size": 0,
        },
        "view_consistency": {
            "recent_view_cv": 0.30,
            "recent_view_median": 20000,
            "sample_size": 5,
        },
        "creator_reply_rate": None,
    }


def _sample_comments():
    return [
        {"author": "FanA", "text": "Great video as always! Been watching since 2020."},
        {"author": "FanB", "text": "Can you do a follow-up on the topic from last week?"},
        {"author": "FanC", "text": "Nice"},
        {"author": "FanD", "text": "First!"},
        {"author": "FanE", "text": "This reminded me of your old series. Loved it!"},
    ]


_MOCK_LLM_RESPONSE = json.dumps({
    "spam_ratio": 0.1,
    "emoji_only_ratio": 0.05,
    "duplicate_ratio": 0.02,
    "substantive_ratio": 0.7,
    "avg_sentiment": 0.6,
    "comment_authenticity_score": 75,
    "past_video_references": 60,
    "questions_asked": 40,
    "loyalty_markers": 55,
    "parasocial_bond_score": 65,
    "analysis_notes": "Good community engagement with loyal viewers.",
})


# ---------------------------------------------------------------------------
# Deterministic community trust
# ---------------------------------------------------------------------------

class TestDeterministicCommunityTrust:
    def test_healthy_channel_scores_high(self):
        result = _deterministic_community_trust(_healthy_signals())
        assert result["score"] is not None
        assert result["score"] >= 60  # strong engagement should score well
        assert result["floor"] < result["score"]
        assert result["cap"] > result["score"]

    def test_weak_channel_scores_low(self):
        result = _deterministic_community_trust(_weak_signals())
        assert result["score"] is not None
        assert result["score"] < 40

    def test_missing_data_returns_partial(self):
        result = _deterministic_community_trust(_minimal_signals())
        assert result["score"] is not None  # Still computes from available data
        assert "like_to_view_ratio unavailable" in result["reasons"]
        assert "comment_to_view_ratio unavailable" in result["reasons"]

    def test_empty_signals(self):
        result = _deterministic_community_trust({})
        # No signals at all — score should be None
        assert result["score"] is None

    def test_floor_cap_bounds(self):
        result = _deterministic_community_trust(_healthy_signals())
        if result["score"] is not None:
            assert result["floor"] >= 0.0
            assert result["cap"] <= 100.0
            assert result["floor"] <= result["score"]
            assert result["cap"] >= result["score"]


# ---------------------------------------------------------------------------
# Deterministic authority
# ---------------------------------------------------------------------------

class TestDeterministicAuthority:
    def test_good_reply_rate(self):
        result = _deterministic_authority(_healthy_signals())
        assert result["score"] is not None
        assert result["score"] >= 50

    def test_no_reply_data(self):
        result = _deterministic_authority(_minimal_signals())
        assert any("creator_reply_rate unavailable" in r for r in result["reasons"])

    def test_low_reply_rate(self):
        result = _deterministic_authority(_weak_signals())
        assert result["score"] is not None
        assert result["score"] < 50

    def test_floor_cap_bounds(self):
        result = _deterministic_authority(_healthy_signals())
        if result["score"] is not None:
            assert result["floor"] >= 0.0
            assert result["cap"] <= 100.0

    def test_band_width_is_20(self):
        """Authority band is now +/-20, matching community trust."""
        result = _deterministic_authority(_healthy_signals())
        if result["score"] is not None:
            expected_floor = max(0.0, result["score"] - 20.0)
            expected_cap = min(100.0, result["score"] + 20.0)
            assert result["floor"] == expected_floor
            assert result["cap"] == expected_cap

    def test_zero_reply_rate_high_view_ratio_scores_above_50(self):
        """A creator with 0% reply rate but high view ratio and comment
        depth should score >= 50 authority (not the old ~28)."""
        signals = {
            "subscriber_count": 100_000,
            "engagement_depth": {
                "like_to_view_ratio": 0.06,
                "comment_to_view_ratio": 0.012,
                "sample_size": 10,
            },
            "view_consistency": {
                "recent_view_cv": 0.20,
                "recent_view_median": 20_000,  # 20% view ratio
                "sample_size": 10,
            },
            "creator_reply_rate": {
                "reply_rate": 0.0,
                "total_threads_sampled": 50,
                "creator_replies_found": 0,
                "videos_sampled": 5,
            },
        }
        result = _deterministic_authority(signals)
        assert result["score"] is not None
        assert result["score"] >= 50, (
            f"Creator with 0% reply rate but strong view_ratio + comment "
            f"depth scored {result['score']}, expected >= 50"
        )

    def test_moderate_reply_rate_no_regression(self):
        """A creator with 20% reply rate should still score well."""
        signals = {
            "subscriber_count": 100_000,
            "engagement_depth": {
                "like_to_view_ratio": 0.05,
                "comment_to_view_ratio": 0.008,
                "sample_size": 10,
            },
            "view_consistency": {
                "recent_view_cv": 0.25,
                "recent_view_median": 15_000,
                "sample_size": 10,
            },
            "creator_reply_rate": {
                "reply_rate": 0.20,
                "total_threads_sampled": 40,
                "creator_replies_found": 8,
                "videos_sampled": 5,
            },
        }
        result = _deterministic_authority(signals)
        assert result["score"] is not None
        assert result["score"] >= 70, (
            f"Creator with 20% reply rate scored {result['score']}, expected >= 70"
        )

    def test_view_ratio_thresholds(self):
        """Verify the view_ratio component at each threshold boundary."""
        base = {
            "engagement_depth": {
                "like_to_view_ratio": 0.05,
                "comment_to_view_ratio": 0.008,
                "sample_size": 10,
            },
            "creator_reply_rate": None,
        }

        def _make(median, subs):
            s = dict(base)
            s["subscriber_count"] = subs
            s["view_consistency"] = {
                "recent_view_cv": 0.20,
                "recent_view_median": median,
                "sample_size": 10,
            }
            return s

        # 20% view ratio -> 25 pts
        r1 = _deterministic_authority(_make(20_000, 100_000))
        assert r1["components"]["view_ratio"]["points"] == 25.0

        # 12% view ratio -> 20 pts
        r2 = _deterministic_authority(_make(12_000, 100_000))
        assert r2["components"]["view_ratio"]["points"] == 20.0

        # 7% view ratio -> 14 pts
        r3 = _deterministic_authority(_make(7_000, 100_000))
        assert r3["components"]["view_ratio"]["points"] == 14.0

        # 4% view ratio -> 8 pts
        r4 = _deterministic_authority(_make(4_000, 100_000))
        assert r4["components"]["view_ratio"]["points"] == 8.0

        # 1% view ratio -> 3 pts
        r5 = _deterministic_authority(_make(1_000, 100_000))
        assert r5["components"]["view_ratio"]["points"] == 3.0


# ---------------------------------------------------------------------------
# Full compute_trust_score — LLM mocked
# ---------------------------------------------------------------------------

class TestComputeTrustScoreWithLLM:
    @pytest.mark.asyncio
    async def test_full_analysis_with_llm(self):
        with patch("utils.trust_scorer.GEMINI_API_KEY", "fake-key"), \
             patch("utils.trust_scorer._gemini_generate", return_value=_MOCK_LLM_RESPONSE):
            result = await compute_trust_score(
                signals=_healthy_signals(),
                comments=_sample_comments(),
            )

        assert result["status"] == "analyzed"
        assert result["composite_trust_score"] is not None
        assert 0 <= result["composite_trust_score"] <= 100
        assert result["confidence"] == "high"
        assert result["override_reason"] is not None  # LLM adjustments recorded
        assert result["community_trust_depth"]["llm_comment_authenticity"] == 75
        assert result["authority"]["llm_parasocial_bond"] == 65

    @pytest.mark.asyncio
    async def test_llm_adjustment_within_bounds(self):
        """LLM score must be capped/floored by deterministic bounds."""
        # Create a response where LLM gives an extreme score
        extreme_llm = json.dumps({
            "spam_ratio": 0.0,
            "emoji_only_ratio": 0.0,
            "duplicate_ratio": 0.0,
            "substantive_ratio": 1.0,
            "avg_sentiment": 1.0,
            "comment_authenticity_score": 100,  # Extreme high
            "past_video_references": 100,
            "questions_asked": 100,
            "loyalty_markers": 100,
            "parasocial_bond_score": 100,  # Extreme high
            "analysis_notes": "Perfect community.",
        })

        with patch("utils.trust_scorer.GEMINI_API_KEY", "fake-key"), \
             patch("utils.trust_scorer._gemini_generate", return_value=extreme_llm):
            result = await compute_trust_score(
                signals=_healthy_signals(),
                comments=_sample_comments(),
            )

        community = result["community_trust_depth"]
        authority = result["authority"]

        # Verify the LLM-adjusted score is within deterministic bounds
        assert community["score"] <= community["cap"]
        assert community["score"] >= community["floor"]
        assert authority["score"] <= authority["cap"]
        assert authority["score"] >= authority["floor"]

        # Override reason should mention capping
        assert "capped" in result["override_reason"] or "within" in result["override_reason"]

    @pytest.mark.asyncio
    async def test_llm_floor_enforcement(self):
        """LLM gives very low score — floored by deterministic layer."""
        low_llm = json.dumps({
            "spam_ratio": 0.9,
            "emoji_only_ratio": 0.5,
            "duplicate_ratio": 0.8,
            "substantive_ratio": 0.0,
            "avg_sentiment": -1.0,
            "comment_authenticity_score": 0,  # Very low
            "past_video_references": 0,
            "questions_asked": 0,
            "loyalty_markers": 0,
            "parasocial_bond_score": 0,  # Very low
            "analysis_notes": "All spam.",
        })

        with patch("utils.trust_scorer.GEMINI_API_KEY", "fake-key"), \
             patch("utils.trust_scorer._gemini_generate", return_value=low_llm):
            result = await compute_trust_score(
                signals=_healthy_signals(),
                comments=_sample_comments(),
            )

        community = result["community_trust_depth"]
        authority = result["authority"]

        # Must be at or above the floor
        assert community["score"] >= community["floor"]
        assert authority["score"] >= authority["floor"]

        # Override reason mentions flooring
        assert "floored" in result["override_reason"]


# ---------------------------------------------------------------------------
# LLM-down / no-key paths
# ---------------------------------------------------------------------------

class TestComputeTrustScoreLLMDown:
    @pytest.mark.asyncio
    async def test_no_api_key_deterministic_only(self):
        """Without GEMINI_API_KEY, returns deterministic-only result."""
        with patch("utils.trust_scorer.GEMINI_API_KEY", ""):
            result = await compute_trust_score(
                signals=_healthy_signals(),
                comments=_sample_comments(),
            )

        assert result["status"] == "deterministic_only"
        assert result["composite_trust_score"] is not None
        # Confidence should NOT be "high" without LLM
        assert result["confidence"] in ("medium", "low")
        assert result["source"] == "Phase-1 deterministic signals (LLM unavailable)"

    @pytest.mark.asyncio
    async def test_llm_exception_degrades_gracefully(self):
        """Gemini raises an exception — deterministic-only result."""
        with patch("utils.trust_scorer.GEMINI_API_KEY", "fake-key"), \
             patch("utils.trust_scorer._gemini_generate",
                   side_effect=Exception("API quota exceeded")):
            result = await compute_trust_score(
                signals=_healthy_signals(),
                comments=_sample_comments(),
            )

        assert result["status"] == "deterministic_only"
        assert result["composite_trust_score"] is not None
        assert result["confidence"] in ("medium", "low")

    @pytest.mark.asyncio
    async def test_llm_bad_json_degrades_gracefully(self):
        """Gemini returns non-JSON — deterministic-only result."""
        with patch("utils.trust_scorer.GEMINI_API_KEY", "fake-key"), \
             patch("utils.trust_scorer._gemini_generate",
                   return_value="This is not JSON"):
            result = await compute_trust_score(
                signals=_healthy_signals(),
                comments=_sample_comments(),
            )

        assert result["status"] == "deterministic_only"
        assert result["composite_trust_score"] is not None

    @pytest.mark.asyncio
    async def test_no_comments_lowers_confidence(self):
        """No comments provided — LLM skipped, confidence lowered."""
        result = await compute_trust_score(
            signals=_healthy_signals(),
            comments=None,
        )

        assert result["status"] == "deterministic_only"
        assert result["confidence"] in ("medium", "low")
        assert "LLM skipped" in result["override_reason"]

    @pytest.mark.asyncio
    async def test_empty_comments_list(self):
        """Empty comments list — LLM skipped."""
        result = await compute_trust_score(
            signals=_healthy_signals(),
            comments=[],
        )

        assert result["status"] == "deterministic_only"
        assert "LLM skipped" in result["override_reason"]


# ---------------------------------------------------------------------------
# No-fabrication rule
# ---------------------------------------------------------------------------

class TestNoFabrication:
    @pytest.mark.asyncio
    async def test_no_signals_returns_unanalyzed(self):
        result = await compute_trust_score(signals=None)
        assert result["status"] == "unanalyzed"
        assert result["composite_trust_score"] is None
        assert result["community_trust_depth"] is None
        assert result["authority"] is None

    @pytest.mark.asyncio
    async def test_empty_signals_returns_unanalyzed(self):
        result = await compute_trust_score(signals={})
        # With empty signals, deterministic layer produces None scores
        # but should not fabricate
        assert result["composite_trust_score"] is None or result["confidence"] == "low"

    def test_unanalyzed_response_helper(self):
        result = unanalyzed_trust_response("test reason")
        assert result["status"] == "unanalyzed"
        assert result["composite_trust_score"] is None
        assert result["confidence"] == "low"
        assert "test reason" in result["override_reason"]


# ---------------------------------------------------------------------------
# Override reason population
# ---------------------------------------------------------------------------

class TestOverrideReason:
    @pytest.mark.asyncio
    async def test_override_reason_populated_on_missing_data(self):
        result = await compute_trust_score(
            signals=_minimal_signals(),
            comments=None,
        )
        assert result["override_reason"] is not None
        assert "unavailable" in result["override_reason"]

    @pytest.mark.asyncio
    async def test_override_reason_records_llm_adjustment(self):
        with patch("utils.trust_scorer.GEMINI_API_KEY", "fake-key"), \
             patch("utils.trust_scorer._gemini_generate", return_value=_MOCK_LLM_RESPONSE):
            result = await compute_trust_score(
                signals=_healthy_signals(),
                comments=_sample_comments(),
            )

        assert result["override_reason"] is not None
        # Should mention LLM adjustment
        assert "LLM-adjusted" in result["override_reason"] or "LLM" in result["override_reason"]


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_llm_missing_required_field_degrades(self):
        """LLM response missing a required field — treated as failure."""
        incomplete = json.dumps({
            "spam_ratio": 0.1,
            # Missing comment_authenticity_score
            "substantive_ratio": 0.7,
        })

        with patch("utils.trust_scorer.GEMINI_API_KEY", "fake-key"), \
             patch("utils.trust_scorer._gemini_generate", return_value=incomplete):
            result = await compute_trust_score(
                signals=_healthy_signals(),
                comments=_sample_comments(),
            )

        # Should degrade to deterministic-only
        assert result["status"] == "deterministic_only"
        assert result["composite_trust_score"] is not None

    @pytest.mark.asyncio
    async def test_composite_is_weighted_average(self):
        """Composite = 65% community + 35% authority."""
        with patch("utils.trust_scorer.GEMINI_API_KEY", ""):
            result = await compute_trust_score(
                signals=_healthy_signals(),
                comments=None,
            )

        community = result["community_trust_depth"]["score"]
        authority = result["authority"]["score"]
        composite = result["composite_trust_score"]

        if community is not None and authority is not None:
            expected = round(community * 0.65 + authority * 0.35, 1)
            assert abs(composite - expected) < 0.2  # Small rounding tolerance
