from fastapi import APIRouter

from app.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str | None]:
    return {
        "status": "ok",
        "environment": settings.app_env,
        "commit": settings.render_git_commit,
    }
