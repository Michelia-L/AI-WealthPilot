"""
API tests for the user-configurable LLM endpoint settings (FR-002).

Covers the /api/settings/llm endpoints (GET / PUT / models probe) and the
src.agents.llm_config resolver priority (DB overrides env, empty key
reverts). Outbound calls to the custom endpoint are monkeypatched at the
router module (api.routers.settings._fetch_models); no real network.
"""

from types import SimpleNamespace

import httpx
import pytest
from openai import APIConnectionError, AuthenticationError
from sqlmodel import Session, create_engine, select

from api import db
from api.routers.settings import _fetch_models
from src.agents.advisor import is_api_configured
from src.agents.llm_config import get_llm_config, mask_api_key

ENV_KEY = "sk-envkey000000abcd"
ENV_URL = "https://api.deepseek.com"
ENV_MODEL = "deepseek-v4-pro"

DB_KEY = "sk-dbkey99990000wxyz"
DB_URL = "https://llm.example.com/v1"
DB_MODEL = "my-custom-model"

_LLM_ROWS = {"llm_base_url", "llm_api_key", "llm_model"}


@pytest.fixture
def env_llm(monkeypatch):
    """Pin the env-side LLM defaults to known values (a developer .env may differ)."""
    monkeypatch.setattr("src.config.DEEPSEEK_API_KEY", ENV_KEY)
    monkeypatch.setattr("src.config.DEEPSEEK_BASE_URL", ENV_URL)
    monkeypatch.setattr("src.config.DEEPSEEK_MODEL", ENV_MODEL)


def _put(client, base_url=DB_URL, api_key=DB_KEY, model=DB_MODEL):
    return client.put(
        "/api/settings/llm",
        json={"base_url": base_url, "api_key": api_key, "model": model},
    )


def _saved_rows():
    with Session(db.engine) as session:
        return session.exec(select(db.AppSettingRecord)).all()


# ---------------------------------------------------------------------------
# GET /api/settings/llm — env fallback
# ---------------------------------------------------------------------------


def test_get_default_env_fallback(client, env_llm):
    resp = client.get("/api/settings/llm")
    assert resp.status_code == 200
    body = resp.json()
    assert body["configured"] is True
    assert body["source"] == "env"
    assert body["model"] == ENV_MODEL
    assert body["base_url"] == ENV_URL
    assert body["api_key_masked"] == mask_api_key(ENV_KEY)
    assert body["demo"] is False
    assert ENV_KEY not in resp.text  # raw key never leaves the API surface


def test_get_unconfigured_when_no_key_anywhere(client, monkeypatch):
    monkeypatch.setattr("src.config.DEEPSEEK_API_KEY", "")
    body = client.get("/api/settings/llm").json()
    assert body["configured"] is False
    assert body["source"] == "none"
    assert body["api_key_masked"] == ""


# ---------------------------------------------------------------------------
# PUT /api/settings/llm
# ---------------------------------------------------------------------------


def test_put_then_get_reflects_db(client, env_llm):
    resp = _put(client)
    assert resp.status_code == 200
    body = resp.json()
    assert body["configured"] is True
    assert body["source"] == "db"
    assert body["model"] == DB_MODEL
    assert body["base_url"] == DB_URL
    assert body["api_key_masked"] == DB_KEY[:3] + "****" + DB_KEY[-4:]
    assert DB_KEY not in resp.text

    # GET agrees with the PUT response, and the rows really landed.
    assert client.get("/api/settings/llm").json() == body
    assert {r.key for r in _saved_rows()} == _LLM_ROWS


def test_put_empty_key_reverts_to_env(client, env_llm):
    assert _put(client).status_code == 200
    assert {r.key for r in _saved_rows()} == _LLM_ROWS

    resp = _put(client, base_url="", api_key="", model="")
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "env"
    assert body["model"] == ENV_MODEL
    assert body["base_url"] == ENV_URL
    assert body["api_key_masked"] == mask_api_key(ENV_KEY)
    assert _saved_rows() == []  # triple rows cleared


@pytest.mark.parametrize(
    "base_url,model",
    [("", DB_MODEL), (DB_URL, ""), ("   ", DB_MODEL), (DB_URL, "  ")],
)
def test_put_key_without_url_or_model_422(client, env_llm, base_url, model):
    resp = _put(client, base_url=base_url, model=model)
    assert resp.status_code == 422
    assert "base_url" in resp.json()["detail"]
    assert _saved_rows() == []  # rejected payload persists nothing


