from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import akshare as ak
import pandas as pd

from .mx import normalize_market, normalize_symbol


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
A_SHARE_CLOSE_TIME = time(15, 0)
HK_CLOSE_TIME = time(16, 0)


def _a_share_prefixed_symbol(symbol: str) -> str:
    if symbol.startswith(("5", "6", "9")):
        return f"sh{symbol}"
    if symbol.startswith(("4", "8")):
        return f"bj{symbol}"
    return f"sz{symbol}"


def _history_cutoff_date(market: str) -> date:
    now = datetime.now(SHANGHAI_TZ)
    close_time = A_SHARE_CLOSE_TIME if market == "a" else HK_CLOSE_TIME
    if now.time() < close_time:
        return now.date() - timedelta(days=1)
    return now.date()


def expected_latest_trade_date(market: str) -> date:
    return _history_cutoff_date(normalize_market(market))


def _normalize_history_frame(frame: pd.DataFrame, symbol: str, source: str, market: str) -> pd.DataFrame:
    df = frame.copy()
    if "date" not in df.columns:
        raise ValueError(f"{source} 历史数据缺少 date 列")
    for column in ("open", "high", "low", "close"):
        if column not in df.columns:
            raise ValueError(f"{source} 历史数据缺少 {column} 列")
    if "volume" not in df.columns:
        df["volume"] = df.get("amount", 0.0)
    df["date"] = pd.to_datetime(df["date"])
    for column in ("open", "high", "low", "close", "volume"):
        df[column] = pd.to_numeric(df[column], errors="coerce")
    cutoff_date = _history_cutoff_date(market)
    df = df[df["date"].dt.date <= cutoff_date]
    df = df.dropna(subset=["date", "open", "high", "low", "close"]).sort_values("date").reset_index(drop=True)
    df["symbol"] = symbol
    df["source"] = source
    return df[["date", "open", "high", "low", "close", "volume", "symbol", "source"]]


