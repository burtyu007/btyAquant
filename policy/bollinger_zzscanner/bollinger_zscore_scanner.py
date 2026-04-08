#!/usr/bin/env python3
"""布林带 Z-Score A股扫描器 — 使用说明详见 README.md"""

import akshare as ak
import pandas as pd
import numpy as np
import json
import sqlite3
import time
import random
import re
import requests
import threading
import warnings
import sys
import os
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from akshare.stock.cons import (
    zh_sina_a_stock_count_url,
    zh_sina_a_stock_payload,
    zh_sina_a_stock_url,
)
from akshare.utils import demjson

warnings.filterwarnings('ignore')


# ============================================================
# 全局限流器（参考 CSDN 文章的智能延时控制）
# ============================================================

class SmartRateLimiter:
    """请求限流器：控制东财接口访问频率，防止触发反爬"""
    def __init__(self, min_interval=3.0, batch_size=10, batch_pause=15.0):
        self.min_interval = min_interval   # 单次请求最小间隔（秒）
        self.batch_size = batch_size       # 每多少次请求后暂停
        self.batch_pause = batch_pause     # 批次暂停时长（秒）
        self.last_request_time = None
        self.request_count = 0
        self._lock = threading.Lock()

    def wait(self):
        """请求前调用，自动等待到合法时间窗口"""
        with self._lock:
            self.request_count += 1

            if self.request_count > 1 and self.request_count % self.batch_size == 0:
                print(f"    [限流] 已请求 {self.request_count} 次，暂停 {self.batch_pause}s...")
                time.sleep(self.batch_pause)

            if self.last_request_time is not None:
                elapsed = (datetime.now() - self.last_request_time).total_seconds()
                if elapsed < self.min_interval:
                    wait_sec = self.min_interval - elapsed + random.uniform(0.05, 0.2)
                    time.sleep(wait_sec)

            self.last_request_time = datetime.now()


# 分源限流器：东财更保守，腾讯更激进
_em_rate_limiter = SmartRateLimiter(min_interval=1.2, batch_size=20, batch_pause=6.0)
_tx_rate_limiter = SmartRateLimiter(min_interval=0.08, batch_size=100, batch_pause=1.5)


def fetch_with_retry(fn, *args, max_retries=3, rate_limiter=None, **kwargs):
    """带重试的接口调用包装器"""
    for attempt in range(max_retries):
        try:
            if rate_limiter is not None:
                rate_limiter.wait()
            return fn(*args, **kwargs)
        except Exception as e:
            err_str = str(e)
            if attempt < max_retries - 1:
                wait_sec = random.uniform(1.5, 3.0) * (attempt + 1)
                print(f"    [重试 {attempt+1}/{max_retries}] {err_str[:60]}，等待 {wait_sec:.1f}s...")
                time.sleep(wait_sec)
            else:
                raise
    return None

# ============================================================
# 可配置变量（修改这里即可调整扫描参数）
# ============================================================

CONFIG = {
    # ---- 市场参数 ----
    "market": "A",          # "A": 沪深A股 / "SH": 上证 / "SZ": 深证

    # ---- 数据源开关 ----
    # True: 优先使用东财接口，失败后降级到腾讯
    # False: 直接使用腾讯接口（跳过东财）
    "use_em": False,
    "use_local_db": True,  # 优先使用本地 SQLite 日线库
    "daily_db_path": "/Users/burtyu/Work/python/cron/stock_data/stock_daily.db",
    "prefer_sina_spot": True,  # 东财不可用时优先用新浪全量快照，避免腾讯逐股拼快照

    # ---- 布林带参数 ----
    "bb_window": 60,        # 布林带窗口（日），默认20日
    "bb_std": 2.0,          # 布林带标准差倍数，默认2倍

    # ---- 历史回看区间 ----
    "lookback_months": 60,  # 历史回看区间（月），用于获取日线数据，默认24（约2年）

    # ---- Z-Score 筛选条件 ----
    "zscore_min": -999,    # Z-Score 下限阈值：仅保留 Z-Score >= 此值的股票，-999 表示关闭下限
                           # 典型用法：
                           #   筛选超跌（价格严重低于均线）：zscore_min = -999, zscore_max = -2.5
                           #   筛选超买（价格严重高于均线）：zscore_min = 2.5,  zscore_max = 999
                           #   宽松双向筛选：              zscore_min = -3.0, zscore_max = 3.0

    "zscore_max": -2.0,    # Z-Score 上限阈值：仅保留 Z-Score <= 此值的股票，999 表示关闭上限
                           # 默认 -2.5：筛选出 Z-Score ≤ -2.5 的超跌股

    # ---- 排序与数量 ----
    "sort_by": "buy_score",  # 排序字段：zscore / buy_score / return_60d / debt_ratio / price
    "ascending": False,      # 排序方向：
                             #   按 zscore    升序(True)  → 超跌最深的排前面（推荐）
                             #   按 buy_score 升序(True)  → ⚠️ 低分排前，若想高分排前请改为 False
                             #   按 buy_score 降序(False) → 综合评分最高的排前面（推荐）✅ 当前配置
    "top_n": 100,            # 最多返回N条，默认500

    # ---- 基础过滤 ----
    "min_price": 1.0,       # 最低股价过滤（元），默认1.0
    "exclude_st": True,     # 是否排除ST股，默认True

    # ---- 综合评分门槛 ----
    "score_min": 0,         # 综合评分最低门槛，低于此值不显示，默认0（不过滤）

    # ---- 候选股初筛 ----
    "prefilter_return_days": 60,       # 初筛使用多少日的涨跌幅，默认60日
    "prefilter_return_pct": -5,       # 初筛：N日涨跌幅阈值，默认-5%（超跌方向）
    "max_candidates": 5400,           # 最大候选股数量，防止运行时间过长（正式运行设为5000）

    # ---- 新闻数量 ----
    "news_count": 5,        # 每只股票获取的新闻条数，默认5

    # ---- 自选股列表 ----
    # 非空时只扫描这几只股票，忽略全量扫描逻辑（6位代码，不带前缀）
    # 例如：["000001", "600000", "300001"]
    # 为空列表 [] 时扫全量
    "watch_list": [],

    # ---- 并发控制 ----
    "spot_concurrent_workers": 12,  # 新浪全量快照分页并发数
    # 腾讯日线拉取并发数，建议 3-6，太高可能触发限流
    "tx_concurrent_workers": 6,
    "scan_concurrent_workers": 6,  # 扫描候选股时的并发数

    # ---- 性能/功能开关 ----
    "load_industry_map": False,  # 获取全量行业映射非常慢，默认关闭
}


