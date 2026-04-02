from __future__ import annotations

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import relationship, Mapped, mapped_column

from .db import Base
from .services.crypto import decrypt_text


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"comment": "系统用户表，存储登录账号、权限角色和用户专属 MX Key 密文"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, comment="用户主键 ID")
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True, comment="登录用户名，系统内唯一")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False, comment="登录密码的 PBKDF2 哈希值")
    mx_api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True, comment="用户专属 MX API Key 的 RSA 加密密文")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, comment="是否为管理员，1 表示管理员")
    is_super_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, comment="是否为超级管理员，1 表示超级管理员")
    created_at: Mapped[str] = mapped_column(DateTime, server_default=func.now(), nullable=False, comment="账号创建时间")

    analysis_records = relationship("AnalysisRecord", back_populates="user", cascade="all, delete-orphan")
    quant_regression_histories = relationship("QuantRegressionHistory", back_populates="user", cascade="all, delete-orphan")
    watchlist_items = relationship("WatchlistItem", back_populates="user", cascade="all, delete-orphan")

    @property
    def has_mx_api_key(self) -> bool:
        return bool(self.mx_api_key_encrypted)

    @property
    def masked_mx_api_key(self) -> str | None:
        if not self.mx_api_key_encrypted:
            return None
        try:
            api_key = decrypt_text(self.mx_api_key_encrypted)
        except Exception:
            return None
        if len(api_key) <= 6:
            return "*" * len(api_key)
        return f"{api_key[:3]}{'*' * (len(api_key) - 6)}{api_key[-3:]}"

    @property
    def role_label(self) -> str:
        if self.is_super_admin:
            return "超级管理员"
        if self.is_admin:
            return "管理员"
        return "普通用户"


class AnalysisRecord(Base):
    __tablename__ = "analysis_records"
    __table_args__ = {"comment": "策略分析记录表，保存每次量化分析的请求参数和结果快照"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, comment="分析记录主键 ID")
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="所属用户 ID，关联 users.id")
    symbol: Mapped[str] = mapped_column(String(16), nullable=False, index=True, comment="分析标的代码")
    market: Mapped[str] = mapped_column(String(8), nullable=False, index=True, comment="市场标识，例如 a 或 hk")
    strategy_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True, comment="策略注册键，例如 bollinger_mean_reversion")
    lookback_period: Mapped[str] = mapped_column(String(16), nullable=False, default="2y", index=True, comment="历史回看区间键，例如 6m、1y、2y")
    bollinger_window: Mapped[str] = mapped_column(String(16), nullable=False, default="20d", index=True, comment="布林带窗口键，例如 10d、20d、30d、60d")
    price_frequency: Mapped[str] = mapped_column(String(16), nullable=False, default="daily", index=True, comment="分析使用的K线频率，例如 daily")
    request_payload: Mapped[str] = mapped_column(Text, nullable=False, comment="分析请求参数 JSON")
    result_payload: Mapped[str] = mapped_column(Text, nullable=False, comment="策略分析结果 JSON 快照")
    created_at: Mapped[str] = mapped_column(DateTime, server_default=func.now(), nullable=False, comment="分析记录创建时间")

    user = relationship("User", back_populates="analysis_records")


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (
        UniqueConstraint("user_id", "symbol", "market", name="uq_watchlist_user_symbol_market"),
        {"comment": "用户本地自选股表，保存每个用户维护的股票及最近一次刷新行情"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, comment="自选记录主键 ID")
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="所属用户 ID，关联 users.id")
    symbol: Mapped[str] = mapped_column(String(16), nullable=False, index=True, comment="自选股票代码")
    market: Mapped[str] = mapped_column(String(8), nullable=False, index=True, comment="市场标识，例如 a 或 hk")
    display_name: Mapped[str | None] = mapped_column(String(80), nullable=True, comment="股票名称或展示名称")
    last_price: Mapped[float | None] = mapped_column(Float, nullable=True, comment="最近一次刷新得到的当前价格")
    open_price: Mapped[float | None] = mapped_column(Float, nullable=True, comment="最近一次刷新得到的开盘价")
    close_price: Mapped[float | None] = mapped_column(Float, nullable=True, comment="最近一次刷新得到的收盘价或最新收盘参考价")
    day_high: Mapped[float | None] = mapped_column(Float, nullable=True, comment="最近一次刷新得到的当日最高价")
    day_low: Mapped[float | None] = mapped_column(Float, nullable=True, comment="最近一次刷新得到的当日最低价")
    last_price_at: Mapped[str | None] = mapped_column(DateTime, nullable=True, comment="最近一次行情刷新时间")
    created_at: Mapped[str] = mapped_column(DateTime, server_default=func.now(), nullable=False, comment="自选记录创建时间")

    user = relationship("User", back_populates="watchlist_items")


