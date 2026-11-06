from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import require_viewer
from app.config import settings
from app.flows.routers import data as flow_data
from app.flows.routers import edit as flow_edit
from app.flows.routers import explorer as flow_explorer
from app.migrate import run_migrations
from app.routers import environments, health, variables


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.run_migrations:
        run_migrations()
    yield


app = FastAPI(title=settings.app_name, version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")

# Environment management
app.include_router(environments.router, prefix="/api", dependencies=[Depends(require_viewer)])
app.include_router(variables.router, prefix="/api", dependencies=[Depends(require_viewer)])

# Integration Flow Explorer
app.include_router(flow_explorer.router, prefix="/api")
app.include_router(flow_data.router, prefix="/api")
app.include_router(flow_edit.router, prefix="/api")
