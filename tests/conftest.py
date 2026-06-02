import pytest
from pathlib import Path

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
