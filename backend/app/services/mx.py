from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import pandas as pd
import requests


MX_DATA_URL = "https://mkapi2.dfcfs.com/finskillshub/api/claw/query"
MX_SEARCH_URL = "https://mkapi2.dfcfs.com/finskillshub/api/claw/news-search"
MX_SELF_SELECT_GET_URL = "https://mkapi2.dfcfs.com/finskillshub/api/claw/self-select/get"
MX_SELF_SELECT_MANAGE_URL = "https://mkapi2.dfcfs.com/finskillshub/api/claw/self-select/manage"
MX_STOCK_SCREEN_URL = "https://mkapi2.dfcfs.com/finskillshub/api/claw/stock-screen"

MARKET_LABELS = {"a": "A股", "hk": "港股"}


def normalize_market(market: str = "a") -> str:
    aliases = {
        "a": "a",
        "ashare": "a",
        "a-share": "a",
        "cn": "a",
        "zh": "a",
        "hk": "hk",
        "hshare": "hk",
        "h-shares": "hk",
        "hongkong": "hk",
    }
    resolved = aliases.get((market or "a").strip().lower())
    if not resolved:
        raise ValueError("market 仅支持 a 或 hk")
    return resolved


def normalize_symbol(symbol: str, market: str = "a") -> str:
    resolved_market = normalize_market(market)
    digits = "".join(char for char in str(symbol).strip() if char.isdigit())
    if not digits:
        raise ValueError("symbol 不能为空")
    return digits.zfill(6 if resolved_market == "a" else 5)


def market_from_short_name(value: str | None) -> str:
    short_name = (value or "").strip().upper()
    if short_name == "HK":
        return "hk"
    return "a"


def parse_numeric_value(value: Any) -> float | None:
    if value in (None, "", "-"):
        return None
    text = str(value).strip().replace(",", "")
    multiplier = 1.0
    for unit, factor in (("万亿", 1e12), ("亿", 1e8), ("万", 1e4)):
        if unit in text:
            multiplier = factor
            text = text.replace(unit, "")
            break
    for token in ("港元", "元", "股", "%"):
        text = text.replace(token, "")
    text = text.strip()
    if text in ("", "-"):
        return None
    return float(text) * multiplier


def safe_float(value: Any, default: float = 0.0) -> float:
    parsed = parse_numeric_value(value)
    return default if parsed is None else float(parsed)


def title_matches_symbol(title: str, symbol: str, market: str) -> bool:
    cleaned = re.sub(r"\s+", "", title or "")
    if market == "hk":
        return f"({symbol}.HK)" in cleaned
    return bool(re.search(rf"\({symbol}\.(SH|SZ|BJ)\)", cleaned))


def _looks_like_symbol_row(value: str, symbol: str, market: str) -> bool:
    return title_matches_symbol(value or "", symbol, market)


def _flatten_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _pick_first(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if row.get(key) not in (None, ""):
            return row.get(key)
    return None


def _first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _pick_by_title(row: dict[str, Any], title_map: dict[str, str], keywords: tuple[str, ...]) -> Any:
    lowered_keywords = tuple(keyword.lower() for keyword in keywords)
    for key, value in row.items():
        title = title_map.get(key, key).lower()
        if any(keyword in title for keyword in lowered_keywords):
            return value
    return None


def _unwrap_payload(result: dict[str, Any]) -> dict[str, Any]:
    payload = result.get("data") or {}
    while isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        if payload.get("allResults") or payload.get("partialResults"):
            break
        payload = payload["data"]
    return payload if isinstance(payload, dict) else {}


def _extract_result_block(result: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str], list[dict[str, Any]], dict[str, Any]]:
    payload = _unwrap_payload(result)
    all_results = ((payload.get("allResults") or {}).get("result") or {})
    if not all_results:
        raise ValueError("mx 接口未返回结构化结果")
    columns = all_results.get("columns") or []
    title_map = {
        str(column.get("key")): _flatten_value(column.get("title"))
        for column in columns
        if isinstance(column, dict) and column.get("key")
    }
    return payload, title_map, all_results.get("dataList") or [], all_results


def _ordered_keys(table: dict[str, Any], indicator_order: list[Any]) -> list[Any]:
    data_keys = [key for key in table.keys() if key != "headName"]
    key_map = {str(key): key for key in data_keys}
    preferred: list[Any] = []
    seen: set[str] = set()
    for key in indicator_order:
        key_str = str(key)
        if key_str in key_map and key_str not in seen:
            preferred.append(key_map[key_str])
            seen.add(key_str)
    for key in data_keys:
        key_str = str(key)
        if key_str not in seen:
            preferred.append(key)
            seen.add(key_str)
    return preferred


