"""API routes for A-share market summary."""

from __future__ import annotations

import json

from fastapi import APIRouter
from loguru import logger

from tradepilot.config import DATA_ROOT
from tradepilot.summary.models import TradingStatusResponse, WatchlistConfig
from tradepilot.summary.service import get_trading_status

router = APIRouter()

_WATCHLIST_PATH = DATA_ROOT / "watchlist.json"

_DEFAULT_WATCHLIST = WatchlistConfig(
    watchlist={
        "sectors": [
            {"name": "AI应用"},
            {"name": "算力"},
            {"name": "机器人概念"},
            {"name": "半导体"},
        ],
        "stocks": [
            {"code": "600519", "name": "贵州茅台"},
            {"code": "300750", "name": "宁德时代"},
        ],
    }
)


def _normalize_watchlist(config: WatchlistConfig) -> WatchlistConfig:
    """Return a normalized watchlist config for workflow consumers."""

    return WatchlistConfig(**config.model_dump())


def _load_watchlist() -> WatchlistConfig:
    """Load watchlist from JSON file, creating default if missing."""
    if not _WATCHLIST_PATH.exists():
        _save_watchlist(_DEFAULT_WATCHLIST)
        return _DEFAULT_WATCHLIST
    try:
        data = json.loads(_WATCHLIST_PATH.read_text(encoding="utf-8"))
        return _normalize_watchlist(WatchlistConfig(**data))
    except Exception as exc:
        logger.warning("failed to load watchlist: {}, using default", exc)
        return _DEFAULT_WATCHLIST


def _save_watchlist(config: WatchlistConfig) -> None:
    """Persist watchlist to JSON file."""
    normalized = _normalize_watchlist(config)
    _WATCHLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    _WATCHLIST_PATH.write_text(
        json.dumps(normalized.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


@router.get("/trading-status", response_model=TradingStatusResponse)
def trading_status() -> TradingStatusResponse:
    """Get current A-share trading session status."""
    return get_trading_status()


@router.get("/watchlist", response_model=WatchlistConfig)
def get_watchlist() -> WatchlistConfig:
    """Get current watchlist configuration."""
    return _load_watchlist()


@router.put("/watchlist", response_model=WatchlistConfig)
def update_watchlist(config: WatchlistConfig) -> WatchlistConfig:
    """Update watchlist configuration."""
    normalized = _normalize_watchlist(config)
    _save_watchlist(normalized)
    logger.info(
        "watchlist updated: {} watch sectors, {} watch stocks, {} position sectors, {} position stocks",
        len(normalized.watchlist.sectors),
        len(normalized.watchlist.stocks),
        len(normalized.positions.sectors),
        len(normalized.positions.stocks),
    )
    return normalized
