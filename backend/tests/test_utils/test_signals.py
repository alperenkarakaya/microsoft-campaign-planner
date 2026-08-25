"""Tests for the deterministic signal layer — fully offline, no network.

Tests the pure computation functions (sponsorship detection, upload cadence,
engagement depth, view consistency). Does NOT test the async YouTube-fetching
functions (those require a live API key and are integration tests).
"""

from datetime import datetime, timezone, timedelta

import pytest

from utils.signals import (
    compute_engagement_depth,
    compute_upload_cadence,
    compute_view_consistency,
    detect_sponsorship_signals,
)


# ---------------------------------------------------------------------------
# Sponsorship detection
# ---------------------------------------------------------------------------

class TestDetectSponsorshipSignals:
    def test_empty_description(self):
        result = detect_sponsorship_signals("")
        assert result["has_promo_code"] is False
        assert result["has_affiliate_link"] is False
        assert result["has_sponsorship_mention"] is False
        assert result["matched_patterns"] == []

    def test_none_description(self):
        result = detect_sponsorship_signals(None)
        assert result["has_promo_code"] is False

    def test_use_code_detected(self):
        result = detect_sponsorship_signals("Use code GAMER20 for 20% off!")
        assert result["has_promo_code"] is True
        assert len(result["matched_patterns"]) >= 1

    def test_promo_code_detected(self):
        result = detect_sponsorship_signals("Get your promo code at checkout")
        assert result["has_promo_code"] is True

    def test_discount_code_detected(self):
        result = detect_sponsorship_signals("discount code: SAVE10")
        assert result["has_promo_code"] is True

    def test_sponsored_by_detected(self):
        result = detect_sponsorship_signals("This video is sponsored by NordVPN")
        assert result["has_sponsorship_mention"] is True

    def test_hashtag_ad_detected(self):
        result = detect_sponsorship_signals("Check it out! #ad #sponsored")
        assert result["has_sponsorship_mention"] is True

    def test_affiliate_link_detected(self):
        result = detect_sponsorship_signals("Check the affiliate link below")
        assert result["has_affiliate_link"] is True

    def test_bitly_url_detected(self):
        result = detect_sponsorship_signals("Get it here: https://bit.ly/abc123")
        assert result["has_affiliate_link"] is True

    def test_utm_tracking_url_detected(self):
        result = detect_sponsorship_signals("https://example.com/product?ref=creator123")
        assert result["has_affiliate_link"] is True

    def test_no_false_positives_on_clean_description(self):
        result = detect_sponsorship_signals(
            "In this video we explore the new game update. "
            "Like and subscribe for more content!"
        )
        assert result["has_promo_code"] is False
        assert result["has_affiliate_link"] is False
        assert result["has_sponsorship_mention"] is False

    def test_partnership_detected(self):
        result = detect_sponsorship_signals("Partnered with Razer for this build")
        assert result["has_sponsorship_mention"] is True

    def test_multiple_signals_in_one_description(self):
        result = detect_sponsorship_signals(
            "Sponsored by GamerSupps! Use code CREATOR for 10% off. "
            "Link: https://bit.ly/gsupps"
        )
        assert result["has_promo_code"] is True
        assert result["has_affiliate_link"] is True
        assert result["has_sponsorship_mention"] is True
        assert len(result["matched_patterns"]) >= 3

    # --- Self-promotion stoplist tests ---

    def test_patreon_link_not_counted_as_sponsorship(self):
        result = detect_sponsorship_signals(
            "Support me on https://patreon.com/mychannel?ref=description"
        )
        assert result["has_affiliate_link"] is False
        assert result["has_promo_code"] is False
        assert result["has_sponsorship_mention"] is False

    def test_discord_link_not_counted(self):
        result = detect_sponsorship_signals(
            "Join my Discord: https://discord.gg/mychannel?utm_source=yt"
        )
        assert result["has_affiliate_link"] is False

    def test_social_only_description_returns_no_signals(self):
        desc = (
            "Follow me:\n"
            "Twitter: https://twitter.com/me?ref=yt\n"
            "Instagram: https://instagram.com/me?utm_source=yt\n"
            "Discord: https://discord.gg/me?ref=desc\n"
            "Patreon: https://patreon.com/me?ref=desc\n"
            "TikTok: https://tiktok.com/@me?utm_source=yt\n"
        )
        result = detect_sponsorship_signals(desc)
        assert result["has_promo_code"] is False
        assert result["has_affiliate_link"] is False
        assert result["has_sponsorship_mention"] is False
        assert result["matched_patterns"] == []

    def test_real_sponsorship_plus_social_links(self):
        desc = (
            "This video is sponsored by NordVPN! "
            "Check out https://bit.ly/nordvpn-deal for 60% off.\n"
            "Follow me: https://twitter.com/me?ref=yt "
            "https://discord.gg/me?utm_source=yt "
            "https://patreon.com/me?ref=yt"
        )
        result = detect_sponsorship_signals(desc)
        assert result["has_sponsorship_mention"] is True
        assert result["has_affiliate_link"] is True
        # Social links should NOT add to matched_patterns as affiliate
        # We expect "sponsored by" + bit.ly match only
        social_pattern_count = sum(
            1 for p in result["matched_patterns"]
            if "twitter" in p.lower() or "discord" in p.lower() or "patreon" in p.lower()
        )
        assert social_pattern_count == 0

    def test_twitch_link_not_counted(self):
        result = detect_sponsorship_signals(
            "Watch live: https://twitch.tv/me?ref=yt"
        )
        assert result["has_affiliate_link"] is False

    def test_ko_fi_link_not_counted(self):
        result = detect_sponsorship_signals(
            "Tip me: https://ko-fi.com/me?utm_source=yt"
        )
        assert result["has_affiliate_link"] is False

    def test_reddit_link_not_counted(self):
        result = detect_sponsorship_signals(
            "Join the community: https://reddit.com/r/mychannel?ref=yt"
        )
        assert result["has_affiliate_link"] is False


