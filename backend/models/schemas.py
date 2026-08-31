"""Pydantic 数据模型（请求/响应 Schema）—— 所有 API 路由的唯一模型来源。"""
from __future__ import annotations

import re
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator


# ==================== 股票搜索 ====================

class StockSearchResponse(BaseModel):
    """股票搜索响应。"""
    status: str = "ok"
    data: list[dict]


# ==================== 策略 ====================

class SaveStrategyRequest(BaseModel):
    """保存自定义策略请求。"""
    key: str
    code: str


# ==================== 数据管理 ====================

class FetchDataRequest(BaseModel):
    """下载数据请求。"""
    symbol: str = Field(..., description="股票代码，如 000001")
    start_date: str = Field(..., description="YYYYMMDD")
    end_date: str = Field(..., description="YYYYMMDD")
    period: str = Field("daily")

    @field_validator('start_date', 'end_date')
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        if not re.match(r'^\d{8}$', v):
            raise ValueError(f'日期格式必须为 YYYYMMDD（8位数字），当前值: {v}')
        return v


class RealtimeQuoteRequest(BaseModel):
    """实时行情请求。"""
    symbols: list[str] = Field(..., description="股票代码列表")


# ==================== 回测 ====================

class BacktestRequest(BaseModel):
    """预置策略回测请求。"""
    strategy: str = Field(..., description="策略 key，如 dual_ma")
    symbol: str = Field(..., description="股票代码，如 000001")
    start_date: str = Field(..., description="起始日期 YYYYMMDD")
    end_date: str = Field(..., description="结束日期 YYYYMMDD")
    params: dict = Field(default_factory=dict, description="策略参数")
    cash: float = Field(1_000_000, ge=10000, description="初始资金（最低 1 万）")
    commission: float = Field(0.0003, ge=0, le=0.1, description="佣金费率")
    slippage: float = Field(0.001, ge=0, le=0.1, description="滑点")
    period: str = Field("daily", description="K线周期")
    adjust: str = Field("qfq", description="复权方式: qfq前复权 / hfq后复权 / (空)不复权")

    @field_validator('start_date', 'end_date')
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        if not re.match(r'^\d{8}$', v):
            raise ValueError(f'日期格式必须为 YYYYMMDD（8位数字），当前值: {v}')
        return v

    @field_validator('symbol')
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        """清洗股票代码：去除 sh/sz 前缀和空白，仅保留数字。"""
        v = v.strip().lower().replace('sh', '').replace('sz', '')
        if not re.match(r'^\d{6}$', v):
            raise ValueError(f'股票代码必须为6位数字，当前值: {v}')
        return v

    @field_validator('adjust')
    @classmethod
    def validate_adjust(cls, v: str) -> str:
        """复权方式仅允许 qfq / hfq / 空字符串（不复权）。"""
        v = (v or "").strip().lower()
        if v not in ("qfq", "hfq", ""):
            raise ValueError(f'复权方式必须为 qfq / hfq / 空（不复权），当前值: {v}')
        return v


class BacktestCodeRequest(BaseModel):
    """自定义代码回测请求。"""
    code: str = Field(..., max_length=500000, description="策略 Python 代码")
    symbol: str = Field(..., description="股票代码，如 000001")
    start_date: str = Field(..., description="起始日期 YYYYMMDD")
    end_date: str = Field(..., description="结束日期 YYYYMMDD")
    cash: float = Field(1_000_000, ge=10000, description="初始资金（最低 1 万）")
    commission: float = Field(0.0003, ge=0, le=0.1, description="佣金费率")
    slippage: float = Field(0.001, ge=0, le=0.1, description="滑点")
    period: str = Field("daily", description="K线周期")
    adjust: str = Field("qfq", description="复权方式: qfq前复权 / hfq后复权 / (空)不复权")

    @field_validator('start_date', 'end_date')
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        if not re.match(r'^\d{8}$', v):
            raise ValueError(f'日期格式必须为 YYYYMMDD（8位数字），当前值: {v}')
        return v

    @field_validator('symbol')
    @classmethod
    def validate_symbol_code(cls, v: str) -> str:
        """清洗股票代码：去除 sh/sz 前缀和空白，仅保留数字。"""
        v = v.strip().lower().replace('sh', '').replace('sz', '')
        if not re.match(r'^\d{6}$', v):
            raise ValueError(f'股票代码必须为6位数字，当前值: {v}')
        return v


class CompareRequest(BaseModel):
    """策略比较请求。"""
    strategies: list[str] = Field(..., description="策略key列表")
    symbol: str = Field(..., description="股票代码")
    start_date: str = Field(..., description="起始日期 YYYYMMDD")
    end_date: str = Field(..., description="结束日期 YYYYMMDD")
    cash: float = Field(1_000_000, ge=10000, description="初始资金（最低 1 万）")
    commission: float = Field(0.0003, ge=0, le=0.1, description="佣金费率")
    slippage: float = Field(0.001, ge=0, le=0.1, description="滑点")
    period: str = Field("daily", description="K线周期")
    adjust: str = Field("qfq", description="复权方式: qfq前复权 / hfq后复权 / (空)不复权")

    @field_validator('start_date', 'end_date')
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        if not re.match(r'^\d{8}$', v):
            raise ValueError(f'日期格式必须为 YYYYMMDD（8位数字），当前值: {v}')
        return v

    @field_validator('symbol')
    @classmethod
    def validate_symbol_compare(cls, v: str) -> str:
        """清洗股票代码：去除 sh/sz 前缀和空白，仅保留数字。"""
        v = v.strip().lower().replace('sh', '').replace('sz', '')
        if not re.match(r'^\d{6}$', v):
            raise ValueError(f'股票代码必须为6位数字，当前值: {v}')
        return v


