import json
from typing import Annotated, Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Env Management API"
    # "local", "qa" or "production" — reported by /api/health.
    app_env: str = "local"
    database_url: str = "sqlite:///./env_management.db"
    # Accepts a JSON list (["https://a", "https://b"]) or a comma-separated string.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]
    # Optional regex for extra allowed origins, e.g. Cloudflare Pages preview URLs:
    # ^https://[a-z0-9-]+\.env-management\.pages\.dev$
    cors_origin_regex: str | None = None
    # Render sets this automatically; exposed by /api/health so CI can verify a deploy.
    render_git_commit: str | None = None

    # Apply Alembic migrations on startup. Disable if migrations run as a separate deploy step.
    run_migrations: bool = True

    # Path to the flow explorer styling/layout config. Empty = bundled default.
    flow_config_path: str = ""

    # Max accepted size of an uploaded Excel workbook (bytes).
    max_upload_bytes: int = 10 * 1024 * 1024

    # --- Authentication -------------------------------------------------------
    # "dev":    no login; every request runs as `dev_user` with `dev_roles`. Local use only.
    # "header": SSO is handled by the platform gateway / auth proxy (OIDC or SAML, e.g.
    #           oauth2-proxy), which forwards the authenticated user and groups as headers.
    #           The backend must then only be reachable through that gateway.
    auth_mode: Literal["dev", "header"] = "dev"
    dev_user: str = "dev-user"
    dev_roles: list[str] = ["viewer", "maintainer"]
    auth_user_header: str = "X-Forwarded-User"
    auth_groups_header: str = "X-Forwarded-Groups"
    # Groups (from the groups header) mapped to roles. Empty viewer_groups = any authenticated user can view.
    maintainer_groups: list[str] = ["integration-maintainers"]
    viewer_groups: list[str] = []
    admin_groups: list[str] = []
    env_manager_groups: list[str] = []
    contributor_groups: list[str] = []
    booker_groups: list[str] = []
    # GOV-06: users see only environments in their scoped role assignments (admins see all).
    portfolio_segregation: bool = False

    # --- Platform -------------------------------------------------------------
    # Background scheduler: booking auto-release, expiry/SLA notifications, scheduled health checks.
    scheduler_enabled: bool = True
    scheduler_interval_seconds: int = 300
    health_check_timeout_seconds: float = 5.0
    health_degraded_ms: float = 2000.0
    # Deliver webhooks (Slack, Teams, generic) in a background thread.
    webhooks_enabled: bool = True
    # Optional SMTP for e-mail notifications (BKG-09, HLT-06).
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "env-management@localhost"
    # Days after which a system instance / integration verification is stale (TOP-09).
    stale_after_days: int = 90

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("database_url")
    @classmethod
    def _normalize_db_url(cls, v: str) -> str:
        # Supabase/Heroku-style URLs -> SQLAlchemy + psycopg (v3) driver.
        if v.startswith("postgres://"):
            v = "postgresql://" + v[len("postgres://") :]
        if v.startswith("postgresql://"):
            v = "postgresql+psycopg://" + v[len("postgresql://") :]
        return v

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors(cls, v):
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("["):
                return json.loads(v)
            return [o.strip() for o in v.split(",") if o.strip()]
        return v


settings = Settings()
