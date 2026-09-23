"""Separate client/staff entry points for the shared assistant runtime."""

from fastapi import APIRouter, Depends, HTTPException, Request

from api.agent_tools import AuthorizedAgentTools
from api.auth import get_current_session
from api.db import AuthSessionRecord
from api.i18n import get_request_locale, msg
from api.schemas import (
    AdvisorCopilotResponse,
    AssistantRequest,
    ClientAssistantResponse,
)
from src.agents.assistant import AssistantUnavailable, Persona, run_assistant
from src.agents.demo_mode import is_demo_mode

router = APIRouter()


def answer(
    payload: AssistantRequest,
    request: Request,
    login: AuthSessionRecord,
    persona: Persona,
):
    locale = get_request_locale(request)
    tools = AuthorizedAgentTools(request, login.token_hash, persona)
    tools.authorize()
    try:
        if is_demo_mode():
            # Deterministic fixture response; exercise the real scoped dispatcher
            # without contacting a provider or claiming live answer quality.
            tools.invoke(
                "read_own_portfolio" if persona == "client" else "list_clients", "{}"
            )
            tools.authorize()
            return {"answer": msg(f"assistant.demo_{persona}", locale), "demo": True}
        content = run_assistant(payload.message, tools, locale)
        return {"answer": content, "demo": False}
    except HTTPException:
        raise
    except AssistantUnavailable:
        raise HTTPException(503, msg("assistant.unavailable", locale)) from None
    except Exception:
        # No exception text, provider configuration, prompts or tool results in
        # logs/errors. Only the final answer is part of either public DTO.
        raise HTTPException(502, msg("assistant.failed", locale)) from None


@router.post(
    "/me/assistant",
    tags=["Client Portal"],
    response_model=ClientAssistantResponse,
    openapi_extra={"x-access-scope": "client-scoped"},
)
def client_assistant(
    payload: AssistantRequest,
    request: Request,
    login: AuthSessionRecord = Depends(get_current_session),
):
    return answer(payload, request, login, "client")


@router.post(
    "/advisor/copilot",
    tags=["advisor"],
    response_model=AdvisorCopilotResponse,
    openapi_extra={"x-access-scope": "advisor-scoped"},
)
def advisor_copilot(
    payload: AssistantRequest,
    request: Request,
    login: AuthSessionRecord = Depends(get_current_session),
):
    return answer(payload, request, login, "advisor")
