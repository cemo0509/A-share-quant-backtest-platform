"""因子选股引擎：对本地 K 线数据按可视化条件（VisualRule）做向量化筛选。

与 codegen 的根本区别：
- codegen 把条件编译成 backtrader 策略代码，再跑完整回测（慢，每股一次回测）。
- 本模块直接对 pandas DataFrame 计算指标并做布尔判断（不跑回测），
  配合本地 parquet 缓存与线程池并发，做到「改条件秒级刷新」。

数据约定：fetch_kline 返回 [date, open, high, low, close, volume, amount]；
mock 数据（df.attrs['is_mock']）一律跳过——随机行情筛出的股票毫无参考价值。
"""
from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Optional

import numpy as np
import pandas as pd

from core.data_loader import fetch_kline
from data.stock_names import get_stock_name, get_stock_sector

logger = logging.getLogger("screener")


# ==================== 指标计算（pandas 向量化） ====================

def _ma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(int(n)).mean()


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=int(n), adjust=False).mean()


def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0).rolling(int(n)).mean()
    down = (-delta.clip(upper=0)).rolling(int(n)).mean()
    rs = up / down.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def _macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    dif = _ema(close, fast) - _ema(close, slow)
    dea = dif.ewm(span=int(signal), adjust=False).mean()
    histo = (dif - dea) * 2
    return dif, dea, histo


def _kdj(df: pd.DataFrame, period: int = 9, k: int = 3, d: int = 3):
    low_n = df["low"].rolling(int(period)).min()
    high_n = df["high"].rolling(int(period)).max()
    rsv = (df["close"] - low_n) / (high_n - low_n).replace(0, np.nan) * 100
    K = rsv.ewm(com=max(int(k) - 1, 0), adjust=False).mean()
    D = K.ewm(com=max(int(d) - 1, 0), adjust=False).mean()
    J = 3 * K - 2 * D
    return K, D, J


def _boll(close: pd.Series, n: int = 20, dev: float = 2.0):
    mid = close.rolling(int(n)).mean()
    std = close.rolling(int(n)).std()
    return mid + dev * std, mid, mid - dev * std  # upper, mid, lower


def _cci(df: pd.DataFrame, n: int = 14) -> pd.Series:
    tp = (df["high"] + df["low"] + df["close"]) / 3
    ma = tp.rolling(int(n)).mean()
    md = tp.rolling(int(n)).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    return (tp - ma) / (0.015 * md.replace(0, np.nan))


def _wr(df: pd.DataFrame, n: int = 10) -> pd.Series:
    hn = df["high"].rolling(int(n)).max()
    ln = df["low"].rolling(int(n)).min()
    return (hn - df["close"]) / (hn - ln).replace(0, np.nan) * 100


def _bias(close: pd.Series, n: int = 6) -> pd.Series:
    ma = _ma(close, n)
    return (close - ma) / ma.replace(0, np.nan) * 100


def _obv(df: pd.DataFrame) -> pd.Series:
    direction = np.sign(df["close"].diff().fillna(0))
    return (direction * df["volume"]).cumsum()


# ==================== 指标 -> 具体某条线的 Series ====================

