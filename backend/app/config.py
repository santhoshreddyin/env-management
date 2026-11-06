from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Env Management API"
    database_url: str = "sqlite:///./env_management.db"
    cors_origins: list[str] = ["http://localhost:5173"]

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

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
