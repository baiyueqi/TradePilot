"""Collector API: manual sync endpoints for ingestion."""

from fastapi import APIRouter

from tradepilot.ingestion.models import SyncRequest, SyncResult
from tradepilot.ingestion.service import IngestionService

router = APIRouter()
_service = IngestionService()


@router.post("/market/sync")
def market_sync(request: SyncRequest | None = None) -> SyncResult:
    """Trigger a manual market data sync."""
    if request is None:
        request = SyncRequest()
    return _service.sync_market(request)


@router.get("/runs")
def list_runs() -> list[dict]:
    """Return ingestion run history."""
    return _service.get_runs()


@router.get("/status")
def ingestion_status() -> dict:
    """Return high-level ingestion status."""
    return _service.get_status()
