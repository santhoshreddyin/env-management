from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_maintainer
from app.database import get_db
from app.models import Environment
from app.schemas import EnvironmentCreate, EnvironmentRead, EnvironmentUpdate

router = APIRouter(prefix="/environments", tags=["environments"])


def _to_read(env: Environment) -> EnvironmentRead:
    return EnvironmentRead.model_validate(env).model_copy(update={"variable_count": len(env.variables)})


def get_environment_or_404(env_id: int, db: Session) -> Environment:
    env = db.get(Environment, env_id)
    if env is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Environment not found")
    return env


def _ensure_unique_name(db: Session, name: str, exclude_id: int | None = None) -> None:
    existing = db.scalar(select(Environment).where(Environment.name == name))
    if existing is not None and existing.id != exclude_id:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Environment '{name}' already exists")


@router.get("", response_model=list[EnvironmentRead])
def list_environments(db: Session = Depends(get_db)):
    envs = db.scalars(select(Environment).order_by(Environment.name)).all()
    return [_to_read(e) for e in envs]


@router.post("", response_model=EnvironmentRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_maintainer)])
def create_environment(payload: EnvironmentCreate, db: Session = Depends(get_db)):
    _ensure_unique_name(db, payload.name)
    env = Environment(**payload.model_dump())
    db.add(env)
    db.commit()
    db.refresh(env)
    return _to_read(env)


@router.get("/{env_id}", response_model=EnvironmentRead)
def get_environment(env_id: int, db: Session = Depends(get_db)):
    return _to_read(get_environment_or_404(env_id, db))


@router.patch("/{env_id}", response_model=EnvironmentRead, dependencies=[Depends(require_maintainer)])
def update_environment(env_id: int, payload: EnvironmentUpdate, db: Session = Depends(get_db)):
    env = get_environment_or_404(env_id, db)
    data = payload.model_dump(exclude_unset=True)
    if "name" in data:
        _ensure_unique_name(db, data["name"], exclude_id=env.id)
    for field, value in data.items():
        setattr(env, field, value)
    db.commit()
    db.refresh(env)
    return _to_read(env)


@router.delete("/{env_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_maintainer)])
def delete_environment(env_id: int, db: Session = Depends(get_db)):
    env = get_environment_or_404(env_id, db)
    db.delete(env)
    db.commit()