# ============================================================
# 字段映射：CSV/JSON key → 中文名称
# ============================================================
FIELD_NAMES = {
    "rank":           "排名(rank)",
    "code":           "股票代码(code)",
    "name":           "股票名称(name)",
    "price":          "最新价(price)",
    "pct_change":     "涨跌幅(pct_change)",
    "zscore":         "Z-Score(zscore)",
    "pct_from_mean":  "偏离均值(pct_from_mean)",
    "mean_20":        "20日均线(mean_20)",
    "std_20":         "20日标准差(std_20)",
    "upper_band":     "布林上轨(upper_band)",
    "lower_band":     "布林下轨(lower_band)",
    f"return_60d":    f"60日涨跌幅(return_60d)",
    "vol_ratio":      "量比(vol_ratio)",
    "atr_pct":        "ATR波动率(atr_pct)",
    "debt_ratio":     "资产负债率(debt_ratio)",
    "debt_ratio_val": "资产负债率数值(debt_ratio_val)",
    "roe":            "净资产收益率(ROE)",
    "net_profit":     "净利润(net_profit)",
    "revenue":        "营业收入(revenue)",
    "revenue_yoy":    "营收同比(revenue_yoy)",
    "profit_yoy":     "净利润同比(profit_yoy)",
    "eps":            "每股收益(EPS)",
    "book_value":     "每股净资产(book_value)",
    "total_mv":       "总市值(total_mv)",
    "float_mv":       "流通市值(float_mv)",
    "industry":       "行业板块(industry)",
    "report_period":  "报告期(report_period)",
    "news_summary":   "消息摘要(news_summary)",
    "news_score":     "消息评分(news_score)",
    "tech_score":     "技术评分(tech_score)",
    "finance_score":  "财务评分(finance_score)",
    "buy_score":      "综合评分(buy_score)",
    "score_detail":   "评分依据(score_detail)",
    "risk":           "风险提示(risk)",
    "news_list":      "近期新闻(news_list)",
}


# ============================================================
# 内部实现
# ============================================================

def _build_all_a_codes():
    """构造全量A股代码列表（沪深主板 + 创业板 + 科创板）

    范围：
      沪市主板  600000-605999
      科创板    688000-688999
      深主板    000001-002999
      创业板    300001-301999
    返回 list[str]，6位字符串代码
    """
    sh_main  = [f"{i}"      for i in range(600000, 606000)]
    sh_star  = [f"{i}"      for i in range(688000, 689000)]
    sz_main  = [f"{i:06d}"  for i in range(1, 3000)]
    sz_cyb   = [f"{i}"      for i in range(300001, 302000)]
    return sh_main + sh_star + sz_main + sz_cyb


def _cache_path(prefix):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    today_str = datetime.now().strftime("%Y%m%d")
    return os.path.join(script_dir, f"{prefix}_{today_str}.json")


def _get_db_connection():
    db_path = CONFIG.get('daily_db_path')
    if not db_path:
        raise ValueError("CONFIG['daily_db_path'] 未配置")
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)


def _get_db_latest_trade_date():
    with _get_db_connection() as conn:
        row = conn.execute("SELECT MAX(date) FROM stock_daily").fetchone()
    return row[0] if row else None


def ensure_db_indexes():
    db_path = CONFIG.get('daily_db_path')
    if not db_path:
        return

    try:
        conn = sqlite3.connect(db_path, timeout=30)
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_stock_daily_date_code ON stock_daily(date, code)"
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"  [WARN] 创建本地数据库索引失败: {e}")


def _get_db_stock_list(codes=None, return_days=None):
    latest_date = _get_db_latest_trade_date()
    if not latest_date:
        return pd.DataFrame()

    return_days = int(return_days or CONFIG.get('prefilter_return_days', 60))
    return_days = max(1, return_days)
    ret_col = f"return_{return_days}d"
    offset = return_days - 1

    query = """
    SELECT
        s.code AS code,
        s.name AS name,
        s.close AS price,
        s.change_pct AS pct_change,
        CASE
            WHEN h.close IS NOT NULL AND h.close != 0
            THEN ROUND((s.close / h.close - 1) * 100, 2)
            ELSE NULL
        END AS {ret_col},
        s.date AS trade_date,
        s.amount AS amount,
        s.volume AS volume
    FROM stock_daily s
    """.format(ret_col=ret_col)

    params = []
    if codes:
        placeholders = ",".join(["?"] * len(codes))
        query += f"""
        INNER JOIN (
            SELECT code, MAX(date) AS max_date
            FROM stock_daily
            WHERE code IN ({placeholders})
            GROUP BY code
        ) latest
        ON s.code = latest.code AND s.date = latest.max_date
        LEFT JOIN stock_daily h
        ON h.code = s.code
        AND h.date = (
            SELECT d.date
            FROM stock_daily d
            WHERE d.code = s.code AND d.date < s.date
            ORDER BY d.date DESC
            LIMIT 1 OFFSET {offset}
        )
        """
        params.extend([str(c).zfill(6) for c in codes])
    else:
        query += f"""
        LEFT JOIN stock_daily h
        ON h.code = s.code
        AND h.date = (
            SELECT d.date
            FROM stock_daily d
            WHERE d.code = s.code AND d.date < s.date
            ORDER BY d.date DESC
            LIMIT 1 OFFSET {offset}
        )
        WHERE s.date = ?
        """
        params.append(latest_date)

    with _get_db_connection() as conn:
        spot_df = pd.read_sql_query(query, conn, params=params)

    if len(spot_df) == 0:
        return spot_df

    print(f"  ✅ 从本地数据库读取股票池: {len(spot_df)} 只（最新交易日 {latest_date}）")
    spot_df['total_mv'] = None
    spot_df['float_mv'] = None
    return spot_df


def _read_daily_cache(cache_path):
    if not os.path.exists(cache_path):
        return None, None

    cache_time = datetime.fromtimestamp(os.path.getmtime(cache_path))
    if cache_time.strftime("%Y%m%d") != datetime.now().strftime("%Y%m%d"):
        return None, cache_time

    try:
        with open(cache_path, 'r', encoding='utf-8') as f:
            return pd.DataFrame(json.load(f)), cache_time
    except Exception:
        return None, cache_time


def _write_daily_cache(df, cache_path, label):
    if df is None or len(df) == 0:
        return
    try:
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(df.to_dict(orient='records'), f, ensure_ascii=False, indent=None)
        print(f"  💾 {label}已缓存: {cache_path}")
    except Exception as e:
        print(f"  [WARN] {label}缓存写入失败: {e}")


