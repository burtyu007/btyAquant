from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

import pandas as pd

from .akshare_history import fetch_a_share_t_minus_1_history
from .mx import MARKET_LABELS, normalize_market, normalize_symbol


DEFAULT_LOOKBACK_PERIOD = "2y"
DEFAULT_BOLLINGER_WINDOW = "20d"
DEFAULT_PRICE_FREQUENCY = "daily"

LOOKBACK_PERIODS = {
    "6m": {"label": "6个月", "trading_days": 126},
    "1y": {"label": "1年", "trading_days": 252},
    "2y": {"label": "2年", "trading_days": 504},
    "3y": {"label": "3年", "trading_days": 756},
    "5y": {"label": "5年", "trading_days": 1260},
    "10y": {"label": "10年", "trading_days": 2520},
}

WINDOWS = {
    "10d": {"label": "10日", "days": 10},
    "20d": {"label": "20日", "days": 20},
    "30d": {"label": "30日", "days": 30},
    "60d": {"label": "60日", "days": 60},
}


@dataclass
class StrategySpec:
    key: str
    title: str
    description: str
    handler: Callable[[str, str, str, str], dict]


def resolve_lookback_period(period_key: str | None) -> dict:
    resolved_key = (period_key or DEFAULT_LOOKBACK_PERIOD).lower()
    if resolved_key not in LOOKBACK_PERIODS:
        raise ValueError(f"未知历史回看区间: {period_key}")
    return {"key": resolved_key, **LOOKBACK_PERIODS[resolved_key]}


def resolve_bollinger_window(window_key: str | None) -> dict:
    resolved_key = (window_key or DEFAULT_BOLLINGER_WINDOW).lower()
    if resolved_key not in WINDOWS:
        raise ValueError(f"未知布林带窗口: {window_key}")
    return {"key": resolved_key, **WINDOWS[resolved_key]}


def _history_fetch_days(lookback: dict, window: dict) -> int:
    return max(lookback["trading_days"] + window["days"] * 3, 300)


def _zscore_recommendation(zscore: float) -> dict:
    if zscore > 2.5:
        return {
            "action": "激进做空 / 止损",
            "signal_meaning": "价格处于统计学肥尾区域，极小概率事件，随时可能反转或继续逼空。",
            "risk_level": "⭐⭐⭐⭐⭐",
        }
    if zscore > 1.8:
        return {
            "action": "尝试做空 / 减仓",
            "signal_meaning": "价格突破布林带上轨，是经典的均值回归卖点。",
            "risk_level": "⭐⭐⭐",
        }
    if zscore >= 0.4:
        return {
            "action": "谨慎持有 / 不追高",
            "signal_meaning": "价格偏离均值但未进入极端区间，继续追高的性价比下降。",
            "risk_level": "⭐⭐",
        }
    if zscore > -0.4:
        return {
            "action": "平仓 / 观望",
            "signal_meaning": "价格回归合理区间，是获利了结与等待下一次信号的区域。",
            "risk_level": "⭐",
        }
    if zscore >= -1.8:
        return {
            "action": "分批观察 / 轻仓低吸",
            "signal_meaning": "价格向下偏离均值但未到极端超卖，可小仓位等待确认。",
            "risk_level": "⭐⭐",
        }
    if zscore >= -2.5:
        return {
            "action": "尝试做多 / 建仓",
            "signal_meaning": "价格跌破布林带下轨，常见于非理性恐慌抛售后的抄底区。",
            "risk_level": "⭐⭐⭐",
        }
    return {
        "action": "激进做多 / 止损",
        "signal_meaning": "价格处于极端低位，回归概率高，但仍需防范黑天鹅继续下跌。",
        "risk_level": "⭐⭐⭐⭐⭐",
    }


