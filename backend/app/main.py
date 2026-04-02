from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from .config import settings
from .db import Base, SessionLocal, engine
from .models import User
from .routers import admin, analysis, auth, market, policy, watchlist
from .security import get_password_hash
from .services.crypto import ensure_rsa_keys

TABLE_COMMENT_DDLS = {
    "users": "ALTER TABLE users COMMENT = '系统用户表，存储登录账号、权限角色和用户专属 MX Key 密文'",
    "analysis_records": "ALTER TABLE analysis_records COMMENT = '策略分析记录表，保存每次量化分析的请求参数和结果快照'",
    "quant_regression_history": "ALTER TABLE quant_regression_history COMMENT = '量化回归历史表，保存基于历史数据的策略回测结果，使用 JSON 结果兼容多种量化算法扩展'",
    "watchlist_items": "ALTER TABLE watchlist_items COMMENT = '用户本地自选股表，保存每个用户维护的股票及最近一次刷新行情'",
    "market_news": "ALTER TABLE market_news COMMENT = '财经热点消息表，聚合 AKShare 与 MX 抓取的各平台财经资讯，供站内热点新闻流展示'",
    "policy_files": "ALTER TABLE policy_files COMMENT = '量化策略文件表'",
}

COLUMN_COMMENT_DDLS = {
    "users": {
        "id": "ALTER TABLE users MODIFY COLUMN id INT NOT NULL AUTO_INCREMENT COMMENT '用户主键 ID'",
        "username": "ALTER TABLE users MODIFY COLUMN username VARCHAR(50) NOT NULL COMMENT '登录用户名，系统内唯一'",
        "password_hash": "ALTER TABLE users MODIFY COLUMN password_hash VARCHAR(255) NOT NULL COMMENT '登录密码的 PBKDF2 哈希值'",
        "mx_api_key_encrypted": "ALTER TABLE users MODIFY COLUMN mx_api_key_encrypted TEXT NULL COMMENT '用户专属 MX API Key 的 RSA 加密密文'",
        "is_admin": "ALTER TABLE users MODIFY COLUMN is_admin TINYINT(1) NOT NULL COMMENT '是否为管理员，1 表示管理员'",
        "is_super_admin": "ALTER TABLE users MODIFY COLUMN is_super_admin TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否为超级管理员，1 表示超级管理员'",
        "created_at": "ALTER TABLE users MODIFY COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '账号创建时间'",
    },
    "analysis_records": {
        "id": "ALTER TABLE analysis_records MODIFY COLUMN id INT NOT NULL AUTO_INCREMENT COMMENT '分析记录主键 ID'",
        "user_id": "ALTER TABLE analysis_records MODIFY COLUMN user_id INT NOT NULL COMMENT '所属用户 ID，关联 users.id'",
        "symbol": "ALTER TABLE analysis_records MODIFY COLUMN symbol VARCHAR(16) NOT NULL COMMENT '分析标的代码'",
        "market": "ALTER TABLE analysis_records MODIFY COLUMN market VARCHAR(8) NOT NULL COMMENT '市场标识，例如 a 或 hk'",
        "strategy_key": "ALTER TABLE analysis_records MODIFY COLUMN strategy_key VARCHAR(80) NOT NULL COMMENT '策略注册键，例如 bollinger_mean_reversion'",
        "lookback_period": "ALTER TABLE analysis_records MODIFY COLUMN lookback_period VARCHAR(16) NOT NULL DEFAULT '2y' COMMENT '历史回看区间键，例如 6m、1y、2y'",
        "bollinger_window": "ALTER TABLE analysis_records MODIFY COLUMN bollinger_window VARCHAR(16) NOT NULL DEFAULT '20d' COMMENT '布林带窗口键，例如 10d、20d、30d、60d'",
        "price_frequency": "ALTER TABLE analysis_records MODIFY COLUMN price_frequency VARCHAR(16) NOT NULL DEFAULT 'daily' COMMENT '分析使用的K线频率，例如 daily'",
        "request_payload": "ALTER TABLE analysis_records MODIFY COLUMN request_payload TEXT NOT NULL COMMENT '分析请求参数 JSON'",
        "result_payload": "ALTER TABLE analysis_records MODIFY COLUMN result_payload TEXT NOT NULL COMMENT '策略分析结果 JSON 快照'",
        "created_at": "ALTER TABLE analysis_records MODIFY COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '分析记录创建时间'",
    },
    "quant_regression_history": {
        "id": "ALTER TABLE quant_regression_history MODIFY COLUMN id INT NOT NULL AUTO_INCREMENT COMMENT '量化回归历史主键 ID'",
        "user_id": "ALTER TABLE quant_regression_history MODIFY COLUMN user_id INT NOT NULL COMMENT '所属用户 ID，关联 users.id'",
        "symbol": "ALTER TABLE quant_regression_history MODIFY COLUMN symbol VARCHAR(16) NOT NULL COMMENT '回归标的代码'",
        "market": "ALTER TABLE quant_regression_history MODIFY COLUMN market VARCHAR(8) NOT NULL COMMENT '市场标识，例如 a 或 hk'",
        "algorithm_key": "ALTER TABLE quant_regression_history MODIFY COLUMN algorithm_key VARCHAR(80) NOT NULL COMMENT '量化算法键，例如 bollinger_mean_reversion'",
        "source_label": "ALTER TABLE quant_regression_history MODIFY COLUMN source_label VARCHAR(128) NULL COMMENT '回归使用的数据源说明'",
        "request_payload": "ALTER TABLE quant_regression_history MODIFY COLUMN request_payload TEXT NOT NULL COMMENT '回归请求参数 JSON'",
        "result_payload": "ALTER TABLE quant_regression_history MODIFY COLUMN result_payload TEXT NOT NULL COMMENT '回归结果 JSON，兼容多策略扩展'",
        "created_at": "ALTER TABLE quant_regression_history MODIFY COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '回归记录创建时间'",
    },
    "watchlist_items": {
        "id": "ALTER TABLE watchlist_items MODIFY COLUMN id INT NOT NULL AUTO_INCREMENT COMMENT '自选记录主键 ID'",
        "user_id": "ALTER TABLE watchlist_items MODIFY COLUMN user_id INT NOT NULL COMMENT '所属用户 ID，关联 users.id'",
        "symbol": "ALTER TABLE watchlist_items MODIFY COLUMN symbol VARCHAR(16) NOT NULL COMMENT '自选股票代码'",
        "market": "ALTER TABLE watchlist_items MODIFY COLUMN market VARCHAR(8) NOT NULL COMMENT '市场标识，例如 a 或 hk'",
        "display_name": "ALTER TABLE watchlist_items MODIFY COLUMN display_name VARCHAR(80) NULL COMMENT '股票名称或展示名称'",
        "last_price": "ALTER TABLE watchlist_items MODIFY COLUMN last_price FLOAT NULL COMMENT '最近一次刷新得到的当前价格'",
        "last_price_at": "ALTER TABLE watchlist_items MODIFY COLUMN last_price_at DATETIME NULL COMMENT '最近一次行情刷新时间'",
        "created_at": "ALTER TABLE watchlist_items MODIFY COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '自选记录创建时间'",
        "open_price": "ALTER TABLE watchlist_items MODIFY COLUMN open_price DOUBLE NULL COMMENT '最近一次刷新得到的开盘价'",
        "close_price": "ALTER TABLE watchlist_items MODIFY COLUMN close_price DOUBLE NULL COMMENT '最近一次刷新得到的收盘价或最新收盘参考价'",
        "day_high": "ALTER TABLE watchlist_items MODIFY COLUMN day_high DOUBLE NULL COMMENT '最近一次刷新得到的当日最高价'",
        "day_low": "ALTER TABLE watchlist_items MODIFY COLUMN day_low DOUBLE NULL COMMENT '最近一次刷新得到的当日最低价'",
    },
    "market_news": {
        "id": "ALTER TABLE market_news MODIFY COLUMN id INT NOT NULL AUTO_INCREMENT COMMENT '消息主键 ID'",
        "provider": "ALTER TABLE market_news MODIFY COLUMN provider VARCHAR(32) NOT NULL COMMENT '数据接入方，例如 akshare 或 mx'",
        "platform": "ALTER TABLE market_news MODIFY COLUMN platform VARCHAR(64) NOT NULL COMMENT '消息来源平台标识，例如 eastmoney、cls、sina、mx_hot'",
        "source": "ALTER TABLE market_news MODIFY COLUMN source VARCHAR(128) NULL COMMENT '页面展示用的来源名称'",
        "title": "ALTER TABLE market_news MODIFY COLUMN title VARCHAR(255) NOT NULL COMMENT '新闻标题'",
        "summary": "ALTER TABLE market_news MODIFY COLUMN summary TEXT NULL COMMENT '新闻摘要或短内容'",
        "content": "ALTER TABLE market_news MODIFY COLUMN content TEXT NULL COMMENT '新闻正文或详细内容'",
        "info_type": "ALTER TABLE market_news MODIFY COLUMN info_type VARCHAR(64) NULL COMMENT '资讯类型，例如 快讯、要闻、公告'",
        "security": "ALTER TABLE market_news MODIFY COLUMN security VARCHAR(255) NULL COMMENT '关联证券或主题名称'",
        "url": "ALTER TABLE market_news MODIFY COLUMN url VARCHAR(500) NULL COMMENT '原始资讯链接'",
        "published_at": "ALTER TABLE market_news MODIFY COLUMN published_at DATETIME NULL COMMENT '资讯发布时间，供站内按时间倒序展示'",
        "published_at_text": "ALTER TABLE market_news MODIFY COLUMN published_at_text VARCHAR(64) NULL COMMENT '原始发布时间文本，解析失败时保留'",
        "content_hash": "ALTER TABLE market_news MODIFY COLUMN content_hash VARCHAR(64) NOT NULL COMMENT '基于平台、标题、内容和发布时间生成的去重哈希'",
        "raw_payload": "ALTER TABLE market_news MODIFY COLUMN raw_payload TEXT NULL COMMENT '原始消息 JSON 快照，便于排查与回溯'",
        "created_at": "ALTER TABLE market_news MODIFY COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '消息入库时间'",
    },
    "policy_files": {
        "id": "ALTER TABLE policy_files MODIFY COLUMN id INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '自增id'",
        "name": "ALTER TABLE policy_files MODIFY COLUMN name VARCHAR(128) NOT NULL DEFAULT '' COMMENT '策略名称'",
        "folder": "ALTER TABLE policy_files MODIFY COLUMN folder VARCHAR(255) NULL COMMENT '策略目录'",
        "readme": "ALTER TABLE policy_files MODIFY COLUMN readme VARCHAR(255) NOT NULL DEFAULT '' COMMENT '策略脚本使用文档'",
        "path": "ALTER TABLE policy_files MODIFY COLUMN path VARCHAR(255) NOT NULL DEFAULT '' COMMENT '文件路径'",
        "results": "ALTER TABLE policy_files MODIFY COLUMN results VARCHAR(255) NULL COMMENT '结果文件'",
        "list_show_fields": "ALTER TABLE policy_files MODIFY COLUMN list_show_fields VARCHAR(500) NOT NULL DEFAULT '' COMMENT '列表展示字段，不超过5个'",
        "created_user_id": "ALTER TABLE policy_files MODIFY COLUMN created_user_id INT UNSIGNED NOT NULL COMMENT '策略创建人'",
        "created_at": "ALTER TABLE policy_files MODIFY COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间'",
        "updated_at": "ALTER TABLE policy_files MODIFY COLUMN updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间'",
    },
}


