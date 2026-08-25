"""AI Partnership Assistant — grounded, deterministic-fallback in tests
(no GEMINI_API_KEY per conftest)."""

from database import get_db
from models import Influencer, InfluencerAnalysis


def _seed_tiered_influencer(db):
    inf = Influencer(
        platform="youtube", platform_id="UC_assistant", username="assistant_creator",
        display_name="Assistant Creator", followers_count=40_000, engagement_rate=4.0,
        category="gaming", country="US",
    )
    db.add(inf)
    db.flush()
    db.refresh(inf)
    a = InfluencerAnalysis(
        influencer_id=inf.id,
        trust_breakdown={"status": "analyzed", "composite_trust_score": 65.0, "confidence": "high"},
        overall_match_score=0.0,
        content_style_match_score=60.0, audience_match_score=55.0,
        engagement_quality_score=70.0, brand_safety_score=80.0,
        ai_analysis_summary="Test", content_tone="friendly", top_video_themes=[],
    )
    db.add(a)
    db.commit()
    db.refresh(inf)
    return inf.id


def test_requires_auth(client):
    r = client.post("/api/v1/assistant/query", json={"query": "test"})
    assert r.status_code == 401


def test_assistant_grounds_on_real_roster_data(auth_client):
    db = next(get_db())
    try:
        _seed_tiered_influencer(db)
    finally:
        db.close()

    r = auth_client.post("/api/v1/assistant/query", json={"query": "Who are the best creators?"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == "deterministic_fallback"  # no GEMINI_API_KEY in test env
    assert body["grounded_on"]["creators"]
    assert any(c["display_name"] == "Assistant Creator" for c in body["grounded_on"]["creators"])


def test_assistant_empty_workspace_says_no_data(auth_client):
    r = auth_client.post("/api/v1/assistant/query", json={"query": "Who should I contact?"})
    assert r.status_code == 200
    body = r.json()
    assert body["grounded_on"]["creators"] == []
    assert "No matching data" in body["answer"]