def _indicator_series(df: pd.DataFrame, leaf: dict) -> pd.Series:
    ind = leaf.get("indicator", "")
    line = leaf.get("line", "")
    params = leaf.get("params") or {}

    def pi(k: str, d: int) -> int:
        try:
            return int(params.get(k, d))
        except Exception:
            return d

    def pf(k: str, d: float) -> float:
        try:
            return float(params.get(k, d))
        except Exception:
            return d

    close = df["close"]

    if ind == "ma":
        return _ma(close, pi("period", 5))
    if ind == "ema":
        return _ema(close, pi("period", 12))
    if ind in ("macd", "macd_cross"):
        dif, dea, histo = _macd(close, pi("fast", 12), pi("slow", 26), pi("signal", 9))
        m = {
            "dif": dif, "dea": dea, "histo": histo, "macd": histo,
            # 金叉/死叉线：用 DIF 与 DEA 的相对关系表示（>0 金叉区，<0 死叉区）
            "gold": (dif - dea), "death": (dif - dea),
            "dif_gold": (dif - dea), "dif_death": (dif - dea),
        }
        return m.get(line, dif)
    if ind == "rsi":
        return _rsi(close, pi("period", 14))
    if ind == "cci":
        return _cci(df, pi("period", 14))
    if ind in ("kdj", "kdj_bull"):
        K, D, J = _kdj(df, pi("period", 9), pi("smooth_k", 3), pi("smooth_d", 3))
        m = {"k": K, "d": D, "j": J, "gold": (K - D), "death": (K - D)}
        return m.get(line, K)
    if ind == "boll":
        u, m, l = _boll(close, pi("period", 20), pf("dev", 2.0))
        return {"boll_upper": u, "boll_mid": m, "boll_lower": l}.get(line, m)
    if ind == "wr":
        return _wr(df, pi("period", 10))
    if ind == "bias":
        return _bias(close, pi("period", 6))
    if ind == "obv":
        return _obv(df)
    if ind == "vol":
        # line=ma 时为均量线，否则当日成交量
        if line == "ma":
            return _ma(df["volume"], pi("period", 5))
        return df["volume"]
    if ind == "vol_ratio":
        n = pi("period", 5)
        return df["volume"] / _ma(df["volume"], n).replace(0, np.nan)
    if ind == "amt":
        return close * df["volume"]
    if ind == "turnover":
        # 近似：成交量 / 均量 × 100（无流通股本数据）
        n = pi("period", 5)
        return df["volume"] / _ma(df["volume"], n).replace(0, np.nan) * 100
    if ind == "price":
        return {"close": close, "open": df["open"], "high": df["high"], "low": df["low"]}.get(line, close)
    if ind == "high_low_range":
        prev = close.shift(1)
        return (df["high"] - df["low"]) / prev.replace(0, np.nan) * 100
    if ind == "rise_rate":
        prev = close.shift(1)
        return (close - prev) / prev.replace(0, np.nan) * 100
    if ind == "new_high":
        return df["high"].rolling(pi("period", 20)).max()
    if ind == "new_low":
        return df["low"].rolling(pi("period", 20)).min()
    if ind == "ma_arrangement":
        f = _ma(close, pi("fast", 5))
        m = _ma(close, pi("mid", 10))
        s = _ma(close, pi("slow", 20))
        # bull: f>m>s 输出 1 否则 0；bear: f<m<s
        if line == "bear":
            return ((f < m) & (m < s)).astype(float)
        return ((f > m) & (m > s)).astype(float)

    raise ValueError(f"不支持的指标「{ind}」")


# ==================== 对照指标（targetType=indicator） ====================

def _parse_target_indicator(df: pd.DataFrame, leaf: dict) -> pd.Series:
    """解析对照指标标识（如 ma20 / boll_upper / dea），返回对应 Series。"""
    target = (leaf.get("targetIndicator") or "").strip()
    line = leaf.get("targetLine") or ""

    # 直接是已知名称（boll_upper / dif / dea / k / d 等）
    if target in ("boll_upper", "boll_mid", "boll_lower"):
        u, m, l = _boll(df["close"], 20, 2.0)
        return {"boll_upper": u, "boll_mid": m, "boll_lower": l}[target]

    # 形如 ma20 / ema12 / ma / ema
    m = re.match(r"^(ma|ema)(\d+)?$", target)
    if m:
        kind, n = m.group(1), int(m.group(2) or 5)
        return _ma(df["close"], n) if kind == "ma" else _ema(df["close"], n)

    # 兜底：当成某个指标 key，用通用计算
    try:
        return _indicator_series(df, {"indicator": target, "line": line, "params": leaf.get("params") or {}})
    except Exception:
        raise ValueError(f"无法解析对照指标「{target}」")


# ==================== 目标值 ====================

def _target_value(df: pd.DataFrame, leaf: dict):
    ttype = leaf.get("targetType", "value")
    if ttype == "price":
        return df["close"]
    if ttype == "indicator":
        return _parse_target_indicator(df, leaf)
    try:
        return float(leaf.get("targetValue") or 0)
    except Exception:
        return 0.0


