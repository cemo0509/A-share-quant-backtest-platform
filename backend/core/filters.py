"""选股前置过滤器（CCI+MACD 选股需求新增）。

提供：
- 停牌过滤（无实时数据或成交量为0）
- ST/*ST 过滤（名称含 ST）
- 成交额过滤（当日成交额 >= 阈值）

依赖 akshare 全市场实时快照 stock_zh_a_spot_em()，带内存缓存避免频繁请求。
网络不可用时降级为空快照（此时过滤器放行，交由下游指标计算判断）。
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

import pandas as pd

logger = logging.getLogger("filters")

# 全市场实时快照缓存
_SPOT_CACHE: dict = {"ts": 0.0, "df": None}
_SPOT_CACHE_TTL = 30  # 快照缓存 30 秒
_SPOT_CACHE_LOCK = threading.Lock()


def get_spot_snapshot(force_refresh: bool = False) -> pd.DataFrame:
    """获取全市场实时快照（带缓存）。

    Returns:
        DataFrame，列含 代码/名称/成交量/成交额 等；失败返回空 DataFrame。
    """
    now = time.time()
    with _SPOT_CACHE_LOCK:
        if (not force_refresh
                and _SPOT_CACHE["df"] is not None
                and now - _SPOT_CACHE["ts"] < _SPOT_CACHE_TTL):
            return _SPOT_CACHE["df"]

    df = pd.DataFrame()
    try:
        import core.datasource as datasource
        df = datasource.fetch_spot_snapshot()
    except Exception as e:
        logger.warning(f"获取全市场实时快照失败: {e}，返回空快照（过滤器放行）")
        df = pd.DataFrame()

    with _SPOT_CACHE_LOCK:
        _SPOT_CACHE["ts"] = now
        _SPOT_CACHE["df"] = df

    return df


def _normalize_code(symbol: str) -> str:
    """去除市场前缀，返回纯数字代码。"""
    return symbol.replace("sh", "").replace("sz", "").replace("SH", "").replace("SZ", "")


def is_st(name: str) -> bool:
    """判断是否为 ST/*ST 股（名称含 ST）。"""
    if not name:
        return False
    return "ST" in str(name).upper()


def is_suspended(symbol: str, spot_df: Optional[pd.DataFrame] = None) -> bool:
    """判断是否停牌：快照中无该股或成交量为 0。

    快照为空时返回 False（放行，不误杀）。
    """
    if spot_df is None:
        spot_df = get_spot_snapshot()
    if spot_df is None or spot_df.empty or "代码" not in spot_df.columns:
        return False
    code = _normalize_code(symbol)
    row = spot_df[spot_df["代码"] == code]
    if row.empty:
        return True
    try:
        vol = float(row["成交量"].iloc[0] or 0)
        return vol == 0
    except Exception:
        return False


def amount_ok(symbol: str, spot_df: Optional[pd.DataFrame] = None, min_amount: float = 5e8) -> bool:
    """成交额过滤：当日成交额 >= min_amount（元）。

    快照为空时返回 True（放行，不误杀）。
    """
    if spot_df is None:
        spot_df = get_spot_snapshot()
    if spot_df is None or spot_df.empty or "代码" not in spot_df.columns:
        return True
    code = _normalize_code(symbol)
    row = spot_df[spot_df["代码"] == code]
    if row.empty:
        return False
    try:
        amt = float(row["成交额"].iloc[0] or 0)
        return amt >= min_amount
    except Exception:
        return True


def get_name_from_spot(symbol: str, spot_df: Optional[pd.DataFrame] = None) -> str:
    """从快照获取股票名称（用于 ST 判断和展示）。"""
    if spot_df is None:
        spot_df = get_spot_snapshot()
    if spot_df is None or spot_df.empty or "代码" not in spot_df.columns:
        return ""
    code = _normalize_code(symbol)
    row = spot_df[spot_df["代码"] == code]
    if row.empty or "名称" not in spot_df.columns:
        return ""
    try:
        return str(row["名称"].iloc[0])
    except Exception:
        return ""


def passes_prefilter(
    symbol: str,
    name: str = "",
    spot_df: Optional[pd.DataFrame] = None,
    min_amount: float = 5e8,
    exclude_st: bool = True,
    exclude_suspended: bool = True,
) -> tuple[bool, str]:
    """综合前置过滤：停牌 / ST / 成交额。

    Returns:
        (是否通过, 未通过原因)
    """
    if spot_df is None:
        spot_df = get_spot_snapshot()

    # 名称优先用传入的，其次从快照取
    real_name = name or get_name_from_spot(symbol, spot_df)

    if exclude_st and is_st(real_name):
        return False, "ST股"
    if exclude_suspended and is_suspended(symbol, spot_df):
        return False, "停牌"
    if not amount_ok(symbol, spot_df, min_amount):
        return False, f"成交额<{min_amount/1e8:.1f}亿"

    return True, ""
