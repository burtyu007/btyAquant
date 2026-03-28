#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import sys
from typing import Any


MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = os.getenv("MYSQL_PORT", "3380")
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "Burtyu1989")
MYSQL_DB = os.getenv("MYSQL_DB", "quant")
MX_APIKEY = os.getenv("MX_APIKEY", "")

os.environ["MYSQL_HOST"] = MYSQL_HOST
os.environ["MYSQL_PORT"] = str(MYSQL_PORT)
os.environ["MYSQL_USER"] = MYSQL_USER
os.environ["MYSQL_PASSWORD"] = MYSQL_PASSWORD
os.environ["MYSQL_DB"] = MYSQL_DB

from backend.app.db import SessionLocal, engine
from backend.app.models import MarketNews
from backend.app.services.mx import MXSearchClient
from backend.app.services.news_store import upsert_market_news


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="使用 MX Skills 抓取财经热点并写入 quant.market_news")
    parser.add_argument(
        "--query",
        default="中国财经要闻 A股 港股 经济 金融 市场 热点",
        help="MX 新闻搜索关键词，默认抓中国财经与市场热点",
    )
    parser.add_argument("--limit", type=int, default=30, help="入库条数上限，默认 30")
    return parser.parse_args()


def _normalize_items(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in rows[:limit]:
        content = (row.get("content") or "").strip()
        items.append(
            {
                "provider": "mx",
                "platform": "mx_hot",
                "source": (row.get("insName") or "东方财富妙想").strip(),
                "title": (row.get("title") or "").strip() or (content[:48] if content else "MX 热点"),
                "summary": content[:200] or None,
                "content": content,
                "info_type": row.get("informationType"),
                "security": row.get("entityFullName"),
                "published_at": row.get("date"),
                "published_at_text": row.get("date"),
                "raw_payload": row,
            }
        )
    return items


def main() -> int:
    args = parse_args()
    MarketNews.__table__.create(bind=engine, checkfirst=True)

    if not MX_APIKEY:
        print("MX_APIKEY 未配置，请先导出环境变量或直接修改脚本顶部变量。", file=sys.stderr)
        return 1

    client = MXSearchClient(api_key=MX_APIKEY)
    try:
        rows = client.search(args.query)
    except Exception as exc:
        print(f"MX 新闻抓取失败: {exc}", file=sys.stderr)
        return 1

    items = _normalize_items(rows, args.limit)
    if not items:
        print("MX 新闻接口没有返回可入库的热点数据。", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        inserted, updated = upsert_market_news(db, items)
    finally:
        db.close()

    print(f"[MX] 入库完成，收集 {len(items)} 条，新增 {inserted} 条，更新 {updated} 条。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