def _get_sina_page_count():
    response = requests.get(zh_sina_a_stock_count_url, timeout=15)
    count = int(re.findall(r"\d+", response.text)[0])
    return max(1, (count + 79) // 80)


def _fetch_one_sina_spot_page(page):
    payload = zh_sina_a_stock_payload.copy()
    payload.update({"page": str(page)})
    response = requests.get(zh_sina_a_stock_url, params=payload, timeout=20)
    rows = demjson.decode(response.text) or []
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    rename_map = {
        'code': 'code',
        'name': 'name',
        'trade': 'price',
        'changepercent': 'pct_change',
        'mktcap': 'total_mv',
        'nmc': 'float_mv',
    }
    df = df.rename(columns=rename_map)
    keep_cols = ['code', 'name', 'price', 'pct_change', 'total_mv', 'float_mv']
    for col in keep_cols:
        if col not in df.columns:
            df[col] = None
    return df[keep_cols]


def _get_sina_stock_list():
    cache_path = _cache_path("sina_spot_cache")
    cached_df, cache_time = _read_daily_cache(cache_path)
    if cached_df is not None and len(cached_df) > 0:
        print(f"  ✅ 读取新浪快照缓存: {len(cached_df)} 只（{cache_time.strftime('%H:%M')}）")
        return cached_df

    page_count = _get_sina_page_count()
    workers = min(CONFIG.get('spot_concurrent_workers', 12), page_count)
    print(f"  调用新浪全量快照，共 {page_count} 页，使用 {workers} 线程并发抓取...")

    frames = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_fetch_one_sina_spot_page, page): page
            for page in range(1, page_count + 1)
        }
        for i, future in enumerate(as_completed(futures), 1):
            page = futures[future]
            try:
                frame = future.result()
                if frame is not None and len(frame) > 0:
                    frames.append(frame)
            except Exception as e:
                print(f"  [WARN] 新浪快照第 {page} 页失败: {e}")
            if i % 10 == 0 or i == page_count:
                print(f"    新浪快照进度: {i}/{page_count}")

    if not frames:
        return pd.DataFrame()

    spot_df = pd.concat(frames, ignore_index=True)
    for col in ['price', 'pct_change', 'total_mv', 'float_mv']:
        spot_df[col] = pd.to_numeric(spot_df[col], errors='coerce')
    spot_df['return_60d'] = None
    spot_df = spot_df.drop_duplicates(subset=['code']).reset_index(drop=True)
    _write_daily_cache(spot_df, cache_path, "新浪快照")
    return spot_df


def _get_em_stock_list():
    cache_path = _cache_path("spot_cache")
    cached_df, cache_time = _read_daily_cache(cache_path)
    if cached_df is not None and len(cached_df) > 0:
        print(f"  ✅ 读取东财快照缓存: {len(cached_df)} 只（{cache_time.strftime('%H:%M')}）")
        return cached_df

    print("  调用东财 stock_zh_a_spot_em 获取全量快照...")
    spot_df = fetch_with_retry(
        ak.stock_zh_a_spot_em,
        max_retries=1,
        rate_limiter=_em_rate_limiter,
    )
    _write_daily_cache(spot_df, cache_path, "东财快照")
    return spot_df


def _standardize_spot_df(spot_df):
    if spot_df is None or len(spot_df) == 0:
        return pd.DataFrame()

    col_map = {
        '代码': 'code', '名称': 'name', '最新价': 'price',
        '涨跌幅': 'pct_change', '60日涨跌幅': 'return_60d',
        '总市值': 'total_mv', '流通市值': 'float_mv',
        '行业': 'industry', '行业板块': 'industry',
    }
    existing = {k: v for k, v in col_map.items() if k in spot_df.columns}
    spot_df = spot_df.rename(columns=existing)

    for col in ['code', 'name', 'price', 'pct_change', 'return_60d', 'total_mv', 'float_mv', 'industry']:
        if col not in spot_df.columns:
            spot_df[col] = None

    spot_df['code'] = spot_df['code'].astype(str).str.extract(r'(\d{6})', expand=False).fillna(spot_df['code'])
    return spot_df


def _fetch_one_tx_hist(code, start_date, end_date):
    """单只股票腾讯日线拉取（用于并发）"""
    try:
        _tx_rate_limiter.wait()
        prefix = 'sh' if str(code).startswith('6') else 'sz'
        tx_code = f"{prefix}{code}"
        df = ak.stock_zh_a_hist_tx(symbol=tx_code, start_date=start_date, end_date=end_date)
        return code, df
    except Exception:
        return code, None


def _fallback_stock_list(codes=None):
    """降级策略：东财快照不可用时，用腾讯日线拉全量（或指定）股票数据

    参数：
        codes: list[str] 或 None
            - 非空：只拉这些代码
            - None / 空：拉全量静态代码列表
    腾讯接口需要 sh/sz 前缀，6/688开头→sh，其余→sz
    拉最近90天日线，取最新收盘价 + 60日涨跌幅
    支持并发拉取 + 当日15点前缓存
    """
    # ── 检查腾讯降级缓存 ──
    script_dir = os.path.dirname(os.path.abspath(__file__))
    today_str = datetime.now().strftime("%Y%m%d")
    cache_path = os.path.join(script_dir, f"tx_spot_cache_{today_str}.json")

    # 删除前一天的缓存
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
    yesterday_cache = os.path.join(script_dir, f"tx_spot_cache_{yesterday}.json")
    if os.path.exists(yesterday_cache):
        try:
            os.remove(yesterday_cache)
            print(f"  🗑️  已删除昨日缓存: {yesterday_cache}")
        except Exception as e:
            print(f"  [WARN] 删除昨日缓存失败: {e}")

    # 如果是 watch_list 模式，从缓存文件中读取对应股票的数据
    if codes and os.path.exists(cache_path):
        cache_time = datetime.fromtimestamp(os.path.getmtime(cache_path))
        cache_date = cache_time.strftime("%Y%m%d")

        # 当天缓存都有效（不区分15点前后）
        if cache_date == today_str:
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cached_data = json.load(f)
                # 从缓存中筛选出需要的股票
                cached_stocks = {item['code']: item for item in cached_data}
                filtered = []
                for code in codes:
                    code6 = str(code).zfill(6)
                    if code6 in cached_stocks:
                        filtered.append(cached_stocks[code6])
                if filtered:
                    print(f"  ✅ 读取腾讯降级缓存: {len(filtered)} 只（{cache_time.strftime('%H:%M')}）")
                    return pd.DataFrame(filtered)
            except Exception as e:
                print(f"  [WARN] 缓存读取失败: {e}，重新拉取...")

    # 如果是全量模式，直接从缓存读取
    if codes is None and os.path.exists(cache_path):
        cache_time = datetime.fromtimestamp(os.path.getmtime(cache_path))
        cache_date = cache_time.strftime("%Y%m%d")

        # 当天缓存都有效（不区分15点前后）
        if cache_date == today_str:
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cached_data = json.load(f)
                print(f"  ✅ 读取腾讯降级缓存: {len(cached_data)} 只（{cache_time.strftime('%H:%M')}）")
                return pd.DataFrame(cached_data)
            except Exception as e:
                print(f"  [WARN] 缓存读取失败: {e}，重新拉取...")

    if codes:
        all_codes = [str(c).zfill(6) for c in codes]
        print(f"  [降级] watch_list 模式，共 {len(all_codes)} 只股票...")
    else:
        all_codes = _build_all_a_codes()
        # 受 max_candidates 限制
        print(f"  [降级] 全量模式，构造静态A股代码列表，共尝试 {len(all_codes)} 只...")

    rows = [{'code': c, 'name': c, 'price': None,
             'pct_change': None, 'return_60d': None,
             'total_mv': 'N/A', 'float_mv': 'N/A'}
            for c in all_codes]
    df_codes = pd.DataFrame(rows)

    end_date  = datetime.now().strftime("%Y%m%d")
    start_90  = (datetime.now() - timedelta(days=90)).strftime("%Y%m%d")

    # ── 并发拉取腾讯日线 ─────────────────────────────────────
    workers = CONFIG.get('tx_concurrent_workers', 6)
    print(f"  [降级] 使用 {workers} 线程并发拉取...")

    code_to_idx = {c: i for i, c in enumerate(all_codes)}
    success = 0
    total = len(all_codes)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_fetch_one_tx_hist, c, start_90, end_date): c
            for c in all_codes
        }
        for i, future in enumerate(as_completed(futures), 1):
            code, df_h = future.result()
            if i % 50 == 0:
                print(f"    降级进度: {i}/{total}，已成功 {success} 只")

            if df_h is None or len(df_h) < 2:
                continue

            df_h = df_h.sort_values('date').reset_index(drop=True)
            price      = float(df_h.iloc[-1]['close'])
            prev_close = float(df_h.iloc[-2]['close'])
            pct_change = round((price / prev_close - 1) * 100, 2)

            # 60日涨跌幅
            if len(df_h) >= 61:
                return_60d = round((price / float(df_h.iloc[-61]['close']) - 1) * 100, 2)
            elif len(df_h) >= 2:
                return_60d = round((price / float(df_h.iloc[0]['close']) - 1) * 100, 2)
            else:
                return_60d = 0.0

            if price < CONFIG['min_price']:
                continue

            idx = code_to_idx[code]
            df_codes.at[idx, 'price']      = price
            df_codes.at[idx, 'pct_change'] = pct_change
            df_codes.at[idx, 'return_60d'] = return_60d
            success += 1

    df_codes = df_codes.dropna(subset=['price']).reset_index(drop=True)
    print(f"  [降级] 成功获取 {success} 只股票价格数据")

    # 写入缓存（当天都有效，跨天自动失效）
    if len(df_codes) > 0:
        try:
            cached_data = df_codes.to_dict(orient='records')
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(cached_data, f, ensure_ascii=False, indent=None)
            print(f"  💾 腾讯降级数据已缓存: {cache_path}")
        except Exception as e:
            print(f"  [WARN] 缓存写入失败: {e}")

    return df_codes


