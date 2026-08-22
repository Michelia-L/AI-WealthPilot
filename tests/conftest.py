import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from api.db import get_session
from api.main import create_app


@pytest.fixture(autouse=True)
def isolate_storage_dirs(tmp_path, monkeypatch):
    """
    Automatically mock PROFILES_DIR, REPORTS_DIR and IPS_DIR for all tests to
    use a temporary directory, preventing local filesystem pollution and
    ensuring test isolation.
    """
    # Create isolated folders inside pytest's temporary directory
    temp_profiles_dir = tmp_path / "data" / "profiles"
    temp_reports_dir = tmp_path / "data" / "reports"
    temp_ips_dir = tmp_path / "data" / "ips"

    temp_profiles_dir.mkdir(parents=True, exist_ok=True)
    temp_reports_dir.mkdir(parents=True, exist_ok=True)
    temp_ips_dir.mkdir(parents=True, exist_ok=True)

    # Monkeypatch the module-level directory paths
    monkeypatch.setattr("src.agents.profiler.PROFILES_DIR", temp_profiles_dir)
    monkeypatch.setattr("src.agents.report_storage.REPORTS_DIR", temp_reports_dir)
    monkeypatch.setattr("src.agents.ips_storage.IPS_DIR", temp_ips_dir)

    # Never exercise the paid provider with the developer's real token from
    # .env — tests stub the provider explicitly when they need it.
    monkeypatch.setattr("src.data.tushare_provider.TUSHARE_TOKEN", "")
    # Same guard for the yield-curve module, which imports the token from
    # src.config (where the real .env value is loaded).
    monkeypatch.setattr("src.data.yield_curve.TUSHARE_TOKEN", "")
    # The optional CN fallback tier is off by default; tests enable it.
    monkeypatch.setattr("src.data.akshare_provider.is_available", lambda: False)
    # Demo mode (P20) is opt-in per test; a developer .env with DEMO_MODE=1
    # must not flip the whole suite onto the fixture-replay path.
    monkeypatch.setattr("src.config.DEMO_MODE", False)

    # LLM settings (app_settings table, FR-002) live in the app SQLite and
    # are read via a dynamically-resolved api.db.engine — point it at a
    # throwaway tmp DB so a developer's real data/wealthpilot.db can never
    # leak saved endpoint settings into the suite.
    engine = create_engine(
        f"sqlite:///{tmp_path}/unit.db", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr("api.db.engine", engine)

    return temp_profiles_dir, temp_reports_dir


def _make_client(tmp_path, monkeypatch) -> TestClient:
    """Build a TestClient backed by an isolated tmp-path SQLite database."""
    engine = create_engine(
        f"sqlite:///{tmp_path}/test.db", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)
    # The lifespan hook would otherwise create/seed the real data/wealthpilot.db.
    monkeypatch.setattr("api.main.init_db", lambda: None)
    monkeypatch.setattr("api.main.maybe_auto_import", lambda: None)
    # ... and query the real DB for interrupted background tasks on boot.
    monkeypatch.setattr("api.main.reconcile_interrupted_tasks", lambda: 0)
    # Task persistence (api/tasks.py) resolves api.db.engine directly instead
    # of the get_session dependency — point it at the same tmp database.
    monkeypatch.setattr("api.db.engine", engine)

    app = create_app()

    def override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    return TestClient(app)


@pytest.fixture
def client(tmp_path, monkeypatch):
    """API TestClient backed by an isolated tmp-path SQLite database.

    Sends ``X-Locale: zh`` (P22) so the pre-i18n Chinese assertions keep
    exercising the localized message tables unchanged; per-request headers
    still override it.
    """
    with _make_client(tmp_path, monkeypatch) as test_client:
        test_client.headers["X-Locale"] = "zh"
        yield test_client


@pytest.fixture
def bare_client(tmp_path, monkeypatch):
    """Same as ``client`` but with no X-Locale header (API default: English)."""
    with _make_client(tmp_path, monkeypatch) as test_client:
        yield test_client
