"""Campaign CRUD, ROI recompute, validation, and ownership isolation."""


def _make_influencer(client):
    r = client.post("/api/v1/influencers/", json={
        "platform": "youtube", "platform_id": "chan_1", "username": "creator",
        "display_name": "Creator", "followers_count": 50000, "engagement_rate": 4.2,
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _make_campaign(client, influencer_id, **over):
    payload = {
        "name": "Launch", "budget": 1000.0,
        "start_date": "2026-01-01T00:00:00", "influencer_id": influencer_id,
    }
    payload.update(over)
    return client.post("/api/v1/campaigns/", json=payload)


def test_campaign_create_and_patch_recomputes_roi(auth_client):
    inf = _make_influencer(auth_client)
    r = _make_campaign(auth_client, inf)
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    assert r.json()["roi_percentage"] == 0.0

    patch = auth_client.patch(f"/api/v1/campaigns/{cid}", json={
        "views": 100000, "clicks": 2000, "conversions": 100,
        "revenue": 3000.0, "status": "completed",
    })
    assert patch.status_code == 200, patch.text
    body = patch.json()
    assert body["roi_percentage"] == 200.0
    assert body["cpm"] == 10.0
    assert body["cpc"] == 0.5
    assert body["cpa"] == 10.0


def test_invalid_status_rejected(auth_client):
    inf = _make_influencer(auth_client)
    cid = _make_campaign(auth_client, inf).json()["id"]
    r = auth_client.patch(f"/api/v1/campaigns/{cid}", json={"status": "bogus"})
    assert r.status_code == 422


def test_negative_budget_rejected(auth_client):
    inf = _make_influencer(auth_client)
    r = _make_campaign(auth_client, inf, budget=-5.0)
    assert r.status_code == 422


def test_campaign_requires_existing_influencer(auth_client):
    r = _make_campaign(auth_client, 99999)
    assert r.status_code == 404


def test_ownership_isolation(client):
    # User A creates an influencer + campaign.
    client.post("/api/v1/auth/register", json={
        "email": "a@x.com", "username": "usera", "password": "supersecret123"})
    ta = client.post("/api/v1/auth/login",
                     data={"username": "a@x.com", "password": "supersecret123"}).json()["access_token"]
    ha = {"Authorization": f"Bearer {ta}"}
    inf = client.post("/api/v1/influencers/", json={
        "platform": "youtube", "platform_id": "c2", "username": "c", "display_name": "C",
        "followers_count": 1000, "engagement_rate": 1.0}, headers=ha).json()["id"]
    cid = client.post("/api/v1/campaigns/", json={
        "name": "A", "budget": 100.0, "start_date": "2026-01-01T00:00:00",
        "influencer_id": inf}, headers=ha).json()["id"]

    # User B must not see or fetch it.
    client.post("/api/v1/auth/register", json={
        "email": "b@x.com", "username": "userb", "password": "supersecret123"})
    tb = client.post("/api/v1/auth/login",
                     data={"username": "b@x.com", "password": "supersecret123"}).json()["access_token"]
    hb = {"Authorization": f"Bearer {tb}"}
    assert client.get(f"/api/v1/campaigns/{cid}", headers=hb).status_code == 404
    assert client.get("/api/v1/campaigns/", headers=hb).json() == []


def test_ai_analysis_requires_metrics(auth_client):
    inf = _make_influencer(auth_client)
    cid = _make_campaign(auth_client, inf).json()["id"]
    # No actuals yet → 400.
    assert auth_client.get(f"/api/v1/campaigns/{cid}/ai-analysis").status_code == 400

    auth_client.patch(f"/api/v1/campaigns/{cid}",
                      json={"revenue": 3000.0, "status": "completed"})
    r = auth_client.get(f"/api/v1/campaigns/{cid}/ai-analysis")
    # With no GEMINI_API_KEY configured the endpoint degrades gracefully (200, null score).
    assert r.status_code == 200
    body = r.json()
    assert "score" in body and "insights" in body and "recommendations" in body


def test_dashboard_excludes_planning_from_avg_roi(auth_client):
    inf = _make_influencer(auth_client)
    # One completed (good ROI) + one planning (default zeros).
    cid = _make_campaign(auth_client, inf).json()["id"]
    auth_client.patch(f"/api/v1/campaigns/{cid}",
                      json={"revenue": 3000.0, "status": "completed"})
    _make_campaign(auth_client, inf, name="Draft")  # stays planning

    dash = auth_client.get("/api/v1/analytics/dashboard").json()
    assert dash["total_campaigns"] == 2
    assert dash["measurable_campaigns"] == 1
    # Average ROI reflects only the measurable (completed) campaign.
    assert dash["avg_roi_percentage"] == 200.0
