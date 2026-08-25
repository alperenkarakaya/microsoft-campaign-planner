"""Tests for the enrichment orchestration pipeline (Phase 6).

Covers:
  - Happy path: mock YouTube + Gemini, all three JSON blobs persisted + last_enriched_at set
  - Failure isolation: one creator/sub-step fails -> others still persist, failed one recorded
  - Stale-only selection logic
  - Brand-agnostic InfluencerAnalysis row (brand_profile_id = NULL)
  - Comment pass-through: when comments are captured by signals.py, trust_scorer
    and sponsorship_analyzer receive them and produce LLM-derived sub-scores
  - Degradation: when comments are unavailable or Gemini fails, scorers degrade
    to deterministic-only with no fabrication

All tests are fully OFFLINE — YouTube and Gemini calls are mocked.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

import database
from models import Influencer, InfluencerAnalysis
from database import get_db
from utils.enrichment_pipeline import (
    enrich_single_creator,
    enrich_batch,
    _select_stale_influencers,
    _persist_intrinsic_analysis,
    EnrichmentResult,
    BatchEnrichmentResult,
    DEFAULT_STALE_DAYS,
)
from utils.trust_scorer import compute_trust_score
from utils.sponsorship_analyzer import compute_sponsorship_profile


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_influencer(
    db,
    *,
    username="testcreator",
    platform_id="UC_test_123",
    source_handle="testcreator",
    business_email="test@example.com",
    last_enriched_at=None,
    enrichment_status=None,
):
    inf = Influencer(
        platform="youtube",
        platform_id=platform_id,
        username=username,
        display_name=f"Display {username}",
        source_handle=source_handle,
        business_email=business_email,
        followers_count=10_000,
        engagement_rate=5.0,
        category="gaming",
        country="US",
        last_enriched_at=last_enriched_at,
        enrichment_status=enrichment_status,
    )
    db.add(inf)
    db.flush()
    db.refresh(inf)
    return inf


def _mock_signals():
    """Fake Phase-1 signals blob."""
    return {
        "computed_at": "2026-06-21T00:00:00+00:00",
        "channel_id": "UC_test_123",
        "subscriber_count": 50_000,
        "view_count": 5_000_000,
        "video_count": 200,
        "view_consistency": {
            "recent_view_median": 15_000,
            "recent_view_cv": 0.25,
            "sample_size": 10,
        },
        "engagement_depth": {
            "like_to_view_ratio": 0.06,
            "comment_to_view_ratio": 0.008,
            "sample_size": 10,
        },
        "upload_cadence": {
            "cadence_days_median": 7.0,
            "cadence_days_mean": 8.0,
            "last_upload_days_ago": 5.0,
        },
        "creator_reply_rate": {
            "reply_rate": 0.15,
            "total_threads_sampled": 40,
            "creator_replies_found": 6,
            "videos_sampled": 5,
        },
        "sponsorship_detection": {
            "videos_with_description_signals": 3,
            "total_videos_checked": 10,
            "videos_with_paid_placement_flag": 1,
            "videos_checked_for_placement": 10,
            "hits": [
                {"video_id": "v1", "title": "Test", "signals": {"has_promo_code": True}},
            ],
        },
        "source": "YouTube Data API v3",
        "videos_sampled": 10,
    }


def _mock_trust_breakdown():
    """Fake Phase-2 trust breakdown."""
    return {
        "status": "deterministic_only",
        "community_trust_depth": {"score": 72.0},
        "authority": {"score": 55.0},
        "composite_trust_score": 66.1,
        "confidence": "medium",
        "source": "Phase-1 deterministic signals (LLM unavailable)",
        "override_reason": "LLM skipped: comments not fetched",
        "computed_at": "2026-06-21T00:00:00+00:00",
    }


def _mock_sponsorship_profile():
    """Fake Phase-3 sponsorship profile."""
    return {
        "status": "deterministic_only",
        "maturity": {"label": "mature", "score": 80.0},
        "quality": {"score": 45.0},
        "integration_style": {"style": "unknown", "score": None},
        "authenticity": {"score": None},
        "composite_sponsorship_score": 62.5,
        "confidence": "low",
        "source": "Phase-1 sponsorship signals (LLM unavailable)",
        "override_reason": None,
        "computed_at": "2026-06-21T00:00:00+00:00",
    }


# ---------------------------------------------------------------------------
# Tests: enrich_single_creator
# ---------------------------------------------------------------------------

class TestEnrichSingleCreator:

    @pytest.mark.asyncio
    async def test_happy_path_all_steps_succeed(self):
        """All three steps succeed: signals, trust, sponsorship persisted."""
        db = next(get_db())
        try:
            inf = _make_influencer(db)
            db.commit()

            with patch(
                "utils.enrichment_pipeline.compute_signals_for_channel",
                new_callable=AsyncMock,
                return_value=_mock_signals(),
            ), patch(
                "utils.enrichment_pipeline.compute_trust_score",
                new_callable=AsyncMock,
                return_value=_mock_trust_breakdown(),
            ), patch(
                "utils.enrichment_pipeline.compute_sponsorship_profile",
                new_callable=AsyncMock,
                return_value=_mock_sponsorship_profile(),
            ), patch(
                "utils.enrichment_pipeline.get_cached_videos",
                return_value=[],
            ):
                result = await enrich_single_creator(db, inf)
                db.commit()

            assert result.status == "completed"
            assert result.signals_ok is True
            assert result.trust_ok is True
            assert result.sponsorship_ok is True
            assert result.error is None

            # Check persisted data
            db.refresh(inf)
            assert inf.enrichment_signals is not None
            assert inf.enrichment_signals["subscriber_count"] == 50_000
            assert inf.followers_count == 50_000
            assert inf.last_enriched_at is not None
            assert inf.enrichment_status == "completed"
            assert inf.enrichment_error is None

            # Check brand-agnostic InfluencerAnalysis row
            analysis = (
                db.query(InfluencerAnalysis)
                .filter(
                    InfluencerAnalysis.influencer_id == inf.id,
                    InfluencerAnalysis.brand_profile_id.is_(None),
                )
                .first()
            )
            assert analysis is not None
            assert analysis.trust_breakdown is not None
            assert analysis.trust_breakdown["composite_trust_score"] == 66.1
            assert analysis.sponsorship_profile is not None
            assert analysis.sponsorship_profile["composite_sponsorship_score"] == 62.5
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_unresolved_channel_fails_immediately(self):
        """Unresolved channel ID should fail without calling any API."""
        db = next(get_db())
        try:
            inf = _make_influencer(db, platform_id="unresolved:testhandle")
            db.commit()

            result = await enrich_single_creator(db, inf)
            db.commit()

            assert result.status == "failed"
            assert "unresolved" in result.error
            assert inf.enrichment_status == "failed"
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_signals_failure_still_records_partial(self):
        """If signals fail but trust/sponsorship work with existing data, status is partial."""
        db = next(get_db())
        try:
            # Pre-populate with existing signals so trust/sponsorship can run
            inf = _make_influencer(db)
            inf.enrichment_signals = _mock_signals()
            db.commit()

            with patch(
                "utils.enrichment_pipeline.compute_signals_for_channel",
                new_callable=AsyncMock,
                side_effect=Exception("YouTube API down"),
            ), patch(
                "utils.enrichment_pipeline.compute_trust_score",
                new_callable=AsyncMock,
                return_value=_mock_trust_breakdown(),
            ), patch(
                "utils.enrichment_pipeline.compute_sponsorship_profile",
                new_callable=AsyncMock,
                return_value=_mock_sponsorship_profile(),
            ), patch(
                "utils.enrichment_pipeline.get_cached_videos",
                return_value=[],
            ):
                result = await enrich_single_creator(db, inf)
                db.commit()

            assert result.status == "partial"
            assert result.signals_ok is False
            assert result.trust_ok is True
            assert result.sponsorship_ok is True
            assert "YouTube API down" in result.error

            db.refresh(inf)
            assert inf.enrichment_status == "partial"
            assert inf.enrichment_error is not None
            assert inf.last_enriched_at is not None  # Still marked (partial)
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_trust_failure_does_not_block_sponsorship(self):
        """Trust failing should not prevent sponsorship from running."""
        db = next(get_db())
        try:
            inf = _make_influencer(db)
            db.commit()

            with patch(
                "utils.enrichment_pipeline.compute_signals_for_channel",
                new_callable=AsyncMock,
                return_value=_mock_signals(),
            ), patch(
                "utils.enrichment_pipeline.compute_trust_score",
                new_callable=AsyncMock,
                side_effect=Exception("Gemini quota exceeded"),
            ), patch(
                "utils.enrichment_pipeline.compute_sponsorship_profile",
                new_callable=AsyncMock,
                return_value=_mock_sponsorship_profile(),
            ), patch(
                "utils.enrichment_pipeline.get_cached_videos",
                return_value=[],
            ):
                result = await enrich_single_creator(db, inf)
                db.commit()

            assert result.status == "partial"
            assert result.signals_ok is True
            assert result.trust_ok is False
            assert result.sponsorship_ok is True
            assert "Gemini quota exceeded" in result.error

            # Sponsorship should still be persisted
            analysis = (
                db.query(InfluencerAnalysis)
                .filter(
                    InfluencerAnalysis.influencer_id == inf.id,
                    InfluencerAnalysis.brand_profile_id.is_(None),
                )
                .first()
            )
            assert analysis is not None
            assert analysis.trust_breakdown is None  # Trust failed
            assert analysis.sponsorship_profile is not None  # Sponsorship succeeded
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_all_steps_fail_records_failed_status(self):
        """All steps failing should produce 'failed' status with error details."""
        db = next(get_db())
        try:
            inf = _make_influencer(db)
            db.commit()

            with patch(
                "utils.enrichment_pipeline.compute_signals_for_channel",
                new_callable=AsyncMock,
                return_value=None,  # signals returns None = API unavailable
            ), patch(
                "utils.enrichment_pipeline.get_cached_videos",
                return_value=None,
            ):
                result = await enrich_single_creator(db, inf)
                db.commit()

            assert result.status == "failed"
            assert result.signals_ok is False
            assert result.trust_ok is False
            assert result.sponsorship_ok is False

            db.refresh(inf)
            assert inf.enrichment_status == "failed"
            assert inf.enrichment_error is not None
            assert inf.last_enriched_at is None  # Not marked as enriched on total failure
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_updates_existing_brand_agnostic_analysis(self):
        """Re-enrichment should update existing brand-agnostic row, not create duplicates."""
        db = next(get_db())
        try:
            inf = _make_influencer(db)
            # Create an existing brand-agnostic analysis row
            existing_analysis = InfluencerAnalysis(
                influencer_id=inf.id,
                brand_profile_id=None,
                trust_breakdown={"status": "old", "composite_trust_score": 50.0},
                sponsorship_profile={"status": "old", "composite_sponsorship_score": 40.0},
                content_style_match_score=0.0,
                audience_match_score=0.0,
                engagement_quality_score=0.0,
                brand_safety_score=0.0,
                overall_match_score=0.0,
                ai_analysis_summary="Old intrinsic enrichment",
                content_tone="n/a",
            )
            db.add(existing_analysis)
            db.commit()
            existing_id = existing_analysis.id

            with patch(
                "utils.enrichment_pipeline.compute_signals_for_channel",
                new_callable=AsyncMock,
                return_value=_mock_signals(),
            ), patch(
                "utils.enrichment_pipeline.compute_trust_score",
                new_callable=AsyncMock,
                return_value=_mock_trust_breakdown(),
            ), patch(
                "utils.enrichment_pipeline.compute_sponsorship_profile",
                new_callable=AsyncMock,
                return_value=_mock_sponsorship_profile(),
            ), patch(
                "utils.enrichment_pipeline.get_cached_videos",
                return_value=[],
            ):
                result = await enrich_single_creator(db, inf)
                db.commit()

            assert result.status == "completed"

            # Should have updated the existing row, not created a new one
            analyses = (
                db.query(InfluencerAnalysis)
                .filter(
                    InfluencerAnalysis.influencer_id == inf.id,
                    InfluencerAnalysis.brand_profile_id.is_(None),
                )
                .all()
            )
            assert len(analyses) == 1
            assert analyses[0].id == existing_id
            assert analyses[0].trust_breakdown["composite_trust_score"] == 66.1
            assert analyses[0].sponsorship_profile["composite_sponsorship_score"] == 62.5
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Tests: stale selection logic
# ---------------------------------------------------------------------------

class TestStaleSelection:

    def test_selects_never_enriched(self):
        db = next(get_db())
        try:
            inf = _make_influencer(db, last_enriched_at=None)
            db.commit()

            results = _select_stale_influencers(db, stale_days=7, only_stale=True)
            assert len(results) == 1
            assert results[0].id == inf.id
        finally:
            db.close()

    def test_selects_stale_creators(self):
        db = next(get_db())
        try:
            old_time = datetime.now(timezone.utc) - timedelta(days=10)
            inf = _make_influencer(db, last_enriched_at=old_time)
            db.commit()

            results = _select_stale_influencers(db, stale_days=7, only_stale=True)
            assert len(results) == 1
            assert results[0].id == inf.id
        finally:
            db.close()

    def test_skips_fresh_creators(self):
        db = next(get_db())
        try:
            recent_time = datetime.now(timezone.utc) - timedelta(days=1)
            _make_influencer(db, last_enriched_at=recent_time)
            db.commit()

            results = _select_stale_influencers(db, stale_days=7, only_stale=True)
            assert len(results) == 0
        finally:
            db.close()

    def test_includes_fresh_when_not_only_stale(self):
        db = next(get_db())
        try:
            recent_time = datetime.now(timezone.utc) - timedelta(hours=1)
            _make_influencer(db, last_enriched_at=recent_time)
            db.commit()

            results = _select_stale_influencers(db, stale_days=7, only_stale=False)
            assert len(results) == 1
        finally:
            db.close()

    def test_skips_unresolved_handles(self):
        db = next(get_db())
        try:
            _make_influencer(db, platform_id="unresolved:somehandle")
            db.commit()

            results = _select_stale_influencers(db, stale_days=7, only_stale=True)
            assert len(results) == 0
        finally:
            db.close()

    def test_respects_limit(self):
        db = next(get_db())
        try:
            for i in range(5):
                _make_influencer(
                    db,
                    username=f"creator{i}",
                    platform_id=f"UC_test_{i}",
                    source_handle=f"creator{i}",
                )
            db.commit()

            results = _select_stale_influencers(db, stale_days=7, only_stale=True, limit=3)
            assert len(results) == 3
        finally:
            db.close()

    def test_never_enriched_first_then_oldest(self):
        db = next(get_db())
        try:
            old = _make_influencer(
                db,
                username="old",
                platform_id="UC_old",
                source_handle="old",
                last_enriched_at=datetime.now(timezone.utc) - timedelta(days=20),
            )
            never = _make_influencer(
                db,
                username="never",
                platform_id="UC_never",
                source_handle="never",
                last_enriched_at=None,
            )
            recent = _make_influencer(
                db,
                username="recent_stale",
                platform_id="UC_recent",
                source_handle="recent",
                last_enriched_at=datetime.now(timezone.utc) - timedelta(days=8),
            )
            db.commit()

            results = _select_stale_influencers(db, stale_days=7, only_stale=True)
            assert len(results) == 3
            # Never-enriched should be first
            assert results[0].id == never.id
            # Then oldest stale
            assert results[1].id == old.id
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Tests: enrich_batch
# ---------------------------------------------------------------------------

class TestEnrichBatch:

    @pytest.mark.asyncio
    async def test_batch_enriches_multiple_creators(self):
        db = next(get_db())
        try:
            inf1 = _make_influencer(
                db,
                username="creator_a",
                platform_id="UC_a",
                source_handle="creator_a",
            )
            inf2 = _make_influencer(
                db,
                username="creator_b",
                platform_id="UC_b",
                source_handle="creator_b",
            )
            db.commit()

            with patch(
                "utils.enrichment_pipeline.compute_signals_for_channel",
                new_callable=AsyncMock,
                return_value=_mock_signals(),
            ), patch(
                "utils.enrichment_pipeline.compute_trust_score",
                new_callable=AsyncMock,
                return_value=_mock_trust_breakdown(),
            ), patch(
                "utils.enrichment_pipeline.compute_sponsorship_profile",
                new_callable=AsyncMock,
                return_value=_mock_sponsorship_profile(),
            ), patch(
                "utils.enrichment_pipeline.get_cached_videos",
                return_value=[],
            ):
                result = await enrich_batch(db, stale_days=7, only_stale=True)

            assert result.total == 2
            assert result.completed == 2
            assert result.failed == 0
            assert result.partial == 0
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_one_creator_failure_does_not_abort_batch(self):
        """One creator failing should not prevent others from being enriched."""
        db = next(get_db())
        try:
            inf_ok = _make_influencer(
                db,
                username="good_creator",
                platform_id="UC_good",
                source_handle="good_creator",
            )
            inf_bad = _make_influencer(
                db,
                username="bad_creator",
                platform_id="unresolved:bad",  # Will fail immediately
                source_handle="bad_creator",
            )
            db.commit()

            with patch(
                "utils.enrichment_pipeline.compute_signals_for_channel",
                new_callable=AsyncMock,
                return_value=_mock_signals(),
            ), patch(
                "utils.enrichment_pipeline.compute_trust_score",
                new_callable=AsyncMock,
                return_value=_mock_trust_breakdown(),
            ), patch(
                "utils.enrichment_pipeline.compute_sponsorship_profile",
                new_callable=AsyncMock,
                return_value=_mock_sponsorship_profile(),
            ), patch(
                "utils.enrichment_pipeline.get_cached_videos",
                return_value=[],
            ):
                # Note: bad_creator won't match selection query (unresolved: prefix
                # is excluded by _select_stale_influencers), so only good_creator
                # should be processed.
                result = await enrich_batch(db, stale_days=7, only_stale=True)

            # Only good_creator should be processed (bad is unresolved, excluded)
            assert result.total == 1
            assert result.completed == 1

            # Verify good_creator was enriched
            db.refresh(inf_ok)
            assert inf_ok.enrichment_status == "completed"
            assert inf_ok.last_enriched_at is not None
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_batch_skips_fresh_with_only_stale(self):
        db = next(get_db())
        try:
            # This creator was enriched 1 day ago (fresh)
            recent_time = datetime.now(timezone.utc) - timedelta(days=1)
            _make_influencer(
                db,
                last_enriched_at=recent_time,
                enrichment_status="completed",
            )
            db.commit()

            result = await enrich_batch(db, stale_days=7, only_stale=True)
            assert result.total == 0
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_batch_force_ignores_staleness(self):
        db = next(get_db())
        try:
            recent_time = datetime.now(timezone.utc) - timedelta(hours=1)
            _make_influencer(
                db,
                last_enriched_at=recent_time,
                enrichment_status="completed",
            )
            db.commit()

            with patch(
                "utils.enrichment_pipeline.compute_signals_for_channel",
                new_callable=AsyncMock,
                return_value=_mock_signals(),
            ), patch(
                "utils.enrichment_pipeline.compute_trust_score",
                new_callable=AsyncMock,
                return_value=_mock_trust_breakdown(),
            ), patch(
                "utils.enrichment_pipeline.compute_sponsorship_profile",
                new_callable=AsyncMock,
                return_value=_mock_sponsorship_profile(),
            ), patch(
                "utils.enrichment_pipeline.get_cached_videos",
                return_value=[],
            ):
                result = await enrich_batch(db, force=True)

            assert result.total == 1
            assert result.completed == 1
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_batch_empty_roster(self):
        db = next(get_db())
        try:
            result = await enrich_batch(db, stale_days=7)
            assert result.total == 0
            assert result.completed == 0
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Helpers: mock signals with comment data attached
# ---------------------------------------------------------------------------

def _mock_comment_samples():
    """Fake comment samples as captured by signals.py's fetch_creator_reply_rate."""
    return [
        {"author": "FanUser1", "text": "This is the best guide ever, been watching since 2020!", "video_id": "v1"},
        {"author": "FanUser2", "text": "Your builds are always so detailed, keep it up!", "video_id": "v1"},
        {"author": "GamerX", "text": "I bought the product you recommended, totally worth it", "video_id": "v2"},
        {"author": "NewViewer", "text": "First time watching, subscribed immediately!", "video_id": "v3"},
        {"author": "LoyalFan", "text": "As always, amazing content. Love your editing style.", "video_id": "v3"},
    ]


