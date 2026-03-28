from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AnalysisRecord, User
from ..schemas import AnalysisHistoryItem, AnalysisRequest, AnalysisRunResponse, StrategyCatalogItem, StrategyRunResult
from ..security import get_current_user
from ..services.mx import normalize_market, normalize_symbol
from ..services.akshare_history import expected_latest_trade_date
from ..services.strategies import (
    DEFAULT_BOLLINGER_WINDOW,
    DEFAULT_LOOKBACK_PERIOD,
    DEFAULT_PRICE_FREQUENCY,
    list_strategies,
    resolve_bollinger_window,
    resolve_lookback_period,
    run_strategies,
)


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")

router = APIRouter(prefix="/analysis", tags=["analysis"], dependencies=[Depends(get_current_user)])


@router.get("/strategies", response_model=list[StrategyCatalogItem])
def strategies():
    return [StrategyCatalogItem(**item) for item in list_strategies()]


@router.post("/run", response_model=AnalysisRunResponse)
def run_analysis(payload: AnalysisRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        resolved_market = normalize_market(payload.market)
        resolved_symbol = normalize_symbol(payload.symbol, resolved_market)
        resolved_lookback = resolve_lookback_period(payload.lookback_period)
        resolved_window = resolve_bollinger_window(payload.bollinger_window)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    today = datetime.now(SHANGHAI_TZ).date()

    existing_rows = (
        db.query(AnalysisRecord)
        .filter(AnalysisRecord.user_id == current_user.id)
        .filter(AnalysisRecord.symbol == resolved_symbol)
        .filter(AnalysisRecord.market == resolved_market)
        .filter(AnalysisRecord.lookback_period == resolved_lookback["key"])
        .filter(AnalysisRecord.bollinger_window == resolved_window["key"])
        .filter(AnalysisRecord.price_frequency == DEFAULT_PRICE_FREQUENCY)
        .filter(AnalysisRecord.strategy_key.in_(payload.strategies))
        .filter(func.date(AnalysisRecord.created_at) == today)
        .order_by(AnalysisRecord.created_at.desc())
        .all()
    )
    existing_map = {row.strategy_key: row for row in existing_rows}
    latest_expected_trade_date = expected_latest_trade_date(resolved_market).isoformat()
    valid_existing_map: dict[str, AnalysisRecord] = {}
    for strategy_key, row in existing_map.items():
        try:
            result_payload = json.loads(row.result_payload) if row.result_payload else {}
        except json.JSONDecodeError:
            continue
        trade_date = ((result_payload.get("summary") or {}).get("trade_date") or "").strip()
        if trade_date == latest_expected_trade_date:
            valid_existing_map[strategy_key] = row
    existing_map = valid_existing_map
    missing_strategy_keys = [strategy_key for strategy_key in payload.strategies if strategy_key not in existing_map]
    fresh_items: dict[str, dict] = {}

    if missing_strategy_keys:
        try:
            results = run_strategies(
                resolved_symbol,
                resolved_market,
                missing_strategy_keys,
                lookback_period=resolved_lookback["key"],
                bollinger_window=resolved_window["key"],
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        for item in results:
            request_payload = {
                **payload.model_dump(),
                "symbol": resolved_symbol,
                "market": resolved_market,
                "lookback_period": resolved_lookback["key"],
                "bollinger_window": resolved_window["key"],
                "price_frequency": DEFAULT_PRICE_FREQUENCY,
            }
            record = AnalysisRecord(
                user_id=current_user.id,
                symbol=item["payload"]["symbol"],
                market=item["payload"]["market"],
                strategy_key=item["key"],
                lookback_period=resolved_lookback["key"],
                bollinger_window=resolved_window["key"],
                price_frequency=DEFAULT_PRICE_FREQUENCY,
                request_payload=json.dumps(request_payload, ensure_ascii=False),
                result_payload=json.dumps(item["payload"], ensure_ascii=False),
            )
            db.add(record)
            fresh_items[item["key"]] = item
        db.commit()

    response_items = []
    for strategy_key in payload.strategies:
        if strategy_key in fresh_items:
            item = fresh_items[strategy_key]
            response_items.append(StrategyRunResult(key=item["key"], title=item["title"], payload=item["payload"]))
            continue

        cached_row = existing_map[strategy_key]
        response_items.append(
            StrategyRunResult(
                key=cached_row.strategy_key,
                title=next((item["title"] for item in list_strategies() if item["key"] == cached_row.strategy_key), cached_row.strategy_key),
                payload=json.loads(cached_row.result_payload),
            )
        )

    return AnalysisRunResponse(
        symbol=resolved_symbol,
        market=resolved_market,
        lookback_period=resolved_lookback["key"],
        bollinger_window=resolved_window["key"],
        price_frequency=DEFAULT_PRICE_FREQUENCY,
        cached=not missing_strategy_keys,
        results=response_items,
    )


@router.get("/history", response_model=list[AnalysisHistoryItem])
def history(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    rows = (
        db.query(AnalysisRecord)
        .filter(AnalysisRecord.user_id == current_user.id)
        .order_by(AnalysisRecord.created_at.desc())
        .limit(30)
        .all()
    )
    return [
        AnalysisHistoryItem(
            id=row.id,
            symbol=row.symbol,
            market=row.market,
            strategy_key=row.strategy_key,
            lookback_period=row.lookback_period or DEFAULT_LOOKBACK_PERIOD,
            bollinger_window=row.bollinger_window or DEFAULT_BOLLINGER_WINDOW,
            price_frequency=row.price_frequency or DEFAULT_PRICE_FREQUENCY,
            request_payload=json.loads(row.request_payload) if row.request_payload else None,
            result_payload=json.loads(row.result_payload),
            created_at=row.created_at,
        )
        for row in rows
    ]