def _load_sina(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    return _normalize_history_frame(
        ak.stock_zh_a_daily(symbol=_a_share_prefixed_symbol(symbol), start_date=start_date, end_date=end_date, adjust="qfq"),
        symbol,
        "akshare-sina",
        "a",
    )


def _load_tencent(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    return _normalize_history_frame(
        ak.stock_zh_a_hist_tx(symbol=_a_share_prefixed_symbol(symbol), start_date=start_date, end_date=end_date, adjust="qfq"),
        symbol,
        "akshare-tencent",
        "a",
    )


def _normalize_hk_frame(frame: pd.DataFrame, symbol: str, source: str) -> pd.DataFrame:
    df = frame.copy()
    if "date" not in df.columns:
        raise ValueError(f"{source} 港股历史数据缺少 date 列")
    for column in ("open", "high", "low", "close"):
        if column not in df.columns:
            raise ValueError(f"{source} 港股历史数据缺少 {column} 列")
    if "volume" not in df.columns:
        df["volume"] = df.get("amount", 0.0)
    df["date"] = pd.to_datetime(df["date"])
    for column in ("open", "high", "low", "close", "volume"):
        df[column] = pd.to_numeric(df[column], errors="coerce")
    cutoff_date = _history_cutoff_date("hk")
    df = df[df["date"].dt.date <= cutoff_date]
    df = df.dropna(subset=["date", "open", "high", "low", "close"]).sort_values("date").reset_index(drop=True)
    df["symbol"] = symbol
    df["source"] = source
    return df[["date", "open", "high", "low", "close", "volume", "symbol", "source"]]


def _load_hk_sina(symbol: str) -> pd.DataFrame:
    return _normalize_hk_frame(
        ak.stock_hk_daily(symbol=symbol, adjust="qfq"),
        symbol,
        "akshare-hk-sina",
    )


def _load_hk_em(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    frame = ak.stock_hk_hist(symbol=symbol, period="daily", start_date=start_date, end_date=end_date, adjust="qfq")
    df = frame.rename(
        columns={
            "日期": "date",
            "开盘": "open",
            "收盘": "close",
            "最高": "high",
            "最低": "low",
            "成交量": "volume",
        }
    )
    return _normalize_hk_frame(df, symbol, "akshare-hk-eastmoney")


def _traceability(sina_df: pd.DataFrame | None, tencent_df: pd.DataFrame | None) -> dict:
    trace = {
        "primary_source": None,
        "secondary_source": None,
        "sina_last_date": None,
        "tencent_last_date": None,
        "overlap_days": 0,
        "latest_close_diff": None,
        "latest_high_diff": None,
        "latest_low_diff": None,
    }
    if sina_df is not None and not sina_df.empty:
        trace["sina_last_date"] = sina_df.iloc[-1]["date"].date().isoformat()
    if tencent_df is not None and not tencent_df.empty:
        trace["tencent_last_date"] = tencent_df.iloc[-1]["date"].date().isoformat()
    if sina_df is not None and not sina_df.empty:
        trace["primary_source"] = "akshare-sina"
    if tencent_df is not None and not tencent_df.empty:
        trace["secondary_source"] = "akshare-tencent" if trace["primary_source"] else None
    if sina_df is None or sina_df.empty or tencent_df is None or tencent_df.empty:
        return trace

    merged = sina_df.merge(
        tencent_df,
        on="date",
        how="inner",
        suffixes=("_sina", "_tencent"),
    )
    if merged.empty:
        return trace
    latest = merged.iloc[-1]
    trace["overlap_days"] = int(len(merged))
    trace["latest_close_diff"] = round(float(latest["close_sina"] - latest["close_tencent"]), 4)
    trace["latest_high_diff"] = round(float(latest["high_sina"] - latest["high_tencent"]), 4)
    trace["latest_low_diff"] = round(float(latest["low_sina"] - latest["low_tencent"]), 4)
    return trace


def _resolve_a_share_name(symbol: str) -> str | None:
    try:
        info = ak.stock_individual_info_em(symbol=symbol)
    except Exception:
        return None
    if info is None or info.empty or "item" not in info.columns or "value" not in info.columns:
        return None
    matched = info.loc[info["item"] == "股票简称", "value"]
    if matched.empty:
        return None
    value = matched.iloc[0]
    return str(value).strip() if value not in (None, "") else None


def resolve_security_name(symbol: str, market: str, fallback: str | None = None) -> str:
    resolved_market = normalize_market(market)
    resolved_symbol = normalize_symbol(symbol, resolved_market)
    if resolved_market == "a":
        return _resolve_a_share_name(resolved_symbol) or fallback or resolved_symbol
    return fallback or resolved_symbol


def fetch_watchlist_snapshot(symbol: str, market: str, display_name: str | None = None) -> dict:
    history_df, trace = fetch_a_share_t_minus_1_history(symbol, market, trading_days=5)
    if history_df.empty:
        raise ValueError("未获取到可用于本地自选刷新的历史行情")
    latest = history_df.iloc[-1]
    latest_date = latest["date"]
    latest_trade_date = latest_date.date().isoformat() if hasattr(latest_date, "date") else str(latest_date)
    resolved_market = normalize_market(market)
    resolved_symbol = normalize_symbol(symbol, resolved_market)
    return {
        "symbol": resolved_symbol,
        "market": resolved_market,
        "display_name": resolve_security_name(resolved_symbol, resolved_market, fallback=display_name),
        "price": float(latest["close"]),
        "open": float(latest["open"]),
        "close": float(latest["close"]),
        "high": float(latest["high"]),
        "low": float(latest["low"]),
        "trade_date": latest_trade_date,
        "source": trace.get("primary_source"),
    }


def fetch_a_share_t_minus_1_history(symbol: str, market: str, trading_days: int = 720) -> tuple[pd.DataFrame, dict]:
    resolved_market = normalize_market(market)
    resolved_symbol = normalize_symbol(symbol, resolved_market)

    if resolved_market == "hk":
        today = datetime.now(SHANGHAI_TZ).date()
        start_date = (today - timedelta(days=max(365, trading_days * 2))).strftime("%Y%m%d")
        end_date = (today + timedelta(days=1)).strftime("%Y%m%d")
        hk_sina_df = None
        hk_em_df = None
        errors: dict[str, str] = {}
        try:
            hk_sina_df = _load_hk_sina(resolved_symbol)
        except Exception as exc:
            errors["akshare-hk-sina"] = str(exc)
        try:
            hk_em_df = _load_hk_em(resolved_symbol, start_date, end_date)
        except Exception as exc:
            errors["akshare-hk-eastmoney"] = str(exc)

        candidates = [df for df in (hk_sina_df, hk_em_df) if df is not None and not df.empty]
        if not candidates:
            raise ValueError(f"港股历史数据暂不可用: {errors}")
        hk_df = max(candidates, key=lambda df: (df.iloc[-1]['date'], len(df)))
        trace = {
            "primary_source": hk_df.iloc[-1]["source"],
            "secondary_source": None,
            "sina_last_date": hk_sina_df.iloc[-1]["date"].date().isoformat() if hk_sina_df is not None and not hk_sina_df.empty else None,
            "tencent_last_date": hk_em_df.iloc[-1]["date"].date().isoformat() if hk_em_df is not None and not hk_em_df.empty else None,
            "overlap_days": 0,
            "latest_close_diff": None,
            "latest_high_diff": None,
            "latest_low_diff": None,
            "errors": errors,
        }
        hk_df = hk_df.tail(trading_days).reset_index(drop=True)
        return hk_df.drop(columns=["source"]), trace
    if resolved_market != "a":
        raise ValueError("当前量化分析仅支持 A 股与港股日线历史回测数据")

    today = datetime.now(SHANGHAI_TZ).date()
    start_date = (today - timedelta(days=max(365, trading_days * 2))).strftime("%Y%m%d")
    end_date = (today + timedelta(days=1)).strftime("%Y%m%d")

    sina_df = None
    tencent_df = None
    errors: dict[str, str] = {}
    try:
        sina_df = _load_sina(resolved_symbol, start_date, end_date)
    except Exception as exc:
        errors["akshare-sina"] = str(exc)
    try:
        tencent_df = _load_tencent(resolved_symbol, start_date, end_date)
    except Exception as exc:
        errors["akshare-tencent"] = str(exc)

    primary = sina_df if sina_df is not None and not sina_df.empty else tencent_df
    if primary is None or primary.empty:
        raise ValueError(f"新浪与腾讯历史数据均不可用: {errors}")

    trace = _traceability(sina_df, tencent_df)
    trace["errors"] = errors
    trace["primary_source"] = primary.iloc[-1]["source"]
    primary = primary.tail(trading_days).reset_index(drop=True)
    return primary.drop(columns=["source"]), trace