def get_stock_list(market="A"):
    """获取A股股票列表

    策略优先级（当 use_em=True）：
    1. watch_list 非空 → 直接用腾讯日线拉这几只，跳过东财
    2. 当日磁盘缓存命中 → 直接读缓存
    3. 东财 stock_zh_a_spot_em（带重试限流）→ 成功写缓存
    4. 东财失败 → 降级：腾讯日线拉全量静态代码列表

    策略优先级（当 use_em=False）：
    1. watch_list 非空 → 直接用腾讯日线拉这几只
    2. 腾讯日线拉全量静态代码列表

    返回 DataFrame：code, name, price, pct_change, return_60d, total_mv, float_mv
    """
    watch_list = CONFIG.get('watch_list', [])
    use_em = CONFIG.get('use_em', True)
    use_local_db = CONFIG.get('use_local_db', False)
    return_days = CONFIG.get('prefilter_return_days', 60)

    # ── 0. watch_list 快速路径 ──────────────────────────────────
    if watch_list and use_local_db:
        print(f"  🎯 watch_list 模式：只扫 {watch_list}")
        spot_df = _get_db_stock_list(codes=watch_list, return_days=return_days)
        spot_df = _standardize_spot_df(spot_df)
        spot_df['code'] = spot_df['code'].astype(str).str.zfill(6)
        print(f"  股票总数（watch_list）: {len(spot_df)} 只")
        return spot_df

    if watch_list:
        print(f"  🎯 watch_list 模式：只扫 {watch_list}")
        spot_df = _fallback_stock_list(codes=watch_list)
        # watch_list 模式不做预筛过滤，直接返回
        spot_df['code'] = spot_df['code'].astype(str).str.zfill(6)
        print(f"  股票总数（watch_list）: {len(spot_df)} 只")
        return spot_df

    if use_local_db:
        print("  ⚡ use_local_db=True，优先使用本地 SQLite 股票日线库...")
        spot_df = _get_db_stock_list(return_days=return_days)
        if spot_df is None or len(spot_df) == 0:
            print("  [WARN] 本地数据库未返回股票池，回退到原有网络数据源...")
        else:
            spot_df = _standardize_spot_df(spot_df)
            print(f"  股票总数: {len(spot_df)} 只")

    # ── 0.5. 东财开关判断 ──────────────────────────────────────
    if not use_local_db and not use_em:
        print("  ⚡ use_em=False，跳过东财接口...")
        spot_df = pd.DataFrame()
        if CONFIG.get('prefer_sina_spot', True):
            try:
                spot_df = _get_sina_stock_list()
            except Exception as e:
                print(f"  [WARN] 新浪快照失败: {e}")
                spot_df = pd.DataFrame()
        if spot_df is None or len(spot_df) == 0:
            print("  ⚠️  新浪快照不可用，降级为腾讯逐股历史拼快照...")
            spot_df = _fallback_stock_list(codes=None)
        if spot_df is not None and len(spot_df) > 0:
            spot_df = _standardize_spot_df(spot_df)
            spot_df['code'] = spot_df['code'].astype(str).str.zfill(6)
            print(f"  股票总数: {len(spot_df)} 只")
        else:
            print("  [ERROR] 非东财模式下无法获取股票列表")
            return pd.DataFrame()
    elif not use_local_db:
        spot_df = None
        try:
            spot_df = _get_em_stock_list()
            print(f"  ✅ 东财快照成功: {len(spot_df)} 只")
        except Exception as e:
            print(f"  [ERROR] 东财快照失败: {e}")
            if CONFIG.get('prefer_sina_spot', True):
                try:
                    print("  ⚠️  改用新浪全量快照...")
                    spot_df = _get_sina_stock_list()
                except Exception as sina_error:
                    print(f"  [WARN] 新浪快照失败: {sina_error}")
                    spot_df = None
            if spot_df is None or len(spot_df) == 0:
                print("  ⚠️  最终降级：腾讯日线拉全量股票数据...")
                spot_df = _fallback_stock_list(codes=None)

        if spot_df is None or len(spot_df) == 0:
            print("  [ERROR] 无法获取股票列表")
            return pd.DataFrame()

        spot_df = _standardize_spot_df(spot_df)

    if spot_df is None or len(spot_df) == 0:
        print("  [ERROR] 无法获取股票列表")
        return pd.DataFrame()

    # ── 3. 标准化列名 ──────────────────────────────────────────
    spot_df = _standardize_spot_df(spot_df)

    # 补充缺失列
    for col in ['code', 'name', 'price', 'pct_change', 'return_60d', 'total_mv', 'float_mv', 'industry']:
        if col not in spot_df.columns:
            spot_df[col] = None

    # ── 4. 按市场筛选 ──────────────────────────────────────────
    spot_df['code'] = spot_df['code'].astype(str).str.zfill(6)
    if market == "SH":
        spot_df = spot_df[spot_df['code'].str.startswith('6')]
    elif market == "SZ":
        spot_df = spot_df[spot_df['code'].str.match(r'^(00|30)')]
    else:  # A = 沪深，排除北交所(8/4/9开头)
        spot_df = spot_df[~spot_df['code'].str.startswith(('8', '4', '9'))]

    # ── 5. 排除 ST ──────────────────────────────────────────────
    if CONFIG['exclude_st']:
        spot_df = spot_df[~spot_df['name'].astype(str).str.contains(
            'ST|退市|摘牌|N |C ', na=False, regex=True)]

    # ── 6. 股价过滤 ──────────────────────────────────────────────
    spot_df['price'] = pd.to_numeric(spot_df['price'], errors='coerce')
    spot_df = spot_df.dropna(subset=['price'])
    spot_df = spot_df[spot_df['price'] >= CONFIG['min_price']]

    spot_df = spot_df.reset_index(drop=True)
    print(f"  股票总数（过滤后）: {len(spot_df)} 只")

    return spot_df