def ensure_watchlist_columns() -> None:
    required_columns = {
        "open_price": "ALTER TABLE watchlist_items ADD COLUMN open_price DOUBLE NULL COMMENT '最近一次刷新得到的开盘价'",
        "close_price": "ALTER TABLE watchlist_items ADD COLUMN close_price DOUBLE NULL COMMENT '最近一次刷新得到的收盘价或最新收盘参考价'",
        "day_high": "ALTER TABLE watchlist_items ADD COLUMN day_high DOUBLE NULL COMMENT '最近一次刷新得到的当日最高价'",
        "day_low": "ALTER TABLE watchlist_items ADD COLUMN day_low DOUBLE NULL COMMENT '最近一次刷新得到的当日最低价'",
    }
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "watchlist_items" not in table_names:
        return
    existing_columns = {column["name"] for column in inspector.get_columns("watchlist_items")}
    with engine.begin() as connection:
        for column_name, ddl in required_columns.items():
            if column_name not in existing_columns:
                connection.execute(text(ddl))


def ensure_analysis_record_columns() -> None:
    required_columns = {
        "lookback_period": "ALTER TABLE analysis_records ADD COLUMN lookback_period VARCHAR(16) NOT NULL DEFAULT '2y' COMMENT '历史回看区间键，例如 6m、1y、2y' AFTER strategy_key",
        "bollinger_window": "ALTER TABLE analysis_records ADD COLUMN bollinger_window VARCHAR(16) NOT NULL DEFAULT '20d' COMMENT '布林带窗口键，例如 10d、20d、30d、60d' AFTER lookback_period",
        "price_frequency": "ALTER TABLE analysis_records ADD COLUMN price_frequency VARCHAR(16) NOT NULL DEFAULT 'daily' COMMENT '分析使用的K线频率，例如 daily' AFTER bollinger_window",
    }
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "analysis_records" not in table_names:
        return
    existing_columns = {column["name"] for column in inspector.get_columns("analysis_records")}
    with engine.begin() as connection:
        for column_name, ddl in required_columns.items():
            if column_name not in existing_columns:
                connection.execute(text(ddl))

