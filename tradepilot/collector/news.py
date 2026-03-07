"""News collector skeleton.

Phase-one stub: defines the collector interface and data flow.
Actual scraping logic will be added when AKShare news APIs are validated.
"""

from loguru import logger

from tradepilot.db import get_conn
from tradepilot.ingestion.models import NewsItemRecord


class NewsCollector:
    """Collect financial news from AKShare and persist to DuckDB."""

    def collect(self, stock_codes: list[str] | None = None) -> list[NewsItemRecord]:
        """Fetch and store news items.

        Args:
            stock_codes: Optional stock filter. If empty, fetch market-wide news.

        Returns:
            List of persisted news records.
        """
        logger.info("NewsCollector.collect called (stub), stock_codes={}", stock_codes)
        # TODO: call akshare stock_news_em, transform, dedup, persist
        return []

    def _persist(self, items: list[NewsItemRecord]) -> int:
        """Write news items to DuckDB, skipping duplicates.

        Args:
            items: News records to persist.

        Returns:
            Number of newly inserted rows.
        """
        if not items:
            return 0
        conn = get_conn()
        inserted = 0
        for item in items:
            try:
                conn.execute(
                    """
                    INSERT INTO news_items (source, source_item_id, title, content, category, published_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT DO NOTHING
                    """,
                    [item.source, item.source_item_id, item.title, item.content, item.category, item.published_at],
                )
                inserted += 1
            except Exception:
                logger.exception("Failed to persist news item {}", item.source_item_id)
        return inserted
