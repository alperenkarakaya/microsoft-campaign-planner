"""Auth flow + the security hardening fixes (C2, C3, C4)."""


def _register(client, email="a@b.com", username="alice", password="supersecret123"):
    return client.post("/api/v1/auth/register", json={
        "email": email, "username": username, "password": password})


def test_register_and_login_and_me(client):
    r = _register(client)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["email"] == "a@b.com"
    assert "hashed_password" not in body

    login = client.post("/api/v1/auth/login",
                        data={"username": "a@b.com", "password": "supersecret123"})
    assert login.status_code == 200
    token = login.json()["access_token"]

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["username"] == "alice"


def test_duplicate_email_rejected(client):
    _register(client)
    r = _register(client, username="alice2")
    assert r.status_code == 400


def test_short_password_rejected(client):
    r = _register(client, password="short")
    assert r.status_code == 422  # schema min_length=8


def test_wrong_password_is_401(client):
    _register(client)
    r = client.post("/api/v1/auth/login",
                    data={"username": "a@b.com", "password": "nope"})
    assert r.status_code == 401


def test_malformed_token_returns_401_not_500(client):
    # C2: int(sub) on a non-numeric token must not crash the handler.
    r = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer garbage.token.value"})
    assert r.status_code == 401


def test_protected_route_requires_token(client):
    assert client.get("/api/v1/campaigns/").status_code == 401
