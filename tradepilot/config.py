from pathlib import Path
from enum import StrEnum


class DataProviderType(StrEnum):
    """Supported structured market data providers."""

    MOCK = "mock"
    AKSHARE = "akshare"


DB_PATH = Path(__file__).parent.parent / "data" / "tradepilot.duckdb"
DATA_PROVIDER = DataProviderType.MOCK
DATA_ROOT = Path(__file__).parent.parent / "data"
BILIBILI_STORAGE_PATH = DATA_ROOT / "bilibili"