def _mock_per_video_comments():
    """Fake per-video comment mapping."""
    samples = _mock_comment_samples()
    return {
        "v1": [s for s in samples if s["video_id"] == "v1"],
        "v2": [s for s in samples if s["video_id"] == "v2"],
        "v3": [s for s in samples if s["video_id"] == "v3"],
    }


def _mock_comment_data():
    """Fake comment data dict as stored in Redis / attached to signals."""
    return {
        "comment_samples": _mock_comment_samples(),
        "per_video_comments": _mock_per_video_comments(),
    }


def _mock_signals_with_comments():
    """Phase-1 signals with transient _comment_data attached (as signals.py does)."""
    signals = _mock_signals()
    signals["_comment_data"] = _mock_comment_data()
    return signals


def _mock_llm_trust_breakdown():
    """Trust breakdown when LLM ran successfully (status=analyzed, high confidence)."""
    return {
        "status": "analyzed",
        "community_trust_depth": {
            "score": 75.0,
            "deterministic_baseline": 72.0,
            "floor": 52.0,
            "cap": 92.0,
            "components": {},
            "llm_comment_authenticity": 80.0,
            "llm_spam_ratio": 0.05,
            "llm_substantive_ratio": 0.7,
        },
        "authority": {
            "score": 60.0,
            "deterministic_baseline": 55.0,
            "floor": 30.0,
            "cap": 80.0,
            "components": {},
            "llm_parasocial_bond": 68.0,
            "llm_past_video_references": 45.0,
            "llm_loyalty_markers": 55.0,
        },
        "composite_trust_score": 69.8,
        "confidence": "high",
        "source": "Phase-1 deterministic signals + Gemini comment-quality analysis",
        "override_reason": None,
        "computed_at": "2026-06-21T00:00:00+00:00",
    }


