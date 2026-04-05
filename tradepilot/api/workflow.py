"""Workflow API routes for the simplified daily operating loop."""

from __future__ import annotations

from fastapi import APIRouter, Query

from tradepilot.workflow.models import WorkflowPhase, WorkflowRunResponse, WorkflowTrigger
from tradepilot.workflow.service import DailyWorkflowService

router = APIRouter()
_service = DailyWorkflowService()


@router.get("/latest", response_model=WorkflowRunResponse | None)
def get_latest_workflow(
    phase: WorkflowPhase = Query(..., description="Workflow phase to fetch"),
) -> WorkflowRunResponse | None:
    """Return the latest workflow snapshot for one phase."""
    run = _service.get_latest_run(phase)
    if run is None:
        return None
    return WorkflowRunResponse(run=run)


@router.get("/history")
def get_workflow_history(limit: int = 20) -> list[dict]:
    """Return recent workflow history rows."""
    return [item.model_dump() for item in _service.list_history(limit=limit)]


@router.get("/status")
def get_workflow_status() -> dict:
    """Return the latest status for both workflow phases."""
    return _service.get_workflow_status()


@router.post("/pre/run", response_model=WorkflowRunResponse)
def run_pre_market_workflow(workflow_date: str | None = None) -> WorkflowRunResponse:
    """Trigger a manual pre-market workflow run."""
    run = _service.run_pre_market_workflow(
        workflow_date=workflow_date,
        triggered_by=WorkflowTrigger.MANUAL,
    )
    return WorkflowRunResponse(run=run)


@router.post("/post/run", response_model=WorkflowRunResponse)
def run_post_market_workflow(workflow_date: str | None = None) -> WorkflowRunResponse:
    """Trigger a manual post-market workflow run."""
    run = _service.run_post_market_workflow(
        workflow_date=workflow_date,
        triggered_by=WorkflowTrigger.MANUAL,
    )
    return WorkflowRunResponse(run=run)