# ==================== 参数优化 ====================

class OptimizeRequest(BaseModel):
    """参数优化请求。"""
    symbol: str = Field(..., description="股票代码")
    strategy: str = Field(..., description="策略key")
    start_date: str = Field(..., description="开始日期")
    end_date: str = Field(..., description="结束日期")
    param_grid: dict[str, list[Any]] = Field(..., description="参数网格")
    cash: float = Field(1_000_000, ge=10000, description="初始资金")
    commission: float = Field(0.0003, ge=0, le=0.1, description="手续费率")
    slippage: float = Field(0.001, ge=0, le=0.1, description="滑点")
    metric: str = Field("sharpe_ratio", description="优化目标")

    @field_validator('start_date', 'end_date')
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        if not re.match(r'^\d{8}$', v):
            raise ValueError(f'日期格式必须为 YYYYMMDD（8位数字），当前值: {v}')
        return v


class OptimizeResultItem(BaseModel):
    """参数优化结果单项。"""
    params: dict[str, Any]
    metric_value: float
    total_return: float
    annual_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    total_trades: int


class OptimizeResponse(BaseModel):
    """参数优化响应。"""
    status: str = "ok"
    data: list[OptimizeResultItem]
    best_params: Optional[dict[str, Any]] = None
    best_metric_value: Optional[float] = None


# ==================== 交易 ====================

class PlaceOrderRequest(BaseModel):
    """下单请求。"""
    symbol: str = Field(..., description="股票代码")
    action: str = Field(..., description="操作类型: buy/sell")
    quantity: int = Field(..., ge=1, description="数量")
    price: float = Field(..., gt=0, description="价格")

    @field_validator('action')
    @classmethod
    def validate_action(cls, v: str) -> str:
        if v.lower() not in ('buy', 'sell'):
            raise ValueError('操作类型必须为 buy 或 sell')
        return v.lower()

    @field_validator('symbol')
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        """清洗股票代码：去除 sh/sz 前缀和空白，仅保留数字。"""
        v = v.strip().lower().replace('sh', '').replace('sz', '')
        if not re.match(r'^\d{6}$', v):
            raise ValueError(f'股票代码必须为6位数字，当前值: {v}')
        return v


class ResetAccountRequest(BaseModel):
    """重置账户请求。"""
    initial_cash: float = Field(1000000.0, description="初始资金")


# ==================== 选股扫描 ====================

class StockScanRequest(BaseModel):
    """选股扫描请求。"""
    strategy_type: str = Field(..., description="策略类型 key")
    strategy_params: dict = Field(default_factory=dict, description="策略参数")
    stock_range: str = Field("all", description="扫描范围: all/hs300/zz500/custom")
    custom_stocks: list[str] = Field(default_factory=list, description="自定义股票列表")
    scan_date: Optional[str] = Field(None, description="扫描日期 YYYYMMDD（单日模式，优先用于推导回测终点）")
    start_date: Optional[str] = Field(None, description="扫描区间起点 YYYYMMDD（区间模式）")
    end_date: Optional[str] = Field(None, description="扫描区间终点 YYYYMMDD（区间模式）")
    max_stocks: int = Field(0, description="最多扫描股票数，0 表示扫描范围内全部股票（不限制）")
    prepare_first: bool = Field(True, description="扫描前先批量下载时间范围内全部股票数据到本地缓存（默认开启，避免扫描时并发联网导致崩溃）")
    prepare_only: bool = Field(False, description="仅预热数据、不执行扫描（用于提前缓存数据）")


class StockScanResult(BaseModel):
    """单只股票扫描结果。"""
    symbol: str
    name: str
    price: float = 0
    change_pct: float = 0
    signal_strength: float = 0
    signal_detail: dict = Field(default_factory=dict)
    sector: str = "未知"
    market_cap: float = 0


class StockScanResponse(BaseModel):
    """选股扫描响应。"""
    status: str = "ok"
    scan_date: str = ""
    strategy_name: str = ""
    total_scanned: int = 0
    total_matched: int = 0
    results: list[dict] = []


class DataPrepareRequest(BaseModel):
    """批量缓存数据请求（扫描前的「数据准备」独立入口）。"""
    stock_range: str = Field("all", description="缓存范围: all/hs300/zz500/custom")
    custom_stocks: list[str] = Field(default_factory=list, description="自定义股票列表")
    start_date: str = Field(..., description="数据起点 YYYYMMDD")
    end_date: str = Field(..., description="数据终点 YYYYMMDD")
    period: str = Field("daily", description="K线周期: daily/weekly/monthly")
    max_stocks: int = Field(0, description="最多缓存股票数，0 表示范围内全部")


class WatchlistItem(BaseModel):
    """自选池股票项。"""
    symbol: str
    name: str = ""
    added_at: str = ""
    added_price: float = 0
    notes: str = ""


# ==================== 导出 ====================

class ExportRequest(BaseModel):
    """通用导出请求。"""
    data: dict
    format: str = "json"
    filename: str = "export"


class ExportJsonRequest(BaseModel):
    """JSON 导出请求。"""
    result: dict


class ExportCsvRequest(BaseModel):
    """CSV 导出请求。"""
    trades: list[dict]