def _mock_llm_sponsorship_profile():
    """Sponsorship profile when LLM ran with comment sentiment data."""
    return {
        "status": "analyzed",
        "maturity": {"label": "mature", "score": 80.0},
        "quality": {"score": 45.0},
        "integration_style": {"style": "native", "score": 75.0},
        "authenticity": {
            "score": 72.0,
            "sentiment_sponsored": 0.6,
            "sentiment_organic": 0.8,
            "sentiment_gap": 0.2,
            "audience_welcomes_sponsors": True,
        },
        "composite_sponsorship_score": 68.0,
        "confidence": "high",
        "source": "Phase-1 sponsorship signals + Gemini integration/sentiment analysis",
        "override_reason": None,
        "computed_at": "2026-06-21T00:00:00+00:00",
    }


# ---------------------------------------------------------------------------
# Tests: Comment pass-through (LLM-active path)
# ---------------------------------------------------------------------------

class TestCommentPassThrough:
    """Verify that when comments are available, the pipeline feeds them to
    trust_scorer and sponsorship_analyzer, producing LLM-derived sub-scores."""

    @pytest.mark.asyncio
    async def test_comments_passed_to_trust_scorer(self):
        """When signals include _comment_data, trust_scorer receives comments."""
        db = next(get_db())
        try:
            inf = _make_influencer(db)
            db.commit()

            trust_mock = AsyncMock(return_value=_mock_llm_trust_breakdown())
            spons_mock = AsyncMock(return_value=_mock_llm_sponsorship_profile())

            with patch(
                "utils.enrichment_pipeline.compute_signals_for_channel",
                new_callable=AsyncMock,
                return_value=_mock_signals_with_comments(),
            ), patch(
                "utils.enrichment_pipeline.compute_trust_score",
                trust_mock,
            ), patch(
                "utils.enrichment_pipeline.compute_sponsorship_profile",
                spons_mock,
            ), patch(
                "utils.enrichment_pipeline.get_cached_videos",
                return_value=[],
            ), patch(
                "utils.enrichment_pipeline.get_cached_comments",
                return_value=None,
            ):
                result = await enrich_single_creator(db, inf)
                db.commit()

            assert result.status == "completed"
            assert result.trust_ok is True

            # Verify trust_scorer was called with actual comments (not None)
            trust_mock.assert_called_once()
            call_kwargs = trust_mock.call_args
            comments_arg = call_kwargs.kwargs.get("comments") or call_kwargs[1].get("comments")
            assert comments_arg is not None
            assert len(comments_arg) == 5
            assert comments_arg[0]["author"] == "FanUser1"
            assert "text" in comments_arg[0]
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_comments_split_for_sponsorship_analyzer(self):
        """Sponsorship analyzer receives sponsored vs organic comments split."""
        db = next(get_db())
        try:
            inf = _make_influencer(db)
            db.commit()

            trust_mock = AsyncMock(return_value=_mock_llm_trust_breakdown())
            spons_mock = AsyncMock(return_value=_mock_llm_sponsorship_profile())

            # Video v1 is sponsored (in the hits list of signals)
            mock_videos = [
                {"video_id": "v1", "description": "Use code GAMER20", "paid_product_placement": None},
                {"video_id": "v2", "description": "Normal video", "paid_product_placement": None},
                {"video_id": "v3", "description": "Another video", "paid_product_placement": None},
            ]

            with patch(
                "utils.enrichment_pipeline.compute_signals_for_channel",
                new_callable=AsyncMock,
                return_value=_mock_signals_with_comments(),
            ), patch(
                "utils.enrichment_pipeline.compute_trust_score",
                trust_mock,
            ), patch(
                "utils.enrichment_pipeline.compute_sponsorship_profile",
                spons_mock,
            ), patch(
                "utils.enrichment_pipeline.get_cached_videos",
                return_value=mock_videos,
            ), patch(
                "utils.enrichment_pipeline.get_cached_comments",
                return_value=None,
            ):
                result = await enrich_single_creator(db, inf)
                db.commit()

            assert result.status == "completed"
            assert result.sponsorship_ok is True

            # Verify sponsorship_analyzer was called with split comments
            spons_mock.assert_called_once()
            call_args = spons_mock.call_args
            # The signals' sponsorship_detection.hits has video_id "v1" as sponsored
            sponsored_arg = call_args.kwargs.get("sponsored_comments")
            organic_arg = call_args.kwargs.get("organic_comments")

            # v1 is sponsored (in hits), so its 2 comments go to sponsored
            assert sponsored_arg is not None
            assert all(c["video_id"] == "v1" for c in sponsored_arg)
            # v2 and v3 are organic
            assert organic_arg is not None
            assert all(c["video_id"] in ("v2", "v3") for c in organic_arg)
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_persisted_trust_includes_llm_subscores(self):
        """When LLM runs, the persisted trust_breakdown includes LLM sub-scores."""
        db = next(get_db())
        try:
            inf = _make_influencer(db)
            db.commit()

            with patch(
                "utils.enrichment_pipeline.compute_signals_for_channel",
                new_callable=AsyncMock,
                return_value=_mock_signals_with_comments(),
            ), patch(
                "utils.enrichment_pipeline.compute_trust_score",
                new_callable=AsyncMock,
                return_value=_mock_llm_trust_breakdown(),
            ), patch(
                "utils.enrichment_pipeline.compute_sponsorship_profile",
                new_callable=AsyncMock,
                return_value=_mock_llm_sponsorship_profile(),
            ), patch(
                "utils.enrichment_pipeline.get_cached_videos",
                return_value=[],
            ), patch(
                "utils.enrichment_pipeline.get_cached_comments",
                return_value=None,
            ):
                result = await enrich_single_creator(db, inf)
                db.commit()

            assert result.status == "completed"

            # Check the persisted InfluencerAnalysis row
            analysis = (
                db.query(InfluencerAnalysis)
                .filter(
                    InfluencerAnalysis.influencer_id == inf.id,
                    InfluencerAnalysis.brand_profile_id.is_(None),
                )
                .first()
            )
            assert analysis is not None
            tb = analysis.trust_breakdown
            assert tb is not None
            assert tb["status"] == "analyzed"
            assert tb["confidence"] == "high"

            # LLM-derived sub-scores must be present (not None)
            assert tb["community_trust_depth"]["llm_comment_authenticity"] == 80.0
            assert tb["community_trust_depth"]["llm_spam_ratio"] == 0.05
            assert tb["community_trust_depth"]["llm_substantive_ratio"] == 0.7
            assert tb["authority"]["llm_parasocial_bond"] == 68.0
            assert tb["authority"]["llm_past_video_references"] == 45.0
            assert tb["authority"]["llm_loyalty_markers"] == 55.0

            # Source should indicate Gemini was used
            assert "Gemini" in tb["source"]
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_comment_data_not_persisted_in_enrichment_signals(self):
        """The _comment_data transient key should NOT be stored in enrichment_signals."""
        db = next(get_db())
        try:
            inf = _make_influencer(db)
            db.commit()

            with patch(
                "utils.enrichment_pipeline.compute_signals_for_channel",
                new_callable=AsyncMock,
                return_value=_mock_signals_with_comments(),
            ), patch(
                "utils.enrichment_pipeline.compute_trust_score",
                new_callable=AsyncMock,
                return_value=_mock_llm_trust_breakdown(),
            ), patch(
                "utils.enrichment_pipeline.compute_sponsorship_profile",
                new_callable=AsyncMock,
                return_value=_mock_llm_sponsorship_profile(),
            ), patch(
                "utils.enrichment_pipeline.get_cached_videos",
                return_value=[],
            ), patch(
                "utils.enrichment_pipeline.get_cached_comments",
                return_value=None,
            ):
                result = await enrich_single_creator(db, inf)
                db.commit()

            assert result.status == "completed"

            db.refresh(inf)
            assert inf.enrichment_signals is not None
            # Transient _comment_data must have been popped before persistence
            assert "_comment_data" not in inf.enrichment_signals
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_cached_comments_used_when_signals_lack_comment_data(self):
        """When fresh signals don't include _comment_data, Redis-cached comments are used."""
        db = next(get_db())
        try:
            inf = _make_influencer(db)
            db.commit()

            trust_mock = AsyncMock(return_value=_mock_llm_trust_breakdown())

            # Signals WITHOUT _comment_data (simulating cache-only scenario)
            signals_no_comments = _mock_signals()  # no _comment_data key

            with patch(
                "utils.enrichment_pipeline.compute_signals_for_channel",
                new_callable=AsyncMock,
                return_value=signals_no_comments,
            ), patch(
                "utils.enrichment_pipeline.compute_trust_score",
                trust_mock,
            ), patch(
                "utils.enrichment_pipeline.compute_sponsorship_profile",
                new_callable=AsyncMock,
                return_value=_mock_llm_sponsorship_profile(),
            ), patch(
                "utils.enrichment_pipeline.get_cached_videos",
                return_value=[],
            ), patch(
                "utils.enrichment_pipeline.get_cached_comments",
                return_value=_mock_comment_data(),  # Redis returns cached comments
            ):
                result = await enrich_single_creator(db, inf)
                db.commit()

            assert result.trust_ok is True

            # Trust scorer should still get comments from Redis cache
            trust_mock.assert_called_once()
            call_kwargs = trust_mock.call_args
            comments_arg = call_kwargs.kwargs.get("comments") or call_kwargs[1].get("comments")
            assert comments_arg is not None
            assert len(comments_arg) == 5
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Tests: Degradation path (no comments / Gemini down)
# ---------------------------------------------------------------------------

