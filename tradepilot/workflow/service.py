"""Workflow service for pre-market and post-market daily operations."""

from __future__ import annotations

import json
import time
from datetime import date, datetime
from importlib import import_module

from loguru import logger

from tradepilot.data import get_provider
from tradepilot.db import get_conn
from tradepilot.ingestion.models import NewsSyncRequest, SyncRequest
from tradepilot.ingestion.service import IngestionService
from tradepilot.scanner.daily import DailyScanner, normalize_scan_date
from tradepilot.summary.models import WatchlistConfig
from tradepilot.workflow.models import (
    WorkflowHistoryItem,
    WorkflowPhase,
    WorkflowRunRecord,
    WorkflowStatus,
    WorkflowStepResult,
    WorkflowSummary,
    WorkflowTrigger,
)

_DEFAULT_INDEX_CODES = ["000001", "399001", "399006", "000688"]


class DailyWorkflowService:
    """Coordinate simplified pre-market and post-market workflows."""

    def __init__(self) -> None:
        self._scanner = DailyScanner()
        self._ingestion = IngestionService()
        self._tushare = import_module("tradepilot.data.tushare_client").TushareClient()
        self._summary_api = import_module("tradepilot.api.summary")

    def run_pre_market_workflow(
        self,
        workflow_date: str | None = None,
        triggered_by: WorkflowTrigger = WorkflowTrigger.MANUAL,
    ) -> WorkflowRunRecord:
        """Run the pre-market workflow and persist the resulting snapshot."""
        started_at = datetime.now()
        requested_date, resolved_date, date_resolution = self._resolve_pre_market_date(workflow_date)
        steps: list[WorkflowStepResult] = []
        error_messages: list[str] = []
        previous_post_market = self.get_latest_run(WorkflowPhase.POST_MARKET)
        alerts = self._scanner.list_alerts(unread_only=False)[:10]
        watchlist = self._load_watchlist().model_dump()
        news_items: list[dict] = []

        if not self._should_run_for_trading_day(resolved_date):
            summary = WorkflowSummary(
                title="盘前准备已跳过",
                overview="非交易日，未执行盘前工作流。",
                requested_date=requested_date,
                resolved_date=resolved_date,
                date_resolution=date_resolution,
                watchlist=watchlist,
                alerts=alerts[:5],
                carry_over=self._build_carry_over(previous_post_market),
                steps=[
                    WorkflowStepResult(
                        name="trading_day_check",
                        status=WorkflowStatus.SKIPPED.value,
                        details={"reason": "non-trading day"},
                    )
                ],
            )
            return self._persist_run(
                workflow_date=resolved_date,
                phase=WorkflowPhase.PRE_MARKET,
                triggered_by=triggered_by,
                status=WorkflowStatus.SKIPPED,
                started_at=started_at,
                finished_at=datetime.now(),
                summary=summary,
                error_message="non-trading day",
            )

        news_result = self._ingestion.sync_news(NewsSyncRequest())
        news_status = news_result.run.status.value
        news_step_status = WorkflowStatus.SUCCESS.value if news_status == "success" else WorkflowStatus.FAILED.value
        if news_step_status == WorkflowStatus.FAILED.value:
            error_messages.append(news_result.run.error_message or "news sync failed")
        steps.append(
            WorkflowStepResult(
                name="news_sync",
                status=news_step_status,
                records_affected=news_result.run.records_inserted + news_result.run.records_updated,
                error_message=news_result.run.error_message,
            )
        )
        news_items = self._get_latest_news(limit=8)

        status = self._resolve_status(steps)
        overview = self._build_pre_market_overview(
            previous_post_market,
            news_items,
            watchlist,
            alerts,
            requested_date,
            resolved_date,
            date_resolution,
        )
        summary = WorkflowSummary(
            title="盘前准备",
            overview=overview,
            requested_date=requested_date,
            resolved_date=resolved_date,
            date_resolution=date_resolution,
            watchlist=watchlist,
            alerts=alerts[:8],
            news={
                "status": news_step_status,
                "items": news_items,
            },
            carry_over=self._build_carry_over(previous_post_market),
            scheduler={
                "has_previous_post_market": previous_post_market is not None,
            },
            steps=steps,
        )
        return self._persist_run(
            workflow_date=resolved_date,
            phase=WorkflowPhase.PRE_MARKET,
            triggered_by=triggered_by,
            status=status,
            started_at=started_at,
            finished_at=datetime.now(),
            summary=summary,
            error_message="；".join(error_messages) or None,
        )

    def run_post_market_workflow(
        self,
        workflow_date: str | None = None,
        triggered_by: WorkflowTrigger = WorkflowTrigger.MANUAL,
    ) -> WorkflowRunRecord:
        """Run the post-market workflow and persist the resulting snapshot."""
        started_at = datetime.now()
        requested_date, resolved_date, date_resolution = self._resolve_post_market_date(workflow_date)
        steps: list[WorkflowStepResult] = []
        error_messages: list[str] = []
        watchlist = self._load_watchlist().model_dump()

        if not self._should_run_for_trading_day(resolved_date):
            summary = WorkflowSummary(
                title="盘后复盘已跳过",
                overview="非交易日，未执行盘后工作流。",
                requested_date=requested_date,
                resolved_date=resolved_date,
                date_resolution=date_resolution,
                watchlist=watchlist,
                steps=[
                    WorkflowStepResult(
                        name="trading_day_check",
                        status=WorkflowStatus.SKIPPED.value,
                        details={"reason": "non-trading day"},
                    )
                ],
            )
            return self._persist_run(
                workflow_date=resolved_date,
                phase=WorkflowPhase.POST_MARKET,
                triggered_by=triggered_by,
                status=WorkflowStatus.SKIPPED,
                started_at=started_at,
                finished_at=datetime.now(),
                summary=summary,
                error_message="non-trading day",
            )

        stock_codes, index_codes = self._build_post_market_targets(watchlist)
        try:
            market_request = SyncRequest(
                start_date=resolved_date,
                end_date=resolved_date,
                stock_codes=stock_codes,
                index_codes=index_codes,
                full_refresh=False,
            )
            market_result = self._ingestion.sync_market(market_request)
            market_status = market_result.run.status.value
            market_step_status = WorkflowStatus.SUCCESS.value if market_status == "success" else WorkflowStatus.FAILED.value
            market_records = market_result.run.records_inserted + market_result.run.records_updated
            market_error = market_result.run.error_message
        except Exception as exc:
            logger.exception("post-market workflow market sync failed before run persisted")
            market_step_status = WorkflowStatus.FAILED.value
            market_records = 0
            market_error = str(exc)
        if market_step_status == WorkflowStatus.FAILED.value:
            error_messages.append(market_error or "market sync failed")
        steps.append(
            WorkflowStepResult(
                name="market_sync",
                status=market_step_status,
                records_affected=market_records,
                error_message=market_error,
                details={
                    "stock_codes": stock_codes,
                    "index_codes": index_codes,
                },
            )
        )

        scan_payload: dict = {}
        latest_scan: dict = {"scan_date": None, "advice": []}
        alerts = self._scanner.list_alerts(unread_only=False)[:10]
        try:
            scan_result = self._scanner.run(scan_date=resolved_date)
            latest_scan = self._scanner.get_latest_scan() or {"scan_date": None, "advice": []}
            scan_payload = scan_result.model_dump()
            scan_step_status = WorkflowStatus.SUCCESS.value
            scan_records = len(scan_result.watchlist_advice) + len(scan_result.position_advice) + len(scan_result.core_instrument_advice)
            scan_error = None
        except Exception as exc:
            logger.exception("post-market workflow scan failed")
            scan_step_status = WorkflowStatus.FAILED.value
            scan_records = 0
            scan_error = str(exc)
            error_messages.append(scan_error)
        steps.append(
            WorkflowStepResult(
                name="daily_scan",
                status=scan_step_status,
                records_affected=scan_records,
                error_message=scan_error,
            )
        )

        status = self._resolve_status(steps)
        overview = self._build_post_market_overview(
            latest_scan,
            steps,
            requested_date,
            resolved_date,
            date_resolution,
        )
        summary = WorkflowSummary(
            title="盘后复盘",
            overview=overview,
            requested_date=requested_date,
            resolved_date=resolved_date,
            date_resolution=date_resolution,
            watchlist=watchlist,
            alerts=alerts[:8],
            scan={
                "latest": latest_scan,
                "result": scan_payload,
            },
            scheduler={
                "steps_completed": len([step for step in steps if step.status == WorkflowStatus.SUCCESS.value]),
                "steps_total": len(steps),
            },
            steps=steps,
        )
        return self._persist_run(
            workflow_date=resolved_date,
            phase=WorkflowPhase.POST_MARKET,
            triggered_by=triggered_by,
            status=status,
            started_at=started_at,
            finished_at=datetime.now(),
            summary=summary,
            error_message="；".join(error_messages) or None,
        )

    def get_latest_run(self, phase: WorkflowPhase) -> WorkflowRunRecord | None:
        """Return the latest workflow snapshot for one phase."""
        conn = get_conn()
        row = conn.execute(
            """
            SELECT id, workflow_date, phase, triggered_by, status, started_at, finished_at, summary_json, error_message
            FROM workflow_runs
            WHERE phase = ?
            ORDER BY workflow_date DESC, started_at DESC, id DESC
            LIMIT 1
            """,
            [phase.value],
        ).fetchone()
        if row is None:
            return None
        return self._row_to_run(row)

    def list_history(self, limit: int = 20) -> list[WorkflowHistoryItem]:
        """Return recent workflow history rows."""
        conn = get_conn()
        rows = conn.execute(
            """
            SELECT id, workflow_date, phase, triggered_by, status, started_at, finished_at, error_message
            FROM workflow_runs
            ORDER BY started_at DESC, id DESC
            LIMIT ?
            """,
            [limit],
        ).fetchall()
        return [
            WorkflowHistoryItem(
                id=row[0],
                workflow_date=str(row[1]),
                phase=str(row[2]),
                triggered_by=str(row[3]),
                status=str(row[4]),
                started_at=row[5].isoformat() if row[5] else "",
                finished_at=row[6].isoformat() if row[6] else None,
                error_message=row[7],
            )
            for row in rows
        ]

    def get_workflow_status(self) -> dict:
        """Return the latest status for both workflow phases."""
        return {
            "pre_market": self._status_summary(self.get_latest_run(WorkflowPhase.PRE_MARKET)),
            "post_market": self._status_summary(self.get_latest_run(WorkflowPhase.POST_MARKET)),
        }

    def _resolve_requested_date(self, workflow_date: str | None) -> str:
        normalized = normalize_scan_date(workflow_date)
        return normalized or date.today().isoformat()

    def _resolve_pre_market_date(self, workflow_date: str | None) -> tuple[str, str, str]:
        requested_date = self._resolve_requested_date(workflow_date)
        if self._should_run_for_trading_day(requested_date):
            return requested_date, requested_date, "exact"
        next_trading_date = self._next_trading_day(requested_date)
        if next_trading_date is not None:
            return requested_date, next_trading_date, "fallback_next_trading_day"
        return requested_date, requested_date, "exact"

    def _resolve_post_market_date(self, workflow_date: str | None) -> tuple[str, str, str]:
        requested_date = self._resolve_requested_date(workflow_date)
        if self._should_run_for_trading_day(requested_date):
            return requested_date, requested_date, "exact"
        previous_trading_date = self._tushare.previous_trading_day(requested_date)
        if previous_trading_date is None:
            previous_trading_date = self._previous_trading_day(requested_date)
        if previous_trading_date is not None:
            return requested_date, previous_trading_date, "fallback_previous_trading_day"
        return requested_date, requested_date, "exact"

    def _next_trading_day(self, target_date: str) -> str | None:
        cursor = date.fromisoformat(target_date)
        for _ in range(14):
            cursor = cursor.fromordinal(cursor.toordinal() + 1)
            cursor_str = cursor.isoformat()
            if self._should_run_for_trading_day(cursor_str):
                return cursor_str
        return None

    def _previous_trading_day(self, target_date: str) -> str | None:
        cursor = date.fromisoformat(target_date)
        for _ in range(14):
            cursor = cursor.fromordinal(cursor.toordinal() - 1)
            cursor_str = cursor.isoformat()
            if self._should_run_for_trading_day(cursor_str):
                return cursor_str
        return None

    def _should_run_for_trading_day(self, target_date: str) -> bool:
        return self._tushare.is_trading_day(target_date)

    def _build_post_market_targets(self, watchlist: dict) -> tuple[list[str], list[str]]:
        stock_codes: list[str] = []
        for item in watchlist.get("watch_stocks", []):
            code = str(item.get("code", "")).strip()
            if code and code not in stock_codes:
                stock_codes.append(code)
        for position in self._load_positions():
            code = str(position.get("stock_code", "")).strip()
            if code and code not in stock_codes:
                stock_codes.append(code)
        if not stock_codes:
            stock_codes = [item.get("code", "") for item in watchlist.get("watch_stocks", []) if item.get("code")]
        return stock_codes, _DEFAULT_INDEX_CODES.copy()

    def _load_watchlist(self) -> WatchlistConfig:
        return self._summary_api.get_watchlist()

    def _load_positions(self) -> list[dict]:
        conn = get_conn()
        rows = conn.execute(
            "SELECT stock_code, stock_name FROM portfolio WHERE status = 'open' ORDER BY buy_date DESC"
        ).fetchdf()
        return rows.to_dict(orient="records")

    def _get_latest_news(self, limit: int = 8) -> list[dict]:
        conn = get_conn()
        rows = conn.execute(
            """
            SELECT source, source_item_id, title, content, category, published_at, collected_at
            FROM news_items
            ORDER BY COALESCE(published_at, collected_at) DESC
            LIMIT ?
            """,
            [limit],
        ).fetchdf()
        return rows.to_dict(orient="records")

    def _resolve_status(self, steps: list[WorkflowStepResult]) -> WorkflowStatus:
        statuses = {step.status for step in steps}
        if statuses == {WorkflowStatus.SUCCESS.value}:
            return WorkflowStatus.SUCCESS
        if WorkflowStatus.FAILED.value in statuses and WorkflowStatus.SUCCESS.value in statuses:
            return WorkflowStatus.PARTIAL
        if WorkflowStatus.FAILED.value in statuses:
            return WorkflowStatus.FAILED
        if WorkflowStatus.SKIPPED.value in statuses and len(statuses) == 1:
            return WorkflowStatus.SKIPPED
        return WorkflowStatus.PARTIAL

    def _build_carry_over(self, previous_post_market: WorkflowRunRecord | None) -> dict:
        if previous_post_market is None:
            return {"available": False}
        return {
            "available": True,
            "workflow_date": previous_post_market.workflow_date,
            "overview": previous_post_market.summary.overview,
            "scan": previous_post_market.summary.scan,
        }

    def _build_pre_market_overview(
        self,
        previous_post_market: WorkflowRunRecord | None,
        news_items: list[dict],
        watchlist: dict,
        alerts: list[dict],
        requested_date: str,
        resolved_date: str,
        date_resolution: str,
    ) -> str:
        post_market_text = "已有上一交易日盘后结果" if previous_post_market else "缺少上一交易日盘后结果"
        news_text = f"夜间新闻 {len(news_items)} 条"
        watch_text = f"关注板块 {len(watchlist.get('watch_sectors', []))} 个，关注股票 {len(watchlist.get('watch_stocks', []))} 个"
        alert_text = f"未读/最新预警 {min(len(alerts), 8)} 条"
        date_text = f"日期：{resolved_date}"
        if date_resolution == "fallback_next_trading_day":
            date_text = f"请求日期 {requested_date} 为非交易日，已切换到下一个交易日 {resolved_date}"
        return "；".join([date_text, post_market_text, news_text, watch_text, alert_text])

    def _build_post_market_overview(
        self,
        latest_scan: dict,
        steps: list[WorkflowStepResult],
        requested_date: str,
        resolved_date: str,
        date_resolution: str,
    ) -> str:
        latest_date = latest_scan.get("scan_date") or "未生成扫描日期"
        completed_steps = len([step for step in steps if step.status == WorkflowStatus.SUCCESS.value])
        date_text = f"日期：{resolved_date}"
        if date_resolution == "fallback_previous_trading_day":
            date_text = f"请求日期 {requested_date} 为非交易日，已切换到上一个交易日 {resolved_date}"
        return f"{date_text}；已完成 {completed_steps}/{len(steps)} 个步骤；最新扫描日期：{latest_date}"

    def _persist_run(
        self,
        workflow_date: str,
        phase: WorkflowPhase,
        triggered_by: WorkflowTrigger,
        status: WorkflowStatus,
        started_at: datetime,
        finished_at: datetime,
        summary: WorkflowSummary,
        error_message: str | None,
    ) -> WorkflowRunRecord:
        run = WorkflowRunRecord(
            id=time.time_ns(),
            workflow_date=workflow_date,
            phase=phase,
            triggered_by=triggered_by,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            summary=summary,
            error_message=error_message,
        )
        conn = get_conn()
        conn.execute(
            """
            INSERT INTO workflow_runs (
                id, workflow_date, phase, triggered_by, status,
                started_at, finished_at, summary_json, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                run.id,
                workflow_date,
                phase.value,
                triggered_by.value,
                status.value,
                started_at,
                finished_at,
                json.dumps(summary.model_dump(), ensure_ascii=False),
                error_message,
            ],
        )
        return run

    def _row_to_run(self, row: tuple) -> WorkflowRunRecord:
        return WorkflowRunRecord(
            id=row[0],
            workflow_date=str(row[1]),
            phase=WorkflowPhase(str(row[2])),
            triggered_by=WorkflowTrigger(str(row[3])),
            status=WorkflowStatus(str(row[4])),
            started_at=row[5],
            finished_at=row[6],
            summary=WorkflowSummary(**json.loads(row[7])),
            error_message=row[8],
        )

    def _status_summary(self, run: WorkflowRunRecord | None) -> dict:
        if run is None:
            return {"available": False}
        return {
            "available": True,
            "workflow_date": run.workflow_date,
            "phase": run.phase.value,
            "status": run.status.value,
            "started_at": run.started_at.isoformat(),
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        }
