"""
App settings — user-configurable LLM endpoint (FR-002).

GET  /settings/llm         → effective settings (DB overrides env), key masked
PUT  /settings/llm         → save a custom OpenAI-compatible endpoint triple
                             (empty api_key reverts to env defaults)
POST /settings/llm/models  → probe an endpoint for its available model list

Persistence is the ``app_settings`` key-value table (api/db.py); the
runtime resolution that all LLM consumers share lives in
src/agents/llm_config.py.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from openai import APIConnectionError, APITimeoutError, AuthenticationError, OpenAI
from sqlmodel import Session

from api.db import AppSettingRecord, get_session
from api.i18n import get_request_locale, msg
from api.schemas import (
    LlmModelsFetchRequest,
    LlmModelsResponse,
    LlmSettingsResponse,
    LlmSettingsUpdateRequest,
)
from src.agents.demo_mode import is_demo_mode
from src.agents.llm_config import (
    LLM_SETTING_KEYS,
    KEY_API_KEY,
    KEY_BASE_URL,
    KEY_MODEL,
    get_llm_config,
    mask_api_key,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])


def _current_settings() -> LlmSettingsResponse:
    """Snapshot of the resolved LLM config in the API response shape."""
    cfg = get_llm_config()
    return LlmSettingsResponse(
        configured=cfg.configured,
        model=cfg.model,
        base_url=cfg.base_url,
        source=cfg.source,
        api_key_masked=mask_api_key(cfg.api_key),
        demo=is_demo_mode(),
    )


def _upsert(session: Session, key: str, value: str) -> None:
    record = session.get(AppSettingRecord, key)
    if record is None:
        record = AppSettingRecord(key=key, value=value)
    else:
        record.value = value
        record.updated_at = datetime.now().isoformat()
    session.add(record)


@router.get("/llm", response_model=LlmSettingsResponse)
def get_llm_settings() -> LlmSettingsResponse:
    return _current_settings()


@router.put("/llm", response_model=LlmSettingsResponse)
def put_llm_settings(
    payload: LlmSettingsUpdateRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> LlmSettingsResponse:
    base_url = payload.base_url.strip()
    api_key = payload.api_key.strip()
    model = payload.model.strip()

    if not api_key:
        # No key = revert to env defaults: drop the whole triple.
        for key in LLM_SETTING_KEYS:
            record = session.get(AppSettingRecord, key)
            if record is not None:
                session.delete(record)
        session.commit()
        return _current_settings()

    if not base_url or not model:
        raise HTTPException(
            status_code=422,
            detail=msg("settings.custom_endpoint_fields_required", get_request_locale(request)),
        )

    _upsert(session, KEY_BASE_URL, base_url)
    _upsert(session, KEY_API_KEY, api_key)
    _upsert(session, KEY_MODEL, model)
    session.commit()
    logger.info("LLM endpoint settings updated (base_url=%s, model=%s)", base_url, model)
    return _current_settings()


def _fetch_models(base_url: str, api_key: str) -> list[str]:
    """List model ids from an OpenAI-compatible endpoint (10s, no retries)."""
    client = OpenAI(
        api_key=api_key, base_url=base_url, timeout=10.0, max_retries=0
    )
    return sorted(m.id for m in client.models.list())


@router.post("/llm/models", response_model=LlmModelsResponse)
def list_llm_models(payload: LlmModelsFetchRequest, request: Request) -> LlmModelsResponse:
    locale = get_request_locale(request)
    try:
        return LlmModelsResponse(
            models=_fetch_models(payload.base_url, payload.api_key)
        )
    except (APIConnectionError, APITimeoutError) as e:
        raise HTTPException(
            status_code=502,
            detail=msg("settings.endpoint_unreachable", locale),
        ) from e
    except AuthenticationError as e:
        raise HTTPException(
            status_code=502,
            detail=msg("settings.endpoint_auth_failed", locale),
        ) from e
    except Exception as e:
        text = str(e).strip()
        raise HTTPException(
            status_code=502,
            detail=msg("settings.models_fetch_failed", locale, error=text[:200]),
        ) from e