# ==================== 比较（返回布尔 Series） ====================

def _compare(series: pd.Series, operator: str, target, leaf: dict) -> pd.Series:
    if operator == "greater":
        return series > target
    if operator == "less":
        return series < target
    if operator == "greater_equal":
        return series >= target
    if operator == "less_equal":
        return series <= target
    if operator == "equal":
        return series == target
    if operator == "between":
        low = float(leaf.get("targetValue") or 0)
        high = float(leaf.get("targetParam2") or 0)
        return (series >= low) & (series <= high)
    if operator in ("cross_up", "cross_down"):
        # 目标若是常数，构造同索引常数 Series 以便 shift 比较
        if hasattr(target, "shift"):
            t = target
        else:
            t = pd.Series([target] * len(series), index=series.index)
        prev_s, prev_t = series.shift(1), t.shift(1)
        if operator == "cross_up":
            return (series > t) & (prev_s <= prev_t)
        return (series < t) & (prev_s >= prev_t)
    raise ValueError(f"不支持的运算符「{operator}」")


# ==================== 单叶子求值（最后一个交易日是否满足） ====================

def evaluate_leaf(df: pd.DataFrame, leaf: dict) -> bool:
    """对单只股票的 K 线，求一个叶子条件在**最后一个交易日**是否成立。

    任何指标/运算符不支持都视为「该股票不满足」，但记录原因（A-01 同款原则：
    不能让无法计算的条件静默变成「恒真」，否则会把随机股票当成符合条件返回）。
    """
    series = _indicator_series(df, leaf)
    target = _target_value(df, leaf)
    cond = _compare(series, leaf.get("operator", "greater"), target, leaf)
    valid = cond.dropna()
    if valid.empty:
        return False
    return bool(valid.iloc[-1])


# ==================== 主筛选入口 ====================

def _strip_prefix(symbol: str) -> str:
    return symbol.replace("sh", "").replace("sz", "").replace("SH", "").replace("SZ", "")


def screen_symbols(
    symbols: list[str],
    leaves: list[dict],
    start_date: str,
    end_date: str,
    max_workers: int = 8,
    on_progress=None,
    cancel_event=None,
) -> list[dict]:
    """对一批股票按叶子条件（AND）筛选，返回符合的股票列表。

    每只股票：加载本地缓存 K 线（未命中才联网）→ 计算各叶子 → 全部满足才入选。
    mock 数据与计算异常的股票一律跳过（宁缺毋滥，不返回噪声）。
    """
    results: list[dict] = []
    total = len(symbols)
    scanned = 0

    def _one(symbol: str) -> Optional[dict]:
        if cancel_event is not None and cancel_event.is_set():
            return None
        code = _strip_prefix(symbol)
        try:
            df = fetch_kline(code, start_date, end_date, period="daily")
        except Exception as e:
            logger.debug(f"拉取 {symbol} K线失败: {e}")
            return None
        if df is None or df.empty:
            return None
        if df.attrs.get("is_mock"):
            # 模拟数据（真实行情获取失败的随机兜底）绝不能产生选股结果
            return None
        try:
            if all(evaluate_leaf(df, leaf) for leaf in leaves):
                close = float(df["close"].iloc[-1])
                prev = float(df["close"].iloc[-2]) if len(df) >= 2 else close
                return {
                    "symbol": symbol,
                    "name": get_stock_name(symbol),
                    "price": round(close, 2),
                    "change_pct": round((close - prev) / prev * 100, 2) if prev else 0,
                    "sector": get_stock_sector(symbol),
                    "signal_strength": 1.0,
                    "market_cap": 0,
                }
        except Exception as e:
            logger.debug(f"筛选 {symbol} 异常: {e}")
        return None

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_one, s): s for s in symbols}
        for fut in as_completed(futures):
            scanned += 1
            try:
                item = fut.result()
                if item:
                    results.append(item)
            except Exception:
                pass
            if on_progress:
                try:
                    on_progress(scanned, total, len(results))
                except Exception:
                    pass
            if cancel_event is not None and cancel_event.is_set():
                break

    # 稳定排序：按代码
    results.sort(key=lambda x: x["symbol"])
    return results
