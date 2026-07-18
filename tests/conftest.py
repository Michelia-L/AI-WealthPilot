import pytest
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from api.db import get_session
from api.main import create_app


@pytest.fixture(autouse=True)
def isolate_storage_dirs(tmp_path, monkeypatch):
    """
    Automatically mock PROFILES_DIR and REPORTS_DIR for all tests to use a
    temporary directory, preventing local filesystem pollution and ensuring test isolation.
    """
    # Create isolated folders inside pytest's temporary directory
    temp_profiles_dir = tmp_path / "data" / "profiles"
    temp_reports_dir = tmp_path / "data" / "reports"

    temp_profiles_dir.mkdir(parents=True, exist_ok=True)
    temp_reports_dir.mkdir(parents=True, exist_ok=True)

    # Monkeypatch the module-level directory paths
    monkeypatch.setattr("src.agents.profiler.PROFILES_DIR", temp_profiles_dir)
    monkeypatch.setattr("src.agents.report_storage.REPORTS_DIR", temp_reports_dir)

    return temp_profiles_dir, temp_reports_dir


@pytest.fixture
def client(tmp_path, monkeypatch):
    """API TestClient backed by an isolated tmp-path SQLite database."""
    engine = create_engine(
        f"sqlite:///{tmp_path}/test.db", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)
    # The lifespan hook would otherwise create the real data/wealthpilot.db.
    monkeypatch.setattr("api.main.init_db", lambda: None)

    app = create_app()

    def override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as test_client:
        yield test_client
