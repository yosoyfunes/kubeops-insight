from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.api.routes import router
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
        if settings.auth_enabled and request.url.path.startswith(protected_prefixes) and request.url.path not in public_paths:
            try:
                require_user(request, settings)
            except HTTPException:
                return JSONResponse({"detail": "Authentication required"}, status_code=401)
        return await call_next(request)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0")

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
