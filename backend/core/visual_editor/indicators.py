"""可视化策略编辑器 —— 指标库定义。

定义可被非编程用户使用的指标元信息，包括：
- 指标分组（趋势 / 超买超卖 / 能量 / 量价 / 均线 / 形态）
- 每个指标的参数、支持的分析周期、输出线（LINE）、可用逻辑关系（OPERATOR）
- 目标值的类型（常数 / 另一指标 / 价格）

前端通过 GET /api/visual/indicators 拉取该树形结构，渲染左侧指标树与条件卡片。

指标命名与同花顺 / 东方财富选股平台保持一致，便于用户上手。
"""
from __future__ import annotations

from typing import Any


# ==================== 通用选项 ====================

# 分析周期（同花顺式：日线/周线/月线/分钟线）
TIME_FRAMES: list[dict[str, str]] = [
    {"value": "daily", "label": "日线"},
    {"value": "weekly", "label": "周线"},
    {"value": "monthly", "label": "月线"},
    {"value": "60min", "label": "60分钟"},
    {"value": "30min", "label": "30分钟"},
    {"value": "15min", "label": "15分钟"},
    {"value": "5min", "label": "5分钟"},
]

# 逻辑关系（操作符）—— 同花顺风格
OPERATORS: list[dict[str, str]] = [
    {"value": "greater", "label": "大于"},
    {"value": "less", "label": "小于"},
    {"value": "cross_up", "label": "上穿"},
    {"value": "cross_down", "label": "下穿"},
    {"value": "equal", "label": "等于"},
    {"value": "between", "label": "介于（之间）"},
]

# 目标值类型
TARGET_TYPES: list[dict[str, str]] = [
    {"value": "value", "label": "常数"},
    {"value": "price", "label": "价格（收盘价）"},
    {"value": "indicator", "label": "另一指标"},
]

# ==================== 全局设置选项（策略级，对标东财顶部栏） ====================
# 分析周期（全局，已含 TIME_FRAMES）
# 复权方式
FUQUAN_TYPES: list[dict[str, str]] = [
    {"value": "qfq", "label": "前复权"},
    {"value": "hfq", "label": "后复权"},
    {"value": "none", "label": "不复权"},
]

# 选股范围
SCOPE_TYPES: list[dict[str, str]] = [
    {"value": "all", "label": "全部A股"},
    {"value": "hs300", "label": "沪深300"},
    {"value": "sz50", "label": "上证50"},
    {"value": "zz500", "label": "中证500"},
    {"value": "cyb", "label": "创业板"},
    {"value": "kcb", "label": "科创板"},
]

# 默认全局设置
DEFAULT_GLOBAL: dict[str, Any] = {
    "timeframe": "daily",
    "fuquan": "qfq",
    "scope": "all",
    "exclude_st": True,
    "exclude_halt": True,
    "min_amount": 1,  # 最小成交额（亿元）
}

# ==================== 选中指标时的默认条件映射（对标方案 4.1 表） ====================
# 用途：用户从左侧树点击指标后，自动生成一条合理默认条件（自然语言）。
# 每条映射给出：默认 line / operator / targetType / targetValue / targetParam2 / targetIndicator
DEFAULT_CONDITION_BY_INDICATOR: dict[str, dict[str, Any]] = {
    "macd": {
        "line": "gold", "operator": "equal", "targetType": "value",
        "targetValue": 1, "targetParam2": None, "targetIndicator": None,
        "note": "DIF 上穿 DEA（金叉）",
    },
    "macd_cross": {
        "line": "gold", "operator": "equal", "targetType": "value",
        "targetValue": 1, "targetParam2": None, "targetIndicator": None,
        "note": "DIF 上穿 DEA（金叉）",
    },
    "ma": {
        "line": "cross", "operator": "cross_up", "targetType": "indicator",
        "targetValue": None, "targetParam2": None, "targetIndicator": "ma10",
        "note": "MA5 上穿 MA10",
    },
    "kdj": {
        "line": "gold", "operator": "equal", "targetType": "value",
        "targetValue": 1, "targetParam2": None, "targetIndicator": None,
        "note": "K 上穿 D（金叉）",
    },
    "kdj_bull": {
        "line": "gold", "operator": "equal", "targetType": "value",
        "targetValue": 1, "targetParam2": None, "targetIndicator": None,
        "note": "K 上穿 D（金叉）",
    },
    "rsi": {
        "line": "rsi", "operator": "cross_up", "targetType": "value",
        "targetValue": 30, "targetParam2": None, "targetIndicator": None,
        "note": "RSI 上穿 30",
    },
    "cci": {
        "line": "cci", "operator": "greater", "targetType": "value",
        "targetValue": 300, "targetParam2": None, "targetIndicator": None,
        "note": "CCI 大于 300",
    },
    "boll": {
        "line": "price_lower", "operator": "cross_down", "targetType": "indicator",
        "targetValue": None, "targetParam2": None, "targetIndicator": "boll_lower",
        "note": "价格 下穿 下轨",
    },
    "vol": {
        "line": "vol", "operator": "greater", "targetType": "value",
        "targetValue": 5, "targetParam2": None, "targetIndicator": None,
        "note": "成交量 大于 5 日均量",
    },
    "vol_ratio": {
        "line": "vol_ratio", "operator": "greater", "targetType": "value",
        "targetValue": 2, "targetParam2": None, "targetIndicator": None,
        "note": "成交量 放量（>2倍均量）",
    },
}