def _bollinger_result(
    symbol: str,
    market: str,
    lookback_period: str = DEFAULT_LOOKBACK_PERIOD,
    bollinger_window: str = DEFAULT_BOLLINGER_WINDOW,
) -> dict:
    resolved_market = normalize_market(market)
    resolved_symbol = normalize_symbol(symbol, resolved_market)
    lookback = resolve_lookback_period(lookback_period)
    window = resolve_bollinger_window(bollinger_window)

    data, traceability = fetch_a_share_t_minus_1_history(
        resolved_symbol,
        resolved_market,
        trading_days=_history_fetch_days(lookback, window),
    )
    df = data.copy().tail(lookback["trading_days"]).reset_index(drop=True)
    if len(df) < window["days"] + 2:
        raise ValueError(f"{lookback['label']}范围内历史数据不足，无法计算 {window['label']} 布林带")

    num_std = 2.0
    df["mid"] = df["close"].rolling(window["days"]).mean()
    df["std"] = df["close"].rolling(window["days"]).std(ddof=0)
    df["upper"] = df["mid"] + num_std * df["std"]
    df["lower"] = df["mid"] - num_std * df["std"]
    df["zscore"] = (df["close"] - df["mid"]) / df["std"]
    df = df.dropna().reset_index(drop=True)
    if len(df) < 2:
        raise ValueError(f"{lookback['label']}范围内有效样本不足，无法完成回测")

    latest = df.iloc[-1]
    recommendation = _zscore_recommendation(float(latest["zscore"]))
    if latest["close"] <= latest["lower"]:
        state = "收盘价已触及下轨，属于低吸观察区。"
    elif latest["close"] <= latest["mid"]:
        state = "收盘价位于中轨下方，偏观察，等待更接近下轨。"
    elif latest["close"] >= latest["upper"]:
        state = "收盘价触及上轨，属于止盈或减仓区。"
    else:
        state = "收盘价位于中轨上方但未到上轨，偏中性。"

    commission = 0.0003
    stamp_tax = 0.001 if resolved_market == "a" else 0.0
    quantity = 100
    starting_cash = 200000.0
    cash = starting_cash
    position = 0
    entry_price = None
    entry_time = None
    trades: list[dict] = []
    equity_curve = []

    for idx in range(len(df) - 1):
        row = df.iloc[idx]
        next_row = df.iloc[idx + 1]
        next_open = float(next_row["open"])

        if position == 0 and row["close"] <= row["lower"]:
            cost = next_open * quantity
            buy_fee = cost * commission
            if cash >= cost + buy_fee:
                cash -= cost + buy_fee
                position = quantity
                entry_price = next_open
                entry_time = next_row["date"]
        elif position > 0 and row["close"] >= row["mid"]:
            proceeds = next_open * position
            sell_fee = proceeds * commission + proceeds * stamp_tax
            pnl = (next_open - float(entry_price)) * position - (float(entry_price) * position * commission) - sell_fee
            cash += proceeds - sell_fee
            trades.append(
                {
                    "entry_time": str(entry_time),
                    "exit_time": str(next_row["date"]),
                    "entry_price": round(float(entry_price), 4),
                    "exit_price": round(next_open, 4),
                    "net_pnl": round(pnl, 4),
                    "return_pct": round((next_open / float(entry_price) - 1) * 100, 4),
                }
            )
            position = 0
            entry_price = None
            entry_time = None

        market_value = cash + position * float(row["close"])
        equity_curve.append({"date": row["date"], "equity": market_value})

    if position > 0 and entry_price is not None and entry_time is not None:
        final_price = float(df.iloc[-1]["close"])
        proceeds = final_price * position
        sell_fee = proceeds * commission + proceeds * stamp_tax
        pnl = (final_price - float(entry_price)) * position - (float(entry_price) * position * commission) - sell_fee
        cash += proceeds - sell_fee
        trades.append(
            {
                "entry_time": str(entry_time),
                "exit_time": str(df.iloc[-1]["date"]),
                "entry_price": round(float(entry_price), 4),
                "exit_price": round(final_price, 4),
                "net_pnl": round(pnl, 4),
                "return_pct": round((final_price / float(entry_price) - 1) * 100, 4),
            }
        )

    equity_df = pd.DataFrame(equity_curve)
    if equity_df.empty:
        equity_df = pd.DataFrame([{"date": df.iloc[-1]["date"], "equity": starting_cash}])
    equity_df["peak"] = equity_df["equity"].cummax()
    equity_df["drawdown_pct"] = (equity_df["equity"] / equity_df["peak"] - 1) * 100
    equity_df["period_return"] = equity_df["equity"].pct_change().fillna(0.0)

    sharpe = 0.0
    period_std = equity_df["period_return"].std(ddof=0)
    if period_std and not math.isclose(period_std, 0.0):
        sharpe = float(equity_df["period_return"].mean() / period_std * math.sqrt(252))

    trades_df = pd.DataFrame(trades)
    win_rate = float((trades_df["net_pnl"] > 0).mean() * 100) if not trades_df.empty else 0.0
    total_profit = float(trades_df.loc[trades_df["net_pnl"] > 0, "net_pnl"].sum()) if not trades_df.empty else 0.0
    total_loss = float(-trades_df.loc[trades_df["net_pnl"] < 0, "net_pnl"].sum()) if not trades_df.empty else 0.0
    profit_factor = total_profit / total_loss if total_loss else (999.0 if total_profit > 0 else 0.0)

    buy_signals = (
        df.loc[df["close"] <= df["lower"], ["date", "close", "lower", "mid", "upper"]]
        .tail(5)
        .round(2)
        .to_dict(orient="records")
    )
    sell_signals = (
        df.loc[df["close"] >= df["upper"], ["date", "close", "lower", "mid", "upper"]]
        .tail(5)
        .round(2)
        .to_dict(orient="records")
    )

    for rows in (buy_signals, sell_signals):
        for row in rows:
            row["trade_date"] = pd.Timestamp(row.pop("date")).date().isoformat()
            row["lower_band"] = row.pop("lower")
            row["middle_band"] = row.pop("mid")
            row["upper_band"] = row.pop("upper")

    strategy_name = f"{lookback['label']}范围 {window['label']}布林带均值回归"
    return {
        "symbol": resolved_symbol,
        "market": resolved_market,
        "market_label": MARKET_LABELS[resolved_market],
        "lookback_period_key": lookback["key"],
        "lookback_period_label": lookback["label"],
        "bollinger_window_key": window["key"],
        "bollinger_window_label": window["label"],
        "price_frequency": DEFAULT_PRICE_FREQUENCY,
        "price_frequency_label": "日线",
        "strategy_name": strategy_name,
        "data_source": "AKShare 新浪/腾讯 T-1 历史日线 + pandas backtest",
        "data_notes": f"回测使用最近{lookback['label']}日线数据，布林带窗口为{window['label']}，仅纳入 T-1 已完成交易日数据。",
        "traceability": traceability,
        "summary": {
            "trade_date": pd.Timestamp(latest["date"]).date().isoformat(),
            "close_label": "最新收盘",
            "close": round(float(latest["close"]), 2),
            "middle_band": round(float(latest["mid"]), 2),
            "upper_band": round(float(latest["upper"]), 2),
            "lower_band": round(float(latest["lower"]), 2),
            "zscore": round(float(latest["zscore"]), 2),
            "state": state,
            "recommendation": recommendation,
            "buy_reference": round(float(latest["lower"]), 2),
            "first_take_profit": round(float(latest["mid"]), 2),
            "strong_take_profit": round(float(latest["upper"]), 2),
        },
        "backtest": {
            "trade_count": int(len(trades)),
            "total_return_pct": round((cash / starting_cash - 1) * 100, 4),
            "win_rate": round(win_rate, 2),
            "profit_factor": round(float(profit_factor), 2),
            "max_drawdown_pct": round(abs(float(equity_df["drawdown_pct"].min())), 4),
            "sharpe_ratio": round(sharpe, 2),
        },
        "buy_signals": buy_signals,
        "sell_signals": sell_signals,
        "recent_trades": trades[-5:],
    }


STRATEGIES: dict[str, StrategySpec] = {
    "bollinger_mean_reversion": StrategySpec(
        key="bollinger_mean_reversion",
        title="布林带均值回归",
        description="基于日线布林带，下轨低吸，中轨止盈。",
        handler=_bollinger_result,
    ),
}


def list_strategies() -> list[dict]:
    return [{"key": item.key, "title": item.title, "description": item.description} for item in STRATEGIES.values()]


def run_strategies(
    symbol: str,
    market: str,
    strategy_keys: list[str],
    lookback_period: str = DEFAULT_LOOKBACK_PERIOD,
    bollinger_window: str = DEFAULT_BOLLINGER_WINDOW,
) -> list[dict]:
    results = []
    for key in strategy_keys:
        strategy = STRATEGIES.get(key)
        if not strategy:
            raise ValueError(f"未知策略: {key}")
        results.append(
            {
                "key": strategy.key,
                "title": strategy.title,
                "payload": strategy.handler(symbol, market, lookback_period, bollinger_window),
            }
        )
    return results
