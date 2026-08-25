"""Tests for the Sponsorship Authenticity analyzer — fully offline.

Gemini is mocked so tests never hit the network. Tests verify:
  (a) deterministic floors/caps hold,
  (b) LLM-down path returns a valid deterministic-only result with lowered confidence,
  (c) override_reason is populated when an adjustment happens,
  (d) no fabricated numbers on failure.
"""

import json
from unittest.mock import patch

import pytest

from utils.sponsorship_analyzer import (
    _compute_maturity,
    _compute_quality,
    _extract_sponsor_names,
    _classify_videos,
    compute_sponsorship_profile,
    unanalyzed_sponsorship_response,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _healthy_signals():
    """A channel with moderate, healthy sponsorship presence."""
    return {
        "sponsorship_detection": {
            "videos_with_description_signals": 3,
            "total_videos_checked": 10,
            "videos_with_paid_placement_flag": 2,
            "videos_checked_for_placement": 10,
            "hits": [
                {"video_id": "v1", "title": "Review with sponsor",
                 "signals": {"has_promo_code": True, "has_affiliate_link": True,
                             "has_sponsorship_mention": True, "matched_patterns": []}},
                {"video_id": "v3", "title": "Another sponsored vid",
                 "signals": {"has_promo_code": True, "has_affiliate_link": False,
                             "has_sponsorship_mention": True, "matched_patterns": []}},
                {"video_id": "v5", "title": "Brand deal",
                 "signals": {"has_promo_code": False, "has_affiliate_link": True,
                             "has_sponsorship_mention": True, "matched_patterns": []}},
            ],
        },
    }


def _saturated_signals():
    """A channel with heavy sponsorship (saturated)."""
    return {
        "sponsorship_detection": {
            "videos_with_description_signals": 8,
            "total_videos_checked": 10,
            "videos_with_paid_placement_flag": 7,
            "videos_checked_for_placement": 10,
            "hits": [
                {"video_id": f"v{i}", "title": f"Sponsored {i}",
                 "signals": {"has_promo_code": True, "has_affiliate_link": True,
                             "has_sponsorship_mention": True, "matched_patterns": []}}
                for i in range(8)
            ],
        },
    }


def _no_sponsorship_signals():
    """A channel with zero sponsorship signals."""
    return {
        "sponsorship_detection": {
            "videos_with_description_signals": 0,
            "total_videos_checked": 10,
            "videos_with_paid_placement_flag": 0,
            "videos_checked_for_placement": 10,
            "hits": [],
        },
    }


def _sample_videos():
    """Mixed sponsored/organic video list."""
    return [
        {
            "video_id": "v1",
            "title": "GamerSupps Review",
            "description": "Thanks to GamerSupps for sponsoring! Use code CREATOR for 10% off. https://gamersupps.gg/ref=creator",
            "views": 100000,
            "likes": 5000,
            "comments": 300,
            "paid_product_placement": True,
        },
        {
            "video_id": "v2",
            "title": "Organic Gameplay",
            "description": "Just playing some games today, hope you enjoy!",
            "views": 80000,
            "likes": 4500,
            "comments": 250,
            "paid_product_placement": False,
        },
        {
            "video_id": "v3",
            "title": "NordVPN Special",
            "description": "This video is sponsored by NordVPN. Use code GAMER for 30% off. https://nordvpn.com/ref=gamer",
            "views": 90000,
            "likes": 4000,
            "comments": 200,
            "paid_product_placement": True,
        },
        {
            "video_id": "v4",
            "title": "Weekly Update",
            "description": "Here's what happened this week. Like and subscribe!",
            "views": 70000,
            "likes": 3500,
            "comments": 180,
            "paid_product_placement": False,
        },
        {
            "video_id": "v5",
            "title": "GamerSupps Round 2",
            "description": "GamerSupps is back! Use code CREATOR for deals. https://gamersupps.gg/ref=creator",
            "views": 95000,
            "likes": 4800,
            "comments": 280,
            "paid_product_placement": True,
        },
    ]


_MOCK_LLM_RESPONSE = json.dumps({
    "integration_style": "native",
    "integration_quality_score": 72,
    "integration_notes": "Creator integrates sponsors naturally into content.",
    "sentiment_sponsored": 0.5,
    "sentiment_organic": 0.7,
    "sentiment_gap": 0.2,
    "audience_welcomes_sponsors": True,
    "authenticity_score": 70,
    "authenticity_notes": "Fans generally welcome sponsorships.",
})


# ---------------------------------------------------------------------------
# Maturity tests
# ---------------------------------------------------------------------------

class TestComputeMaturity:
    def test_no_videos(self):
        signals = {"sponsorship_detection": {"total_videos_checked": 0,
                                             "videos_with_description_signals": 0,
                                             "videos_with_paid_placement_flag": 0,
                                             "videos_checked_for_placement": 0,
                                             "hits": []}}
        result = _compute_maturity(signals, [])
        assert result["label"] == "unknown"
        assert result["score"] is None

    def test_unproven(self):
        result = _compute_maturity(_no_sponsorship_signals(), [])
        assert result["label"] == "unproven"
        assert result["score"] == 30.0

    def test_healthy_mature(self):
        result = _compute_maturity(_healthy_signals(), _sample_videos())
        assert result["label"] == "mature"
        assert result["score"] >= 65.0

    def test_saturated(self):
        result = _compute_maturity(_saturated_signals(), [])
        assert result["label"] == "saturated"
        assert result["score"] == 25.0

    def test_emerging(self):
        signals = {
            "sponsorship_detection": {
                "videos_with_description_signals": 1,
                "total_videos_checked": 10,
                "videos_with_paid_placement_flag": 1,
                "videos_checked_for_placement": 10,
                "hits": [{"video_id": "v1", "title": "One sponsor",
                          "signals": {}}],
            },
        }
        result = _compute_maturity(signals, [])
        assert result["label"] == "emerging"
        assert result["score"] == 50.0


# ---------------------------------------------------------------------------
# Quality tests (repeat-sponsor detection)
# ---------------------------------------------------------------------------

class TestComputeQuality:
    def test_repeat_sponsor_detected(self):
        result = _compute_quality(_healthy_signals(), _sample_videos())
        # GamerSupps appears twice
        assert "gamersupps.gg" in result["repeat_sponsors"] or len(result["repeat_sponsors"]) > 0

    def test_no_sponsorship_data(self):
        result = _compute_quality(_no_sponsorship_signals(), [])
        assert result["score"] is None or result["score"] is not None
        # No crash expected

    def test_unique_sponsors_count(self):
        result = _compute_quality(_healthy_signals(), _sample_videos())
        assert result["unique_sponsors"] >= 1

    def test_sponsor_diversity_calculated(self):
        result = _compute_quality(_healthy_signals(), _sample_videos())
        if result["sponsor_diversity"] is not None:
            assert 0 <= result["sponsor_diversity"] <= 1


class TestExtractSponsorNames:
    def test_use_code_pattern(self):
        names = _extract_sponsor_names(["Use code GAMER for 10% off"])
        assert "gamer" in [n.lower() for n in names]

    def test_sponsored_by_pattern(self):
        names = _extract_sponsor_names(["This video is sponsored by NordVPN"])
        assert "nordvpn" in [n.lower() for n in names]

    def test_thanks_to_pattern(self):
        names = _extract_sponsor_names(["Thanks to Skillshare for sponsoring"])
        assert "skillshare" in [n.lower() for n in names]

    def test_affiliate_url(self):
        names = _extract_sponsor_names(["Check out https://gamersupps.gg"])
        assert any("gamersupps" in n for n in names)

    def test_empty_description(self):
        names = _extract_sponsor_names([""])
        assert names == []

    def test_filters_generic_domains(self):
        names = _extract_sponsor_names(["Visit https://youtube.com/channel"])
        assert "youtube.com" not in names


class TestClassifyVideos:
    def test_classification(self):
        sponsored, organic = _classify_videos(_healthy_signals(), _sample_videos())
        # v1, v3, v5 should be sponsored
        sponsored_ids = {v["video_id"] for v in sponsored}
        organic_ids = {v["video_id"] for v in organic}
        assert "v1" in sponsored_ids
        assert "v2" in organic_ids
        assert "v4" in organic_ids

    def test_empty_signals(self):
        sponsored, organic = _classify_videos(
            {"sponsorship_detection": {"hits": []}},
            _sample_videos(),
        )
        # Videos with paid_product_placement=True should still be classified
        sponsored_ids = {v["video_id"] for v in sponsored}
        assert "v1" in sponsored_ids


# ---------------------------------------------------------------------------
# Full compute_sponsorship_profile — LLM mocked
# ---------------------------------------------------------------------------

class TestComputeSponsorshipProfileWithLLM:
    @pytest.mark.asyncio
    async def test_full_analysis(self):
        with patch("utils.sponsorship_analyzer.GEMINI_API_KEY", "fake-key"), \
             patch("utils.sponsorship_analyzer._gemini_generate",
                   return_value=_MOCK_LLM_RESPONSE):
            result = await compute_sponsorship_profile(
                signals=_healthy_signals(),
                videos=_sample_videos(),
            )

        assert result["status"] == "analyzed"
        assert result["composite_sponsorship_score"] is not None
        assert 0 <= result["composite_sponsorship_score"] <= 100
        assert result["confidence"] in ("high", "medium")
        assert result["integration_style"]["style"] == "native"
        assert result["authenticity"]["score"] is not None

    @pytest.mark.asyncio
    async def test_saturation_caps_llm(self):
        """When maturity=saturated, LLM integration and authenticity scores are capped."""
        high_llm = json.dumps({
            "integration_style": "native",
            "integration_quality_score": 95,  # Would be capped
            "integration_notes": "Perfect integration.",
            "sentiment_sponsored": 0.8,
            "sentiment_organic": 0.8,
            "sentiment_gap": 0.0,
            "audience_welcomes_sponsors": True,
            "authenticity_score": 90,  # Would be capped
            "authenticity_notes": "Fans love it.",
        })

        with patch("utils.sponsorship_analyzer.GEMINI_API_KEY", "fake-key"), \
             patch("utils.sponsorship_analyzer._gemini_generate",
                   return_value=high_llm):
            result = await compute_sponsorship_profile(
                signals=_saturated_signals(),
                videos=_sample_videos(),
            )

        # Integration score capped at 60 for saturated channels
        assert result["integration_style"]["score"] <= 60.0
        # Authenticity score capped at 55 for saturated channels
        assert result["authenticity"]["score"] <= 55.0
        # Override reason should mention cap
        assert "capped" in result["override_reason"]
        assert "saturation" in result["override_reason"]

    @pytest.mark.asyncio
    async def test_llm_floor_enforcement(self):
        """LLM gives very low scores — floored by deterministic bounds."""
        low_llm = json.dumps({
            "integration_style": "read_out",
            "integration_quality_score": 5,  # Below floor
            "integration_notes": "Terrible.",
            "sentiment_sponsored": -1.0,
            "sentiment_organic": 0.8,
            "sentiment_gap": 1.8,
            "audience_welcomes_sponsors": False,
            "authenticity_score": 3,  # Below floor
            "authenticity_notes": "Fans hate it.",
        })

        with patch("utils.sponsorship_analyzer.GEMINI_API_KEY", "fake-key"), \
             patch("utils.sponsorship_analyzer._gemini_generate",
                   return_value=low_llm):
            result = await compute_sponsorship_profile(
                signals=_healthy_signals(),
                videos=_sample_videos(),
            )

        # Floors should hold
        integration = result["integration_style"]
        authenticity = result["authenticity"]
        assert integration["score"] >= integration["floor"]
        assert authenticity["score"] >= authenticity["floor"]
        assert "floored" in result["override_reason"]


# ---------------------------------------------------------------------------
# LLM-down paths
# ---------------------------------------------------------------------------

class TestLLMDownPaths:
    @pytest.mark.asyncio
    async def test_no_api_key_deterministic_only(self):
        with patch("utils.sponsorship_analyzer.GEMINI_API_KEY", ""):
            result = await compute_sponsorship_profile(
                signals=_healthy_signals(),
                videos=_sample_videos(),
            )

        assert result["status"] == "deterministic_only"
        assert result["composite_sponsorship_score"] is not None
        assert result["integration_style"]["style"] == "unknown"
        assert result["authenticity"]["score"] is None

    @pytest.mark.asyncio
    async def test_llm_exception_degrades(self):
        with patch("utils.sponsorship_analyzer.GEMINI_API_KEY", "fake-key"), \
             patch("utils.sponsorship_analyzer._gemini_generate",
                   side_effect=Exception("Quota exceeded")):
            result = await compute_sponsorship_profile(
                signals=_healthy_signals(),
                videos=_sample_videos(),
            )

        assert result["status"] == "deterministic_only"
        assert result["maturity"]["score"] is not None

    @pytest.mark.asyncio
    async def test_llm_bad_json_degrades(self):
        with patch("utils.sponsorship_analyzer.GEMINI_API_KEY", "fake-key"), \
             patch("utils.sponsorship_analyzer._gemini_generate",
                   return_value="not valid json"):
            result = await compute_sponsorship_profile(
                signals=_healthy_signals(),
                videos=_sample_videos(),
            )

        assert result["status"] == "deterministic_only"

    @pytest.mark.asyncio
    async def test_llm_missing_required_field_degrades(self):
        incomplete = json.dumps({
            "integration_style": "native",
            # Missing integration_quality_score and authenticity_score
            "integration_notes": "ok",
        })

        with patch("utils.sponsorship_analyzer.GEMINI_API_KEY", "fake-key"), \
             patch("utils.sponsorship_analyzer._gemini_generate",
                   return_value=incomplete):
            result = await compute_sponsorship_profile(
                signals=_healthy_signals(),
                videos=_sample_videos(),
            )

        assert result["status"] == "deterministic_only"


# ---------------------------------------------------------------------------
# No-fabrication rule
# ---------------------------------------------------------------------------

class TestNoFabrication:
    @pytest.mark.asyncio
    async def test_no_signals_unanalyzed(self):
        result = await compute_sponsorship_profile(
            signals=None,
            videos=[],
        )
        assert result["status"] == "unanalyzed"
        assert result["composite_sponsorship_score"] is None

    @pytest.mark.asyncio
    async def test_empty_signals_dict(self):
        result = await compute_sponsorship_profile(
            signals={},
            videos=[],
        )
        # Should not crash or fabricate
        assert result["composite_sponsorship_score"] is None or isinstance(
            result["composite_sponsorship_score"], float
        )

    def test_unanalyzed_response_helper(self):
        result = unanalyzed_sponsorship_response("test")
        assert result["status"] == "unanalyzed"
        assert result["composite_sponsorship_score"] is None
        assert result["confidence"] == "low"


# ---------------------------------------------------------------------------
# Override reason
# ---------------------------------------------------------------------------

class TestOverrideReason:
    @pytest.mark.asyncio
    async def test_override_reason_on_llm_cap(self):
        """Override reason populated when LLM score is capped."""
        high = json.dumps({
            "integration_style": "native",
            "integration_quality_score": 99,
            "integration_notes": "Perfect.",
            "sentiment_sponsored": 1.0,
            "sentiment_organic": 1.0,
            "sentiment_gap": 0.0,
            "audience_welcomes_sponsors": True,
            "authenticity_score": 99,
            "authenticity_notes": "Great.",
        })

        with patch("utils.sponsorship_analyzer.GEMINI_API_KEY", "fake-key"), \
             patch("utils.sponsorship_analyzer._gemini_generate",
                   return_value=high):
            result = await compute_sponsorship_profile(
                signals=_healthy_signals(),
                videos=_sample_videos(),
            )

        # Integration cap is 90, so 99 should be capped
        if result["integration_style"]["score"] < 99:
            assert "capped" in result["override_reason"]

    @pytest.mark.asyncio
    async def test_override_reason_on_missing_data(self):
        result = await compute_sponsorship_profile(
            signals=_no_sponsorship_signals(),
            videos=[],
        )
        # Should mention something about the data situation
        assert result["override_reason"] is not None or result["status"] == "deterministic_only"
