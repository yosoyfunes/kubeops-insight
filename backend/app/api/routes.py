from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.ai.service import ai_status, analyze_cluster, chat
from app.auth import (
    build_oidc_authorization_url,
    clear_oidc_state_cookie,
    clear_session_cookie,
    create_oidc_state,
    create_session_token,
    current_user,
    exchange_oidc_code,
    fetch_oidc_userinfo,
    read_oidc_state,
    set_oidc_state_cookie,
    set_session_cookie,
    verify_credentials,
)
from app.config.settings import get_settings
from app.kubernetes import service as kubernetes_service
from app.metrics.provider import get_metrics_summary

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


class ChatRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    namespace: str | None = None


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)


@router.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready", tags=["system"])
async def ready() -> dict[str, str]:
    settings = get_settings()
    if settings.llm_provider not in {"bedrock", "openai-compatible"}:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="LLM provider is not configured")
    return {"status": "ready", "provider": settings.llm_provider}


@router.get("/auth/me", tags=["auth"])
async def auth_me(request: Request) -> dict[str, object]:
    settings = get_settings()
    user = current_user(request, settings)
    return {
        "authenticated": bool(user),
        "username": user,
        "oidcEnabled": settings.auth_oidc_enabled,
        "localLoginEnabled": bool(settings.auth_password),
    }


@router.post("/auth/login", tags=["auth"])
@limiter.limit("10/minute")
async def auth_login(request: Request, payload: LoginRequest, response: Response) -> dict[str, object]:
    settings = get_settings()
    if not verify_credentials(payload.username, payload.password, settings):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    set_session_cookie(response, create_session_token(payload.username, settings), settings)
    return {"authenticated": True, "username": payload.username}


@router.post("/auth/logout", tags=["auth"])
async def auth_logout(response: Response) -> dict[str, bool]:
    clear_session_cookie(response)
    return {"authenticated": False}


@router.get("/auth/oidc/login", tags=["auth"])
async def auth_oidc_login(next_url: str = "/") -> RedirectResponse:
    settings = get_settings()
    if not settings.auth_oidc_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OIDC is not enabled")
    if not settings.auth_oidc_client_id or not settings.auth_oidc_client_secret or not settings.auth_oidc_redirect_uri:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OIDC client is not configured")
    state = create_oidc_state(settings, next_url)
    redirect = RedirectResponse(await build_oidc_authorization_url(settings, state))
    set_oidc_state_cookie(redirect, state)
    return redirect


@router.get("/auth/oidc/callback", tags=["auth"])
async def auth_oidc_callback(request: Request, code: str, state: str) -> RedirectResponse:
    settings = get_settings()
    expected_state = request.cookies.get("koi_oidc_state")
    if not expected_state or expected_state != state:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid OIDC state")
    state_payload = read_oidc_state(state, settings)
    if not state_payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Expired OIDC state")
    token_response = await exchange_oidc_code(code, settings)
    access_token = token_response.get("access_token")
    if not isinstance(access_token, str):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="OIDC token response missing access token")
    userinfo = await fetch_oidc_userinfo(access_token, settings)
    username = userinfo.get(settings.auth_oidc_username_claim) or userinfo.get("email") or userinfo.get("sub")
    if not isinstance(username, str) or not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="OIDC user identity is missing")
    raw_groups = userinfo.get(settings.auth_oidc_groups_claim, [])
    groups = raw_groups if isinstance(raw_groups, list) else []
    redirect = RedirectResponse(str(state_payload.get("next") or "/"))
    set_session_cookie(redirect, create_session_token(username, settings, [str(group) for group in groups]), settings)
    clear_oidc_state_cookie(redirect)
    return redirect


@router.get("/cluster/summary", tags=["kubernetes"])
async def cluster_summary() -> dict[str, object]:
    return await kubernetes_service.get_cluster_summary()


@router.get("/namespaces", tags=["kubernetes"])
async def namespaces() -> list[dict[str, object]]:
    return await kubernetes_service.list_namespaces()


@router.get("/namespaces/{namespace}/summary", tags=["kubernetes"])
async def namespace_summary(namespace: str) -> dict[str, object]:
    return await kubernetes_service.get_namespace_summary(namespace)


@router.get("/nodes", tags=["kubernetes"])
async def nodes() -> list[dict[str, object]]:
    return await kubernetes_service.list_nodes()


@router.get("/pods", tags=["kubernetes"])
async def pods(namespace: str | None = None) -> list[dict[str, object]]:
    return await kubernetes_service.list_pods(namespace)


@router.get("/pods/{namespace}/{name}", tags=["kubernetes"])
async def pod(namespace: str, name: str) -> dict[str, object]:
    return await kubernetes_service.get_pod(namespace, name)


@router.get("/deployments", tags=["kubernetes"])
async def deployments(namespace: str | None = None) -> list[dict[str, object]]:
    return await kubernetes_service.list_deployments(namespace)


@router.get("/statefulsets", tags=["kubernetes"])
async def statefulsets(namespace: str | None = None) -> list[dict[str, object]]:
    return await kubernetes_service.list_statefulsets(namespace)


@router.get("/daemonsets", tags=["kubernetes"])
async def daemonsets(namespace: str | None = None) -> list[dict[str, object]]:
    return await kubernetes_service.list_daemonsets(namespace)


@router.get("/jobs", tags=["kubernetes"])
async def jobs(namespace: str | None = None) -> list[dict[str, object]]:
    return await kubernetes_service.list_jobs(namespace)


@router.get("/services", tags=["kubernetes"])
async def services(namespace: str | None = None) -> list[dict[str, object]]:
    return await kubernetes_service.list_services(namespace)


@router.get("/pvcs", tags=["kubernetes"])
async def pvcs(namespace: str | None = None) -> list[dict[str, object]]:
    return await kubernetes_service.list_pvcs(namespace)


@router.get("/ingresses", tags=["kubernetes"])
async def ingresses(namespace: str | None = None) -> list[dict[str, object]]:
    return await kubernetes_service.list_ingresses(namespace)


@router.get("/events", tags=["kubernetes"])
async def events(
    namespace: str | None = None, limit: int = 50, minutes: int = 60
) -> list[dict[str, object]]:
    return await kubernetes_service.list_events(namespace, limit, minutes)


@router.get("/workloads", tags=["kubernetes"])
async def workloads(namespace: str | None = None) -> dict[str, object]:
    return await kubernetes_service.get_workloads(namespace)


@router.get("/findings", tags=["diagnostics"])
async def findings() -> list[dict[str, object]]:
    return await kubernetes_service.get_findings()


@router.post("/ai/analyze", tags=["ai"])
async def ai_analyze(namespace: str | None = None) -> dict[str, object]:
    return await analyze_cluster(namespace)


@router.get("/ai/status", tags=["ai"])
async def ai_status_route() -> dict[str, object]:
    return ai_status()


@router.post("/chat", tags=["ai"])
async def ai_chat(request: ChatRequest) -> dict[str, object]:
    return await chat(request.question, request.namespace)


@router.get("/metrics/summary", tags=["metrics"])
async def metrics_summary() -> dict[str, object]:
    return await get_metrics_summary()