def get_industry_map():
    """获取行业板块映射"""
    industry_map = {}
    try:
        boards = ak.stock_board_industry_name_em()
        for _, row in boards.iterrows():
            try:
                cons = ak.stock_board_industry_cons_em(symbol=row['板块名称'])
                for _, s in cons.iterrows():
                    industry_map[s['代码']] = row['板块名称']
            except:
                pass
            time.sleep(0.03)
    except:
        pass
    return industry_map


def _scan_candidate(row, zscore_min, zscore_max, prefilter_days, prefilter_return_pct, industry_map=None):
    code = row['code']
    name = row['name']
    price = row['price']
    pct_change = row['pct_change']

    zdata = calc_zscore(code, price)
    if not zdata:
        return None

    if zdata['return_Nd'] > prefilter_return_pct:
        return None

    zscore = zdata['zscore']
    if not (zscore_min <= zscore <= zscore_max):
        return None

    financial = get_financial_data(code)
    debt_ratio_val = financial['debt_ratio_val']
    news_list = get_news(code)

    tech_score = calc_tech_score(zscore)
    finance_score = calc_finance_score(debt_ratio_val, financial['roe'])
    news_score, news_detail = calc_news_score(news_list, zscore, debt_ratio_val, financial['roe'])
    buy_score = tech_score + finance_score + news_score

    if buy_score < CONFIG['score_min']:
        return None

    industry = row.get('industry') or (industry_map or {}).get(code, '未知')
    risk = build_risk_note(code, name, debt_ratio_val, financial['roe'], zscore, industry)
    news_summary = build_news_summary(code, name, news_list, financial)

    return {
        'code': code,
        'name': name,
        'price': price,
        'pct_change': pct_change,
        'zscore': zscore,
        'pct_from_mean': zdata['pct_from_mean'],
        'mean_20': zdata['mean_20'],
        'std_20': zdata['std_20'],
        'upper_band': zdata['upper_band'],
        'lower_band': zdata['lower_band'],
        f'return_{prefilter_days}d': zdata['return_Nd'],
        'vol_ratio': zdata['vol_ratio'],
        'atr_pct': zdata['atr_pct'],
        'debt_ratio': financial['debt_ratio'],
        'debt_ratio_val': debt_ratio_val,
        'roe': financial['roe'],
        'net_profit': financial['net_profit'],
        'revenue': financial['revenue'],
        'revenue_yoy': financial['revenue_yoy'],
        'profit_yoy': financial['profit_yoy'],
        'eps': financial['eps'],
        'book_value': financial['book_value'],
        'total_mv': row.get('total_mv', 'N/A'),
        'float_mv': row.get('float_mv', 'N/A'),
        'industry': industry,
        'report_period': financial['report_period'],
        'news_summary': news_summary,
        'news_score': news_score,
        'tech_score': tech_score,
        'finance_score': finance_score,
        'buy_score': buy_score,
        'score_detail': f"技术{tech_score}分+财务{finance_score}分+消息{news_score}分 | {news_detail}",
        'risk': risk,
        'news_list': news_list,
    }


def _normalize_hist_df(df):
    """统一历史日线 DataFrame 列名为东财格式（中文）
    
    兼容两种来源：
    - 东财 stock_zh_a_hist：日期, 开盘, 收盘, 最高, 最低, 成交量, 成交额, 振幅, 涨跌幅, 涨跌额, 换手率
    - 腾讯 stock_zh_a_hist_tx：date, open, close, high, low, amount
    """
    if df is None:
        return None
    col_map = {
        'date': '日期',
        'open': '开盘',
        'close': '收盘',
        'high': '最高',
        'low': '最低',
        'amount': '成交量',  # 腾讯的 amount 实际是成交量（手数）
    }
    existing = {k: v for k, v in col_map.items() if k in df.columns}
    if existing:
        df = df.rename(columns=existing)
    if '股票代码' in df.columns:
        df['股票代码'] = df['股票代码'].astype(str).str.extract(r'(\d+)', expand=False).fillna(df['股票代码'])
        df['股票代码'] = df['股票代码'].str.zfill(6)
    if '日期' in df.columns:
        df['日期'] = pd.to_datetime(df['日期'], errors='coerce').dt.strftime('%Y-%m-%d')
    return df


