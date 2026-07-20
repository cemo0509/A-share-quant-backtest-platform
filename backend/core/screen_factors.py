"""可组合选股因子引擎（实时选股池需求升级）。

把"选股条件"抽象为一组独立因子，每个因子是一个判断函数：
    eval_xxx(df, params) -> Optional[bool]
    - True  : 满足条件
    - False : 不满足
    - None  : 数据不足 / 无法判断（视为跳过该因子）

因子定义集中放在 FACTOR_DEFS，前端据此自动渲染勾选面板与参数输入。

支持指标（基于 core.indicators）：
    CCI / MACD(金叉·死叉·零线附近) / RSI / KDJ / 均线多头 / 成交量突破 /
    布林带触轨 / WR / OBV / BIAS
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

import numpy as np
import pandas as pd

from core.indicators import (
    calc_cci, calc_macd, calc_rsi, calc_kdj, calc_ma,
    calc_boll, calc_wr, calc_obv, calc_bias,
)

logger = logging.getLogger("screen_factors")


# ==================== 单个因子判断 ====================

def _last(arr, n=1):
    """取序列最后 n 个值；不足返回 None。"""
    if arr is None or len(arr) < n:
        return None
    return arr.iloc[-n:]


def eval_cci(df: pd.DataFrame, p: dict) -> Optional[bool]:
    """CCI(N) 最新值 与阈值比较。

    p.direction: 'above' (>阈值) / 'below' (<阈值)
    p.period: CCI 周期
    p.threshold: 阈值
    """
    cci = calc_cci(df["high"], df["low"], df["close"], int(p.get("period", 14)))
    if cci is None or len(cci) < 2:
        return None
    v = float(cci.iloc[-1])
    if np.isnan(v):
        return None
    thr = float(p.get("threshold", 100))
    if p.get("direction", "above") == "above":
        return v > thr
    return v < thr


def _macd_cross_state(dif, dea, lookback: int = 5):
    """检测最近 lookback 根 K 线内是否出现金叉/死叉。

    之前只检查最后两根，导致刚过几根就检测不到，
    大部分候选股票因此被筛掉。

    dif/dea 可能是 numpy.ndarray 或 pandas.Series，统一用位置索引取值。
    """
    if dif is None or dea is None or len(dif) < 2 or len(dea) < 2:
        return None
    # 从最新开始逐对回溯
    max_i = min(lookback, len(dif) - 1)
    for i in range(max_i):
        d0, d1 = float(dif[-(i + 1)]), float(dif[-(i + 2)])
        e0, e1 = float(dea[-(i + 1)]), float(dea[-(i + 2)])
        if any(np.isnan(x) for x in (d0, d1, e0, e1)):
            continue
        if d1 <= e1 and d0 > e0:
            return "golden"
        if d1 >= e1 and d0 < e0:
            return "death"
    return None


def eval_macd(df: pd.DataFrame, p: dict) -> Optional[bool]:
    """MACD 判断。

    p.signal: 'golden'(金叉) / 'death'(死叉) / 'above_zero'(DIF>0) / 'below_zero'(DIF<0)
    p.zero_band: 若 >0，要求 |DIF| <= zero_band（零线附近），默认 0 不限制
    p.fast/slow/signal: MACD 参数
    """
    m = calc_macd(df["close"],
                  int(p.get("fast", 12)), int(p.get("slow", 26)), int(p.get("signal_p", 9)))
    dif = np.array(m["dif"], dtype=float)
    dea = np.array(m["dea"], dtype=float)
    if len(dif) < 2:
        return None

    lookback = int(p.get("lookback", 5))
    signal = p.get("signal", "golden")
    if signal == "golden":
        ok = _macd_cross_state(dif, dea, lookback) == "golden"
    elif signal == "death":
        ok = _macd_cross_state(dif, dea, lookback) == "death"
    elif signal == "above_zero":
        ok = dif[-1] > 0
    elif signal == "below_zero":
        ok = dif[-1] < 0
    else:
        ok = False

    zero_band = float(p.get("zero_band", 0) or 0)
    if ok and zero_band > 0:
        ok = abs(dif[-1]) <= zero_band
    return ok


def eval_rsi(df: pd.DataFrame, p: dict) -> Optional[bool]:
    """RSI(N) 超买/超卖判断。

    p.direction: 'above'(>overbought) / 'below'(<oversold)
    p.period: RSI 周期
    p.threshold: 阈值（超买用 high，超卖用 low）
    """
    rsi = calc_rsi(df["close"], int(p.get("period", 14)))
    if rsi is None or len(rsi) < 2:
        return None
    v = float(rsi.iloc[-1])
    if np.isnan(v):
        return None
    thr = float(p.get("threshold", 70))
    if p.get("direction", "above") == "above":
        return v > thr
    return v < thr


def eval_kdj(df: pd.DataFrame, p: dict) -> Optional[bool]:
    """KDJ 判断。

    p.signal: 'golden'(金叉 K上穿D) / 'death'(死叉) /
              'overbuy'(J>阈值) / 'oversold'(J<阈值)
    p.period: KDJ 周期
    p.threshold: J 阈值
    """
    k = calc_kdj(df["high"], df["low"], df["close"], int(p.get("period", 9)))
    kk = np.array(k["k"], dtype=float)
    dd = np.array(k["d"], dtype=float)
    jj = np.array(k["j"], dtype=float)
    if len(kk) < 2:
        return None
    sig = p.get("signal", "golden")
    if sig == "golden":
        if any(np.isnan(x) for x in (kk[-1], kk[-2], dd[-1], dd[-2])):
            return None
        return kk[-2] <= dd[-2] and kk[-1] > dd[-1]
    if sig == "death":
        if any(np.isnan(x) for x in (kk[-1], kk[-2], dd[-1], dd[-2])):
            return None
        return kk[-2] >= dd[-2] and kk[-1] < dd[-1]
    if sig in ("overbuy", "oversold"):
        if np.isnan(jj[-1]):
            return None
        thr = float(p.get("threshold", 80))
        return jj[-1] > thr if sig == "overbuy" else jj[-1] < thr
    return False


def eval_ma_bull(df: pd.DataFrame, p: dict) -> Optional[bool]:
    """均线多头排列：fast > mid > slow 且全部向上倾斜。

    p.fast/mid/slow: 周期
    p.require_向上: '1'/'0' 是否要求均线向上
    """
    fast = int(p.get("fast", 5))
    mid = int(p.get("mid", 10))
    slow = int(p.get("slow", 20))
    ma = calc_ma(df["close"], [fast, mid, slow])
    fa, ma_, sa = ma[f"ma{fast}"], ma[f"ma{mid}"], ma[f"ma{slow}"]
    if len(fa) < 2:
        return None
    if any(np.isnan(x) for x in (fa.iloc[-1], ma_.iloc[-1], sa.iloc[-1])):
        return None
    bull = fa.iloc[-1] > ma_.iloc[-1] > sa.iloc[-1]
    if p.get("require_up", "1") == "1":
        up = fa.iloc[-1] >= fa.iloc[-2] and ma_.iloc[-1] >= ma_.iloc[-2] and sa.iloc[-1] >= sa.iloc[-2]
        bull = bull and up
    return bool(bull)


def eval_volume_breakout(df: pd.DataFrame, p: dict) -> Optional[bool]:
    """放量突破前高。

    p.lookback: 观察窗口
    p.vol_ratio: 当前量 / 均量 倍数
    """
    look = int(p.get("lookback", 20))
    ratio = float(p.get("vol_ratio", 1.5))
    if len(df) < look + 1:
        return None
    vol = df["volume"].astype(float)
    close = df["close"].astype(float)
    cur_vol = vol.iloc[-1]
    avg_vol = vol.iloc[-look - 1:-1].mean()
    if avg_vol is None or np.isnan(avg_vol) or avg_vol <= 0:
        return None
    cur_high = close.iloc[-1]
    prev_high = close.iloc[-look - 1:-1].max()
    return bool(cur_vol >= avg_vol * ratio and cur_high >= prev_high)


def eval_boll(df: pd.DataFrame, p: dict) -> Optional[bool]:
    """布林带触轨。

    p.signal: 'touch_upper'(收盘价>=上轨) / 'touch_lower'(<=下轨)
    p.period/std: 参数
    """
    b = calc_boll(df["close"], int(p.get("period", 20)), float(p.get("std", 2.0)))
    up = np.array(b["upper"], dtype=float)
    lo = np.array(b["lower"], dtype=float)
    close = df["close"].astype(float)
    if len(up) < 1:
        return None
    sig = p.get("signal", "touch_upper")
    if sig == "touch_upper":
        return close.iloc[-1] >= up[-1]
    if sig == "touch_lower":
        return close.iloc[-1] <= lo[-1]
    return False


def eval_wr(df: pd.DataFrame, p: dict) -> Optional[bool]:
    """威廉指标 WR(N)。

    p.direction: 'above'(WR>阈值, 超卖区) / 'below'(WR<阈值, 超买区)
    p.period / p.threshold
    """
    wr = calc_wr(df["high"], df["low"], df["close"], int(p.get("period", 10)))
    if wr is None or len(wr) < 1:
        return None
    v = float(wr.iloc[-1])
    if np.isnan(v):
        return None
    thr = float(p.get("threshold", 80))
    return v > thr if p.get("direction", "above") == "above" else v < thr


def eval_obv(df: pd.DataFrame, p: dict) -> Optional[bool]:
    """OBV 上升（量能配合）。

    p.period: 比较窗口，OBV 近 period 根呈上升
    """
    period = int(p.get("period", 5))
    obv = calc_obv(df["close"], df["volume"].astype(float))
    if len(obv) < period + 1:
        return None
    recent = obv.iloc[-period - 1:]
    return bool(recent.iloc[-1] > recent.iloc[0])


def eval_bias(df: pd.DataFrame, p: dict) -> Optional[bool]:
    """乖离率 BIAS(N)。

    p.direction: 'above'(>阈值) / 'below'(<阈值)
    p.period / p.threshold
    """
    bias = calc_bias(df["close"], int(p.get("period", 6)))
    if bias is None or len(bias) < 1:
        return None
    v = float(bias.iloc[-1])
    if np.isnan(v):
        return None
    thr = float(p.get("threshold", 5))
    return v > thr if p.get("direction", "above") == "above" else v < thr


# ==================== 因子注册表 ====================
# 前端据此自动渲染勾选面板。
# 每个因子：key / name / 参数定义(params) / 默认是否启用(enabled) / 默认参数

FACTOR_DEFS = [
    {
        "key": "cci", "name": "CCI 商品通道", "eval": eval_cci,
        "enabled": True,
        "params": [
            {"name": "period", "label": "周期", "type": "int", "default": 14, "min": 5, "max": 60},
            {"name": "direction", "label": "方向", "type": "select", "default": "above",
             "options": [{"label": "大于阈值", "value": "above"}, {"label": "小于阈值", "value": "below"}]},
            {"name": "threshold", "label": "阈值", "type": "float", "default": 100, "min": -300, "max": 500, "step": 10},
        ],
    },
    {
        "key": "macd", "name": "MACD", "eval": eval_macd,
        "enabled": True,
        "params": [
            {"name": "signal", "label": "信号", "type": "select", "default": "golden",
             "options": [
                 {"label": "金叉", "value": "golden"},
                 {"label": "死叉", "value": "death"},
                 {"label": "DIF>0", "value": "above_zero"},
                 {"label": "DIF<0", "value": "below_zero"},
             ]},
            {"name": "zero_band", "label": "零线附近带宽(0不限制)", "type": "float", "default": 0, "min": 0, "max": 5, "step": 0.1},
            {"name": "lookback", "label": "回溯K线根数", "type": "int", "default": 5, "min": 1, "max": 20, "step": 1},
            {"name": "fast", "label": "快线", "type": "int", "default": 12, "min": 2, "max": 50},
            {"name": "slow", "label": "慢线", "type": "int", "default": 26, "min": 5, "max": 100},
            {"name": "signal_p", "label": "信号线", "type": "int", "default": 9, "min": 2, "max": 30, "hidden": True},
        ],
    },
    {
        "key": "rsi", "name": "RSI 相对强弱", "eval": eval_rsi,
        "enabled": False,
        "params": [
            {"name": "period", "label": "周期", "type": "int", "default": 14, "min": 2, "max": 50},
            {"name": "direction", "label": "方向", "type": "select", "default": "above",
             "options": [{"label": "大于(超买)", "value": "above"}, {"label": "小于(超卖)", "value": "below"}]},
            {"name": "threshold", "label": "阈值", "type": "float", "default": 70, "min": 10, "max": 95, "step": 1},
        ],
    },
    {
        "key": "kdj", "name": "KDJ", "eval": eval_kdj,
        "enabled": False,
        "params": [
            {"name": "signal", "label": "信号", "type": "select", "default": "golden",
             "options": [
                 {"label": "金叉", "value": "golden"},
                 {"label": "死叉", "value": "death"},
                 {"label": "J超买", "value": "overbuy"},
                 {"label": "J超卖", "value": "oversold"},
             ]},
            {"name": "period", "label": "周期", "type": "int", "default": 9, "min": 5, "max": 30},
            {"name": "threshold", "label": "J阈值", "type": "float", "default": 80, "min": 50, "max": 120, "step": 1},
        ],
    },
    {
        "key": "ma_bull", "name": "均线多头排列", "eval": eval_ma_bull,
        "enabled": False,
        "params": [
            {"name": "fast", "label": "短期", "type": "int", "default": 5, "min": 1, "max": 20},
            {"name": "mid", "label": "中期", "type": "int", "default": 10, "min": 5, "max": 60},
            {"name": "slow", "label": "长期", "type": "int", "default": 20, "min": 10, "max": 250},
            {"name": "require_up", "label": "要求向上", "type": "select", "default": "1",
             "options": [{"label": "是", "value": "1"}, {"label": "否", "value": "0"}]},
        ],
    },
    {
        "key": "volume_breakout", "name": "成交量突破", "eval": eval_volume_breakout,
        "enabled": False,
        "params": [
            {"name": "lookback", "label": "观察周期", "type": "int", "default": 20, "min": 5, "max": 60},
            {"name": "vol_ratio", "label": "放量倍数", "type": "float", "default": 1.5, "min": 1.0, "max": 5.0, "step": 0.1},
        ],
    },
    {
        "key": "boll", "name": "布林带触轨", "eval": eval_boll,
        "enabled": False,
        "params": [
            {"name": "signal", "label": "信号", "type": "select", "default": "touch_upper",
             "options": [
                 {"label": "触上轨", "value": "touch_upper"},
                 {"label": "触下轨", "value": "touch_lower"},
             ]},
            {"name": "period", "label": "周期", "type": "int", "default": 20, "min": 5, "max": 100},
            {"name": "std", "label": "标准差倍数", "type": "float", "default": 2.0, "min": 0.5, "max": 4.0, "step": 0.1},
        ],
    },
    {
        "key": "wr", "name": "WR 威廉指标", "eval": eval_wr,
        "enabled": False,
        "params": [
            {"name": "period", "label": "周期", "type": "int", "default": 10, "min": 2, "max": 50},
            {"name": "direction", "label": "方向", "type": "select", "default": "above",
             "options": [{"label": "大于(超卖)", "value": "above"}, {"label": "小于(超买)", "value": "below"}]},
            {"name": "threshold", "label": "阈值", "type": "float", "default": 80, "min": 10, "max": 95, "step": 1},
        ],
    },
    {
        "key": "obv", "name": "OBV 能量潮", "eval": eval_obv,
        "enabled": False,
        "params": [
            {"name": "period", "label": "上升窗口", "type": "int", "default": 5, "min": 2, "max": 30},
        ],
    },
    {
        "key": "bias", "name": "BIAS 乖离率", "eval": eval_bias,
        "enabled": False,
        "params": [
            {"name": "period", "label": "周期", "type": "int", "default": 6, "min": 2, "max": 30},
            {"name": "direction", "label": "方向", "type": "select", "default": "above",
             "options": [{"label": "大于", "value": "above"}, {"label": "小于", "value": "below"}]},
            {"name": "threshold", "label": "阈值(%)", "type": "float", "default": 5, "min": -20, "max": 30, "step": 0.5},
        ],
    },
]

FACTOR_MAP = {f["key"]: f for f in FACTOR_DEFS}


def build_default_factor_config() -> dict:
    """生成默认因子配置（前端初始化用）。

    Returns:
        { key: {"enabled": bool, "params": {name: value}} }
    """
    cfg = {}
    for f in FACTOR_DEFS:
        cfg[f["key"]] = {
            "enabled": f.get("enabled", False),
            "params": {p["name"]: p["default"] for p in f["params"] if not p.get("hidden")},
        }
    return cfg


def eval_factors(df: pd.DataFrame, factor_cfg: dict, combine: str = "AND") -> bool:
    """按因子配置判定一只股票是否入选。

    Args:
        df: 分钟K线 DataFrame
        factor_cfg: { key: {"enabled": bool, "params": {...}} }
        combine: 'AND' 全部满足 / 'OR' 任一满足

    Returns:
        是否满足组合条件。
    """
    results = []
    for key, conf in factor_cfg.items():
        if not conf.get("enabled"):
            continue
        fac = FACTOR_MAP.get(key)
        if not fac:
            continue
        try:
            r = fac["eval"](df, conf.get("params", {}))
        except Exception as e:
            logger.debug(f"因子 {key} 计算异常: {e}")
            r = None
        if r is None:
            # 数据不足：AND 模式下不计为通过也不计为否决；OR 模式忽略
            continue
        results.append(r)

    if not results:
        return False
    if combine == "OR":
        return any(results)
    return all(results)


def list_factor_defs() -> list[dict]:
    """返回前端可用的因子定义（含默认配置），去除 eval 函数引用。"""
    out = []
    for f in FACTOR_DEFS:
        out.append({
            "key": f["key"],
            "name": f["name"],
            "enabled": f.get("enabled", False),
            "params": [
                {k: v for k, v in p.items() if k != "hidden" or not v}
                for p in f["params"]
            ],
        })
    return out