# ==================== 指标定义 ====================

def _param(name: str, label: str, default: Any, **extra: Any) -> dict[str, Any]:
    p = {"name": name, "label": label, "default": default}
    p.update(extra)
    return p


# 每个指标：
#   key        : 唯一标识
#   name       : 显示名
#   lines      : 该指标可输出的线（用于"指标线"下拉）
#   params     : 参数列表
#   operators  : 支持的逻辑关系（默认全部）
#   target_types: 支持的目标值类型
#   note       : 说明
INDICATORS: list[dict[str, Any]] = [
    # ---------- 均线 / 趋势 ----------
    {
        "key": "ma",
        "name": "均线 MA",
        "lines": [
            {"value": "ma", "label": "MA"},
        ],
        "params": [_param("period", "周期", 5, min=1, max=250, type="int")],
        "operators": ["greater", "less", "cross_up", "cross_down", "equal"],
        "target_types": ["value", "price", "indicator"],
        "note": "移动平均线，如 MA5、MA20",
    },
    {
        "key": "ema",
        "name": "指数均线 EMA",
        "lines": [{"value": "ema", "label": "EMA"}],
        "params": [_param("period", "周期", 12, min=1, max=250, type="int")],
        "operators": ["greater", "less", "cross_up", "cross_down", "equal"],
        "target_types": ["value", "price", "indicator"],
        "note": "指数平滑移动平均线",
    },
    {
        "key": "ma_arrangement",
        "name": "均线多头排列",
        "lines": [{"value": "bull", "label": "多头排列"}],
        "params": [
            _param("fast", "短期均线", 5, min=1, max=20, type="int"),
            _param("mid", "中期均线", 10, min=5, max=60, type="int"),
            _param("slow", "长期均线", 20, min=10, max=250, type="int"),
        ],
        "operators": ["equal"],
        "target_types": ["value"],
        "note": "短期>中期>长期且均向上，输出 1 表示成立",
    },
    # ---------- 趋势指标 ----------
    {
        "key": "macd",
        "name": "MACD",
        "lines": [
            {"value": "dif", "label": "DIF(快线)"},
            {"value": "dea", "label": "DEA(慢线)"},
            {"value": "macd", "label": "MACD柱"},
        ],
        "params": [
            _param("fast", "快线周期", 12, min=2, max=50, type="int"),
            _param("slow", "慢线周期", 26, min=5, max=100, type="int"),
            _param("signal", "信号周期", 9, min=2, max=30, type="int"),
        ],
        "operators": ["greater", "less", "cross_up", "cross_down", "between"],
        "target_types": ["value", "indicator"],
        "note": "指数平滑异同移动平均",
    },
    {
        "key": "kdj",
        "name": "KDJ",
        "lines": [
            {"value": "k", "label": "K值"},
            {"value": "d", "label": "D值"},
            {"value": "j", "label": "J值"},
        ],
        "params": [
            _param("period", "周期", 9, min=5, max=30, type="int"),
            _param("smooth_k", "K平滑", 3, min=1, max=10, type="int"),
            _param("smooth_d", "D平滑", 3, min=1, max=10, type="int"),
        ],
        "operators": ["greater", "less", "cross_up", "cross_down", "between"],
        "target_types": ["value", "indicator"],
        "note": "随机指标",
    },
    {
        "key": "boll",
        "name": "布林带 BOLL",
        "lines": [
            {"value": "upper", "label": "上轨"},
            {"value": "mid", "label": "中轨"},
            {"value": "lower", "label": "下轨"},
        ],
        "params": [
            _param("period", "周期", 20, min=5, max=100, type="int"),
            _param("dev", "标准差倍数", 2.0, min=0.5, max=4.0, type="float"),
        ],
        "operators": ["greater", "less", "cross_up", "cross_down"],
        "target_types": ["value", "price", "indicator"],
        "note": "布林带通道",
    },
    # ---------- 超买超卖 ----------
    {
        "key": "rsi",
        "name": "RSI",
        "lines": [{"value": "rsi", "label": "RSI"}],
        "params": [_param("period", "周期", 14, min=2, max=50, type="int")],
        "operators": ["greater", "less", "between"],
        "target_types": ["value"],
        "note": "相对强弱指标，常看超买>70 / 超卖<30",
    },
    {
        "key": "cci",
        "name": "CCI",
        "lines": [{"value": "cci", "label": "CCI"}],
        "params": [_param("period", "周期", 14, min=5, max=50, type="int")],
        "operators": ["greater", "less", "cross_up", "cross_down", "between"],
        "target_types": ["value"],
        "note": "顺势指标，>+100 强势 / <-100 弱势",
    },
    {
        "key": "wr",
        "name": "威廉指标 WR",
        "lines": [{"value": "wr", "label": "WR"}],
        "params": [_param("period", "周期", 10, min=2, max=50, type="int")],
        "operators": ["greater", "less", "between"],
        "target_types": ["value"],
        "note": "W%R，0~100，低于20超买 / 高于80超卖",
    },
    {
        "key": "bias",
        "name": "乖离率 BIAS",
        "lines": [
            {"value": "bias6", "label": "BIAS6"},
            {"value": "bias12", "label": "BIAS12"},
            {"value": "bias24", "label": "BIAS24"},
        ],
        "params": [_param("period", "基准周期", 6, min=3, max=60, type="int")],
        "operators": ["greater", "less", "between"],
        "target_types": ["value"],
        "note": "收盘价与均线的偏离百分比",
    },
    {
        "key": "kdj_bull",
        "name": "KDJ金叉/死叉",
        "lines": [
            {"value": "gold", "label": "金叉(K上穿D)"},
            {"value": "death", "label": "死叉(K下穿D)"},
        ],
        "params": [
            _param("period", "周期", 9, min=5, max=30, type="int"),
            _param("smooth_k", "K平滑", 3, min=1, max=10, type="int"),
            _param("smooth_d", "D平滑", 3, min=1, max=10, type="int"),
        ],
        "operators": ["equal"],
        "target_types": ["value"],
        "note": "输出 1=金叉 / -1=死叉 / 0=其他",
    },
    {
        "key": "macd_cross",
        "name": "MACD金叉/死叉",
        "lines": [
            {"value": "gold", "label": "金叉(DIF上穿DEA)"},
            {"value": "death", "label": "死叉(DIF下穿DEA)"},
        ],
        "params": [
            _param("fast", "快线周期", 12, min=2, max=50, type="int"),
            _param("slow", "慢线周期", 26, min=5, max=100, type="int"),
            _param("signal", "信号周期", 9, min=2, max=30, type="int"),
        ],
        "operators": ["equal"],
        "target_types": ["value"],
        "note": "输出 1=金叉 / -1=死叉 / 0=其他",
    },
    # ---------- 量价 ----------
    {
        "key": "vol",
        "name": "成交量 VOL",
        "lines": [
            {"value": "vol", "label": "成交量"},
            {"value": "ma", "label": "均量线"},
        ],
        "params": [_param("period", "均量周期", 5, min=2, max=60, type="int")],
        "operators": ["greater", "less", "cross_up", "cross_down", "between"],
        "target_types": ["value", "indicator"],
        "note": "成交量及均量线",
    },
    {
        "key": "vol_ratio",
        "name": "量比",
        "lines": [{"value": "ratio", "label": "量比"}],
        "params": [_param("period", "对比周期", 5, min=2, max=20, type="int")],
        "operators": ["greater", "less", "between"],
        "target_types": ["value"],
        "note": "当日成交量/过去N日均量",
    },
    {
        "key": "obv",
        "name": "能量潮 OBV",
        "lines": [{"value": "obv", "label": "OBV"}],
        "params": [],
        "operators": ["greater", "less", "cross_up", "cross_down"],
        "target_types": ["value", "indicator"],
        "note": "累积能量潮",
    },
    {
        "key": "amt",
        "name": "成交额",
        "lines": [{"value": "amount", "label": "成交额(元)"}],
        "params": [],
        "operators": ["greater", "less", "between"],
        "target_types": ["value"],
        "note": "单位：元，可直接写 5亿=500000000",
    },
    {
        "key": "turnover",
        "name": "换手率",
        "lines": [{"value": "turnover", "label": "换手率(%)"}],
        "params": [],
        "operators": ["greater", "less", "between"],
        "target_types": ["value"],
        "note": "单位：百分比",
    },
    # ---------- 价格 / 形态 ----------
    {
        "key": "price",
        "name": "收盘价",
        "lines": [
            {"value": "close", "label": "收盘价"},
            {"value": "open", "label": "开盘价"},
            {"value": "high", "label": "最高价"},
            {"value": "low", "label": "最低价"},
        ],
        "params": [],
        "operators": ["greater", "less", "cross_up", "cross_down", "between"],
        "target_types": ["value", "indicator"],
        "note": "基础价格序列",
    },
    {
        "key": "high_low_range",
        "name": "振幅",
        "lines": [{"value": "range", "label": "振幅(%)"}],
        "params": [],
        "operators": ["greater", "less", "between"],
        "target_types": ["value"],
        "note": "(最高-最低)/昨收*100",
    },
    {
        "key": "rise_rate",
        "name": "涨跌幅",
        "lines": [{"value": "pct", "label": "涨跌幅(%)"}],
        "params": [],
        "operators": ["greater", "less", "between"],
        "target_types": ["value"],
        "note": "当日涨跌百分比",
    },
    {
        "key": "new_high",
        "name": "N日新高",
        "lines": [{"value": "high", "label": "创N日新高"}],
        "params": [_param("period", "周期", 20, min=5, max=250, type="int")],
        "operators": ["equal"],
        "target_types": ["value"],
        "note": "输出 1=创N日新高",
    },
    {
        "key": "new_low",
        "name": "N日新低",
        "lines": [{"value": "low", "label": "创N日新低"}],
        "params": [_param("period", "周期", 20, min=5, max=250, type="int")],
        "operators": ["equal"],
        "target_types": ["value"],
        "note": "输出 1=创N日新低",
    },
]