# ---------------------------------------------------------------------------
# Upload cadence
# ---------------------------------------------------------------------------

class TestComputeUploadCadence:
    def test_empty_list(self):
        result = compute_upload_cadence([])
        assert result["cadence_days_median"] is None
        assert result["last_upload_days_ago"] is None

    def test_single_video(self):
        now = datetime.now(timezone.utc)
        result = compute_upload_cadence([now])
        assert result["cadence_days_median"] is None  # need >= 2 for cadence
        assert result["last_upload_days_ago"] is not None
        assert result["last_upload_days_ago"] < 1.0

    def test_regular_cadence(self):
        now = datetime.now(timezone.utc)
        dates = [now - timedelta(days=i * 7) for i in range(5)]
        result = compute_upload_cadence(dates)
        assert result["cadence_days_median"] == 7.0
        assert result["cadence_days_mean"] == 7.0
        assert result["last_upload_days_ago"] < 1.0

    def test_irregular_cadence(self):
        now = datetime.now(timezone.utc)
        dates = [
            now,
            now - timedelta(days=3),
            now - timedelta(days=10),
            now - timedelta(days=30),
        ]
        result = compute_upload_cadence(dates)
        # Gaps: 3, 7, 20 → median = 7.0
        assert result["cadence_days_median"] == 7.0

    def test_naive_datetimes_handled(self):
        """Naive datetimes (no tzinfo) should not crash."""
        now = datetime.utcnow()
        dates = [now, now - timedelta(days=5)]
        result = compute_upload_cadence(dates)
        assert result["cadence_days_median"] == 5.0


# ---------------------------------------------------------------------------
# Engagement depth
# ---------------------------------------------------------------------------

class TestComputeEngagementDepth:
    def test_empty_videos(self):
        result = compute_engagement_depth([])
        assert result["like_to_view_ratio"] is None
        assert result["comment_to_view_ratio"] is None
        assert result["sample_size"] == 0

    def test_zero_views_skipped(self):
        videos = [{"views": 0, "likes": 5, "comments": 1}]
        result = compute_engagement_depth(videos)
        assert result["sample_size"] == 0

    def test_single_video(self):
        videos = [{"views": 1000, "likes": 50, "comments": 10}]
        result = compute_engagement_depth(videos)
        assert result["like_to_view_ratio"] == 0.05
        assert result["comment_to_view_ratio"] == 0.01
        assert result["sample_size"] == 1

    def test_median_used_not_mean(self):
        """Median resists one viral outlier."""
        videos = [
            {"views": 1000, "likes": 50, "comments": 10},
            {"views": 1000, "likes": 40, "comments": 8},
            {"views": 1000000, "likes": 100000, "comments": 5000},  # outlier
        ]
        result = compute_engagement_depth(videos)
        # Median of [0.05, 0.04, 0.1] = 0.05
        assert result["like_to_view_ratio"] == 0.05
        # Median of [0.01, 0.008, 0.005] = 0.008
        assert result["comment_to_view_ratio"] == 0.008

    def test_missing_fields_default_to_zero(self):
        videos = [{"views": 1000}]  # no likes/comments keys
        result = compute_engagement_depth(videos)
        assert result["like_to_view_ratio"] == 0.0
        assert result["comment_to_view_ratio"] == 0.0


# ---------------------------------------------------------------------------
# View consistency
# ---------------------------------------------------------------------------

class TestComputeViewConsistency:
    def test_empty_list(self):
        result = compute_view_consistency([])
        assert result["recent_view_median"] is None
        assert result["recent_view_variance"] is None
        assert result["sample_size"] == 0

    def test_single_value(self):
        result = compute_view_consistency([5000])
        assert result["recent_view_median"] == 5000
        assert result["recent_view_variance"] is None  # need >= 2
        assert result["sample_size"] == 1

    def test_consistent_views_low_variance(self):
        views = [10000, 10500, 9800, 10200, 10100]
        result = compute_view_consistency(views)
        assert result["recent_view_median"] == 10100
        assert result["recent_view_variance"] is not None
        assert result["recent_view_cv"] is not None
        # CV should be small for consistent views.
        assert result["recent_view_cv"] < 0.1

    def test_spiky_views_high_variance(self):
        views = [1000, 1000, 1000, 1000000]  # one viral spike
        result = compute_view_consistency(views)
        assert result["recent_view_median"] == 1000
        assert result["recent_view_variance"] > 0
        # CV should be large due to the spike.
        assert result["recent_view_cv"] > 1.0

    def test_coefficient_of_variation_none_when_mean_zero(self):
        views = [0, 0, 0]
        result = compute_view_consistency(views)
        assert result["recent_view_cv"] is None