def _get_hist_df(code):
    """获取单只股票历史日线（优先内存缓存 → 磁盘缓存 → 东财接口 → 腾讯降级）"""
    lookback_days = CONFIG['lookback_months'] * 35
    start = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y%m%d")
    end = datetime.now().strftime("%Y%m%d")

    df = None
    use_local_db = CONFIG.get('use_local_db', False)
    use_em = CONFIG.get('use_em', True)

    if use_local_db:
        start_sql = datetime.strptime(start, "%Y%m%d").strftime("%Y-%m-%d")
        end_sql = datetime.strptime(end, "%Y%m%d").strftime("%Y-%m-%d")
        query = """
        SELECT
            date AS 日期,
            open AS 开盘,
            close AS 收盘,
            high AS 最高,
            low AS 最低,
            volume AS 成交量,
            amount AS 成交额,
            amplitude AS 振幅,
            change_pct AS 涨跌幅,
            (close - pre_close) AS 涨跌额,
            NULL AS 换手率,
            CAST(code AS TEXT) AS 股票代码
        FROM stock_daily
        WHERE code = ? AND date BETWEEN ? AND ?
        ORDER BY date ASC
        """
        try:
            with _get_db_connection() as conn:
                df = pd.read_sql_query(query, conn, params=[str(code).zfill(6), start_sql, end_sql])
        except Exception:
            df = None
        return _normalize_hist_df(df) if df is not None and len(df) >= 2 else None

    # ── 内存缓存（本次运行已拉取过）──
    mem_cache = CONFIG.get('_hist_cache', {})
    if code in mem_cache:
        return mem_cache[code]

    # ── 磁盘缓存 ──
    script_dir = os.path.dirname(os.path.abspath(__file__))
    hist_cache_dir = os.path.join(script_dir, 'hist_cache')
    os.makedirs(hist_cache_dir, exist_ok=True)
    today_str = datetime.now().strftime("%Y%m%d")
    disk_path = os.path.join(hist_cache_dir, f"{code}_{today_str}.csv")

    # 删除前一天的缓存
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
    yesterday_path = os.path.join(hist_cache_dir, f"{code}_{yesterday}.csv")
    if os.path.exists(yesterday_path):
        try:
            os.remove(yesterday_path)
        except Exception:
            pass  # 删除失败不影响主流程

    if os.path.exists(disk_path):
        cache_time = datetime.fromtimestamp(os.path.getmtime(disk_path))
        cache_date = cache_time.strftime("%Y%m%d")

        if cache_date == today_str:
            try:
                df = pd.read_csv(disk_path, encoding='utf-8-sig')
                df = _normalize_hist_df(df)
                if '_hist_cache' not in CONFIG:
                    CONFIG['_hist_cache'] = {}
                CONFIG['_hist_cache'][code] = df
                return df
            except Exception:
                pass

    if use_em:
        try:
            df = fetch_with_retry(
                ak.stock_zh_a_hist,
                symbol=code, period="daily",
                start_date=start, end_date=end, adjust="qfq",
                rate_limiter=_em_rate_limiter,
                max_retries=1   # IP 被封时直接失败，避免每只多等 15s
            )
        except Exception:
            df = None

    # ── 东财失败或跳过东财 → 腾讯降级 ──
    if (not use_local_db) and (df is None or len(df) < 2):
        try:
            prefix = 'sh' if str(code).startswith('6') else 'sz'
            tx_code = f"{prefix}{code}"
            df = fetch_with_retry(
                ak.stock_zh_a_hist_tx,
                symbol=tx_code, start_date=start, end_date=end,
                rate_limiter=_tx_rate_limiter,
                max_retries=2
            )
        except Exception:
            df = None

    if df is None or len(df) < 2:
        return None

    df = _normalize_hist_df(df)

    # 写磁盘缓存
    try:
        df.to_csv(disk_path, index=False, encoding='utf-8-sig')
    except Exception:
        pass

    # 写内存缓存
    if '_hist_cache' not in CONFIG:
        CONFIG['_hist_cache'] = {}
    CONFIG['_hist_cache'][code] = df

    return df


def calc_zscore(code, price):
    """计算布林带Z-Score（内存/磁盘双层缓存 + 东财日线 + 重试限流）"""
    window = CONFIG['bb_window']

    df = _get_hist_df(code)
    if df is None or len(df) < window + 2:
        return None

    try:
        df = df.sort_values('日期')
        close = df['收盘'].values

        # 滚动窗口
        win = close[-window:]
        ma = np.mean(win)
        std = np.std(win, ddof=1)

        if std < 0.001:
            return None

        zscore = (price - ma) / std
        upper = ma + CONFIG['bb_std'] * std
        lower = ma - CONFIG['bb_std'] * std
        pct_from_mean = (price - ma) / ma * 100

        # 成交量比
        vol = df['成交量'].values
        vol_avg_N = np.mean(vol[-window:]) if len(vol) >= window else np.mean(vol)
        vol_avg_5 = np.mean(vol[-5:]) if len(vol) >= 5 else np.mean(vol)
        vol_ratio = vol_avg_5 / vol_avg_N if vol_avg_N > 0 else 1.0

        # ATR
        if len(df) >= 14:
            high = df['最高'].values[-14:]
            low = df['最低'].values[-14:]
            close_prev = df['收盘'].values[-15:-1]
            tr = np.maximum(high - low,
                           np.maximum(np.abs(high - close_prev),
                                     np.abs(low - close_prev)))
            atr = np.mean(tr)
            atr_pct = atr / price * 100
        else:
            atr_pct = std / ma * 100

        # N日涨跌幅
        ret_days = CONFIG['prefilter_return_days']
        if len(close) >= ret_days + 1:
            return_Nd = (close[-1] / close[-(ret_days + 1)] - 1) * 100
        else:
            return_Nd = 0.0

        return {
            'zscore': round(zscore, 3),
            'mean_20': round(ma, 3),
            'std_20': round(std, 3),
            'upper_band': round(upper, 3),
            'lower_band': round(lower, 3),
            'pct_from_mean': round(pct_from_mean, 2),
            'return_Nd': round(return_Nd, 2),
            'vol_ratio': round(vol_ratio, 3),
            'atr_pct': round(atr_pct, 2),
        }
    except Exception:
        return None


def get_financial_data(code):
    """获取财务数据"""
    result = {
        'debt_ratio': 'N/A',
        'debt_ratio_val': 999,
        'roe': 'N/A',
        'net_profit': 'N/A',
        'revenue': 'N/A',
        'revenue_yoy': 'N/A',
        'profit_yoy': 'N/A',
        'eps': 'N/A',
        'book_value': 'N/A',
        'report_period': 'N/A',
    }

    try:
        df = ak.stock_financial_abstract_ths(symbol=code, indicator="按年度")
        if df is None or len(df) == 0:
            return result

        df['报告期_int'] = pd.to_numeric(df['报告期'], errors='coerce')
        df = df.dropna(subset=['报告期_int'])
        df = df.sort_values('报告期_int', ascending=False)

        if len(df) == 0:
            return result

        latest = df.iloc[0]
        result['report_period'] = str(latest.get('报告期', 'N/A'))

        dr = str(latest.get('资产负债率', 'N/A'))
        result['debt_ratio'] = dr
        try:
            result['debt_ratio_val'] = float(dr.rstrip('%'))
        except:
            result['debt_ratio_val'] = 999

        roe_val = latest.get('净资产收益率-摊薄', latest.get('净资产收益率', 'N/A'))
        result['roe'] = str(roe_val) if roe_val is not None else 'N/A'
        result['net_profit'] = str(latest.get('净利润', 'N/A'))
        result['revenue'] = str(latest.get('营业总收入', 'N/A'))
        result['revenue_yoy'] = str(latest.get('营业总收入同比增长率', 'N/A'))
        result['profit_yoy'] = str(latest.get('净利润同比增长率', 'N/A'))
        eps_val = latest.get('基本每股收益', 'N/A')
        result['eps'] = str(eps_val) if eps_val is not None else 'N/A'
        bv_val = latest.get('每股净资产', 'N/A')
        result['book_value'] = str(bv_val) if bv_val is not None else 'N/A'
    except:
        pass

    return result


