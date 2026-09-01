"""回测基准对比模块（P0-10）。

解决的问题：
    一个策略回测出「年化 20%」，如果同期买入持有是 25%，那这个策略是失败的。
    但没有基准时，平台只告诉你 20%，不告诉你 25%——
    **没有基准的收益数字，和随机数没有区别。**

提供两条基准：
    1. 买入持有（Buy & Hold）：同一标的，首个交易日买入并持有到最后
    2. 沪深300：同期大盘指数收益（代表「什么都不做，买指数」的机会成本）

并计算**超额收益**（策略 − 基准），这是判断策略好坏最直接的指标。

设计原则：
    - 基准计算失败**绝不能**导致回测失败（网络不可用时降级为 None）
    - 与策略使用同一份 K 线数据，保证口径一致
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Optional

import pandas as pd

logger = logging.getLogger("benchmark")

# 沪深300 指数代码（用于 akshare 指数接口）
HS300_CODE = "000300"


def _max_drawdown(values: list[float]) -> float:
    """从资金序列计算最大回撤（百分比）。"""
    if not values:
        return 0.0
    peak = values[0]
    max_dd = 0.0
    for v in values:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (peak - v) / peak * 100
            if dd > max_dd:
                max_dd = dd
    return max_dd


def _annual_return(total_return_pct: float, days: float) -> float:
    """按实际天数年化收益（与 analyzers._years_from_data 口径一致）。"""
    if days <= 0:
        return 0.0
    years = days / 365.0
    if years <= 0:
        return 0.0
    growth = 1 + total_return_pct / 100.0
    if growth <= 0:
        return -100.0
    return (growth ** (1 / years) - 1) * 100


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def calc_buy_hold(
    df: pd.DataFrame,
    cash: float = 1_000_000,
    commission: float = 0.0003,
    slippage: float = 0.001,
) -> Optional[dict]:
    """买入持有基准：首个交易日按收盘价买入并持有到最后。

    使用与策略**同一份** K 线数据，确保价格口径一致（同样的复权方式）。

    Args:
        df: 策略回测用的 K 线（含 date/open/high/low/close）
        cash: 初始资金（与策略一致）
        commission: 佣金费率（用于计算买入成本）
        slippage: 滑点

    Returns:
        基准结果 dict（含 total_return / annual_return / max_drawdown /
        equity_curve），数据不足时返回 None
    """
    if df is None or df.empty or "close" not in df.columns or len(df) < 2:
        return None

    try:
        closes = df["close"].astype(float).tolist()
        dates = df["date"]

        entry_price = closes[0] * (1 + slippage)
        if entry_price <= 0:
            return None

        # 与策略同样按 95% 资金、取整到 100 股买入
        shares = int(cash * 0.95 / entry_price) // 100 * 100
        if shares <= 0:
            return None

        cost = shares * entry_price
        comm = max(cost * commission, 5.0)  # 最低 5 元佣金
        cash_left = cash - cost - comm

        equity_curve = []
        for i, c in enumerate(closes):
            equity_curve.append({
                "date": str(dates.iloc[i].date()) if hasattr(dates.iloc[i], "date") else str(dates.iloc[i]),
                "value": round(cash_left + shares * c, 2),
            })

        values = [p["value"] for p in equity_curve]
        final_value = values[-1]
        total_return = (final_value - cash) / cash * 100

        # 实际跨越天数（用于年化）
        try:
            d0 = pd.to_datetime(dates.iloc[0])
            d1 = pd.to_datetime(dates.iloc[-1])
            days = max((d1 - d0).days, 1)
        except Exception:
            days = max(len(closes) - 1, 1)

        return {
            "name": "买入持有",
            "key": "buy_hold",
            "total_return": round(total_return, 2),
            "annual_return": round(_annual_return(total_return, days), 2),
            "max_drawdown": round(_max_drawdown(values), 2),
            "shares": int(shares),
            "entry_price": round(float(closes[0]), 3),
            "exit_price": round(float(closes[-1]), 3),
            "equity_curve": equity_curve,
        }
    except Exception as e:
        logger.warning(f"买入持有基准计算失败: {e}")
        return None


# 指数数据缓存文件（避免每次回测都联网拉指数）
_INDEX_CACHE_FILE = "benchmark_hs300.parquet"
# 拉取失败后的冷却时间（秒）：离线时不要每次回测都等网络超时
_INDEX_FAIL_COOLDOWN = 600.0
_index_fail_until = 0.0


def _index_cache_path() -> Optional[Path]:
    try:
        from core.data_loader import CACHE_DIR

        return CACHE_DIR / _INDEX_CACHE_FILE
    except Exception:
        return None


def _load_index_cache() -> Optional[pd.DataFrame]:
    """读取指数缓存（不存在则返回 None）。"""
    p = _index_cache_path()
    if p is None or not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
        df["date"] = pd.to_datetime(df["date"])
        return df
    except Exception:
        return None


def _save_index_cache(df: pd.DataFrame) -> None:
    p = _index_cache_path()
    if p is None or df is None or df.empty:
        return
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(p, index=False)
    except Exception:
        pass


def calc_index_benchmark(
    start_date: str,
    end_date: str,
    cash: float = 1_000_000,
    code: str = HS300_CODE,
    name: str = "沪深300",
) -> Optional[dict]:
    """指数基准（默认沪深300）：同期「买大盘」的收益。

    两层保护，确保不拖慢回测：
    1. **缓存**：指数历史拉一次就缓存，后续回测直接读本地（指数数据不会变）
    2. **失败冷却**：离线时拉一次失败后 10 分钟内不再重试，
       避免每次回测都卡在网络超时上

    网络不可用时返回 None，绝不抛异常——基准是锦上添花，
    不能因为拉不到指数就让整个回测失败。
    """
    global _index_fail_until

    # 冷却期内直接跳过（离线场景的关键优化）
    if time.time() < _index_fail_until:
        return None

    raw = None
    try:
        import akshare as ak

        # 优先用缓存；缓存缺失才联网
        cached = _load_index_cache()
        if cached is not None and not cached.empty:
            raw = cached
        else:
            raw = ak.index_zh_a_hist(
                symbol=code, period="daily",
                start_date="19900101",  # 拉全量，便于后续复用
                end_date=end_date,
            )
            if raw is not None and not raw.empty:
                # 统一列名后落缓存
                _cmap = {"日期": "date", "开盘": "open", "收盘": "close",
                         "最高": "high", "最低": "low"}
                to_save = raw.rename(columns=_cmap)
                if "date" in to_save.columns and "close" in to_save.columns:
                    to_save = to_save[["date", "open", "high", "low", "close"]].copy()
                    to_save["date"] = pd.to_datetime(to_save["date"])
                    _save_index_cache(to_save)
                    raw = to_save

        if raw is None or raw.empty:
            return None

        # 按回测区间过滤
        s = pd.to_datetime(start_date)
        e = pd.to_datetime(end_date)
        if "date" in raw.columns:
            rd = pd.to_datetime(raw["date"])
            mask = (rd >= s) & (rd <= e)
            filtered = raw.loc[mask]
            if not filtered.empty:
                raw = filtered
    except Exception as e:
        # 任何失败都进入冷却，避免反复等待超时
        _index_fail_until = time.time() + _INDEX_FAIL_COOLDOWN
        logger.warning(
            f"{name}基准获取失败，{int(_INDEX_FAIL_COOLDOWN / 60)} 分钟内不再重试"
            f"（不影响回测）: {e}"
        )
        return None

    try:
        if raw is None or raw.empty:
            return None

        # akshare 指数接口返回中文字段
        col_map = {"日期": "date", "开盘": "open", "收盘": "close",
                   "最高": "high", "最低": "low"}
        renamed = raw.rename(columns=col_map)
        if "close" not in renamed.columns or "date" not in renamed.columns:
            return None

        closes = renamed["close"].astype(float).tolist()
        dates = renamed["date"]
        if len(closes) < 2:
            return None

        # 指数不可交易，直接用涨跌幅折算到初始资金
        total_return = (closes[-1] - closes[0]) / closes[0] * 100

        equity_curve = []
        base = closes[0]
        for i, c in enumerate(closes):
            equity_curve.append({
                "date": str(dates.iloc[i]),
                "value": round(cash * (c / base), 2),
            })

        values = [p["value"] for p in equity_curve]
        try:
            d0 = pd.to_datetime(dates.iloc[0])
            d1 = pd.to_datetime(dates.iloc[-1])
            days = max((d1 - d0).days, 1)
        except Exception:
            days = max(len(closes) - 1, 1)

        return {
            "name": name,
            "key": "hs300",
            "total_return": round(total_return, 2),
            "annual_return": round(_annual_return(total_return, days), 2),
            "max_drawdown": round(_max_drawdown(values), 2),
            "shares": 0,
            "entry_price": round(closes[0], 3),
            "exit_price": round(closes[-1], 3),
            "equity_curve": equity_curve,
        }
    except Exception as e:
        logger.warning(f"{name}基准计算失败（不影响回测）: {e}")
        return None


def compute_benchmarks(
    df: pd.DataFrame,
    start_date: str,
    end_date: str,
    cash: float = 1_000_000,
    commission: float = 0.0003,
    slippage: float = 0.001,
    strategy_total_return: Optional[float] = None,
) -> dict:
    """计算全部基准并汇总超额收益。

    Args:
        df: 策略回测用的 K 线数据
        start_date / end_date: 回测区间 YYYYMMDD
        cash / commission / slippage: 与策略一致的参数
        strategy_total_return: 策略总收益率（%，用于算超额）

    Returns:
        {
          "buy_hold": {...} | None,
          "hs300":    {...} | None,
          "excess_vs_buy_hold": float | None,   # 策略 − 买入持有
          "excess_vs_hs300":   float | None,
        }
    """
    buy_hold = calc_buy_hold(df, cash=cash, commission=commission, slippage=slippage)
    hs300 = calc_index_benchmark(start_date, end_date, cash=cash)

    result: dict[str, Any] = {
        "buy_hold": buy_hold,
        "hs300": hs300,
        "excess_vs_buy_hold": None,
        "excess_vs_hs300": None,
    }

    if strategy_total_return is None:
        return result

    if buy_hold is not None:
        result["excess_vs_buy_hold"] = round(
            strategy_total_return - buy_hold["total_return"], 2
        )
    if hs300 is not None:
        result["excess_vs_hs300"] = round(
            strategy_total_return - hs300["total_return"], 2
        )

    return result
