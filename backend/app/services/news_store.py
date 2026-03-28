from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..models import MarketNews


def _coerce_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date) and not isinstance(value, datetime):
        return datetime.combine(value, time.min)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        normalized = text.replace("T", " ")
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y%m%d %H:%M:%S", "%Y-%m-%d", "%Y%m%d"):
            try:
                parsed = datetime.strptime(normalized, fmt)
                if fmt in ("%Y-%m-%d", "%Y%m%d"):
                    return datetime.combine(parsed.date(), time.min)
                return parsed
            except ValueError:
                continue
    return None


def _json_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


def build_news_hash(item: dict[str, Any]) -> str:
    parts = [
        str(item.get("provider") or ""),
        str(item.get("platform") or ""),
        str(item.get("title") or ""),
        str(item.get("content") or item.get("summary") or ""),
        str(item.get("published_at") or item.get("published_at_text") or ""),
        str(item.get("url") or ""),
    ]
    return hashlib.sha256("||".join(parts).encode("utf-8")).hexdigest()


def upsert_market_news(db: Session, items: list[dict[str, Any]]) -> tuple[int, int]:
    if not items:
        return 0, 0

    enriched_items: list[dict[str, Any]] = []
    hashes: set[str] = set()
    for item in items:
        normalized = dict(item)
        normalized["content_hash"] = normalized.get("content_hash") or build_news_hash(normalized)
        normalized["published_at"] = _coerce_datetime(normalized.get("published_at"))
        normalized["published_at_text"] = normalized.get("published_at_text") or (
            str(item.get("published_at")) if item.get("published_at") is not None else None
        )
        normalized["raw_payload"] = _json_text(normalized.get("raw_payload"))
        hashes.add(normalized["content_hash"])
        enriched_items.append(normalized)

    existing_rows = db.execute(select(MarketNews).where(MarketNews.content_hash.in_(hashes))).scalars().all()
    existing_by_hash = {row.content_hash: row for row in existing_rows}

    inserted = 0
    updated = 0
    for item in enriched_items:
        row = existing_by_hash.get(item["content_hash"])
        if row is None:
            row = MarketNews(
                provider=item["provider"],
                platform=item["platform"],
                source=item.get("source"),
                title=item["title"],
                summary=item.get("summary"),
                content=item.get("content"),
                info_type=item.get("info_type"),
                security=item.get("security"),
                url=item.get("url"),
                published_at=item.get("published_at"),
                published_at_text=item.get("published_at_text"),
                content_hash=item["content_hash"],
                raw_payload=item.get("raw_payload"),
            )
            db.add(row)
            inserted += 1
            continue

        row.source = item.get("source")
        row.title = item["title"]
        row.summary = item.get("summary")
        row.content = item.get("content")
        row.info_type = item.get("info_type")
        row.security = item.get("security")
        row.url = item.get("url")
        row.published_at = item.get("published_at")
        row.published_at_text = item.get("published_at_text")
        row.raw_payload = item.get("raw_payload")
        updated += 1

    db.commit()
    return inserted, updated


def latest_market_news(db: Session, limit: int = 20, page_no: int = 1) -> list[dict[str, Any]]:
    offset = max(0, page_no - 1) * limit
    rows = db.execute(
        select(MarketNews).order_by(desc(MarketNews.published_at), desc(MarketNews.id)).offset(offset).limit(limit)
    ).scalars().all()
    items: list[dict[str, Any]] = []
    for row in rows:
        items.append(
            {
                "title": row.title,
                "content": row.content or row.summary or "",
                "date": row.published_at.strftime("%Y-%m-%d %H:%M:%S") if row.published_at else row.published_at_text,
                "source": row.source or row.platform,
                "info_type": row.info_type,
                "security": row.security,
            }
        )
    return items
