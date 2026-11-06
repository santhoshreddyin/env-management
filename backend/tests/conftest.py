import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.flows.models  # noqa: F401 - register tables
from app.auth import User
from app.config import settings
from app.database import Base, get_db
from app.flows.repository import commit_dataset
from app.flows.sample_data import sample_dataset
from app.main import app


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture()
def client(session_factory, monkeypatch):
    monkeypatch.setattr(settings, "run_migrations", False)
    monkeypatch.setattr(settings, "auth_mode", "dev")
    monkeypatch.setattr(settings, "dev_roles", ["viewer", "maintainer"])

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def seeded(client, session_factory):
    with session_factory() as db:
        commit_dataset(db, sample_dataset(), user=User("seed"), source="seed", summary="sample",
                       audit_action="seed")
    return client