class QuantRegressionHistory(Base):
    __tablename__ = "quant_regression_history"
    __table_args__ = {"comment": "量化回归历史表，保存基于历史数据的策略回测结果，使用 JSON 结果兼容多种量化算法扩展"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, comment="量化回归历史主键 ID")
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="所属用户 ID，关联 users.id")
    symbol: Mapped[str] = mapped_column(String(16), nullable=False, index=True, comment="回归标的代码")
    market: Mapped[str] = mapped_column(String(8), nullable=False, index=True, comment="市场标识，例如 a 或 hk")
    algorithm_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True, comment="量化算法键，例如 bollinger_mean_reversion")
    source_label: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="回归使用的数据源说明")
    request_payload: Mapped[str] = mapped_column(Text, nullable=False, comment="回归请求参数 JSON")
    result_payload: Mapped[str] = mapped_column(Text, nullable=False, comment="回归结果 JSON，兼容多策略扩展")
    created_at: Mapped[str] = mapped_column(DateTime, server_default=func.now(), nullable=False, comment="回归记录创建时间")

    user = relationship("User", back_populates="quant_regression_histories")


class PolicyFile(Base):
    __tablename__ = "policy_files"
    __table_args__ = {"comment": "量化策略文件表"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, comment="自增id")
    name: Mapped[str] = mapped_column(String(128), nullable=False, default="", comment="策略名称")
    folder: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="策略目录")
    readme: Mapped[str] = mapped_column(String(255), nullable=False, default="", comment="策略脚本使用文档")
    path: Mapped[str] = mapped_column(String(255), nullable=False, default="", comment="文件路径")
    results: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="结果文件")
    list_show_fields: Mapped[str] = mapped_column(String(500), nullable=False, default="", comment="列表展示字段，不超过5个")
    created_user_id: Mapped[int] = mapped_column(Integer, nullable=False, comment="策略创建人")
    created_at: Mapped[str] = mapped_column(DateTime, server_default=func.now(), nullable=False, comment="创建时间")
    updated_at: Mapped[str] = mapped_column(DateTime, server_default=func.now(), nullable=False, comment="更新时间")


class MarketNews(Base):
    __tablename__ = "market_news"
    __table_args__ = (
        UniqueConstraint("content_hash", name="uq_market_news_content_hash"),
        {"comment": "财经热点消息表，聚合 AKShare 与 MX 抓取的各平台财经资讯，供站内热点新闻流展示"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, comment="消息主键 ID")
    provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True, comment="数据接入方，例如 akshare 或 mx")
    platform: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="消息来源平台标识，例如 eastmoney、cls、sina、mx_hot")
    source: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="页面展示用的来源名称")
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True, comment="新闻标题")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True, comment="新闻摘要或短内容")
    content: Mapped[str | None] = mapped_column(Text, nullable=True, comment="新闻正文或详细内容")
    info_type: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="资讯类型，例如 快讯、要闻、公告")
    security: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="关联证券或主题名称")
    url: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="原始资讯链接")
    published_at: Mapped[str | None] = mapped_column(DateTime, nullable=True, index=True, comment="资讯发布时间，供站内按时间倒序展示")
    published_at_text: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="原始发布时间文本，解析失败时保留")
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment="基于平台、标题、内容和发布时间生成的去重哈希")
    raw_payload: Mapped[str | None] = mapped_column(Text, nullable=True, comment="原始消息 JSON 快照，便于排查与回溯")
    created_at: Mapped[str] = mapped_column(DateTime, server_default=func.now(), nullable=False, comment="消息入库时间")
