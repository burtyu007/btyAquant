from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


class UserBase(BaseModel):
    username: str = Field(min_length=3, max_length=50)


class UserCreate(UserBase):
    password: str = Field(min_length=4, max_length=100)
    is_admin: bool = False


class UserOut(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_admin: bool
    is_super_admin: bool
    has_mx_api_key: bool
    masked_mx_api_key: str | None = None
    role_label: str
    created_at: datetime


class UserManageOut(UserOut):
    can_delete: bool = False
    can_copy_mx_key: bool = False
    can_delete_mx_key: bool = False


class MessageResponse(BaseModel):
    message: str


class MXKeyUpdateRequest(BaseModel):
    api_key: str = Field(min_length=8, max_length=255)


class MXKeyRevealRequest(BaseModel):
    password: str = Field(min_length=4, max_length=100)


class MXKeyRevealResponse(BaseModel):
    api_key: str


class NewsItem(BaseModel):
    title: str
    content: str
    date: str | None = None
    source: str | None = None
    info_type: str | None = None
    security: str | None = None


class WatchlistCreate(BaseModel):
    symbol: str
    market: str = "a"


class WatchlistOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    market: str
    display_name: str | None = None
    last_price: float | None = None
    open_price: float | None = None
    close_price: float | None = None
    day_high: float | None = None
    day_low: float | None = None
    last_price_at: datetime | None = None
    created_at: datetime


class MXWatchlistItem(BaseModel):
    symbol: str
    market: str
    market_short_name: str | None = None
    display_name: str
    last_price: float | None = None
    change_pct: float | None = None
    change_amount: float | None = None
    day_high: float | None = None
    day_low: float | None = None
    turnover_rate: float | None = None
    volume: float | None = None
    amount: float | None = None
    in_optional: bool | None = None


class MXWatchlistResponse(BaseModel):
    total_count: int
    items: list[MXWatchlistItem]


class SmartRecommendationItem(BaseModel):
    symbol: str
    market: str
    market_short_name: str | None = None
    display_name: str
    last_price: float | None = None
    change_pct: float | None = None
    day_high: float | None = None
    day_low: float | None = None
    turnover_rate: float | None = None
    volume: float | None = None
    amount: float | None = None
    industry: str | None = None
    concepts: str | None = None
    in_optional: bool | None = None


class SmartRecommendationResponse(BaseModel):
    keyword: str
    select_logic: str | None = None
    page_no: int
    page_size: int
    total_count: int
    items: list[SmartRecommendationItem]


class MXKlineItem(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None


class MXTrackerResponse(BaseModel):
    symbol: str
    market: str
    display_name: str
    quote: dict[str, Any]
    daily_kline: list[MXKlineItem]
    weekly_kline: list[MXKlineItem]
    monthly_kline: list[MXKlineItem]
    fundamentals: dict[str, Any]
    analysis_points: list[str]


class AnalysisRequest(BaseModel):
    symbol: str
    market: str = "a"
    lookback_period: str = Field(default="2y", min_length=2, max_length=16)
    bollinger_window: str = Field(default="20d", min_length=2, max_length=16)
    strategies: list[str] = Field(default_factory=lambda: ["bollinger_mean_reversion"])


class StrategyCatalogItem(BaseModel):
    key: str
    title: str
    description: str


class StrategyRunResult(BaseModel):
    key: str
    title: str
    payload: dict[str, Any]


class AnalysisRunResponse(BaseModel):
    symbol: str
    market: str
    lookback_period: str
    bollinger_window: str
    price_frequency: str = "daily"
    cached: bool = False
    results: list[StrategyRunResult]


class AnalysisHistoryItem(BaseModel):
    id: int
    symbol: str
    market: str
    strategy_key: str
    lookback_period: str = "2y"
    bollinger_window: str = "20d"
    price_frequency: str = "daily"
    request_payload: dict[str, Any] | None = None
    result_payload: dict[str, Any]
    created_at: datetime


class PolicyDisplayColumn(BaseModel):
    key: str
    label: str


class PolicyResultsOut(BaseModel):
    fields: dict[str, str]
    lists: list[dict[str, Any]]


class PolicyFileListItem(BaseModel):
    id: int
    name: str
    folder: str | None = None
    readme: str
    path: str
    results: str | None = None
    list_show_fields: list[str] = Field(default_factory=list)
    script_language: str
    script_filename: str
    readme_exists: bool = False
    results_exists: bool = False
    result_count: int = 0
    created_user_id: int
    created_user_name: str | None = None
    created_at: datetime
    updated_at: datetime
    can_edit: bool = False
    can_delete: bool = False
    results_format: str = "none"


class PolicyFileUpsert(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    folder: str | None = Field(default=None, max_length=255)
    readme: str = Field(min_length=1, max_length=255)
    path: str = Field(min_length=1, max_length=255)
    results: str | None = Field(default=None, max_length=255)
    list_show_fields: str = Field(default="", max_length=500)
    created_user_id: int | None = None


class PolicyFileDetail(PolicyFileListItem):
    readme_content: str | None = None
    results_data: PolicyResultsOut | None = None
    results_html_content: str | None = None
    list_display_columns: list[PolicyDisplayColumn] = Field(default_factory=list)
    detail_display_columns: list[PolicyDisplayColumn] = Field(default_factory=list)


TokenResponse.model_rebuild()