def get_news(code):
    """获取近期新闻"""
    news_list = []
    try:
        df = ak.stock_news_em(symbol=code)
        if df is not None:
            for _, row in df.head(CONFIG['news_count']).iterrows():
                try:
                    news_list.append({
                        'date': str(row.get('发布时间', ''))[:10],
                        'title': str(row.get('新闻标题', '')),
                    })
                except:
                    pass
    except:
        pass
    return news_list


def calc_news_score(news_list, zscore, debt_ratio_val, roe_str):
    """计算消息面评分（0-30）"""
    score = 0
    details = []

    # 基本分：超跌本身加分
    if zscore < -3.0:
        score += 8
        details.append("Z-Score极度超跌(+8)")
    elif zscore < -2.5:
        score += 5
        details.append("Z-Score严重超跌(+5)")

    # 新闻利好加分
    keywords_good = ['回购', '增持', '分红', '业绩增长', '净利润增长', '中标', '订单', '战略', '突破']
    keywords_bad  = ['减持', '诉讼', '处罚', '亏损', '风险', '警示', '违规']

    good_count = 0
    bad_count = 0
    for n in news_list:
        t = n.get('title', '')
        good_count += sum(1 for kw in keywords_good if kw in t)
        bad_count  += sum(1 for kw in keywords_bad if kw in t)

    score += min(good_count * 3, 12)
    score -= min(bad_count * 3, 6)

    # 财务健康加分
    if debt_ratio_val < 70:
        score += 5
        details.append("资产负债率健康(+5)")
    elif debt_ratio_val < 85:
        score += 2
        details.append("资产负债率尚可(+2)")

    # ROE为正
    try:
        roe_val = float(str(roe_str).rstrip('%'))
        if roe_val > 0:
            score += 5
            details.append("ROE为正(+5)")
        elif roe_val < -10:
            score -= 5
            details.append("ROE大幅亏损(-5)")
    except:
        pass

    return max(0, min(30, score)), "; ".join(details) if details else "无特别利好"


def calc_finance_score(debt_ratio_val, roe_str):
    """计算基本面评分（0-35）"""
    score = 0

    # 资产负债率（35分制）
    if debt_ratio_val < 50:
        score = 35
    elif debt_ratio_val < 60:
        score = 30
    elif debt_ratio_val < 70:
        score = 25
    elif debt_ratio_val < 80:
        score = 18
    elif debt_ratio_val < 90:
        score = 10
    else:
        score = 5

    # ROE修正
    try:
        roe_val = float(str(roe_str).rstrip('%'))
        if roe_val > 20:
            score = min(score + 5, 35)
        elif roe_val > 10:
            score = min(score + 2, 35)
        elif roe_val < -10:
            score = max(score - 15, 0)
        elif roe_val < 0:
            score = max(score - 5, 0)
    except:
        pass

    return score


def calc_tech_score(zscore):
    """计算技术面评分（0-35）
    Z-Score 从 +3 到 -3，每 0.5 一档，共12档
    极度超跌（z≈-3）得35分，极度超买（z≈+3）得0分
    """
    if zscore > 3.0:
        return 0
    elif zscore > 2.5:
        return 3
    elif zscore > 2.0:
        return 6
    elif zscore > 1.5:
        return 10
    elif zscore > 1.0:
        return 13
    elif zscore > 0.5:
        return 16
    elif zscore > 0.0:
        return 20
    elif zscore > -0.5:
        return 24
    elif zscore > -1.0:
        return 27
    elif zscore > -1.5:
        return 29
    elif zscore > -2.0:
        return 31
    elif zscore > -2.5:
        return 33
    else:  # zscore <= -2.5
        return 35


def build_risk_note(code, name, debt_ratio_val, roe_str, zscore, industry):
    """生成风险提示"""
    risks = []
    try:
        dr = debt_ratio_val
        if dr > 90:
            risks.append(f"{industry or '行业'}资产负债率{dr}%偏高，需关注流动性风险")
        if dr < 0:
            risks.append("财务数据异常，请核实")
    except:
        pass

    try:
        roe_val = float(str(roe_str).rstrip('%'))
        if roe_val < -20:
            risks.append("ROE大幅亏损，基本面恶化")
        elif roe_val < 0:
            risks.append("公司当前亏损，基本面较弱")
    except:
        pass

    if zscore < -3.5:
        risks.append("Z-Score极度偏离，注意趋势延续风险（刀片接飞刀）")
    elif zscore < -3.0:
        risks.append("Z-Score极度超跌，注意继续下行风险")

    return "；".join(risks) if risks else "无特别风险提示"


def build_news_summary(code, name, news_list, financial):
    """生成消息摘要"""
    if not news_list:
        return f"{name}近期暂无重大公开消息。财务：资产负债率{financial['debt_ratio']}，ROE{financial['roe']}，净利润{financial['net_profit']}。"

    titles = [n.get('title', '')[:30] for n in news_list[:3]]
    summary = f"近期动态：{' | '.join(titles)}。财务：资产负债率{financial['debt_ratio']}，ROE{financial['roe']}。"
    return summary