# 指标分组（左侧树）—— 与同花顺风格一致
INDICATOR_GROUPS: list[dict[str, Any]] = [
    {"key": "trend", "label": "趋势指标", "children": ["ma", "ema", "ma_arrangement", "macd", "boll", "kdj"]},
    {"key": "overbought", "label": "超买超卖", "children": ["rsi", "cci", "wr", "bias", "kdj_bull", "macd_cross"]},
    {"key": "volume", "label": "量价指标", "children": ["vol", "vol_ratio", "obv", "amt", "turnover"]},
    {"key": "price", "label": "价格与形态", "children": ["price", "high_low_range", "rise_rate", "new_high", "new_low"]},
]

_GROUP_LABEL = {g["key"]: g["label"] for g in INDICATOR_GROUPS}
_INDICATOR_MAP = {ind["key"]: ind for ind in INDICATORS}


def get_indicator_groups() -> list[str]:
    return [g["key"] for g in INDICATOR_GROUPS]


def get_indicator_tree() -> dict[str, Any]:
    """返回前端所需的完整树形结构 + 选项常量。

    结构：
    {
      "timeframes": [...],
      "operators": [...],
      "target_types": [...],
      "groups": [
        {"key", "label", "indicators": [ {指标定义} ]},
        ...
      ]
    }
    """
    groups = []
    for g in INDICATOR_GROUPS:
        inds = []
        for key in g["children"]:
            ind = _INDICATOR_MAP.get(key)
            if ind:
                inds.append(ind)
        groups.append({
            "key": g["key"],
            "label": g["label"],
            "indicators": inds,
        })
    return {
        "timeframes": TIME_FRAMES,
        "operators": OPERATORS,
        "target_types": TARGET_TYPES,
        "groups": groups,
        # 全局设置选项（策略级，对标东财顶部栏）
        "fuquan_types": FUQUAN_TYPES,
        "scope_types": SCOPE_TYPES,
        "default_global": DEFAULT_GLOBAL,
        # 选中指标时的默认条件映射（前端自动预填用）
        "default_conditions": DEFAULT_CONDITION_BY_INDICATOR,
    }


def get_indicator_def(indicator_key: str) -> dict[str, Any] | None:
    """按 key 取单个指标定义（供后端执行/校验用）。"""
    return _INDICATOR_MAP.get(indicator_key)


def get_default_global() -> dict[str, Any]:
    """返回默认全局设置（深拷贝，避免调用方修改原始）。"""
    return dict(DEFAULT_GLOBAL)


def get_default_condition(indicator_key: str) -> dict[str, Any] | None:
    """返回某指标被选中时的默认条件映射（若存在）。"""
    dc = DEFAULT_CONDITION_BY_INDICATOR.get(indicator_key)
    return dict(dc) if dc else None
