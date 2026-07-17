"""
Capital Market Expectations endpoints.

compute_cme() already ships with its own file-based cache and three-tier
degradation (cache → stale → static fallback), so no additional caching
is needed at the API layer.
"""

from fastapi import APIRouter, Query

from api.schemas import CMEResponse
from src.portfolio.cme_engine import compute_cme

router = APIRouter(prefix="/cme", tags=["cme"])


@router.get(
    "",
    response_model=CMEResponse,
    summary="Capital Market Expectations report for all IPS asset classes",
)
def get_cme(
    force_refresh: bool = Query(
        False, description="Bypass the file cache and recompute from live data"
    ),
) -> CMEResponse:
    report, cache_status = compute_cme(force_refresh=force_refresh)
    return CMEResponse(cache_status=cache_status, report=report)
