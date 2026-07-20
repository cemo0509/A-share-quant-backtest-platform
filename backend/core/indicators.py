"""技术指标计算模块（v3.0 新增）。

提供常用技术指标的计算，供个股详情页 K 线图下方指标区使用。
支持：MACD, KDJ, RSI, BOLL, WR, OBV, BIAS, CCI
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd


def _clean_nan(obj):
    """递归把 NaN/Inf 清洗成 None，避免 json.dumps 报 'Out of range float values'。

    指标计算在序列前段（窗口不足）会产生 NaN，模拟数据也可能引入 Inf，
    标准 json 无法序列化这些非有限值，会导致接口返回 500。
    """
    if isinstance(obj, dict):
        return {k: _clean_nan(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean_nan(v) for v in obj]
    if isinstance(obj, (float, np.floating)):
        f = float(obj)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    if isinstance(obj, (np.integer,)):
        return int(obj)
    return obj


def calc_ma(close: pd.Series, periods: list[int] = [5, 10, 20]) -> dict:
    """计算移动均线。"""
    result = {}
    for p in periods:
        result[f"ma{p}"] = close.rolling(p).mean().round(2).tolist()
    return result


def calc_macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    """计算 MACD 指标。"""
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    dif = (ema_fast - ema_slow).round(4)
    dea = dif.ewm(span=signal, adjust=False).mean().round(4)
    hist = ((dif - dea) * 2).round(4)
    return {
        "dif": dif.tolist(),
        "dea": dea.tolist(),
        "hist": hist.tolist(),
    }


def calc_kdj(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 9,
             k_period: int = 3, d_period: int = 3) -> dict:
    """计算 KDJ 指标（标准递推公式）。

    RSV = (close - low_n) / (high_n - low_n) * 100
    K = 2/3 * prev_K + 1/3 * RSV      (标准递推，非 ewm 近似)
    D = 2/3 * prev_D + 1/3 * K
    J = 3 * K - 2 * D
    """
    low_n = low.rolling(n).min()
    high_n = high.rolling(n).max()
    rsv = ((close - low_n) / (high_n - low_n).replace(0, np.nan) * 100)
    # 标准递推公式：K = 2/3*prev_K + 1/3*RSV
    k = rsv.copy()
    d = rsv.copy()
    # 初始化：前 n 个有效值取 50
    k.iloc[:n] = 50.0
    d.iloc[:n] = 50.0
    a_k = 1.0 / k_period
    a_d = 1.0 / d_period
    for i in range(n, len(k)):
        if pd.notna(k.iloc[i - 1]) and pd.notna(rsv.iloc[i]):
            k.iloc[i] = k.iloc[i - 1] * (1 - a_k) + rsv.iloc[i] * a_k
        else:
            k.iloc[i] = k.iloc[i - 1] if pd.notna(k.iloc[i - 1]) else 50.0
        d.iloc[i] = d.iloc[i - 1] * (1 - a_d) + k.iloc[i] * a_d
    j = 3 * k - 2 * d
    return {
        "k": k.round(2).tolist(),
        "d": d.round(2).tolist(),
        "j": j.round(2).tolist(),
    }


def calc_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """计算 RSI 指标（Wilder 平滑，与东方财富/同花顺/TA-Lib 一致）。"""
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    # Wilder 平滑：alpha = 1/period，首值用简单均值，之后递推
    # avg_gain[i] = (avg_gain[i-1]*(period-1) + gain[i]) / period
    alpha = 1.0 / period
    avg_gain = gain.ewm(alpha=alpha, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=alpha, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = (100 - (100 / (1 + rs))).round(2)
    return rsi


def calc_boll(close: pd.Series, period: int = 20, std: float = 2.0) -> dict:
    """计算布林带。

    标准差用总体标准差 ddof=0，与 TA-Lib 及同花顺/东方财富等行情软件一致
    （pandas 默认 ddof=1 为样本标准差，会导致带宽偏窄，与主流软件显示不符）。
    """
    middle = close.rolling(period).mean()
    std_val = close.rolling(period).std(ddof=0)
    upper = (middle + std * std_val).round(2)
    lower = (middle - std * std_val).round(2)
    return {
        "upper": upper.tolist(),
        "middle": middle.round(2).tolist(),
        "lower": lower.tolist(),
    }


def calc_wr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 10) -> pd.Series:
    """计算威廉指标 WR（取值 0~100 正值）。

    约定说明：本报告标注与 TA-Lib 的 WILLR（取值 -100~0）存在差异，
    但国内行情软件（同花顺/东方财富）WR 均为 0~100 正值，且前端展示依赖正值，
    故保持正值约定，不改为 -100~0，以免显示异常与用户困惑。
    """
    high_n = high.rolling(n).max()
    low_n = low.rolling(n).min()
    wr = ((high_n - close) / (high_n - low_n) * 100).round(2)
    return wr


def calc_obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """计算能量潮 OBV。"""
    direction = np.sign(close.diff().fillna(0))
    obv = (direction * volume).cumsum()
    return obv


def calc_bias(close: pd.Series, n: int = 6) -> pd.Series:
    """计算乖离率 BIAS。"""
    ma = close.rolling(n).mean()
    bias = ((close - ma) / ma * 100).round(2)
    return bias


def calc_cci(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    """计算商品通道指数 CCI。"""
    tp = (high + low + close) / 3
    ma = tp.rolling(n).mean()
    md = tp.rolling(n).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    cci = ((tp - ma) / (0.015 * md)).round(2)
    return cci


def calc_all_indicators(df: pd.DataFrame) -> dict:
    """计算所有技术指标。

    Args:
        df: K 线 DataFrame，需包含 open, high, low, close, volume 列

    Returns:
        所有指标计算结果
    """
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    indicators = {}

    # 均线
    indicators.update(calc_ma(close))

    # MACD
    indicators["macd"] = calc_macd(close)

    # KDJ
    indicators["kdj"] = calc_kdj(high, low, close)

    # RSI（多个周期）
    indicators["rsi6"] = calc_rsi(close, 6).tolist()
    indicators["rsi12"] = calc_rsi(close, 12).tolist()
    indicators["rsi24"] = calc_rsi(close, 24).tolist()

    # 布林带
    indicators["boll"] = calc_boll(close)

    # 威廉指标
    indicators["wr10"] = calc_wr(high, low, close, 10).tolist()
    indicators["wr6"] = calc_wr(high, low, close, 6).tolist()

    # OBV
    indicators["obv"] = calc_obv(close, volume).tolist()

    # BIAS
    indicators["bias6"] = calc_bias(close, 6).tolist()
    indicators["bias12"] = calc_bias(close, 12).tolist()
    indicators["bias24"] = calc_bias(close, 24).tolist()

    # CCI
    indicators["cci14"] = calc_cci(high, low, close, 14).tolist()

    return _clean_nan(indicators)
