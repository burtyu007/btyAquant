from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..schemas import MXKlineItem, MXTrackerResponse, NewsItem, SmartRecommendationItem, SmartRecommendationResponse
from ..security import get_current_user, get_user_mx_api_key
from ..services.cache import get_json, recommendation_cache_key, recommendation_cache_ttl, set_json
from ..services.mx import MXDataClient, MXStockScreenClient
from ..services.news_store import latest_market_news


router = APIRouter(prefix="/market", tags=["market"], dependencies=[Depends(get_current_user)])


@router.get("/news", response_model=list[NewsItem])
def daily_news(
    page_no: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=20),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return [NewsItem(**item) for item in latest_market_news(db, limit=limit, page_no=page_no)]


@router.get("/recommendations", response_model=SmartRecommendationResponse)
def recommendations(
    keyword: str = Query(default="东财智选 推荐"),
    page_no: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=20),
    force_refresh: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
):
    cache_key = recommendation_cache_key(current_user.id, keyword, page_no, page_size)
    result = None if force_refresh else get_json(cache_key)
    if result is None:
        result = MXStockScreenClient(api_key=get_user_mx_api_key(current_user)).recommend(
            keyword=keyword,
            page_no=page_no,
            page_size=page_size,
        )
        set_json(cache_key, result, recommendation_cache_ttl())
    return SmartRecommendationResponse(
        keyword=result["keyword"],
        select_logic=result.get("select_logic"),
        page_no=page_no,
        page_size=page_size,
        total_count=result["total_count"],
        items=[SmartRecommendationItem(**item) for item in result["items"]],
    )


@router.get("/tracker", response_model=MXTrackerResponse)
def tracker(
    symbol: str = Query(..., min_length=1),
    market: str = Query(default="a"),
    current_user: User = Depends(get_current_user),
):
    result = MXDataClient(api_key=get_user_mx_api_key(current_user)).fetch_tracker_bundle(symbol=symbol, market=market)
    return MXTrackerResponse(
        symbol=result["symbol"],
        market=result["market"],
        display_name=result["display_name"],
        quote=result["quote"],
        daily_kline=[MXKlineItem(**item) for item in result["daily_kline"]],
        weekly_kline=[MXKlineItem(**item) for item in result["weekly_kline"]],
        monthly_kline=[MXKlineItem(**item) for item in result["monthly_kline"]],
        fundamentals=result["fundamentals"],
        analysis_points=result["analysis_points"],
    )
