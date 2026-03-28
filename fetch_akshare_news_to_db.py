#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date, datetime, time
from typing import Any, Callable

import akshare as ak


MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = os.getenv("MYSQL_PORT", "3380")
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "Burtyu1989")
MYSQL_DB = os.getenv("MYSQL_DB", "quant")

os.environ["MYSQL_HOST"] = MYSQL_HOST
os.environ["MYSQL_PORT"] = str(MYSQL_PORT)
os.environ["MYSQL_USER"] = MYSQL_USER
os.environ["MYSQL_PASSWORD"] = MYSQL_PASSWORD
os.environ["MYSQL_DB"] = MYSQL_DB

from backend.app.db import SessionLocal, engine
from backend.app.models import MarketNews
from backend.app.services.news_store import upsert_market_news


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _title_from_content(text: str, fallback: str = "财经快讯") -> str:
    cleaned = _clean_text(text)
    if not cleaned:
        return fallback
    if cleaned.startswith("【") and "】" in cleaned:
        return cleaned.split("】", 1)[0] + "】"
    for token in ("。", "！", "？", "；"):
        if token in cleaned:
            return cleaned.split(token, 1)[0][:48]
    return cleaned[:48]


def _combine_date_and_time(raw_date: Any, raw_time: Any) -> datetime | None:
    parsed_date: date | None = None
    parsed_time: time | None = None

    if isinstance(raw_date, datetime):
        return raw_date
    if isinstance(raw_date, date):
        parsed_date = raw_date
    elif raw_date not in (None, ""):
        text = str(raw_date).strip()
        for fmt in ("%Y-%m-%d", "%Y%m%d"):
            try:
                parsed_date = datetime.strptime(text, fmt).date()
                break
            except ValueError:
                continue

    if isinstance(raw_time, datetime):
        parsed_time = raw_time.time()
    elif isinstance(raw_time, time):
        parsed_time = raw_time
    elif raw_time not in (None, ""):
        text = str(raw_time).strip()
        for fmt in ("%H:%M:%S", "%H:%M"):
            try:
                parsed_time = datetime.strptime(text, fmt).time()
                break
            except ValueError:
                continue

    if parsed_date and parsed_time:
        return datetime.combine(parsed_date, parsed_time)
    if parsed_date:
        return datetime.combine(parsed_date, time.min)
    return None


def _fetch_eastmoney(limit: int) -> list[dict[str, Any]]:
    frame = ak.stock_info_global_em().head(limit)
    items: list[dict[str, Any]] = []
    for row in frame.to_dict(orient="records"):
        summary = _clean_text(row.get("摘要"))
        items.append(
            {
                "provider": "akshare",
                "platform": "eastmoney",
                "source": "东方财富",
                "title": _clean_text(row.get("标题")) or _title_from_content(summary, "东方财富快讯"),
                "summary": summary,
                "content": summary,
                "info_type": "全球财经快讯",
                "url": _clean_text(row.get("链接")) or None,
                "published_at": row.get("发布时间"),
                "published_at_text": _clean_text(row.get("发布时间")) or None,
                "raw_payload": row,
            }
        )
    return items


def _fetch_cls(limit: int) -> list[dict[str, Any]]:
    frame = ak.stock_info_global_cls().head(limit)
    items: list[dict[str, Any]] = []
    for row in frame.to_dict(orient="records"):
        content = _clean_text(row.get("内容"))
        published_at = _combine_date_and_time(row.get("发布日期"), row.get("发布时间"))
        items.append(
            {
                "provider": "akshare",
                "platform": "cls",
                "source": "财联社",
                "title": _clean_text(row.get("标题")) or _title_from_content(content, "财联社电报"),
                "summary": content[:200] or None,
                "content": content,
                "info_type": "电报",
                "published_at": published_at,
                "published_at_text": (
                    f"{row.get('发布日期')} {row.get('发布时间')}".strip()
                    if row.get("发布日期") or row.get("发布时间")
                    else None
                ),
                "raw_payload": row,
            }
        )
    return items


def _fetch_sina(limit: int) -> list[dict[str, Any]]:
    frame = ak.stock_info_global_sina().head(limit)
    items: list[dict[str, Any]] = []
    for row in frame.to_dict(orient="records"):
        content = _clean_text(row.get("内容"))
        items.append(
            {
                "provider": "akshare",
                "platform": "sina",
                "source": "新浪财经",
                "title": _title_from_content(content, "新浪财经快讯"),
                "summary": content[:200] or None,
                "content": content,
                "info_type": "全球财经快讯",
                "published_at": row.get("时间"),
                "published_at_text": _clean_text(row.get("时间")) or None,
                "raw_payload": row,
            }
        )
    return items


