"""
Portfolio monitoring & rebalancing endpoints (P10).

Thin transport shell over src.portfolio.monitoring.compute_monitoring:
the core raises KeyError (document missing) / ValueError (no SAA),
which this router translates into 404 / 422.
"""

from fastapi import APIRouter, HTTPException

from api.schemas import MonitoringResponse
from src.portfolio.monitoring import compute_monitoring

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


def _is_valid_document_id(document_id: str) -> bool:
    """Same charset rule as ips._find_ips_file (keeps lookups inside IPS_DIR)."""
    return bool(document_id) and all(
        c.isalnum() or c in "_-" for c in document_id
    )


@router.get(
    "/{document_id}",
    response_model=MonitoringResponse,
    summary="Drift monitoring and rebalancing diagnostics for a stored IPS",
)
def get_monitoring(document_id: str) -> MonitoringResponse:
    if not _is_valid_document_id(document_id):
        raise HTTPException(status_code=404, detail="IPS 文档不存在")
    try:
        result = compute_monitoring(document_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="IPS 文档不存在")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return MonitoringResponse(**result)
