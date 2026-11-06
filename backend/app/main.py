import asyncio
import logging
import time
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from app.auth import require_viewer
from app.config import settings
from app.flows.routers import data as flow_data
from app.flows.routers import edit as flow_edit
from app.flows.routers import explorer as flow_explorer
from app.migrate import run_migrations
from app.platform.routers import (
    admin,
    bookings,
    deployments,
    environments,
    integrations,
    operations,
    reports,
    topology,
    variables,
)
from app.routers import health

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("envmgmt.http")


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.run_migrations:
        run_migrations()
    task = None
    if settings.scheduler_enabled:
        from app.platform.scheduler import run_forever

        task = asyncio.create_task(run_forever())
    yield
    if task:
        task.cancel()


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    lifespan=lifespan,
    description="Enterprise environment management: inventory, topology, deployments, bookings, configuration, "
                "health, issues, test data, reporting and integrations. Every path is also served under "
                "`/api/v1/` (stable, versioned). Pipelines authenticate with `Authorization: Bearer emt_…`.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- NFR-08: request metrics and logging; INT-01: /api/v1 alias -------------------------
METRICS: dict[str, float] = defaultdict(float)
LATENCY_BUCKETS = [0.05, 0.1, 0.25, 0.5, 1, 2, 5]


@app.middleware("http")
async def versioned_and_metrics(request: Request, call_next):
    path = request.scope["path"]
    if path.startswith("/api/v1/"):
        request.scope["path"] = "/api/" + path[len("/api/v1/"):]
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - start
    route = request.scope.get("route")
    label = getattr(route, "path", "unmatched")
    METRICS[f'http_requests_total{{method="{request.method}",route="{label}",status="{response.status_code}"}}'] += 1
    METRICS[f'http_request_seconds_sum{{route="{label}"}}'] += elapsed
    for b in LATENCY_BUCKETS:
        if elapsed <= b:
            METRICS[f'http_request_seconds_bucket{{route="{label}",le="{b}"}}'] += 1
    response.headers["X-Response-Time-ms"] = f"{elapsed * 1000:.1f}"
    if elapsed > 2:
        log.warning("slow request %s %s %.0fms", request.method, path, elapsed * 1000)
    return response


@app.get("/api/metrics", response_class=PlainTextResponse, tags=["health"])
def metrics():
    """Prometheus metrics for the platform itself."""
    return "\n".join(f"envmgmt_{k} {v:g}" for k, v in sorted(METRICS.items())) + "\n"


app.include_router(health.router, prefix="/api")

# Environment management platform
for r in (environments, variables, topology, deployments, bookings, operations, reports, admin, integrations):
    app.include_router(r.router, prefix="/api", dependencies=[Depends(require_viewer)])

# Integration Flow Explorer (system and integration catalogue)
app.include_router(flow_explorer.router, prefix="/api")
app.include_router(flow_data.router, prefix="/api")
app.include_router(flow_edit.router, prefix="/api")
