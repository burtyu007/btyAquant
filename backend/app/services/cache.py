from __future__ import annotations

import json
from datetime import datetime, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

import redis

from ..config import settings


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


@lru_cache(maxsize=1)
def get_redis_client() -> redis.Redis:
    return redis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_db,
        password=settings.redis_password or None,
        decode_responses=True,
        socket_timeout=2,
        socket_connect_timeout=2,
    )


def recommendation_cache_key(user_id: int, keyword: str, page_no: int, page_size: int) -> str:
    return f"{settings.redis_key_prefix}:mx:recommend:{user_id}:{keyword}:{page_no}:{page_size}"


def mx_self_select_cache_key(user_id: int) -> str:
    return f"{settings.redis_key_prefix}:mx:self-select:{user_id}"


def recommendation_cache_ttl(now: datetime | None = None) -> int:
    current = now.astimezone(SHANGHAI_TZ) if now else datetime.now(SHANGHAI_TZ)
    market_open = current.replace(hour=9, minute=0, second=0, microsecond=0)
    market_close = current.replace(hour=15, minute=0, second=0, microsecond=0)

    if market_open <= current < market_close:
        return 3600
    if current >= market_close:
        next_open = market_open + timedelta(days=1)
        return max(60, int((next_open - current).total_seconds()))
    return max(60, int((market_open - current).total_seconds()))


def mx_self_select_cache_ttl() -> int:
    return 4 * 3600


def get_json(key: str) -> dict | None:
    try:
        cached = get_redis_client().get(key)
    except redis.RedisError:
        return None
    if not cached:
        return None
    try:
        return json.loads(cached)
    except json.JSONDecodeError:
        return None


def set_json(key: str, value: dict, ttl_seconds: int) -> None:
    try:
        get_redis_client().setex(key, ttl_seconds, json.dumps(value, ensure_ascii=False))
    except redis.RedisError:
        return


def delete_key(key: str) -> None:
    try:
        get_redis_client().delete(key)
    except redis.RedisError:
        return
