"""End-to-end tests for the AI Campaign Intelligence layer:
analyze -> match -> shortlist -> tasks -> brief -> content -> performance ->
analyze-performance -> report, plus ownership isolation.

Runs fully offline (no GEMINI_API_KEY / YOUTUBE_API_KEY, per conftest), so
every AI service exercises its deterministic fallback path.
"""

from datetime import datetime, timedelta

from database import get_db
import database
from models import BrandProfile, Influencer, InfluencerAnalysis


def _seed_influencer(db, *, username="creator1", followers_count=50_000, category="gaming", country="US"):
    inf = Influencer(
        platform="youtube", platform_id=f"UC_{username}", username=username,
        display_name=username.title(), followers_count=followers_count,
        engagement_rate=5.0, category=category, country=country,
        business_email="creator@example.com", talent_agency=False,
        enrichment_signals={
            "upload_cadence": {"last_upload_days_ago": 10.0},
            "view_consistency": {"recent_view_median": 15_000, "recent_view_cv": 0.25, "sample_size": 10},
            "engagement_depth": {"like_to_view_ratio": 0.06, "comment_to_view_ratio": 0.008, "sample_size": 10},
            "subscriber_count": followers_count,
        },
    )
    db.add(inf)
    db.flush()
    db.refresh(inf)
    return inf


def _seed_analysis(db, influencer_id, *, trust_score=75.0, sponsorship_score=70.0, content_tone="friendly"):
    a = InfluencerAnalysis(
        influencer_id=influencer_id,
        trust_breakdown={"status": "analyzed", "composite_trust_score": trust_score, "confidence": "high"},
        sponsorship_profile={
            "status": "analyzed", "composite_sponsorship_score": sponsorship_score, "confidence": "high",
            "maturity": {"label": "mature", "score": 80.0, "sponsored_ratio": 0.3},
        },
        overall_match_score=0.0,
        content_style_match_score=60.0, audience_match_score=55.0,
        engagement_quality_score=70.0, brand_safety_score=80.0,
        ai_analysis_summary="Test analysis", content_tone=content_tone,
        top_video_themes=["gaming", "reviews"],
    )
    db.add(a)
    db.flush()
    db.refresh(a)
    return a


def _seed_brand_profile(db, user_id):
    bp = BrandProfile(
        user_id=user_id, name="TestBrand",
        aggressive_score=5.0, creative_score=5.0, humorous_score=5.0,
        professional_score=5.0, edgy_score=5.0,
        target_age_min=18, target_age_max=35, target_countries=["US"],
        preferred_categories=["gaming"], target_aov=40.0,
    )
    db.add(bp)
    db.flush()
    db.refresh(bp)
    return bp


def _make_campaign(auth_client, influencer_id, **over):
    payload = {
        "name": "Gaming Laptop Launch", "budget": 5000.0,
        "start_date": "2026-01-01T00:00:00", "influencer_id": influencer_id,
    }
    payload.update(over)
    r = auth_client.post("/api/v1/campaigns/", json=payload)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _get_user_id(auth_client):
    return auth_client.get("/api/v1/auth/me").json()["id"]


