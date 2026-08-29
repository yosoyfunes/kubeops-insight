import base64
import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import urlencode, urlsplit

import httpx
from fastapi import HTTPException, Request, Response, status
from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.config.settings import Settings

SESSION_COOKIE_NAME = "koi_session"
OIDC_STATE_COOKIE_NAME = "koi_oidc_state"


def _sign(payload: str, secret: str) -> str:
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def create_session_token(username: str, settings: Settings, groups: list[str] | None = None) -> str:
    secret = settings.auth_session_secret or ""
    payload = {
        "sub": username,
        "exp": int(time.time()) + settings.auth_session_ttl_seconds,
        "groups": groups or [],
    }
    encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()
    return f"{encoded}.{_sign(encoded, secret)}"


def read_session_token(token: str, settings: Settings) -> dict[str, Any] | None:
    secret = settings.auth_session_secret or ""
    try:
        encoded, signature = token.split(".", 1)
    except ValueError:
        return None
    if not hmac.compare_digest(signature, _sign(encoded, secret)):
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(encoded.encode()).decode())
    except (json.JSONDecodeError, ValueError):
        return None
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    return payload


def verify_credentials(username: str, password: str, settings: Settings) -> bool:
    stored = settings.auth_password or ""
    return hmac.compare_digest(username, settings.auth_username) and hmac.compare_digest(
        password, stored
    )


def set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=settings.auth_session_ttl_seconds,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")


def create_oidc_state(settings: Settings, next_url: str = "/") -> str:
    secret = settings.auth_session_secret or ""
    serializer = URLSafeTimedSerializer(secret, salt="oidc-state")
    return serializer.dumps({"next": sanitize_next_path(next_url)})


def read_oidc_state(state: str, settings: Settings) -> dict[str, Any] | None:
    secret = settings.auth_session_secret or ""
    serializer = URLSafeTimedSerializer(secret, salt="oidc-state")
    try:
        payload = serializer.loads(state, max_age=600)
    except BadSignature:
        return None
    return payload if isinstance(payload, dict) else None


def set_oidc_state_cookie(response: Response, state: str, settings: Settings) -> None:
    response.set_cookie(
        OIDC_STATE_COOKIE_NAME,
        state,
        max_age=600,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_oidc_state_cookie(response: Response) -> None:
    response.delete_cookie(OIDC_STATE_COOKIE_NAME, path="/")


def sanitize_next_path(next_url: str | None) -> str:
    if not next_url:
        return "/"
    parsed = urlsplit(next_url)
    if parsed.scheme or parsed.netloc:
        return "/"
    if not parsed.path.startswith("/") or parsed.path.startswith("//"):
        return "/"
    if "\\" in next_url:
        return "/"
    safe_path = parsed.path or "/"
    return f"{safe_path}?{parsed.query}" if parsed.query else safe_path


def _oidc_http_error(detail: str, status_code: int) -> HTTPException:
    return HTTPException(status_code=status_code, detail=detail)


def _parse_json_response(response: httpx.Response, detail: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise _oidc_http_error(detail, status.HTTP_502_BAD_GATEWAY) from exc
    if not isinstance(payload, dict):
        raise _oidc_http_error(detail, status.HTTP_502_BAD_GATEWAY)
    return payload


async def oidc_discovery(settings: Settings) -> dict[str, Any]:
    if not settings.auth_oidc_issuer_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OIDC issuer is not configured")
    issuer = settings.auth_oidc_issuer_url.rstrip("/")
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            response = await client.get(f"{issuer}/.well-known/openid-configuration")
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise _oidc_http_error("OIDC discovery request failed", status.HTTP_502_BAD_GATEWAY) from exc
        return _parse_json_response(response, "OIDC discovery returned an invalid response")


async def build_oidc_authorization_url(settings: Settings, state: str) -> str:
    discovery = await oidc_discovery(settings)
    authorization_endpoint = discovery.get("authorization_endpoint")
    if not authorization_endpoint:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OIDC authorization endpoint is missing")
    params = {
        "client_id": settings.auth_oidc_client_id,
        "redirect_uri": settings.auth_oidc_redirect_uri,
        "response_type": "code",
        "scope": settings.auth_oidc_scopes,
        "state": state,
    }
    return f"{authorization_endpoint}?{urlencode(params)}"


async def exchange_oidc_code(code: str, settings: Settings) -> dict[str, Any]:
    discovery = await oidc_discovery(settings)
    token_endpoint = discovery.get("token_endpoint")
    if not token_endpoint:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OIDC token endpoint is missing")
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.auth_oidc_redirect_uri,
        "client_id": settings.auth_oidc_client_id,
        "client_secret": settings.auth_oidc_client_secret,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.post(token_endpoint, data=data)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED}:
                raise _oidc_http_error("OIDC code exchange failed", status.HTTP_401_UNAUTHORIZED) from exc
            raise _oidc_http_error("OIDC token endpoint request failed", status.HTTP_502_BAD_GATEWAY) from exc
        except httpx.HTTPError as exc:
            raise _oidc_http_error("OIDC token endpoint request failed", status.HTTP_502_BAD_GATEWAY) from exc
        return _parse_json_response(response, "OIDC token endpoint returned an invalid response")


async def fetch_oidc_userinfo(access_token: str, settings: Settings) -> dict[str, Any]:
    discovery = await oidc_discovery(settings)
    userinfo_endpoint = discovery.get("userinfo_endpoint")
    if not userinfo_endpoint:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OIDC userinfo endpoint is missing")
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            response = await client.get(
                userinfo_endpoint, headers={"Authorization": f"Bearer {access_token}"}
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == status.HTTP_401_UNAUTHORIZED:
                raise _oidc_http_error("OIDC userinfo request failed", status.HTTP_401_UNAUTHORIZED) from exc
            raise _oidc_http_error("OIDC userinfo request failed", status.HTTP_502_BAD_GATEWAY) from exc
        except httpx.HTTPError as exc:
            raise _oidc_http_error("OIDC userinfo request failed", status.HTTP_502_BAD_GATEWAY) from exc
        return _parse_json_response(response, "OIDC userinfo endpoint returned an invalid response")


def current_user(request: Request, settings: Settings) -> str | None:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    payload = read_session_token(token, settings)
    subject = payload.get("sub") if payload else None
    return subject if isinstance(subject, str) else None


def require_user(request: Request, settings: Settings) -> str:
    user = current_user(request, settings)
    if user:
        return user
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
