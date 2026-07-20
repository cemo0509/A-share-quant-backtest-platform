"""CCI+MACD 选股核心判断（供选股扫描与盘中监控共用）。

不走 backtrader 回测，直接用指标计算判断"当前时点是否入选"，
符合需求"不做历史回测，只输出选股结果"的边界。
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np

logger = logging.getLogger("cci_macd_scanner")


def check_cci_macd(
    symbol: str,
    period: str = "30",
    cci_threshold: float = 300.0,
    zero_line_band: float = 0.5,
    golden_gap: float = 0.1,
    limit: int = 200,
) -> Optional[dict]:
    """判断单只股票是否满足 CCI+MACD 选股条件。

    核心逻辑（时序错位修正）：
        CCI 是先行动量指标，往往在 MACD 之前爆发。因此二者**很少同一根 K 线同时满足**
        「CCI 突破阈值」与「MACD 已金叉」。正确信号应是：

        - CCI(14) 最新值 > cci_threshold（动量已爆发的先行信号）
        - MACD 出现「即将在零线附近金叉」的预兆：DIF 仍在 DEA 下方（尚未金叉），
          但 DIF 已拐头向上（dif_now > dif_prev）并逼近 DEA（dea - dif <= golden_gap），
          且 DIF / DEA 都贴近零线（|dif| <= zero_line_band），即金叉一触即发。

    注意 golden_gap 取相对量（与 |DIF| 同比），避免不同价位股票绝对差不可比。

    Returns:
        满足条件时返回 dict（含 cci/dif/dea/price 等），否则 None。
    """
    from core.data_loader import fetch_minute_kline
    from core.indicators import calc_cci, calc_macd

    try:
        df = fetch_minute_kline(symbol, period=period, limit=limit)
    except Exception as e:
        logger.debug(f"{symbol} 分钟K线获取失败: {e}")
        return None

    if df is None or df.empty or len(df) < 35:
        return None

    try:
        high = df["high"]
        low = df["low"]
        close = df["close"]

        # CCI(14)
        cci_series = calc_cci(high, low, close, 14)
        cci_now = float(cci_series.iloc[-1]) if len(cci_series) else float("nan")
        if np.isnan(cci_now):
            return None

        # MACD
        macd = calc_macd(close, 12, 26, 9)
        dif = np.array(macd["dif"], dtype=float)
        dea = np.array(macd["dea"], dtype=float)
        if len(dif) < 3 or np.isnan(dif[-1]) or np.isnan(dea[-1]) \
                or np.isnan(dif[-2]) or np.isnan(dea[-2]) \
                or np.isnan(dif[-3]) or np.isnan(dea[-3]):
            return None

        dif_now, dea_now = dif[-1], dea[-1]
        dif_prev, dea_prev = dif[-2], dea[-2]
        dif_prev2 = dif[-3]

        # 先行动量信号：CCI 已突破阈值
        cci_ok = cci_now > cci_threshold

        # 即将金叉的预兆（而非"已经完成金叉"）：
        #   1) DIF 仍在 DEA 下方（尚未金叉，避免与 CCI 时序错位冲突）
        #   2) DIF 已拐头向上：dif_now > dif_prev > dif_prev2（连续回升）
        #   3) DIF 逼近 DEA：gap = dea_now - dif_now 为正且相对很小
        #   4) DIF / DEA 都贴近零线
        gap = dea_now - dif_now
        gap_ratio = gap / (abs(dif_now) + 1e-9)
        near_zero = (abs(dif_now) <= zero_line_band) and (abs(dea_now) <= zero_line_band)
        dif_rising = (dif_now > dif_prev) and (dif_prev >= dif_prev2)
        approaching = (gap > 0) and (gap_ratio <= golden_gap)
        macd_precross = near_zero and dif_rising and approaching

        # 已金叉（DIF 上穿 DEA）也视为满足 MACD 条件，作为兼容兜底
        macd_golden = (dif_prev <= dea_prev) and (dif_now > dea_now) and near_zero
        macd_ok = macd_precross or macd_golden

        if not (cci_ok and macd_ok):
            return None

        price = float(close.iloc[-1])
        last_time = str(df["date"].iloc[-1])

        return {
            "symbol": symbol,
            "cci": round(cci_now, 2),
            "dif": round(float(dif_now), 4),
            "dea": round(float(dea_now), 4),
            # 标记实际命中类型：precross=即将金叉预兆，golden=已完成金叉
            "macd_cross": "precross" if macd_precross else "golden",
            "price": round(price, 2),
            "period": period,
            "kline_time": last_time,
        }
    except Exception as e:
        # 单只计算异常不应中断整个扫描线程
        logger.debug(f"{symbol} CCI+MACD 计算异常: {e}")
        return None