def ensure_user_columns() -> None:
    required_columns = {
        "mx_api_key_encrypted": "ALTER TABLE users ADD COLUMN mx_api_key_encrypted TEXT NULL COMMENT '用户专属 MX API Key 的 RSA 加密密文'",
        "is_super_admin": "ALTER TABLE users ADD COLUMN is_super_admin BOOLEAN NOT NULL DEFAULT FALSE COMMENT '是否为超级管理员，1 表示超级管理员'",
    }
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "users" not in table_names:
        return
    existing_columns = {column["name"] for column in inspector.get_columns("users")}
    with engine.begin() as connection:
        for column_name, ddl in required_columns.items():
            if column_name not in existing_columns:
                connection.execute(text(ddl))


def ensure_schema_comments() -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    with engine.begin() as connection:
        for table_name, ddl in TABLE_COMMENT_DDLS.items():
            if table_name in table_names:
                connection.execute(text(ddl))
        for table_name, column_map in COLUMN_COMMENT_DDLS.items():
            if table_name not in table_names:
                continue
            existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, ddl in column_map.items():
                if column_name in existing_columns:
                    connection.execute(text(ddl))


def init_database() -> None:
    ensure_rsa_keys()
    Base.metadata.create_all(bind=engine)
    ensure_user_columns()
    ensure_watchlist_columns()
    ensure_analysis_record_columns()
    ensure_schema_comments()
    db: Session = SessionLocal()
    try:
        admin_user = db.query(User).filter(User.username == "admin").first()
        if not admin_user:
            admin_user = User(username="admin", password_hash=get_password_hash("admin"), is_admin=True, is_super_admin=True)
            db.add(admin_user)
            db.commit()
        elif not admin_user.is_super_admin:
            admin_user.is_super_admin = True
            admin_user.is_admin = True
            db.commit()
    finally:
        db.close()


app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_database()


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(admin.router, prefix=settings.api_prefix)
app.include_router(market.router, prefix=settings.api_prefix)
app.include_router(analysis.router, prefix=settings.api_prefix)
app.include_router(policy.router, prefix=settings.api_prefix)
app.include_router(watchlist.router, prefix=settings.api_prefix)
