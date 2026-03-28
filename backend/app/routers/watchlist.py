from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User, WatchlistItem
from ..schemas import MXWatchlistItem, MXWatchlistResponse, MessageResponse, WatchlistCreate, WatchlistOut
from ..security import get_current_user, get_user_mx_api_key
from ..services.akshare_history import fetch_watchlist_snapshot
from ..services.cache import delete_key, get_json, mx_self_select_cache_key, mx_self_select_cache_ttl, set_json
from ..services.mx import MXSelfSelectClient, normalize_market, normalize_symbol


router = APIRouter(prefix="/watchlist", tags=["watchlist"], dependencies=[Depends(get_current_user)])


def _refresh_item(item: WatchlistItem) -> WatchlistItem:
    quote = fetch_watchlist_snapshot(item.symbol, item.market, display_name=item.display_name)
    item.last_price = quote.get("price")
    item.open_price = quote.get("open")
    item.close_price = quote.get("close")
    item.day_high = quote.get("high")
    item.day_low = quote.get("low")
    item.last_price_at = datetime.now()
    item.display_name = quote.get("display_name") or item.display_name
    return item


@router.get("", response_model=list[WatchlistOut])
def list_watchlist(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    items = (
        db.query(WatchlistItem)
        .filter(WatchlistItem.user_id == current_user.id)
        .order_by(WatchlistItem.created_at.desc())
        .all()
    )
    return [WatchlistOut.model_validate(item) for item in items]


@router.post("", response_model=WatchlistOut)
def add_watchlist(payload: WatchlistCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    count = db.query(WatchlistItem).filter(WatchlistItem.user_id == current_user.id).count()
    if count >= 50:
        raise HTTPException(status_code=400, detail="每个用户最多添加 50 只自选股票")

    symbol = normalize_symbol(payload.symbol, payload.market)
    market = normalize_market(payload.market)
    existing = (
        db.query(WatchlistItem)
        .filter(WatchlistItem.user_id == current_user.id, WatchlistItem.symbol == symbol, WatchlistItem.market == market)
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="该股票已在自选中")

    item = WatchlistItem(user_id=current_user.id, symbol=symbol, market=market)
    _refresh_item(item)
    db.add(item)
    db.commit()
    db.refresh(item)
    return WatchlistOut.model_validate(item)


@router.post("/{item_id}/refresh", response_model=WatchlistOut)
def refresh_watchlist(item_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    item = db.query(WatchlistItem).filter(WatchlistItem.id == item_id, WatchlistItem.user_id == current_user.id).first()
    if not item:
        raise HTTPException(status_code=404, detail="自选项不存在")
    _refresh_item(item)
    db.commit()
    db.refresh(item)
    return WatchlistOut.model_validate(item)


@router.post("/refresh-all", response_model=list[WatchlistOut])
def refresh_all(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    items = db.query(WatchlistItem).filter(WatchlistItem.user_id == current_user.id).all()
    for item in items:
        _refresh_item(item)
    db.commit()
    for item in items:
        db.refresh(item)
    return [WatchlistOut.model_validate(item) for item in items]


@router.delete("/{item_id}", response_model=MessageResponse)
def delete_watchlist(item_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    item = db.query(WatchlistItem).filter(WatchlistItem.id == item_id, WatchlistItem.user_id == current_user.id).first()
    if not item:
        raise HTTPException(status_code=404, detail="自选项不存在")
    db.delete(item)
    db.commit()
    return MessageResponse(message="自选股票已删除")


@router.get("/mx-self-select", response_model=MXWatchlistResponse)
def mx_self_select(force_refresh: bool = False, current_user: User = Depends(get_current_user)):
    cache_key = mx_self_select_cache_key(current_user.id)
    result = None if force_refresh else get_json(cache_key)
    if result is None:
        result = MXSelfSelectClient(api_key=get_user_mx_api_key(current_user)).list_watchlist()
        set_json(cache_key, result, mx_self_select_cache_ttl())
    return MXWatchlistResponse(total_count=result["total_count"], items=[MXWatchlistItem(**item) for item in result["items"]])


@router.post("/mx-self-select", response_model=MessageResponse)
def add_mx_self_select(payload: WatchlistCreate, current_user: User = Depends(get_current_user)):
    market = normalize_market(payload.market)
    symbol = normalize_symbol(payload.symbol, market)
    MXSelfSelectClient(api_key=get_user_mx_api_key(current_user)).add_watchlist(symbol, market)
    delete_key(mx_self_select_cache_key(current_user.id))
    return MessageResponse(message=f"已同步将 {symbol} 加入 MX 自选")


@router.delete("/mx-self-select/{market}/{symbol}", response_model=MessageResponse)
def delete_mx_self_select(symbol: str, market: str, current_user: User = Depends(get_current_user)):
    resolved_market = normalize_market(market)
    resolved_symbol = normalize_symbol(symbol, resolved_market)
    MXSelfSelectClient(api_key=get_user_mx_api_key(current_user)).remove_watchlist(resolved_symbol, resolved_market)
    delete_key(mx_self_select_cache_key(current_user.id))
    return MessageResponse(message=f"已同步将 {resolved_symbol} 从 MX 自选删除")


@router.post("/mx-self-select/import", response_model=MessageResponse)
def import_mx_self_select(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = MXSelfSelectClient(api_key=get_user_mx_api_key(current_user)).list_watchlist()
    existing_items = db.query(WatchlistItem).filter(WatchlistItem.user_id == current_user.id).all()
    existing_keys = {(item.symbol, item.market) for item in existing_items}
    remaining_slots = max(0, 50 - len(existing_items))
    imported = 0
    skipped = 0

    for remote_item in result["items"]:
        if remaining_slots <= 0:
            skipped += 1
            continue
        item_key = (remote_item["symbol"], remote_item["market"])
        if item_key in existing_keys:
            skipped += 1
            continue
        item = WatchlistItem(
            user_id=current_user.id,
            symbol=remote_item["symbol"],
            market=remote_item["market"],
            display_name=remote_item.get("display_name"),
            last_price=remote_item.get("last_price"),
            close_price=remote_item.get("last_price"),
            day_high=remote_item.get("day_high"),
            day_low=remote_item.get("day_low"),
            last_price_at=datetime.now(),
        )
        db.add(item)
        existing_keys.add(item_key)
        imported += 1
        remaining_slots -= 1

    db.commit()
    return MessageResponse(message=f"已从 MX 自选同步 {imported} 只股票，跳过 {skipped} 只")