def _return_code_map(block: dict[str, Any]) -> dict[str, str]:
    for key in ("returnCodeMap", "returnCodeNameMap", "codeMap"):
        value = block.get(key)
        if isinstance(value, dict):
            return {str(k): _flatten_value(v) for k, v in value.items()}
    return {}


def _format_indicator_label(key: str, name_map: dict[str, Any], code_map: dict[str, str]) -> str:
    mapped = name_map.get(key)
    if mapped is None and key.isdigit():
        mapped = name_map.get(int(key))
    if mapped not in (None, ""):
        return _flatten_value(mapped)
    mapped_code = code_map.get(key)
    if mapped_code not in (None, ""):
        return _flatten_value(mapped_code)
    return "" if key.isdigit() else key


def _table_to_rows(block: dict[str, Any]) -> tuple[list[dict[str, str]], list[str]]:
    table = block.get("table") or {}
    name_map = block.get("nameMap") or {}
    if isinstance(name_map, list):
        name_map = {str(i): v for i, v in enumerate(name_map)}
    elif not isinstance(name_map, dict):
        name_map = {}
    if not isinstance(table, dict):
        return [], []
    headers = table.get("headName") or []
    if not isinstance(headers, list) or not headers:
        return [], []

    order = _ordered_keys(table, block.get("indicatorOrder") or [])
    code_map = _return_code_map(block)
    fieldnames = ["date"]
    for key in order:
        if key == "headName":
            continue
        label = _format_indicator_label(str(key), name_map, code_map)
        if label:
            fieldnames.append(label)

    rows: list[dict[str, str]] = []
    for row_idx, head in enumerate(headers):
        row = {"date": _flatten_value(head)}
        for key in order:
            if key == "headName":
                continue
            label = _format_indicator_label(str(key), name_map, code_map)
            if not label:
                continue
            raw_values = table.get(key, [])
            row[label] = _flatten_value(raw_values[row_idx] if row_idx < len(raw_values) else "")
        rows.append(row)
    return rows, fieldnames


@dataclass
class MXTable:
    title: str
    rows: list[dict[str, str]]
    fieldnames: list[str]

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows, columns=self.fieldnames)


