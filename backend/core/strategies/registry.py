"""策略注册表：统一管理预置策略 + 自定义策略，供前端选择。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Type, Optional

import backtrader as bt

from .dual_ma import DualMAStrategy
from .bollinger import BollingerStrategy
from .rsi import RSIStrategy
from .macd import MACDStrategy
from .turtle import TurtleStrategy
from .kdj import KDJStrategy
from .ma_bullish import MABullishStrategy
from .volume_breakout import VolumeBreakoutStrategy
from .mean_reversion import MeanReversionStrategy
from .momentum import MomentumStrategy
from .grid_trading import GridTradingStrategy
from .adaptive_strategy import AdaptiveStrategy
from .smart_exit_strategy import SmartExitStrategy
from .factor_strategy import FactorScoreStrategy
from .cci_macd_selection import CCIMACDSelectionStrategy
from .custom_manager import list_custom_strategies, load_custom_strategy_class


@dataclass
class StrategyInfo:
    """策略元信息，用于前端展示和参数配置。"""
    key: str
    name: str
    description: str
    category: str = "trading"  # screening(选股) / trading(操盘) / hybrid(混合)
    strategy_cls: Optional[Type[bt.Strategy]] = None  # 自定义策略可能为None
    params: list[dict] = field(default_factory=list)
    is_custom: bool = False  # 是否为自定义策略
    # 可视化编辑器「智能推荐」默认规则（贴合前端 ConditionLeaf 模型）。
    # 形如 {"operator": "AND", "items": [ {type:"condition",...}, ... ], "recommended_indicators": [...]}
    visual_defaults: Optional[dict] = None
    # 智能推荐预设 key：进入可视化编辑器时自动预填对应的 visual_defaults。
    # 若与 REGISTRY 的 key 不一致可显式指定，否则默认用本策略 key。
    preset_key: Optional[str] = None


# 预置策略注册表
REGISTRY: dict[str, StrategyInfo] = {
    "dual_ma": StrategyInfo(
        key="dual_ma",
        name="双均线策略",
        description="短期均线上穿长期均线买入（金叉），下穿卖出（死叉）",
        category="trading",
        strategy_cls=DualMAStrategy,
        params=[
            {"name": "fast", "label": "短期均线周期", "default": 5, "min": 1, "max": 60, "type": "int"},
            {"name": "slow", "label": "长期均线周期", "default": 20, "min": 5, "max": 250, "type": "int"},
        ],
    ),
    "bollinger": StrategyInfo(
        key="bollinger",
        name="布林带策略",
        description="价格触及下轨买入，触及上轨卖出",
        category="hybrid",
        strategy_cls=BollingerStrategy,
        params=[
            {"name": "period", "label": "布林带周期", "default": 20, "min": 5, "max": 100, "type": "int"},
            {"name": "dev", "label": "标准差倍数", "default": 2.0, "min": 0.5, "max": 4.0, "type": "float"},
        ],
    ),
    "rsi": StrategyInfo(
        key="rsi",
        name="RSI超买超卖",
        description="RSI低于超卖线买入，高于超买线卖出",
        category="trading",
        strategy_cls=RSIStrategy,
        params=[
            {"name": "period", "label": "RSI周期", "default": 14, "min": 2, "max": 50, "type": "int"},
            {"name": "oversold", "label": "超卖阈值", "default": 30, "min": 5, "max": 50, "type": "int"},
            {"name": "overbought", "label": "超买阈值", "default": 70, "min": 50, "max": 95, "type": "int"},
        ],
    ),
    "macd": StrategyInfo(
        key="macd",
        name="MACD策略",
        description="MACD金叉买入，死叉卖出",
        category="trading",
        strategy_cls=MACDStrategy,
        params=[
            {"name": "fast_period", "label": "快线周期", "default": 12, "min": 2, "max": 50, "type": "int"},
            {"name": "slow_period", "label": "慢线周期", "default": 26, "min": 5, "max": 100, "type": "int"},
            {"name": "signal_period", "label": "信号线周期", "default": 9, "min": 2, "max": 30, "type": "int"},
        ],
    ),
    "turtle": StrategyInfo(
        key="turtle",
        name="海龟交易策略",
        description="价格突破N日最高点买入，跌破最低点卖出（海龟交易法则）",
        category="trading",
        strategy_cls=TurtleStrategy,
        params=[
            {"name": "n", "label": "突破周期", "default": 20, "min": 5, "max": 100, "type": "int"},
            {"name": "add_n", "label": "加仓周期", "default": 10, "min": 5, "max": 50, "type": "int"},
            {"name": "risk_percent", "label": "风险比例", "default": 0.01, "min": 0.001, "max": 0.05, "type": "float"},
        ],
    ),
    # ===== 新增策略 =====
    "kdj": StrategyInfo(
        key="kdj",
        name="KDJ策略",
        description="K线和D线金叉买入，死叉卖出，结合超买超卖区",
        category="trading",
        strategy_cls=KDJStrategy,
        params=[
            {"name": "period", "label": "KDJ周期", "default": 9, "min": 5, "max": 30, "type": "int"},
            {"name": "smooth_k", "label": "K值平滑", "default": 3, "min": 1, "max": 10, "type": "int"},
            {"name": "smooth_d", "label": "D值平滑", "default": 3, "min": 1, "max": 10, "type": "int"},
            {"name": "oversold", "label": "超卖阈值", "default": 20, "min": 5, "max": 50, "type": "int"},
            {"name": "overbought", "label": "超买阈值", "default": 80, "min": 50, "max": 95, "type": "int"},
        ],
    ),
    "ma_bullish": StrategyInfo(
        key="ma_bullish",
        name="均线多头排列",
        description="5/10/20日均线多头排列且向上倾斜时买入，适合筛选趋势走强的股票",
        category="screening",
        strategy_cls=MABullishStrategy,
        params=[
            {"name": "fast", "label": "短期均线周期", "default": 5, "min": 1, "max": 20, "type": "int"},
            {"name": "mid", "label": "中期均线周期", "default": 10, "min": 5, "max": 60, "type": "int"},
            {"name": "slow", "label": "长期均线周期", "default": 20, "min": 10, "max": 250, "type": "int"},
            {"name": "hold_days", "label": "最小持有天数", "default": 3, "min": 1, "max": 30, "type": "int"},
        ],
    ),
    "volume_breakout": StrategyInfo(
        key="volume_breakout",
        name="成交量突破",
        description="放量突破前高时买入，适合筛选资金关注的活跃股票",
        category="screening",
        strategy_cls=VolumeBreakoutStrategy,
        params=[
            {"name": "lookback", "label": "突破观察周期", "default": 20, "min": 5, "max": 60, "type": "int"},
            {"name": "volume_ma_period", "label": "均量线周期", "default": 5, "min": 2, "max": 20, "type": "int"},
            {"name": "volume_ratio", "label": "放量倍数", "default": 1.5, "min": 1.0, "max": 5.0, "type": "float"},
            {"name": "stop_loss", "label": "止损比例", "default": 0.95, "min": 0.85, "max": 0.99, "type": "float"},
            {"name": "max_hold", "label": "最大持有天数", "default": 20, "min": 5, "max": 60, "type": "int"},
        ],
    ),
    # ===== 新增策略（第二阶段） =====
    "mean_reversion": StrategyInfo(
        key="mean_reversion",
        name="均值回归策略",
        description="基于价格偏离均值的反转策略，适合震荡市场",
        category="trading",
        strategy_cls=MeanReversionStrategy,
        params=[
            {"name": "period", "label": "均值周期", "default": 20, "min": 10, "max": 50, "type": "int"},
            {"name": "std_dev", "label": "标准差倍数", "default": 2.0, "min": 1.0, "max": 3.0, "type": "float"},
            {"name": "rsi_period", "label": "RSI周期", "default": 14, "min": 5, "max": 30, "type": "int"},
            {"name": "rsi_oversold", "label": "RSI超卖线", "default": 30, "min": 10, "max": 50, "type": "int"},
            {"name": "rsi_overbought", "label": "RSI超买线", "default": 70, "min": 50, "max": 90, "type": "int"},
            {"name": "max_hold_days", "label": "最大持有天数", "default": 10, "min": 3, "max": 30, "type": "int"},
            {"name": "profit_target", "label": "止盈目标", "default": 0.03, "min": 0.01, "max": 0.10, "type": "float"},
            {"name": "stop_loss", "label": "止损比例", "default": 0.02, "min": 0.01, "max": 0.05, "type": "float"},
        ],
    ),
    "momentum": StrategyInfo(
        key="momentum",
        name="动量策略",
        description="基于价格动量的趋势策略，适合趋势市场",
        category="trading",
        strategy_cls=MomentumStrategy,
        params=[
            {"name": "momentum_period", "label": "动量周期", "default": 20, "min": 10, "max": 50, "type": "int"},
            {"name": "ma_period", "label": "趋势均线周期", "default": 50, "min": 20, "max": 100, "type": "int"},
            {"name": "momentum_threshold", "label": "动量阈值", "default": 0.02, "min": 0.01, "max": 0.05, "type": "float"},
            {"name": "profit_target", "label": "止盈目标", "default": 0.05, "min": 0.02, "max": 0.15, "type": "float"},
            {"name": "stop_loss", "label": "止损比例", "default": 0.03, "min": 0.01, "max": 0.08, "type": "float"},
            {"name": "trailing_stop", "label": "追踪止损", "default": 0.02, "min": 0.01, "max": 0.05, "type": "float"},
            {"name": "max_hold_days", "label": "最大持有天数", "default": 30, "min": 10, "max": 60, "type": "int"},
            {"name": "position_size", "label": "仓位比例", "default": 0.3, "min": 0.1, "max": 0.5, "type": "float"},
        ],
    ),
    "grid_trading": StrategyInfo(
        key="grid_trading",
        name="网格交易策略",
        description="适合震荡市场的网格交易策略，持续低买高卖",
        category="trading",
        strategy_cls=GridTradingStrategy,
        params=[
            {"name": "grid_count", "label": "网格数量（单边）", "default": 10, "min": 5, "max": 20, "type": "int"},
            {"name": "grid_spacing", "label": "网格间距", "default": 0.01, "min": 0.005, "max": 0.03, "type": "float"},
            {"name": "base_position", "label": "基准仓位", "default": 0.5, "min": 0.2, "max": 0.8, "type": "float"},
            {"name": "single_position", "label": "单格交易仓位", "default": 0.05, "min": 0.02, "max": 0.10, "type": "float"},
            {"name": "center_type", "label": "中枢类型", "default": "dynamic", "options": ["fixed", "dynamic"], "type": "select"},
            {"name": "center_price", "label": "固定中枢价格", "default": 0.0, "min": 0, "max": 10000, "type": "float"},
            {"name": "dynamic_period", "label": "动态中枢周期", "default": 20, "min": 10, "max": 50, "type": "int"},
            {"name": "min_spread", "label": "最小价差", "default": 0.005, "min": 0.002, "max": 0.01, "type": "float"},
            {"name": "max_position", "label": "最大仓位", "default": 0.95, "min": 0.5, "max": 1.0, "type": "float"},
        ],
    ),
    # ===== 阶段2：智能策略升级 =====
    "adaptive": StrategyInfo(
        key="adaptive",
        name="市场状态自适应策略",
        description="根据市场状态（牛市/震荡/熊市）自动调整双均线参数和仓位",
        category="hybrid",
        strategy_cls=AdaptiveStrategy,
        params=[
            {"name": "bull_fast", "label": "牛市短期均线", "default": 5, "min": 1, "max": 20, "type": "int"},
            {"name": "bull_slow", "label": "牛市长期均线", "default": 20, "min": 5, "max": 60, "type": "int"},
            {"name": "bear_fast", "label": "熊市短期均线", "default": 10, "min": 5, "max": 30, "type": "int"},
            {"name": "bear_slow", "label": "熊市长期均线", "default": 60, "min": 20, "max": 120, "type": "int"},
            {"name": "position_scale", "label": "动态调整仓位", "default": True, "type": "bool"},
        ],
    ),
    "smart_exit": StrategyInfo(
        key="smart_exit",
        name="智能退出策略",
        description="基于双均线策略，集成追踪止损、时间退出、硬止损等多种退出机制",
        category="trading",
        strategy_cls=SmartExitStrategy,
        params=[
            {"name": "fast", "label": "短期均线周期", "default": 5, "min": 1, "max": 60, "type": "int"},
            {"name": "slow", "label": "长期均线周期", "default": 20, "min": 5, "max": 250, "type": "int"},
            {"name": "trailing_stop_pct", "label": "追踪止损%", "default": 8.0, "min": 3.0, "max": 20.0, "type": "float"},
            {"name": "time_exit_days", "label": "时间退出天数", "default": 45, "min": 10, "max": 90, "type": "int"},
            {"name": "hard_stop_pct", "label": "硬止损%", "default": 12.0, "min": 5.0, "max": 20.0, "type": "float"},
            {"name": "profit_target", "label": "止盈目标", "default": 0.2, "min": 0.1, "max": 0.5, "type": "float"},
        ],
    ),
    "factor_score": StrategyInfo(
        key="factor_score",
        name="因子评分选股策略",
        description="基于多因子评分（动量、波动率、成交量、均线）的选股策略",
        category="screening",
        strategy_cls=FactorScoreStrategy,
        params=[
            {"name": "factor_weights", "label": "因子权重", "default": [0.3, 0.3, 0.2, 0.2], "type": "list"},
            {"name": "top_n", "label": "选前N名", "default": 5, "min": 1, "max": 20, "type": "int"},
            {"name": "rebalance_days", "label": "调仓周期（天）", "default": 20, "min": 5, "max": 60, "type": "int"},
        ],
    ),
    # ===== CCI+MACD 双因子短线选股（30分钟周期，仅选股/监控，不回测） =====
    "cci_macd_selection": StrategyInfo(
        key="cci_macd_selection",
        name="CCI+MACD双因子选股",
        description="30分钟周期 CCI(14)>300 且 MACD零线附近金叉，剔除停牌/ST/成交额<5亿。短线选股，不含回测。",
        category="screening",
        strategy_cls=CCIMACDSelectionStrategy,
        params=[
            {"name": "cci_threshold", "label": "CCI阈值", "default": 300, "min": 100, "max": 500, "step": 10, "type": "float"},
            {"name": "min_amount", "label": "最小成交额(亿)", "default": 5.0, "min": 1.0, "max": 50.0, "step": 0.5, "type": "float"},
            {"name": "zero_line_band", "label": "零线带宽", "default": 0.5, "min": 0.1, "max": 5.0, "step": 0.1, "type": "float"},
            {"name": "period", "label": "选股周期(分钟)", "default": "30", "options": ["15", "30", "60"], "type": "select"},
        ],
    ),
}


# ==================== 可视化「智能推荐」默认规则 ====================
# 这些规则在用户进入可视化模式并选择某预置策略时，自动预填到条件编辑区。
# 字段严格对齐前端 VisualRule / ConditionLeaf 模型（见 frontend/src/components/visual-editor/types.ts）。
# 注意：dif/dea 在指标库里不是独立指标，DIF上穿DEA 用 macd_cross(line=gold) 表达；
#       MACD柱介于某区间用 macd(line=macd, operator=between) 表达。

def _c(indicator, line, operator, target_type="value", target_value=None,
        target_param2=None, params=None, timeframe="daily", target_indicator=None,
        recommended_indicators=None):
    """构造单个条件叶子（与前端 ConditionLeaf 字段一致）。"""
    return {
        "type": "condition",
        "indicator": indicator,
        "line": line,
        "params": params or {},
        "timeframe": timeframe,
        "operator": operator,
        "targetType": target_type,
        "targetValue": target_value,
        "targetParam2": target_param2,
        "targetIndicator": target_indicator,
    }


# 各策略的推荐规则（只挂到能精确映射到现有 ConditionLeaf 模型的策略）。
# 说明：现有模型 targetType=indicator 仅支持「目标指标 key」，不支持目标 line/period，
# 因此「双均线交叉」「价格穿越布林带」这类需「两列比较」的策略无法精确表达，暂不纳入推荐。
# recommended_indicators 用于前端指标库「两段式」：第一段高亮推荐，第二段（更多指标）折叠。
_VISUAL_DEFAULTS: dict[str, dict] = {
    # MACD：DIF 上穿 DEA（金叉）—— macd_cross 输出 1=金叉
    "macd": {
        "operator": "AND",
        "items": [
            _c("macd_cross", "gold", "equal", target_type="value", target_value=1,
               params={"fast": 12, "slow": 26, "signal": 9}),
        ],
        "recommended_indicators": ["macd_cross", "macd", "rsi", "ma_arrangement", "vol"],
    },
    # RSI：RSI(14) 小于 30（超卖）
    "rsi": {
        "operator": "AND",
        "items": [
            _c("rsi", "rsi", "less", target_type="value", target_value=30,
               params={"period": 14}),
        ],
        "recommended_indicators": ["rsi", "wr", "cci", "bias", "kdj_bull", "macd_cross"],
    },
    # KDJ：K上穿D（金叉）—— kdj_bull 输出 1=金叉
    "kdj": {
        "operator": "AND",
        "items": [
            _c("kdj_bull", "gold", "equal", target_type="value", target_value=1,
               params={"period": 9, "smooth_k": 3, "smooth_d": 3}),
        ],
        "recommended_indicators": ["kdj_bull", "kdj", "macd_cross", "rsi", "ma_arrangement"],
    },
    # 均线多头排列 —— ma_arrangement 输出 1=成立
    "ma_bullish": {
        "operator": "AND",
        "items": [
            _c("ma_arrangement", "bull", "equal", target_type="value", target_value=1,
               params={"fast": 5, "mid": 10, "slow": 20}),
        ],
        "recommended_indicators": ["ma_arrangement", "ma", "ema", "macd_cross", "vol"],
    },
}


# 把默认规则挂到对应策略上，并回填 preset_key（默认与策略 key 一致）
for _k, _v in _VISUAL_DEFAULTS.items():
    if _k in REGISTRY:
        REGISTRY[_k].visual_defaults = _v
        REGISTRY[_k].preset_key = _k


def get_strategy(key: str) -> StrategyInfo:
    """获取策略信息，支持预置策略和自定义策略。"""
    # 先查预置策略
    if key in REGISTRY:
        return REGISTRY[key]
    
    # 再查自定义策略
    try:
        strategy_cls = load_custom_strategy_class(key)
        
        # 获取自定义策略元信息
        custom_list = list_custom_strategies()
        custom_info = next((s for s in custom_list if s["key"] == key), None)
        
        if custom_info:
            return StrategyInfo(
                key=key,
                name=custom_info["name"],
                description=custom_info["description"],
                strategy_cls=strategy_cls,
                is_custom=True,
            )
    except ValueError:
        pass
    
    raise ValueError(f"未知策略: {key}，可选: {list(REGISTRY.keys())} 及自定义策略")


def list_strategies() -> list[dict]:
    """返回所有策略的元信息（不含 strategy_cls，便于序列化）。"""
    # 预置策略
    result = [
        {
            "key": s.key,
            "name": s.name,
            "description": s.description,
            "category": s.category,
            "params": s.params,
            "type": "preset",
        }
        for s in REGISTRY.values()
    ]

    # 自定义策略
    try:
        custom_list = list_custom_strategies()
        for custom_info in custom_list:
            result.append({
                "key": custom_info["key"],
                "name": custom_info["name"],
                "description": custom_info["description"],
                "category": "trading",  # 自定义策略默认归为操盘策略
                "params": [],
                "type": "custom",
            })
    except Exception:
        pass

    return result