# ---------------------------------------------------------------------------
# POST /api/settings/llm/models
# ---------------------------------------------------------------------------


def test_models_probe_success(client, monkeypatch):
    monkeypatch.setattr(
        "api.routers.settings._fetch_models",
        lambda base_url, api_key: ["a-model", "b-model"],
    )
    resp = client.post(
        "/api/settings/llm/models",
        json={"base_url": DB_URL, "api_key": DB_KEY},
    )
    assert resp.status_code == 200
    assert resp.json() == {"models": ["a-model", "b-model"]}


def test_models_probe_validation_422(client):
    resp = client.post(
        "/api/settings/llm/models", json={"base_url": "", "api_key": DB_KEY}
    )
    assert resp.status_code == 422


def test_fetch_models_helper_sorts_and_configures_client(monkeypatch):
    """The real helper hits OpenAI.models.list with a tight timeout, sorted ids."""
    captured = {}

    class _Models:
        def list(self):
            return [SimpleNamespace(id="z-model"), SimpleNamespace(id="a-model")]

    class _Client:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.models = _Models()

    monkeypatch.setattr("api.routers.settings.OpenAI", _Client)
    assert _fetch_models(DB_URL, DB_KEY) == ["a-model", "z-model"]
    assert captured["api_key"] == DB_KEY
    assert captured["base_url"] == DB_URL
    assert captured["timeout"] == 10.0
    assert captured["max_retries"] == 0


_CONN_ERR = APIConnectionError(request=httpx.Request("GET", "http://x"))
_AUTH_ERR = AuthenticationError(
    "nope",
    response=httpx.Response(401, request=httpx.Request("GET", "http://x")),
    body=None,
)


@pytest.mark.parametrize(
    "exc,needle",
    [
        (_CONN_ERR, "无法连接到该端点"),
        (_AUTH_ERR, "端点认证失败"),
        (RuntimeError("boom"), "获取模型列表失败"),
    ],
)
def test_models_probe_failure_maps_to_502(client, monkeypatch, exc, needle):
    def _raise(base_url, api_key):
        raise exc

    monkeypatch.setattr("api.routers.settings._fetch_models", _raise)
    resp = client.post(
        "/api/settings/llm/models",
        json={"base_url": DB_URL, "api_key": DB_KEY},
    )
    assert resp.status_code == 502
    assert needle in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Resolver priority (src.agents.llm_config)
# ---------------------------------------------------------------------------


def test_resolver_db_overrides_env(client, env_llm):
    assert get_llm_config().source == "env"

    _put(client)
    cfg = get_llm_config()
    assert (cfg.base_url, cfg.api_key, cfg.model) == (DB_URL, DB_KEY, DB_MODEL)
    assert cfg.configured is True and cfg.source == "db"

    _put(client, base_url="", api_key="", model="")
    cfg = get_llm_config()
    assert (cfg.base_url, cfg.api_key, cfg.model) == (ENV_URL, ENV_KEY, ENV_MODEL)
    assert cfg.configured is True and cfg.source == "env"


def test_resolver_survives_missing_table(tmp_path, monkeypatch):
    """Scripts using src/ without init_db must fall back to env, not crash."""
    monkeypatch.setattr(
        "api.db.engine", create_engine(f"sqlite:///{tmp_path}/no_tables.db")
    )
    monkeypatch.setattr("src.config.DEEPSEEK_API_KEY", "")
    cfg = get_llm_config()
    assert cfg.configured is False and cfg.source == "none"


def test_is_api_configured_dual_source(client, monkeypatch):
    monkeypatch.setattr("src.config.DEEPSEEK_API_KEY", "")
    assert is_api_configured() is False  # both sources empty

    _put(client)  # DB key only
    assert is_api_configured() is True


def test_advisor_status_reflects_db_model(client, env_llm):
    assert client.get("/api/advisor/status").json()["model"] == ENV_MODEL
    _put(client)
    body = client.get("/api/advisor/status").json()
    assert body["model"] == DB_MODEL
    assert body["configured"] is True


# ---------------------------------------------------------------------------
# mask_api_key
# ---------------------------------------------------------------------------


def test_mask_api_key():
    assert mask_api_key("") == ""
    assert mask_api_key("short") == "****"
    assert mask_api_key("12345678") == "****"  # len == 8 boundary
    assert mask_api_key("sk-abcdefgh1234") == "sk-****1234"