class TestDegradationPath:
    """Verify that when comments are unavailable or Gemini fails, the pipeline
    degrades to deterministic-only scoring with no fabrication."""

    @pytest.mark.asyncio
    async def test_no_comments_produces_deterministic_only_trust(self):
        """When no comments are available, trust_scorer degrades to deterministic_only."""
        db = next(get_db())
        try:
            inf = _make_influencer(db)
            db.commit()

            # Use the REAL trust_scorer (not mocked) to prove degradation path
            signals = _mock_signals()  # no _comment_data

            with patch(
                "utils.enrichment_pipeline.compute_signals_for_channel",
                new_callable=AsyncMock,
                return_value=signals,
            ), patch(
                "utils.enrichment_pipeline.compute_sponsorship_profile",
                new_callable=AsyncMock,
                return_value=_mock_sponsorship_profile(),
            ), patch(
                "utils.enrichment_pipeline.get_cached_videos",
                return_value=[],
            ), patch(
                "utils.enrichment_pipeline.get_cached_comments",
                return_value=None,  # No cached comments either
            ):
                result = await enrich_single_creator(db, inf)
                db.commit()

            assert result.trust_ok is True

            analysis = (
                db.query(InfluencerAnalysis)
                .filter(
                    InfluencerAnalysis.influencer_id == inf.id,
                    InfluencerAnalysis.brand_profile_id.is_(None),
                )
                .first()
            )
            assert analysis is not None
            tb = analysis.trust_breakdown
            assert tb is not None
            assert tb["status"] == "deterministic_only"
            # Confidence should be lower without LLM
            assert tb["confidence"] in ("medium", "low")

            # LLM sub-scores must be None (no fabrication)
            assert tb["community_trust_depth"]["llm_comment_authenticity"] is None
            assert tb["community_trust_depth"]["llm_spam_ratio"] is None
            assert tb["authority"]["llm_parasocial_bond"] is None
            assert tb["authority"]["llm_past_video_references"] is None

            # Deterministic baseline must still be computed
            assert tb["community_trust_depth"]["deterministic_baseline"] is not None
            assert tb["authority"]["deterministic_baseline"] is not None
            assert tb["composite_trust_score"] is not None

            # Source should indicate deterministic only
            assert "LLM unavailable" in tb["source"]
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_gemini_down_produces_deterministic_only_trust(self):
        """When Gemini API key is not set, LLM analysis is skipped gracefully."""
        db = next(get_db())
        try:
            inf = _make_influencer(db)
            db.commit()

            # Provide comments but ensure GEMINI_API_KEY is empty
            signals = _mock_signals_with_comments()

            with patch(
                "utils.enrichment_pipeline.compute_signals_for_channel",
                new_callable=AsyncMock,
                return_value=signals,
            ), patch(
                "utils.enrichment_pipeline.compute_sponsorship_profile",
                new_callable=AsyncMock,
                return_value=_mock_sponsorship_profile(),
            ), patch(
                "utils.enrichment_pipeline.get_cached_videos",
                return_value=[],
            ), patch(
                "utils.enrichment_pipeline.get_cached_comments",
                return_value=None,
            ), patch(
                "utils.trust_scorer.GEMINI_API_KEY", "",
            ):
                result = await enrich_single_creator(db, inf)
                db.commit()

            assert result.trust_ok is True

            analysis = (
                db.query(InfluencerAnalysis)
                .filter(
                    InfluencerAnalysis.influencer_id == inf.id,
                    InfluencerAnalysis.brand_profile_id.is_(None),
                )
                .first()
            )
            assert analysis is not None
            tb = analysis.trust_breakdown
            assert tb is not None
            # Even with comments provided, no LLM available = deterministic_only
            assert tb["status"] == "deterministic_only"
            assert tb["community_trust_depth"]["llm_comment_authenticity"] is None
            assert tb["authority"]["llm_parasocial_bond"] is None
            assert tb["composite_trust_score"] is not None
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_empty_comments_list_degrades_gracefully(self):
        """Empty comment list (comments disabled) degrades to deterministic_only."""
        db = next(get_db())
        try:
            inf = _make_influencer(db)
            db.commit()

            signals = _mock_signals()
            signals["_comment_data"] = {
                "comment_samples": [],  # Empty — comments were disabled
                "per_video_comments": {},
            }

            with patch(
                "utils.enrichment_pipeline.compute_signals_for_channel",
                new_callable=AsyncMock,
                return_value=signals,
            ), patch(
                "utils.enrichment_pipeline.compute_sponsorship_profile",
                new_callable=AsyncMock,
                return_value=_mock_sponsorship_profile(),
            ), patch(
                "utils.enrichment_pipeline.get_cached_videos",
                return_value=[],
            ), patch(
                "utils.enrichment_pipeline.get_cached_comments",
                return_value=None,
            ):
                result = await enrich_single_creator(db, inf)
                db.commit()

            assert result.trust_ok is True

            analysis = (
                db.query(InfluencerAnalysis)
                .filter(
                    InfluencerAnalysis.influencer_id == inf.id,
                    InfluencerAnalysis.brand_profile_id.is_(None),
                )
                .first()
            )
            assert analysis is not None
            tb = analysis.trust_breakdown
            assert tb is not None
            # Empty comments list = no LLM analysis = deterministic only
            assert tb["status"] == "deterministic_only"
            assert tb["community_trust_depth"]["llm_comment_authenticity"] is None
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_no_fabrication_on_total_signal_failure(self):
        """When signals are completely unavailable, trust returns unanalyzed, never fabricates."""
        db = next(get_db())
        try:
            inf = _make_influencer(db)
            db.commit()

            with patch(
                "utils.enrichment_pipeline.compute_signals_for_channel",
                new_callable=AsyncMock,
                return_value=None,
            ), patch(
                "utils.enrichment_pipeline.get_cached_videos",
                return_value=None,
            ), patch(
                "utils.enrichment_pipeline.get_cached_comments",
                return_value=None,
            ):
                result = await enrich_single_creator(db, inf)
                db.commit()

            assert result.status == "failed"
            assert result.trust_ok is False
            assert result.sponsorship_ok is False

            # No analysis row should be created (no data = no fabrication)
            analysis = (
                db.query(InfluencerAnalysis)
                .filter(
                    InfluencerAnalysis.influencer_id == inf.id,
                    InfluencerAnalysis.brand_profile_id.is_(None),
                )
                .first()
            )
            assert analysis is None
        finally:
            db.close()
