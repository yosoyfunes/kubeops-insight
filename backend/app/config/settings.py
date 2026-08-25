from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "KubeOps Insight"
    api_prefix: str = "/api/v1"
    kubernetes_mode: str = "auto"
    cache_ttl_seconds: int = 15
    cors_origins: list[str] = ["http://localhost:5173"]
    llm_provider: str = "bedrock"
    bedrock_region: str = "us-east-1"
    bedrock_model_id: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    bedrock_max_tokens: int = 1800
    bedrock_temperature: float = 0
    aws_profile: str | None = None
    openai_compatible_base_url: str | None = None
    openai_compatible_model: str | None = None
    openai_compatible_api_key: str | None = None
    ai_cache_ttl_seconds: int = 120
    ai_max_findings: int = 12
    ai_max_resources: int = 20
    ai_max_events: int = 10
    ai_max_tools_per_chat: int = 16
    ai_max_log_tail_lines: int = 50
    agent_max_cycles: int = 5
    agent_timeout_seconds: int = 30
    agent_max_input_tokens: int = 25_000
    agent_max_output_tokens: int = 2_000
    agent_log_max_lines: int = 200
    agent_log_max_characters: int = 20_000
    agent_cost_enabled: bool = True
    agent_max_estimated_cost_per_request: float = 0.10
    auth_enabled: bool = False
    auth_username: str = "admin"
    auth_password: str = "admin"
    auth_session_secret: str = "change-me"
    auth_session_ttl_seconds: int = 28_800
    auth_oidc_enabled: bool = False
    auth_oidc_issuer_url: str | None = None
    auth_oidc_client_id: str | None = None
    auth_oidc_client_secret: str | None = None
    auth_oidc_redirect_uri: str | None = None
    auth_oidc_scopes: str = "openid profile email groups"
    auth_oidc_username_claim: str = "email"
    auth_oidc_groups_claim: str = "groups"

    model_config = SettingsConfigDict(env_prefix="KOI_", env_file=".env")


@lru_cache
def get_settings() -> Settings:
    return Settings()