def _fetch_futu(limit: int) -> list[dict[str, Any]]:
    frame = ak.stock_info_global_futu().head(limit)
    items: list[dict[str, Any]] = []
    for row in frame.to_dict(orient="records"):
        content = _clean_text(row.get("内容"))
        title = _clean_text(row.get("标题")) or _title_from_content(content, "富途牛牛快讯")
        items.append(
            {
                "provider": "akshare",
                "platform": "futu",
                "source": "富途牛牛",
                "title": title,
                "summary": content[:200] or None,
                "content": content,
                "info_type": "快讯",
                "url": _clean_text(row.get("链接")) or None,
                "published_at": row.get("发布时间"),
                "published_at_text": _clean_text(row.get("发布时间")) or None,
                "raw_payload": row,
            }
        )
    return items


def _fetch_ths(limit: int) -> list[dict[str, Any]]:
    frame = ak.stock_info_global_ths().head(limit)
    items: list[dict[str, Any]] = []
    for row in frame.to_dict(orient="records"):
        content = _clean_text(row.get("内容"))
        items.append(
            {
                "provider": "akshare",
                "platform": "ths",
                "source": "同花顺",
                "title": _clean_text(row.get("标题")) or _title_from_content(content, "同花顺快讯"),
                "summary": content[:200] or None,
                "content": content,
                "info_type": "全球财经直播",
                "url": _clean_text(row.get("链接")) or None,
                "published_at": row.get("发布时间"),
                "published_at_text": _clean_text(row.get("发布时间")) or None,
                "raw_payload": row,
            }
        )
    return items


def _fetch_cctv(cctv_date: str, limit: int) -> list[dict[str, Any]]:
    frame = ak.news_cctv(date=cctv_date).head(limit)
    items: list[dict[str, Any]] = []
    for row in frame.to_dict(orient="records"):
        content = _clean_text(row.get("content"))
        items.append(
            {
                "provider": "akshare",
                "platform": "cctv",
                "source": "新闻联播",
                "title": _clean_text(row.get("title")) or _title_from_content(content, "新闻联播"),
                "summary": content[:200] or None,
                "content": content,
                "info_type": "新闻联播",
                "published_at": row.get("date"),
                "published_at_text": _clean_text(row.get("date")) or None,
                "raw_payload": row,
            }
        )
    return items


SOURCE_FETCHERS: dict[str, Callable[..., list[dict[str, Any]]]] = {
    "eastmoney": _fetch_eastmoney,
    "cls": _fetch_cls,
    "sina": _fetch_sina,
    "futu": _fetch_futu,
    "ths": _fetch_ths,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="使用 AKShare 抓取多平台财经热点并写入 quant.market_news")
    parser.add_argument("--per-source-limit", type=int, default=20, help="每个平台抓取条数，默认 20")
    parser.add_argument(
        "--sources",
        default="eastmoney,cls,sina,futu,ths",
        help="要抓取的平台列表，逗号分隔，默认 eastmoney,cls,sina,futu,ths",
    )
    parser.add_argument("--include-cctv", action="store_true", help="是否额外抓取新闻联播文字稿")
    parser.add_argument(
        "--cctv-date",
        default=datetime.now().strftime("%Y%m%d"),
        help="新闻联播日期，格式 YYYYMMDD，默认今天",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    MarketNews.__table__.create(bind=engine, checkfirst=True)

    selected_sources = [item.strip().lower() for item in args.sources.split(",") if item.strip()]
    collected: list[dict[str, Any]] = []
    errors: list[str] = []

    for source in selected_sources:
        fetcher = SOURCE_FETCHERS.get(source)
        if not fetcher:
            errors.append(f"{source}: 未识别的平台")
            continue
        try:
            items = fetcher(args.per_source_limit)
            collected.extend(items)
            print(f"[AKShare] {source} 抓取 {len(items)} 条")
        except Exception as exc:
            errors.append(f"{source}: {exc}")

    if args.include_cctv:
        try:
            cctv_items = _fetch_cctv(args.cctv_date, args.per_source_limit)
            collected.extend(cctv_items)
            print(f"[AKShare] cctv 抓取 {len(cctv_items)} 条")
        except Exception as exc:
            errors.append(f"cctv: {exc}")

    if not collected:
        print("未抓到任何 AKShare 财经热点数据。", file=sys.stderr)
        if errors:
            print("\n".join(errors), file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        inserted, updated = upsert_market_news(db, collected)
    finally:
        db.close()

    print(f"[AKShare] 入库完成，收集 {len(collected)} 条，新增 {inserted} 条，更新 {updated} 条。")
    if errors:
        print("[AKShare] 以下平台抓取失败：")
        for item in errors:
            print(f"  - {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