class MXBaseClient:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key
        if not self.api_key:
            raise ValueError("当前用户未配置 MX Key")

    def _post(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = requests.post(
            url,
            headers={"Content-Type": "application/json", "apikey": self.api_key},
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        result = response.json()
        if result.get("status") not in (None, 0):
            raise ValueError(f"mx 接口错误: {result.get('status')} {result.get('message', '')}")
        return result


class MXDataClient(MXBaseClient):
    def __init__(self, api_key: str | None = None):
        super().__init__(api_key=api_key)

    def query(self, tool_query: str) -> dict[str, Any]:
        return self._post(MX_DATA_URL, {"toolQuery": tool_query})

    def query_tables(self, tool_query: str) -> list[MXTable]:
        result = self.query(tool_query)
        if result.get("status") != 0:
            raise ValueError(f"mx_data 接口错误: {result.get('status')} {result.get('message', '')}")

        dto_list = (((result.get("data") or {}).get("data") or {}).get("searchDataResultDTO") or {}).get("dataTableDTOList", [])
        tables: list[MXTable] = []
        for dto in dto_list:
            if not isinstance(dto, dict):
                continue
            rows, fieldnames = _table_to_rows(dto)
            if not rows:
                continue
            tables.append(MXTable(title=dto.get("title") or dto.get("frontendTitle") or "", rows=rows, fieldnames=fieldnames))
        if not tables:
            raise ValueError("mx_data 未返回可解析表格")
        return tables

    def fetch_quote(self, symbol: str, market: str) -> dict[str, Any]:
        resolved_symbol = normalize_symbol(symbol, market)
        resolved_market = normalize_market(market)
        quote = {
            "symbol": resolved_symbol,
            "market": resolved_market,
            "display_name": resolved_symbol,
            "price": None,
            "open": None,
            "close": None,
            "high": None,
            "low": None,
            "volume": None,
            "timestamp": None,
        }

        try:
            day_tables = self.query_tables(f"{resolved_symbol} 当日行情")
            day_snapshot = self._extract_day_snapshot(day_tables, resolved_symbol, resolved_market)
            quote.update(day_snapshot)
        except Exception:
            pass

        try:
            latest_tables = self.query_tables(f"{resolved_symbol} 最新价")
            latest_snapshot = self._extract_latest_snapshot(latest_tables, resolved_symbol, resolved_market)
            for key, value in latest_snapshot.items():
                if quote.get(key) is None and value is not None:
                    quote[key] = value
        except Exception:
            pass

        if quote["display_name"] == resolved_symbol:
            quote["display_name"] = self._display_name_from_history_title(resolved_symbol, resolved_market)

        needs_history = any(quote[key] is None for key in ("price", "open", "close", "high", "low", "timestamp"))
        if needs_history:
            history = self.fetch_kline_history(resolved_symbol, market, trading_days=60)
            latest = history.iloc[-1]
            if quote["price"] is None:
                quote["price"] = float(latest["close"])
            if quote["open"] is None:
                quote["open"] = float(latest["open"])
            if quote["close"] is None:
                quote["close"] = float(latest["close"])
            if quote["high"] is None:
                quote["high"] = float(latest["high"])
            if quote["low"] is None:
                quote["low"] = float(latest["low"])
            if quote["timestamp"] is None:
                quote["timestamp"] = latest["date"].date().isoformat()
        return quote

    def _display_name_from_history_title(self, symbol: str, market: str) -> str:
        tables = self.query_tables(f"{symbol} 最新价")
        for table in tables:
            cleaned = re.sub(r"当前的.*$", "", table.title or "").strip()
            if title_matches_symbol(cleaned, symbol, market):
                return cleaned
        return symbol

    def _extract_day_snapshot(self, tables: list[MXTable], symbol: str, market: str) -> dict[str, Any]:
        for table in tables:
            if "最新价" not in table.fieldnames:
                continue
            for row in table.rows:
                security_label = row.get("date", "")
                if not _looks_like_symbol_row(security_label, symbol, market):
                    continue
                return {
                    "display_name": security_label.split("(")[0].strip() or symbol,
                    "price": parse_numeric_value(row.get("最新价")),
                    "open": parse_numeric_value(row.get("开盘价")),
                    "high": parse_numeric_value(row.get("最高价")),
                    "low": parse_numeric_value(row.get("最低价")),
                    "volume": parse_numeric_value(row.get("成交量")),
                    "timestamp": None,
                }
        return {}

    def _extract_latest_snapshot(self, tables: list[MXTable], symbol: str, market: str) -> dict[str, Any]:
        snapshot: dict[str, Any] = {}
        for table in tables:
            frame = table.to_frame()
            if "收盘价" in frame.columns and not frame.empty:
                cleaned = re.sub(r"的收盘价$", "", table.title or "").strip()
                if not title_matches_symbol(cleaned, symbol, market):
                    continue
                latest_row = frame.iloc[0].to_dict()
                snapshot["close"] = parse_numeric_value(latest_row.get("收盘价"))
                if latest_row.get("date"):
                    snapshot["timestamp"] = latest_row.get("date")
                snapshot["display_name"] = cleaned.split("(")[0].strip() or symbol
            elif table.rows and len(table.fieldnames) >= 2:
                first_row = table.rows[0]
                numeric_value = next(
                    (parse_numeric_value(value) for key, value in first_row.items() if key != "date" and parse_numeric_value(value) is not None),
                    None,
                )
                if numeric_value is not None and snapshot.get("price") is None:
                    snapshot["price"] = numeric_value
                    snapshot["timestamp"] = first_row.get("date")
        return snapshot

    def fetch_kline_history(self, symbol: str, market: str, trading_days: int = 720) -> pd.DataFrame:
        resolved_symbol = normalize_symbol(symbol, market)
        resolved_market = normalize_market(market)
        tables = self.query_tables(f"{resolved_symbol} 近{trading_days}个交易日K线")

        def choose(title_part: str) -> MXTable:
            for table in tables:
                if title_part in table.title and title_matches_symbol(table.title, resolved_symbol, resolved_market):
                    return table
            for table in tables:
                if title_part in table.title:
                    return table
            raise ValueError(f"mx_data 未返回 {resolved_symbol} 的 {title_part} 表")

        open_close = choose("开盘价、收盘价").to_frame()
        if "开盘价" not in open_close.columns or "收盘价" not in open_close.columns:
            raise ValueError("mx_data 历史数据缺少开盘价或收盘价")

        frame = open_close[["date", "开盘价", "收盘价"]].rename(columns={"开盘价": "open", "收盘价": "close"})
        frame["date"] = pd.to_datetime(frame["date"])
        frame["open"] = frame["open"].map(parse_numeric_value)
        frame["close"] = frame["close"].map(parse_numeric_value)

        try:
            volume_table = choose("区间成交量").to_frame()
            volume_column = next((column for column in volume_table.columns if "成交量" in column), None)
            if volume_column:
                volume = volume_table[["date", volume_column]].rename(columns={volume_column: "volume"})
                volume["date"] = pd.to_datetime(volume["date"])
                volume["volume"] = volume["volume"].map(parse_numeric_value)
                frame = frame.merge(volume, on="date", how="left")
            else:
                frame["volume"] = 0.0
        except Exception:
            frame["volume"] = 0.0

        frame["high"] = frame[["open", "close"]].max(axis=1)
        frame["low"] = frame[["open", "close"]].min(axis=1)
        frame["symbol"] = resolved_symbol
        frame["market"] = resolved_market
        frame = frame.sort_values("date").reset_index(drop=True)
        frame["volume"] = frame["volume"].fillna(0.0)
        return frame

    def fetch_tracker_bundle(self, symbol: str, market: str) -> dict[str, Any]:
        resolved_symbol = normalize_symbol(symbol, market)
        resolved_market = normalize_market(market)
        quote = self.fetch_quote(resolved_symbol, resolved_market)
        daily = self.fetch_kline_history(resolved_symbol, resolved_market, trading_days=180)
        weekly = self._aggregate_kline(daily, "W-FRI").tail(24)
        monthly = self._aggregate_kline(daily, "ME").tail(24)
        fundamentals = self._fetch_fundamentals(resolved_symbol, resolved_market)
        return {
            "symbol": resolved_symbol,
            "market": resolved_market,
            "display_name": quote.get("display_name") or resolved_symbol,
            "quote": {
                "price": quote.get("price"),
                "open": quote.get("open"),
                "close": quote.get("close"),
                "high": quote.get("high"),
                "low": quote.get("low"),
                "volume": quote.get("volume"),
                "timestamp": quote.get("timestamp"),
            },
            "daily_kline": self._frame_to_kline(daily.tail(90)),
            "weekly_kline": self._frame_to_kline(weekly),
            "monthly_kline": self._frame_to_kline(monthly),
            "fundamentals": fundamentals,
            "analysis_points": self._build_fundamental_analysis(fundamentals, quote),
        }

    def _aggregate_kline(self, frame: pd.DataFrame, rule: str) -> pd.DataFrame:
        grouped = (
            frame.set_index("date")
            .resample(rule)
            .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
            .dropna(subset=["open", "high", "low", "close"])
            .reset_index()
        )
        return grouped

    def _frame_to_kline(self, frame: pd.DataFrame) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for row in frame.to_dict(orient="records"):
            records.append(
                {
                    "date": pd.Timestamp(row["date"]).date().isoformat(),
                    "open": round(float(row["open"]), 4),
                    "high": round(float(row["high"]), 4),
                    "low": round(float(row["low"]), 4),
                    "close": round(float(row["close"]), 4),
                    "volume": round(float(row["volume"]), 4) if row.get("volume") is not None else None,
                }
            )
        return records

    def _fetch_fundamentals(self, symbol: str, market: str) -> dict[str, Any]:
        try:
            tables = self.query_tables(f"{symbol} 基本面分析")
        except Exception:
            tables = self.query_tables(f"{symbol} 财务指标")

        fundamentals: dict[str, Any] = {"valuation": {}, "profitability": {}, "ranking": {}}
        for table in tables:
            if table.rows:
                if market == "a" and not title_matches_symbol(table.title, symbol, market):
                    continue
                row = table.rows[0]
                if "市盈率PE(TTM)" in table.fieldnames:
                    fundamentals["valuation"] = {
                        "pe_ttm": parse_numeric_value(row.get("市盈率PE(TTM)")),
                        "pb_mrq": parse_numeric_value(row.get("市净率PB(MRQ,按最近公告日)")),
                        "ps_ttm": parse_numeric_value(row.get("市销率PS(TTM)")),
                        "pcf_ttm": parse_numeric_value(row.get("市现率PCF(TTM,现金净流量)")),
                        "pe_percentile_3y": parse_numeric_value(row.get("3年市盈率历史百分位")),
                        "pb_percentile_3y": parse_numeric_value(row.get("3年市净率PB历史百分位")),
                    }
                elif "市盈率(TTM)行业排名" in table.fieldnames:
                    fundamentals["ranking"] = {
                        "pe_rank": _flatten_value(row.get("市盈率(TTM)行业排名")) or None,
                        "pb_rank": _flatten_value(row.get("市净率行业排名")) or None,
                        "ps_rank": _flatten_value(row.get("市销率(TTM)行业排名")) or None,
                    }
                elif "营业总收入" in table.fieldnames:
                    fundamentals["profitability"] = {
                        "report_date": row.get("date"),
                        "revenue": parse_numeric_value(row.get("营业总收入")),
                        "net_profit": parse_numeric_value(row.get("归属于母公司股东的净利润")),
                        "cashflow": parse_numeric_value(row.get("经营活动产生的现金流量净额")),
                        "eps": parse_numeric_value(row.get("每股收益EPS(基本)")),
                        "roe": parse_numeric_value(row.get("净资产收益率ROE(加权)") or row.get("净资产收益率(年化)(%)")),
                        "profit_yoy": parse_numeric_value(row.get("归属母公司股东的净利润同比增长率")),
                    }
        return fundamentals

    def _build_fundamental_analysis(self, fundamentals: dict[str, Any], quote: dict[str, Any]) -> list[str]:
        points: list[str] = []
        valuation = fundamentals.get("valuation", {})
        profitability = fundamentals.get("profitability", {})
        ranking = fundamentals.get("ranking", {})

        pe_percentile = valuation.get("pe_percentile_3y")
        if pe_percentile is not None:
            if pe_percentile <= 30:
                points.append("估值处于近三年偏低区间，适合继续观察安全边际。")
            elif pe_percentile >= 70:
                points.append("估值处于近三年偏高区间，追涨前建议结合业绩确认。")
        roe = profitability.get("roe")
        if roe is not None:
            if roe >= 12:
                points.append("净资产收益率表现较强，盈利质量在同类资产中具备一定支撑。")
            else:
                points.append("净资产收益率中性偏弱，基本面要结合利润增速一起看。")
        profit_yoy = profitability.get("profit_yoy")
        if profit_yoy is not None:
            if profit_yoy > 0:
                points.append("最新利润同比仍在增长区间，基本面趋势偏正向。")
            else:
                points.append("最新利润同比承压，策略信号需要更重视风控。")
        if ranking.get("pe_rank"):
            points.append(f"行业估值位置可参考：PE 排名 {ranking['pe_rank']}。")
        if quote.get("price") and quote.get("open"):
            if float(quote["price"]) >= float(quote["open"]):
                points.append("当前价格位于日内开盘价上方，短线情绪偏强。")
            else:
                points.append("当前价格位于日内开盘价下方，短线仍偏震荡。")
        return points[:5]


class MXSearchClient(MXBaseClient):
    def __init__(self, api_key: str | None = None):
        super().__init__(api_key=api_key)

    def search(self, query: str) -> list[dict[str, Any]]:
        result = self._post(MX_SEARCH_URL, {"query": query})
        return (((result.get("data") or {}).get("data") or {}).get("llmSearchResponse") or {}).get("data", []) or []

    def daily_hot_news(self, limit: int = 12) -> list[dict[str, Any]]:
        items = self.search("中国财经要闻 A股 港股 经济 金融 市场 热点")
        results = []
        for item in items[:limit]:
            results.append(
                {
                    "title": item.get("title", ""),
                    "content": item.get("content", ""),
                    "date": item.get("date"),
                    "source": item.get("insName"),
                    "info_type": item.get("informationType"),
                    "security": item.get("entityFullName"),
                }
            )
        return results


class MXSelfSelectClient(MXBaseClient):
    def list_watchlist(self) -> dict[str, Any]:
        result = self._post(MX_SELF_SELECT_GET_URL, {})
        payload, title_map, rows, all_results = _extract_result_block(result)
        items = [self._parse_row(row, title_map) for row in rows]
        return {
            "total_count": payload.get("securityCount") or all_results.get("totalRecordCount") or len(items),
            "items": items,
        }

    def add_watchlist(self, symbol: str, market: str = "a") -> dict[str, Any]:
        resolved_symbol = normalize_symbol(symbol, market)
        resolved_market = normalize_market(market)
        return self._post(
            MX_SELF_SELECT_MANAGE_URL,
            {"query": f"把{MARKET_LABELS[resolved_market]} {resolved_symbol} 添加到我的自选股列表"},
        )

    def remove_watchlist(self, symbol: str, market: str = "a") -> dict[str, Any]:
        resolved_symbol = normalize_symbol(symbol, market)
        resolved_market = normalize_market(market)
        return self._post(
            MX_SELF_SELECT_MANAGE_URL,
            {"query": f"把{MARKET_LABELS[resolved_market]} {resolved_symbol} 从我的自选股列表删除"},
        )

    def _parse_row(self, row: dict[str, Any], title_map: dict[str, str]) -> dict[str, Any]:
        market_short_name = _flatten_value(row.get("MARKET_SHORT_NAME"))
        market = market_from_short_name(market_short_name)
        return {
            "symbol": normalize_symbol(_pick_first(row, "SECURITY_CODE"), market),
            "market": market,
            "market_short_name": market_short_name,
            "display_name": _flatten_value(_pick_first(row, "SECURITY_SHORT_NAME")) or "-",
            "last_price": parse_numeric_value(_first_present(_pick_first(row, "NEWEST_PRICE"), _pick_by_title(row, title_map, ("最新价",)))),
            "change_pct": parse_numeric_value(_first_present(_pick_first(row, "CHG"), _pick_by_title(row, title_map, ("涨跌幅",)))),
            "change_amount": parse_numeric_value(_first_present(_pick_first(row, "PCHG"), _pick_by_title(row, title_map, ("涨跌额",)))),
            "day_high": parse_numeric_value(_pick_by_title(row, title_map, ("最高价",))),
            "day_low": parse_numeric_value(_pick_by_title(row, title_map, ("最低价",))),
            "turnover_rate": parse_numeric_value(_pick_by_title(row, title_map, ("换手率",))),
            "volume": parse_numeric_value(_pick_by_title(row, title_map, ("成交量",))),
            "amount": parse_numeric_value(_pick_by_title(row, title_map, ("成交额",))),
            "in_optional": row.get("IN_OPTIONAL"),
        }


class MXStockScreenClient(MXBaseClient):
    def recommend(self, keyword: str, page_no: int = 1, page_size: int = 10) -> dict[str, Any]:
        result = self._post(MX_STOCK_SCREEN_URL, {"keyword": keyword, "pageNo": page_no, "pageSize": page_size})
        payload, title_map, rows, all_results = _extract_result_block(result)
        items = [self._parse_row(row, title_map) for row in rows]
        reported_total = payload.get("securityCount") or all_results.get("totalRecordCount") or len(items)
        if len(items) > page_size:
            # Some MX responses ignore page size and return a large fixed result set.
            start = (page_no - 1) * page_size
            items = items[start : start + page_size]
            total_count = len(rows)
        else:
            total_count = reported_total
        return {
            "keyword": keyword,
            "select_logic": payload.get("selectLogic"),
            "total_count": total_count,
            "items": items,
        }

    def _parse_row(self, row: dict[str, Any], title_map: dict[str, str]) -> dict[str, Any]:
        market_short_name = _flatten_value(row.get("MARKET_SHORT_NAME"))
        market = market_from_short_name(market_short_name)
        return {
            "symbol": normalize_symbol(_pick_first(row, "SECURITY_CODE"), market),
            "market": market,
            "market_short_name": market_short_name,
            "display_name": _flatten_value(_pick_first(row, "SECURITY_SHORT_NAME")) or "-",
            "last_price": parse_numeric_value(_first_present(_pick_first(row, "NEWEST_PRICE"), _pick_by_title(row, title_map, ("最新价",)))),
            "change_pct": parse_numeric_value(_first_present(_pick_first(row, "CHG"), _pick_by_title(row, title_map, ("涨跌幅",)))),
            "day_high": parse_numeric_value(_pick_by_title(row, title_map, ("最高价",))),
            "day_low": parse_numeric_value(_pick_by_title(row, title_map, ("最低价",))),
            "turnover_rate": parse_numeric_value(_pick_by_title(row, title_map, ("换手率",))),
            "volume": parse_numeric_value(_pick_by_title(row, title_map, ("成交量",))),
            "amount": parse_numeric_value(_pick_by_title(row, title_map, ("成交额",))),
            "industry": _flatten_value(_pick_by_title(row, title_map, ("行业",))),
            "concepts": _flatten_value(_pick_by_title(row, title_map, ("概念",))),
            "in_optional": row.get("IN_OPTIONAL"),
        }