def test_full_campaign_intelligence_flow(auth_client):
    db = next(get_db())
    try:
        user_id = _get_user_id(auth_client)
        inf = _seed_influencer(db)
        _seed_analysis(db, inf.id)
        bp = _seed_brand_profile(db, user_id)
        db.commit()
        inf_id, bp_id = inf.id, bp.id
    finally:
        db.close()

    cid = _make_campaign(auth_client, inf_id)

    # 1) AI Campaign Builder — natural language + structured override
    r = auth_client.post(f"/api/v1/campaigns/{cid}/ai/analyze", json={
        "raw_input": "Launch a gaming laptop for 18-30 year olds in the US.",
        "budget": 5000.0,
    })
    assert r.status_code == 200, r.text
    understanding = r.json()
    assert understanding["budget"] == 5000.0
    assert understanding["source"] in ("manual", "gemini+manual_overrides")

    # 2) AI Creator Matching
    r = auth_client.post(f"/api/v1/campaigns/{cid}/ai/match-creators", json={
        "brand_profile_id": bp_id,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] >= 1
    match = next(m for m in body["matches"] if m["influencer_id"] == inf_id)
    assert match["trust_score"] == 75.0          # intrinsic, unrelated to match_score
    assert match["match_score"] is not None
    assert match["why"]
    assert match["category_fit"] == 100.0        # both "gaming"

    # 3) List stored matches with a filter
    r = auth_client.get(f"/api/v1/campaigns/{cid}/matches", params={"tier": match["tier"]})
    assert r.status_code == 200, r.text
    assert any(m["influencer_id"] == inf_id for m in r.json()["matches"])

    # 4) Shortlist
    r = auth_client.post(f"/api/v1/campaigns/{cid}/shortlist", json={"influencer_ids": [inf_id]})
    assert r.status_code == 201, r.text
    creators = r.json()
    assert creators[0]["status"] == "shortlisted"
    assert creators[0]["match_score"] == match["match_score"]

    # 5) List campaign creators
    r = auth_client.get(f"/api/v1/campaigns/{cid}/creators")
    assert r.status_code == 200
    assert len(r.json()) == 1

    # 6) Update status + actuals
    r = auth_client.patch(f"/api/v1/campaigns/{cid}/creators/{inf_id}", json={
        "status": "live", "views": 200_000, "clicks": 4000, "conversions": 150,
        "revenue": 9000.0, "spend": 3000.0,
    })
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "live"

    # Invalid status is rejected
    r = auth_client.patch(f"/api/v1/campaigns/{cid}/creators/{inf_id}", json={"status": "bogus"})
    assert r.status_code == 422

    # 7) Tasks
    r = auth_client.post(f"/api/v1/campaigns/{cid}/creators/{inf_id}/tasks", json={
        "task_type": "brief_sent", "deadline": (datetime.utcnow() - timedelta(days=1)).isoformat(),
    })
    assert r.status_code == 201, r.text
    assert r.json()["is_overdue"] is True

    r = auth_client.get(f"/api/v1/campaigns/{cid}/creators/{inf_id}/tasks")
    assert r.status_code == 200 and len(r.json()) == 1

    # Invalid task_type rejected
    r = auth_client.post(f"/api/v1/campaigns/{cid}/creators/{inf_id}/tasks", json={"task_type": "not_a_type"})
    assert r.status_code == 422

    # 8) AI Brief (deterministic fallback — no GEMINI_API_KEY in test env)
    r = auth_client.post(f"/api/v1/campaigns/{cid}/brief", json={"influencer_ids": [inf_id]})
    assert r.status_code == 200, r.text
    brief = r.json()[0]
    assert brief["source"] == "deterministic_template"
    assert brief["objective"]
    assert len(brief["talking_points"]) > 0

    r = auth_client.get(f"/api/v1/campaigns/{cid}/brief/{inf_id}")
    assert r.status_code == 200
    assert r.json()["hook"] == brief["hook"]

    # 9) Content Studio
    r = auth_client.post("/api/v1/campaigns/content/generate", json={
        "influencer_id": inf_id, "campaign_id": cid, "content_type": "youtube_title",
    })
    assert r.status_code == 201, r.text
    content = r.json()
    assert content["title"]
    assert content["source"] == "deterministic_template"

    # 10) Performance aggregation from real actuals
    r = auth_client.get(f"/api/v1/campaigns/{cid}/performance")
    assert r.status_code == 200, r.text
    perf = r.json()
    assert perf["views"] == 200_000
    assert perf["revenue"] == 9000.0
    assert perf["roi_percentage"] == 200.0
    assert perf["data_completeness"] == "full"

    # 11) AI Performance Analyst — grounded, no fabrication
    r = auth_client.post(f"/api/v1/campaigns/{cid}/ai/analyze-performance")
    assert r.status_code == 200, r.text
    analysis = r.json()
    assert analysis["source"] == "deterministic"
    assert "creator1" in analysis["what_happened"] or "200,000" in analysis["what_happened"]
    assert len(analysis["insights"]) == 3

    # 12) Campaign report assembles everything, no fabricated numbers
    r = auth_client.get(f"/api/v1/campaigns/{cid}/report")
    assert r.status_code == 200, r.text
    report = r.json()
    assert report["campaign_performance"]["revenue"] == 9000.0
    assert len(report["creator_intelligence"]) == 1
    assert report["key_insights"]


def test_performance_reports_insufficient_data_without_actuals(auth_client):
    db = next(get_db())
    try:
        inf = _seed_influencer(db, username="noactuals")
        db.commit()
        inf_id = inf.id
    finally:
        db.close()

    cid = _make_campaign(auth_client, inf_id)
    r = auth_client.get(f"/api/v1/campaigns/{cid}/performance")
    assert r.status_code == 200
    perf = r.json()
    assert perf["data_completeness"] == "none"
    assert perf["roi_percentage"] is None

    r = auth_client.post(f"/api/v1/campaigns/{cid}/ai/analyze-performance")
    assert r.status_code == 200
    body = r.json()
    assert "Insufficient data" in body["what_happened"]
    assert "Insufficient data" in body["why"]


def test_match_creators_requires_owned_brand_profile(auth_client):
    db = next(get_db())
    try:
        inf = _seed_influencer(db, username="creator2")
        db.commit()
        inf_id = inf.id
    finally:
        db.close()
    cid = _make_campaign(auth_client, inf_id)
    r = auth_client.post(f"/api/v1/campaigns/{cid}/ai/match-creators", json={"brand_profile_id": 999999})
    assert r.status_code == 404


def test_ownership_isolation_for_campaign_intelligence(client):
    client.post("/api/v1/auth/register", json={"email": "a2@x.com", "username": "a2user", "password": "supersecret123"})
    ta = client.post("/api/v1/auth/login", data={"username": "a2@x.com", "password": "supersecret123"}).json()["access_token"]
    ha = {"Authorization": f"Bearer {ta}"}

    db = next(get_db())
    try:
        inf = _seed_influencer(db, username="creator3")
        db.commit()
        inf_id = inf.id
    finally:
        db.close()

    cid = client.post("/api/v1/campaigns/", json={
        "name": "A", "budget": 100.0, "start_date": "2026-01-01T00:00:00",
        "influencer_id": inf_id,
    }, headers=ha).json()["id"]

    client.post("/api/v1/auth/register", json={"email": "b2@x.com", "username": "b2user", "password": "supersecret123"})
    tb = client.post("/api/v1/auth/login", data={"username": "b2@x.com", "password": "supersecret123"}).json()["access_token"]
    hb = {"Authorization": f"Bearer {tb}"}

    assert client.get(f"/api/v1/campaigns/{cid}/creators", headers=hb).status_code == 404
    assert client.get(f"/api/v1/campaigns/{cid}/performance", headers=hb).status_code == 404
    assert client.get(f"/api/v1/campaigns/{cid}/report", headers=hb).status_code == 404
