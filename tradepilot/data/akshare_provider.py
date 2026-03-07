"""AKShare-backed structured market data provider (stub).

Full implementation will call akshare APIs with retry and rate-limit handling.
For now, this delegates to MockProvider so the wiring can be verified end-to-end.
"""

from loguru import logger
import pandas as pd

from tradepilot.data.mock_provider import MockProvider
from tradepilot.data.provider import DataProvider


class AKShareProvider(DataProvider):
    """Structured data provider backed by akshare.

    Phase-one stub: delegates to MockProvider and logs calls.
    Replace method bodies with real akshare calls as each dataset is validated.
    """

    def __init__(self) -> None:
        self._fallback = MockProvider()
        logger.info("AKShareProvider initialised (stub mode)")

    def get_stock_daily(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """Return daily OHLCV data for a stock."""
        logger.debug("akshare stub: get_stock_daily {}", stock_code)
        return self._fallback.get_stock_daily(stock_code, start_date, end_date)

    def get_stock_weekly(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """Return weekly OHLCV data for a stock."""
        logger.debug("akshare stub: get_stock_weekly {}", stock_code)
        return self._fallback.get_stock_weekly(stock_code, start_date, end_date)

    def get_stock_monthly(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """Return monthly OHLCV data for a stock."""
        logger.debug("akshare stub: get_stock_monthly {}", stock_code)
        return self._fallback.get_stock_monthly(stock_code, start_date, end_date)

    def get_index_daily(self, index_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """Return daily OHLCV data for an index."""
        logger.debug("akshare stub: get_index_daily {}", index_code)
        return self._fallback.get_index_daily(index_code, start_date, end_date)

    def get_etf_flow(self, etf_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """Return ETF flow data."""
        logger.debug("akshare stub: get_etf_flow {}", etf_code)
        return self._fallback.get_etf_flow(etf_code, start_date, end_date)

    def get_margin_data(self, start_date: str, end_date: str) -> pd.DataFrame:
        """Return margin trading data."""
        logger.debug("akshare stub: get_margin_data")
        return self._fallback.get_margin_data(start_date, end_date)

    def get_northbound_flow(self, start_date: str, end_date: str) -> pd.DataFrame:
        """Return northbound capital flow data."""
        logger.debug("akshare stub: get_northbound_flow")
        return self._fallback.get_northbound_flow(start_date, end_date)

    def get_stock_valuation(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """Return valuation data for a stock."""
        logger.debug("akshare stub: get_stock_valuation {}", stock_code)
        return self._fallback.get_stock_valuation(stock_code, start_date, end_date)

    def get_sector_data(self, start_date: str, end_date: str) -> pd.DataFrame:
        """Return aggregated sector metrics."""
        logger.debug("akshare stub: get_sector_data")
        return self._fallback.get_sector_data(start_date, end_date)

    def get_sector_stocks(self, sector: str, as_of_date: str | None = None) -> pd.DataFrame:
        """Return stock members for a sector."""
        logger.debug("akshare stub: get_sector_stocks {}", sector)
        return self._fallback.get_sector_stocks(sector, as_of_date)

    def get_stock_sector(self, stock_code: str, as_of_date: str | None = None) -> pd.DataFrame:
        """Return sector mappings for a stock."""
        logger.debug("akshare stub: get_stock_sector {}", stock_code)
        return self._fallback.get_stock_sector(stock_code, as_of_date)