def main():
    """主函数"""
    cfg = CONFIG

    print("=" * 60)
    print("  布林带 Z-Score A股扫描器")
    print("=" * 60)
    print(f"\n当前配置：")
    for k, v in cfg.items():
        print(f"  {k:25s} = {v}")
    print()

    # 全量扫描提示
    if not cfg.get('watch_list') and cfg.get('max_candidates', 0) > 100:
        print("=" * 60)
        print("  📊 即将进行全量扫描")
        print(f"  候选股票数量: {cfg['max_candidates']} 只")
        print(f"  预估耗时: {cfg['max_candidates'] * 2.4 / 60:.1f} 分钟（基于 2.4秒/只）")
        print("=" * 60)

        # 检查缓存
        script_dir = os.path.dirname(os.path.abspath(__file__))
        today_str = datetime.now().strftime("%Y%m%d")
        tx_cache = os.path.join(script_dir, f"tx_spot_cache_{today_str}.json")

        if os.path.exists(tx_cache):
            cache_time = datetime.fromtimestamp(os.path.getmtime(tx_cache))
            cache_date = cache_time.strftime("%Y%m%d")
            if cache_date == today_str:
                print(f"  ✅ 发现今日缓存（{cache_time.strftime('%H:%M')}），将复用缓存数据")
            else:
                print(f"  🗑️  检测到旧缓存，将自动删除并重新拉取")

        print("\n开始扫描...\n")

    market = cfg['market']
    bb_window = cfg['bb_window']
    zscore_min = cfg['zscore_min']
    zscore_max = cfg['zscore_max']
    lookback = cfg['lookback_months']
    prefilter_days = cfg['prefilter_return_days']
    ret_col = f'return_{prefilter_days}d'

    if cfg.get('use_local_db', False):
        ensure_db_indexes()

    end_date = datetime.now().strftime("%Y-%m-%d")
    print(f"[{end_date}] 开始扫描...")

    # 1. 获取股票列表
    print("\n>>> Step 1: 获取A股股票列表...")
    spot_df = get_stock_list(market)
    print(f"  股票总数: {len(spot_df)}")

    # 2. 初筛候选股（利用东财快照中的 return_60d 过滤超跌股）
    print(f"\n>>> Step 2: 候选股预筛（{prefilter_days}日涨跌幅 ≤ {cfg['prefilter_return_pct']}%）...")
    candidates = spot_df.copy()

    # 用 return_Nd 初筛（超跌方向）
    if ret_col in candidates.columns:
        candidates[ret_col] = pd.to_numeric(candidates[ret_col], errors='coerce')
        pre_len = len(candidates)
        candidates = candidates[
            candidates[ret_col].isna() |
            (candidates[ret_col] <= cfg['prefilter_return_pct'])
        ]
        print(f"  涨跌幅预筛: {pre_len} → {len(candidates)} 只（{prefilter_days}日涨跌幅 ≤ {cfg['prefilter_return_pct']}%）")

    if (ret_col not in candidates.columns) or candidates[ret_col].notna().sum() == 0:
        candidates['pct_change'] = pd.to_numeric(candidates['pct_change'], errors='coerce')
        candidates = candidates.sort_values(['pct_change', 'price'], ascending=[True, True], na_position='last')
        print(f"  [提示] 当前快照不含 {prefilter_days} 日涨跌幅，先按当日涨跌幅从低到高优先扫描")

    if len(candidates) > cfg['max_candidates']:
        candidates = candidates.head(cfg['max_candidates'])
        print(f"  候选股过多，截取前 {cfg['max_candidates']} 只")
    print(f"  候选股数量: {len(candidates)}")

    # 3. 获取行业映射
    industry_map = {}
    if cfg.get('load_industry_map', False):
        print("\n>>> Step 3: 获取行业板块...")
        industry_map = get_industry_map()
        print(f"  已映射: {len(industry_map)} 只股票")
    else:
        print("\n>>> Step 3: 跳过全量行业映射（默认关闭以提升性能）...")

    # 4. 批量计算 Z-Score
    print(f"\n>>> Step 4: 精确计算布林带 Z-Score...")
    print(f"  布林带窗口: {bb_window}日 | 历史回看: {lookback}月")
    print(f"  筛选条件: {zscore_min} ≤ Z-Score ≤ {zscore_max}")
    print(f"  排序: {cfg['sort_by']} ({'升序' if cfg['ascending'] else '降序'})")
    print(f"  并发扫描: {cfg.get('scan_concurrent_workers', 6)} 线程")

    results = []
    total = len(candidates)
    candidate_rows = candidates.to_dict(orient='records')
    workers = min(cfg.get('scan_concurrent_workers', 6), max(1, total))

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                _scan_candidate,
                row,
                zscore_min,
                zscore_max,
                prefilter_days,
                cfg['prefilter_return_pct'],
                industry_map,
            ): row['code']
            for row in candidate_rows
        }
        for i, future in enumerate(as_completed(futures), 1):
            if i % 200 == 0 or i == total:
                found = len(results)
                print(f"  进度: {i}/{total} ({i/total*100:.1f}%) | 已找到: {found}")
            try:
                result = future.result()
            except Exception as e:
                code = futures[future]
                print(f"  [WARN] {code} 扫描失败: {e}")
                continue
            if result:
                results.append(result)

    print(f"\n  ✅ 扫描完成！共找到 {len(results)} 只满足条件的股票")

    if not results:
        print("\n⚠️ 未找到满足条件的股票，请调整 Z-Score 阈值或初筛条件。")
        return

    # 5. 排序
    sort_key = cfg['sort_by']
    df = pd.DataFrame(results)

    # 动态重命名字段（return_Nd）
    if sort_key not in df.columns and sort_key == 'return_60d':
        sort_key = ret_col

    df['_sort'] = pd.to_numeric(df[sort_key], errors='coerce')
    df = df.sort_values('_sort', ascending=cfg['ascending'])
    df = df.drop(columns=['_sort'])
    df = df.head(cfg['top_n'])

    # 添加排名
    df.insert(0, 'rank', range(1, len(df) + 1))
    df = df.reset_index(drop=True)
    df['rank'] = range(1, len(df) + 1)

    # 6. 保存 CSV
    script_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(script_dir, 'results.csv')
    df.drop(columns=['news_list'], errors='ignore').to_csv(csv_path, index=False,
        encoding='utf-8-sig')
    print(f"  📄 CSV 已保存: {csv_path}")

    # 7. 生成 JSON（新结构：fields + lists）
    df_json = df.copy()
    if ret_col in df_json.columns:
        df_json = df_json.rename(columns={ret_col: f'return_{prefilter_days}d'})

    field_names = dict(FIELD_NAMES)
    field_names.pop('return_60d', None)
    field_names[ret_col] = f'{prefilter_days}日涨跌幅({ret_col})'

    # fields：{中文名: 英文key}
    fields = {}
    for eng_key, cn_label in field_names.items():
        # cn_label 格式："中文名(eng_key)"，提取中文名部分
        cn_name = cn_label.split('(')[0]
        fields[cn_name] = eng_key

    # lists：记录用英文 key
    json_records = []
    for _, row in df_json.iterrows():
        record = {}
        for eng_key in field_names.keys():
            val = row.get(eng_key, None)
            if eng_key == 'news_list':
                val = row.get('news_list', [])
            record[eng_key] = val
        json_records.append(record)

    output = {"fields": fields, "lists": json_records}

    json_path = os.path.join(script_dir, 'results.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)
    print(f"  📄 JSON 已保存: {json_path}")

    # 8. 打印摘要
    print(f"\n{'='*60}")
    print(f"  扫描结果摘要（按 {sort_key} {'升序' if cfg['ascending'] else '降序'}）")
    print(f"{'='*60}")
    print(f"{'排名':^4} {'代码':^8} {'名称':^10} {'Z-Score':^8} {'偏离均值':^8} "
          f"{'评分':^6} {'资产负债率':^10} {'ROE':^8}")
    print("-" * 70)
    for _, r in df.iterrows():
        roe_str = str(r['roe'])[:7]
        print(f"{int(r['rank']):^4} {r['code']:^8} {r['name']:^10} "
              f"{r['zscore']:^8.3f} {r['pct_from_mean']:>+7.2f}% "
              f"{int(r['buy_score']):^6} {r['debt_ratio']:^10} {roe_str:^8}")
    print("-" * 70)
    print(f"\n✅ 完成！更多详情请查看 results.csv 和 results.json")

    return df


if __name__ == "__main__":
    main()
