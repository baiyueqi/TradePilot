"""Collect financial news from public market news feeds."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime

import requests
from loguru import logger

from tradepilot.db import get_conn
from tradepilot.ingestion.models import NewsItemRecord

_NEWS_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


class NewsCollector:
    """Collect financial news from public feeds and persist to DuckDB."""

    def collect(self, stock_codes: list[str] | None = None) -> list[NewsItemRecord]:
        """Fetch and store news items.

        Args:
            stock_codes: Optional stock filter. If empty, fetch market-wide news.

        Returns:
            List of persisted news records.
        """
        logger.info("NewsCollector.collect called, stock_codes={}", stock_codes)
        items = self._fetch_cls_telegraph(limit=40) + self._fetch_eastmoney_kuaixun(limit=30)
        items = self._deduplicate(items)
        if stock_codes:
            items = self._filter_by_stock_codes(items, stock_codes)
        records = [self._to_record(item) for item in items]
        self._persist(records)
        return records

    def _fetch_cls_telegraph(self, limit: int = 30) -> list[dict]:
        """Fetch telegraph news from CLS."""
        api = "https://www.cls.cn/nodeapi/updateTelegraphList"
        params = {"app": "CailianpressWeb", "os": "web", "sv": "7.7.5", "rn": str(limit)}
        try:
            data = requests.get(api, params=params, headers=_NEWS_HEADERS, timeout=10).json()
        except Exception as exc:
            logger.warning("cls telegraph fetch failed: {}", exc)
            return []

        items: list[dict] = []
        for roll in data.get("data", {}).get("roll_data", []):
            title = roll.get("title") or roll.get("brief") or (roll.get("content") or "")[:80]
            if not title:
                continue
            content = roll.get("content") or roll.get("brief") or title
            share_url = roll.get("shareurl", "")
            item_id = str(roll.get("id") or self._hash_id(title, content))
            published_at = self._from_timestamp(roll.get("ctime"))
            subjects = [
                subject.get("subject_name", "")
                for subject in (roll.get("subjects") or [])
                if subject.get("subject_name")
            ]
            stocks = [
                stock.get("stock_code", "") or stock.get("secu_code", "")
                for stock in (roll.get("stock_list") or [])
                if stock.get("stock_code") or stock.get("secu_code")
            ]
            items.append(
                {
                    "source": "cls_telegraph",
                    "source_item_id": item_id,
                    "title": title,
                    "content": content,
                    "category": self._categorize(title, content, subjects),
                    "published_at": published_at,
                    "url": share_url or f"https://www.cls.cn/detail/{item_id}",
                    "subjects": subjects,
                    "stock_codes": stocks,
                }
            )
        return items

    def _fetch_eastmoney_kuaixun(self, limit: int = 30) -> list[dict]:
        """Fetch kuaixun news from Eastmoney."""
        api = "https://np-listapi.eastmoney.com/comm/web/getNewsByColumns"
        params = {
            "column": "350",
            "pageSize": str(limit),
            "pageIndex": "1",
            "client": "web",
            "biz": "web_news_col",
            "req_trace": str(int(datetime.now().timestamp() * 1000)),
        }
        try:
            data = requests.get(api, params=params, headers=_NEWS_HEADERS, timeout=10).json()
        except Exception as exc:
            logger.warning("eastmoney kuaixun fetch failed: {}", exc)
            return []

        items: list[dict] = []
        for article in (data.get("data") or {}).get("list", []):
            title = article.get("title", "")
            if not title:
                continue
            content = article.get("digest", "") or title
            item_id = str(article.get("code") or article.get("infoCode") or self._hash_id(title, content))
            published_at = self._parse_datetime(article.get("showTime"))
            items.append(
                {
                    "source": "eastmoney_kuaixun",
                    "source_item_id": item_id,
                    "title": title,
                    "content": content,
                    "category": self._categorize(title, content),
                    "published_at": published_at,
                    "url": article.get("uniqueUrl", "") or article.get("url", ""),
                    "subjects": [],
                    "stock_codes": [],
                }
            )
        return items

    def _deduplicate(self, items: list[dict]) -> list[dict]:
        """Remove duplicate news items by source item id and normalized title."""
        seen_ids: set[str] = set()
        seen_titles: set[str] = set()
        result: list[dict] = []
        for item in items:
            source_item_id = str(item.get("source_item_id") or "")
            title = str(item.get("title") or "")
            title_key = re.sub(r"[\s\u3000:：,，。.!！?？【】\[\]()（）]", "", title)[:20]
            if source_item_id and source_item_id in seen_ids:
                continue
            if title_key and title_key in seen_titles:
                continue
            if source_item_id:
                seen_ids.add(source_item_id)
            if title_key:
                seen_titles.add(title_key)
            result.append(item)
        return result

    def _filter_by_stock_codes(self, items: list[dict], stock_codes: list[str]) -> list[dict]:
        """Filter items to stock-linked news when stock codes are provided."""
        stock_code_set = {code.strip() for code in stock_codes if code.strip()}
        if not stock_code_set:
            return items
        result: list[dict] = []
        for item in items:
            linked_codes = {str(code).strip() for code in item.get("stock_codes", []) if str(code).strip()}
            if linked_codes & stock_code_set:
                result.append(item)
        return result

    def _to_record(self, item: dict) -> NewsItemRecord:
        """Convert a fetched dict item to the persisted schema."""
        return NewsItemRecord(
            source=item["source"],
            source_item_id=str(item["source_item_id"]),
            title=item["title"],
            content=item.get("content", "") or item["title"],
            category=item.get("category"),
            published_at=item.get("published_at"),
        )

    def _categorize(self, title: str, content: str, subjects: list[str] | None = None) -> str:
        """Apply lightweight category mapping compatible with workflow usage."""
        text = " ".join([title, content, " ".join(subjects or [])])
        keyword_mapping = {
            "macro": ["经济", "货币", "财政", "美联储", "CPI", "PPI", "GDP", "降息", "加息"],
            "industry": ["行业", "景气", "产业链", "算力", "机器人", "半导体", "新能源"],
            "company": ["公告", "业绩", "财报", "订单", "中标", "合作", "融资"],
            "geopolitics": ["关税", "制裁", "冲突", "外交", "地缘"],
            "overseas": ["美股", "纳指", "标普", "英伟达", "特斯拉", "海外"],
        }
        for category, keywords in keyword_mapping.items():
            if any(keyword.lower() in text.lower() for keyword in keywords):
                return category
        return "industry"

    def _hash_id(self, title: str, content: str) -> str:
        """Build a deterministic fallback identifier for one news item."""
        payload = f"{title}|{content}".encode("utf-8", errors="ignore")
        return hashlib.md5(payload).hexdigest()

    def _from_timestamp(self, timestamp: int | float | str | None) -> datetime | None:
        """Convert a unix timestamp to datetime if possible."""
        if timestamp in (None, ""):
            return None
        try:
            return datetime.fromtimestamp(int(timestamp))
        except Exception:
            return None

    def _parse_datetime(self, value: str | None) -> datetime | None:
        """Parse Eastmoney datetime string."""
        if not value:
            return None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
        return None

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
                before = conn.execute(
                    "SELECT 1 FROM news_items WHERE source = ? AND source_item_id = ? LIMIT 1",
                    [item.source, item.source_item_id],
                ).fetchone()
                conn.execute(
                    """
                    INSERT INTO news_items (source, source_item_id, title, content, category, published_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT DO NOTHING
                    """,
                    [item.source, item.source_item_id, item.title, item.content, item.category, item.published_at],
                )
                if before is None:
                    inserted += 1
            except Exception:
                logger.exception("Failed to persist news item {}", item.source_item_id)
        return inserted
