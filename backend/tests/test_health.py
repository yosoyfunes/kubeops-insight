import httpx
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.auth import create_oidc_state, read_oidc_state
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
    settings = Settings(auth_password="secret", auth_session_secret="test-secret", auth_cookie_secure=False)
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
        auth_cookie_secure=False,
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
        auth_cookie_secure=True,
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
    assert "Secure" in response.headers["set-cookie"]


def test_oidc_login_sanitizes_external_next_url(monkeypatch) -> None:
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
    response = client.get(
        "/api/v1/auth/oidc/login",
        params={"next_url": "https://evil.example/steal"},
        follow_redirects=False,
    )

    state = response.cookies.get("koi_oidc_state")
    assert state is not None
    payload = read_oidc_state(state, settings)
    assert payload == {"next": "/"}


def test_login_cookie_secure_defaults_to_true(monkeypatch) -> None:
    settings = Settings(auth_password="secret", auth_session_secret="test-secret", auth_cookie_secure=True)
    monkeypatch.setattr("app.api.routes.get_settings", lambda: settings)

    auth_client = TestClient(app)
    response = auth_client.post("/api/v1/auth/login", json={"username": "admin", "password": "secret"})

    assert response.status_code == 200
    assert "Secure" in response.headers["set-cookie"]


def test_login_cookie_can_disable_secure_for_local_dev(monkeypatch) -> None:
    settings = Settings(auth_password="secret", auth_session_secret="test-secret", auth_cookie_secure=False)
    monkeypatch.setattr("app.api.routes.get_settings", lambda: settings)

    auth_client = TestClient(app)
    response = auth_client.post("/api/v1/auth/login", json={"username": "admin", "password": "secret"})

    assert response.status_code == 200
    assert "Secure" not in response.headers["set-cookie"]


def test_oidc_callback_redirects_to_sanitized_path(monkeypatch) -> None:
    settings = Settings(
        auth_password="secret",
        auth_oidc_enabled=True,
        auth_oidc_issuer_url="https://example.okta.com/oauth2/default",
        auth_oidc_client_id="client-id",
        auth_oidc_client_secret="client-secret",
        auth_oidc_redirect_uri="https://kubeops.example.com/api/v1/auth/oidc/callback",
        auth_session_secret="test-secret",
    )

    async def fake_exchange(code: str, settings: Settings) -> dict[str, str]:
        return {"access_token": "access-token"}

    async def fake_userinfo(access_token: str, settings: Settings) -> dict[str, object]:
        return {"email": "user@example.com", "groups": ["sre"]}

    state = create_oidc_state(settings, "https://evil.example/post-auth")
    monkeypatch.setattr("app.api.routes.get_settings", lambda: settings)
    monkeypatch.setattr("app.api.routes.exchange_oidc_code", fake_exchange)
    monkeypatch.setattr("app.api.routes.fetch_oidc_userinfo", fake_userinfo)

    auth_client = TestClient(app)
    auth_client.cookies.set("koi_oidc_state", state)
    response = auth_client.get(
        "/api/v1/auth/oidc/callback",
        params={"code": "valid-code", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 307
    assert response.headers["location"] == "/"


class _FakeAsyncClient:
    def __init__(self, response=None, error: Exception | None = None, method: str = "get", timeout: int = 15):
        self.response = response
        self.error = error
        self.method = method

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, *args, **kwargs):
        if self.error is not None:
            raise self.error
        return self.response

    async def post(self, *args, **kwargs):
        if self.error is not None:
            raise self.error
        return self.response


def test_oidc_discovery_network_errors_return_502(monkeypatch) -> None:
    settings = Settings(auth_session_secret="test-secret", auth_oidc_issuer_url="https://issuer.example")
    monkeypatch.setattr(
        "app.auth.httpx.AsyncClient",
        lambda timeout=15: _FakeAsyncClient(error=httpx.ConnectError("boom"), timeout=timeout),
    )

    from app.auth import oidc_discovery

    try:
        import asyncio

        asyncio.run(oidc_discovery(settings))
    except HTTPException as exc:
        assert exc.status_code == 502
        assert exc.detail == "OIDC discovery request failed"
    else:
        raise AssertionError("Expected OIDC discovery to fail")


def test_oidc_code_exchange_invalid_code_returns_401(monkeypatch) -> None:
    settings = Settings(
        auth_session_secret="test-secret",
        auth_oidc_issuer_url="https://issuer.example",
        auth_oidc_client_id="client-id",
        auth_oidc_client_secret="client-secret",
        auth_oidc_redirect_uri="https://kubeops.example.com/api/v1/auth/oidc/callback",
    )

    async def fake_discovery(settings: Settings) -> dict[str, str]:
        return {"token_endpoint": "https://issuer.example/token"}

    request = httpx.Request("POST", "https://issuer.example/token")
    response = httpx.Response(401, request=request)
    monkeypatch.setattr("app.auth.oidc_discovery", fake_discovery)
    monkeypatch.setattr(
        "app.auth.httpx.AsyncClient",
        lambda timeout=30: _FakeAsyncClient(response=response, timeout=timeout),
    )

    from app.auth import exchange_oidc_code

    try:
        import asyncio

        asyncio.run(exchange_oidc_code("bad-code", settings))
    except HTTPException as exc:
        assert exc.status_code == 401
        assert exc.detail == "OIDC code exchange failed"
    else:
        raise AssertionError("Expected OIDC code exchange to fail")
