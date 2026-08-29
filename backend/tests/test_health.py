from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready() -> None:
    response = client.get("/api/v1/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_cluster_summary_uses_live_kubernetes(monkeypatch) -> None:
    async def fake_summary() -> dict[str, object]:
        return {"mode": "live", "cluster": {"status": "healthy"}}

    monkeypatch.setattr("app.api.routes.kubernetes_service.get_cluster_summary", fake_summary)
    settings = Settings(auth_password="secret", auth_session_secret="test-secret")
    monkeypatch.setattr("app.main.get_settings", lambda: settings)
    monkeypatch.setattr("app.api.routes.get_settings", lambda: settings)

    auth_client = TestClient(app)
    login = auth_client.post("/api/v1/auth/login", json={"username": "admin", "password": "secret"})
    assert login.status_code == 200
    response = auth_client.get("/api/v1/cluster/summary")
    assert response.status_code == 200
    assert response.json()["mode"] == "live"


def test_auth_blocks_protected_api_when_enabled(monkeypatch) -> None:
    settings = Settings(auth_password="secret", auth_session_secret="test-secret")
    monkeypatch.setattr("app.main.get_settings", lambda: settings)
    auth_client = TestClient(app)
    response = auth_client.get("/api/v1/cluster/summary")
    assert response.status_code == 401


def test_auth_login_allows_protected_api(monkeypatch) -> None:
    settings = Settings(
        auth_username="admin",
        auth_password="secret",
        auth_session_secret="test-secret",
    )
    async def fake_summary() -> dict[str, object]:
        return {"mode": "live", "cluster": {"status": "healthy"}}

    monkeypatch.setattr("app.main.get_settings", lambda: settings)
    monkeypatch.setattr("app.api.routes.get_settings", lambda: settings)
    monkeypatch.setattr("app.api.routes.kubernetes_service.get_cluster_summary", fake_summary)
    auth_client = TestClient(app)
    login = auth_client.post("/api/v1/auth/login", json={"username": "admin", "password": "secret"})
    assert login.status_code == 200
    response = auth_client.get("/api/v1/cluster/summary")
    assert response.status_code == 200


def test_auth_me_reports_oidc_enabled(monkeypatch) -> None:
    settings = Settings(auth_password="secret", auth_oidc_enabled=True, auth_session_secret="test-secret")
    monkeypatch.setattr("app.api.routes.get_settings", lambda: settings)
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 200
    payload = response.json()
    assert payload["oidcEnabled"] is True
    assert payload["localLoginEnabled"] is True


def test_oidc_login_redirects_to_provider(monkeypatch) -> None:
    settings = Settings(
        auth_password="secret",
        auth_oidc_enabled=True,
        auth_oidc_issuer_url="https://example.okta.com/oauth2/default",
        auth_oidc_client_id="client-id",
        auth_oidc_client_secret="client-secret",
        auth_oidc_redirect_uri="https://kubeops.example.com/api/v1/auth/oidc/callback",
        auth_session_secret="test-secret",
    )

    async def fake_authorization_url(settings, state: str) -> str:
        return f"https://example.okta.com/oauth2/default/v1/authorize?state={state}"

    monkeypatch.setattr("app.api.routes.get_settings", lambda: settings)
    monkeypatch.setattr("app.api.routes.build_oidc_authorization_url", fake_authorization_url)
    response = client.get("/api/v1/auth/oidc/login", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"].startswith("https://example.okta.com")
