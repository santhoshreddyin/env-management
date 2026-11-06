from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_maintainer
from app.database import get_db
from app.models import Variable
from app.routers.environments import get_environment_or_404
from app.schemas import VariableCreate, VariableRead, VariableUpdate

router = APIRouter(prefix="/environments/{env_id}/variables", tags=["variables"])


def _get_variable_or_404(env_id: int, var_id: int, db: Session) -> Variable:
    var = db.get(Variable, var_id)
    if var is None or var.environment_id != env_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Variable not found")
    return var


def _ensure_unique_key(db: Session, env_id: int, key: str, exclude_id: int | None = None) -> None:
    existing = db.scalar(select(Variable).where(Variable.environment_id == env_id, Variable.key == key))
    if existing is not None and existing.id != exclude_id:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Variable '{key}' already exists in this environment")


@router.get("", response_model=list[VariableRead])
def list_variables(env_id: int, db: Session = Depends(get_db)):
    return get_environment_or_404(env_id, db).variables


@router.post("", response_model=VariableRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_maintainer)])
def create_variable(env_id: int, payload: VariableCreate, db: Session = Depends(get_db)):
    get_environment_or_404(env_id, db)
    _ensure_unique_key(db, env_id, payload.key)
    var = Variable(environment_id=env_id, **payload.model_dump())
    db.add(var)
    db.commit()
    db.refresh(var)
    return var


@router.patch("/{var_id}", response_model=VariableRead, dependencies=[Depends(require_maintainer)])
def update_variable(env_id: int, var_id: int, payload: VariableUpdate, db: Session = Depends(get_db)):
    var = _get_variable_or_404(env_id, var_id, db)
    data = payload.model_dump(exclude_unset=True)
    if "key" in data:
        _ensure_unique_key(db, env_id, data["key"], exclude_id=var.id)
    for field, value in data.items():
        setattr(var, field, value)
    db.commit()
    db.refresh(var)
    return var


@router.delete("/{var_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_maintainer)])
def delete_variable(env_id: int, var_id: int, db: Session = Depends(get_db)):
    var = _get_variable_or_404(env_id, var_id, db)
    db.delete(var)
    db.commit()


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


@router.get("/export/dotenv", response_class=Response)
def export_dotenv(env_id: int, db: Session = Depends(get_db)):
    """Export the environment's variables as a .env file."""
    env = get_environment_or_404(env_id, db)
    lines = [f'{v.key}="{_escape(v.value)}"' for v in env.variables]
    body = "\n".join(lines) + ("\n" if lines else "")
    return Response(
        content=body,
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{env.name}.env"'},
    )
