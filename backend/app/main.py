from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.api.routes import limiter, router
from app.auth import require_user
from app.config.settings import get_settings


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        protected_prefixes = (
            settings.api_prefix,
            "/ai",
            "/chat",
            "/cluster",
            "/daemonsets",
            "/deployments",
            "/events",
            "/findings",
            "/ingresses",
            "/jobs",
            "/metrics",
            "/namespaces",
            "/nodes",
            "/pods",
            "/pvcs",
            "/services",
            "/statefulsets",
            "/workloads",
        )
        public_paths = {
            "/health",
            "/ready",
            f"{settings.api_prefix}/health",
            f"{settings.api_prefix}/ready",
            f"{settings.api_prefix}/auth/login",
            f"{settings.api_prefix}/auth/logout",
            f"{settings.api_prefix}/auth/me",
            f"{settings.api_prefix}/auth/oidc/login",
            f"{settings.api_prefix}/auth/oidc/callback",
        }
        if request.url.path.startswith(protected_prefixes) and request.url.path not in public_paths:
            try:
                require_user(request, settings)
            except HTTPException:
                return JSONResponse({"detail": "Authentication required"}, status_code=401)
        return await call_next(request)


def _validate_auth_config(settings) -> None:
    """Validate auth configuration at startup.

    Password and session secret are required.
    These must be provided via environment variables or .env file - never
    hardcoded. This validation runs once at startup so misconfiguration
    fails early with a clear message, not silently at login time.
    """
    missing = []
    if not settings.auth_password:
        missing.append("KOI_AUTH_PASSWORD")
    if not settings.auth_session_secret:
        missing.append("KOI_AUTH_SESSION_SECRET")
    if missing:
        msg = (
            f"Auth is enabled but required secrets are not configured: {', '.join(missing)}. "
            "Set these as environment variables or in backend/.env. "
            "See backend/.env.example for reference."
        )
        raise RuntimeError(msg)


def create_app() -> FastAPI:
    settings = get_settings()
    _validate_auth_config(settings)
    app = FastAPI(title=settings.app_name, version="0.1.0")

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(AuthMiddleware)

    app.include_router(router, prefix=settings.api_prefix)
    app.include_router(router)
    return app


app = create_app()
