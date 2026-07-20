"""智能仓位管理模块：根据信号强度和市场状态动态调整仓位。

参考量化策略中的仓位管理公式，结合信号等级、市场状态、量化参与度等因素。
"""

from __future__ import annotations

from enum import Enum
from typing import Optional


class SignalGrade(Enum):
    """信号等级枚举。"""
    A = "A"   # 强信号：高确定性
    B = "B"   # 中信号：中等确定性
    C = "C"   # 弱信号：低确定性


class MarketState(Enum):
    """市场状态枚举。"""
    BULL = "bull"       # 牛市
    NORMAL = "normal"   # 震荡
    BEAR = "bear"       # 熊市


class QuantParticipation(Enum):
    """量化参与度枚举。"""
    HIGH = "high"   # 高：量化资金主导
    MID = "mid"     # 中：量化与主观并存
    LOW = "low"     # 低：主观资金主导


def calc_position_size(
    base_size: float,
    signal_grade: str = "B",
    market_state: str = "normal",
    quant_participation: str = "mid",
    volatility: str = "normal",
) -> float:
    """计算仓位大小。
    
    根据信号等级、市场状态、量化参与度、波动率等因素，
    动态调整仓位大小。
    
    Args:
        base_size: 基础仓位（0-1之间，如0.3表示30%仓位）
        signal_grade: 信号等级（A/B/C）
        market_state: 市场状态（bull/normal/bear）
        quant_participation: 量化参与度（high/mid/low）
        volatility: 波动率状态（high/normal/low）
        
    Returns:
        调整后仓位（0-1之间）
    """
    # 参数验证
    if base_size < 0 or base_size > 1:
        base_size = max(0.0, min(1.0, base_size))
    
    signal_grade = signal_grade.upper() if signal_grade else "B"
    market_state = market_state.lower() if market_state else "normal"
    quant_participation = quant_participation.lower() if quant_participation else "mid"
    volatility = volatility.lower() if volatility else "normal"
    
    # 信号等级乘数
    grade_mult = {
        SignalGrade.A.value: 1.2,
        SignalGrade.B.value: 1.0,
        SignalGrade.C.value: 0.6,
    }.get(signal_grade, 1.0)
    
    # 市场状态乘数
    market_mult = {
        MarketState.BULL.value: 1.0,
        MarketState.NORMAL.value: 0.7,
        MarketState.BEAR.value: 0.3,
    }.get(market_state, 0.7)
    
    # 量化参与度乘数（量化主导时降低仓位，避免同质化竞争）
    quant_mult = {
        QuantParticipation.HIGH.value: 0.6,
        QuantParticipation.MID.value: 0.8,
        QuantParticipation.LOW.value: 1.0,
    }.get(quant_participation, 0.8)
    
    # 波动率乘数（高波动时降低仓位）
    volatility_mult = {
        "high": 0.6,
        "normal": 1.0,
        "low": 1.2,
    }.get(volatility, 1.0)
    
    # 计算最终仓位
    position_size = base_size * grade_mult * market_mult * quant_mult * volatility_mult
    
    # 限制仓位范围 [0, 1]
    return max(0.0, min(1.0, position_size))


def calc_kelly_position(
    win_rate: float,
    avg_win: float,
    avg_loss: float,
    max_position: float = 0.3,
) -> float:
    """使用凯利公式计算最优仓位。
    
    凯利公式：f = (p * b - q) / b
    其中 p = 胜率, q = 1-p, b = 盈亏比(avg_win/avg_loss)
    
    Args:
        win_rate: 胜率（0-1之间）
        avg_win: 平均盈利（正数）
        avg_loss: 平均亏损（正数，取绝对值）
        max_position: 最大仓位限制（默认0.3）
        
    Returns:
        最优仓位（0-1之间）
    """
    if avg_loss == 0:
        return 0.0
    
    q = 1 - win_rate
    b = avg_win / avg_loss
    
    # 凯利公式
    kelly = (win_rate * b - q) / b
    
    # 限制凯利仓位（实际中通常使用半凯利或更低）
    kelly = max(0.0, min(kelly, max_position))
    
    return kelly


def calc_volatility_position(
    base_size: float,
    current_volatility: float,
    target_volatility: float = 0.15,
    max_position: float = 0.5,
) -> float:
    """根据波动率调整仓位（目标波动率方法）。
    
    当市场波动率高于目标波动率时，降低仓位；
    当市场波动率低于目标波动率时，增加仓位。
    
    Args:
        base_size: 基础仓位
        current_volatility: 当前波动率（年化）
        target_volatility: 目标波动率（默认0.15，即15%）
        max_position: 最大仓位限制
        
    Returns:
        调整后仓位
    """
    if current_volatility == 0:
        return base_size
    
    # 波动率调整因子
    vol_mult = target_volatility / current_volatility
    
    # 限制调整因子范围 [0.2, 2.0]
    vol_mult = max(0.2, min(2.0, vol_mult))
    
    position_size = base_size * vol_mult
    
    return max(0.0, min(max_position, position_size))


def calc_atr_position(
    capital: float,
    atr_value: float,
    atr_multiplier: float = 2.0,
    risk_percent: float = 0.01,
    current_price: float = 0.0,
) -> int:
    """根据ATR（平均真实波幅）计算交易数量。
    
    基于风险的仓位管理：每笔交易风险不超过总资金的固定比例。
    
    Args:
        capital: 总资金
        atr_value: ATR值
        atr_multiplier: ATR乘数（止损距离 = ATR * multiplier）
        risk_percent: 风险比例（默认0.01，即1%）
        current_price: 当前价格（用于计算股数）
        
    Returns:
        交易数量（股数）
    """
    if atr_value == 0 or current_price == 0:
        return 0
    
    # 计算止损距离
    stop_distance = atr_value * atr_multiplier
    
    # 计算允许的最大亏损金额
    max_loss = capital * risk_percent
    
    # 计算股数
    shares = int(max_loss / stop_distance)
    
    # 根据当前价格计算实际市值
    if shares > 0 and current_price > 0:
        # 确保不超过基础仓位限制
        max_shares = int(capital * 0.3 / current_price)
        shares = min(shares, max_shares)
    
    return max(0, shares)


class PositionSizer:
    """仓位计算器：封装多种仓位管理策略。"""
    
    def __init__(
        self,
        base_size: float = 0.3,
        max_position: float = 0.5,
        risk_percent: float = 0.01,
    ):
        """初始化仓位计算器。
        
        Args:
            base_size: 基础仓位（默认0.3）
            max_position: 最大仓位（默认0.5）
            risk_percent: 风险比例（默认0.01）
        """
        self.base_size = base_size
        self.max_position = max_position
        self.risk_percent = risk_percent
    
    def calc_position(
        self,
        signal_grade: str = "B",
        market_state: str = "normal",
        quant_participation: str = "mid",
        volatility: str = "normal",
    ) -> float:
        """计算仓位大小（综合方法）。"""
        return calc_position_size(
            base_size=self.base_size,
            signal_grade=signal_grade,
            market_state=market_state,
            quant_participation=quant_participation,
            volatility=volatility,
        )
    
    def calc_kelly(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
    ) -> float:
        """计算凯利仓位。"""
        return calc_kelly_position(
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            max_position=self.max_position,
        )
    
    def calc_volatility(
        self,
        base_size: float,
        current_volatility: float,
        target_volatility: float = 0.15,
    ) -> float:
        """计算波动率调整仓位。"""
        return calc_volatility_position(
            base_size=base_size,
            current_volatility=current_volatility,
            target_volatility=target_volatility,
            max_position=self.max_position,
        )
    
    def calc_atr(
        self,
        capital: float,
        atr_value: float,
        atr_multiplier: float = 2.0,
        current_price: float = 0.0,
    ) -> int:
        """计算ATR仓位（股数）。"""
        return calc_atr_position(
            capital=capital,
            atr_value=atr_value,
            atr_multiplier=atr_multiplier,
            risk_percent=self.risk_percent,
            current_price=current_price,
        )


if __name__ == "__main__":
    # 测试
    sizer = PositionSizer(base_size=0.3)
    
    # 测试不同场景
    print("=== 仓位计算测试 ===")
    
    # 牛市场景
    pos = sizer.calc_position(
        signal_grade="A",
        market_state="bull",
        quant_participation="low",
        volatility="normal",
    )
    print(f"牛市+强信号: {pos:.2%}")
    
    # 熊市场景
    pos = sizer.calc_position(
        signal_grade="B",
        market_state="bear",
        quant_participation="high",
        volatility="high",
    )
    print(f"熊市+高波动: {pos:.2%}")
    
    # 凯利公式
    kelly = sizer.calc_kelly(
        win_rate=0.55,
        avg_win=0.05,
        avg_loss=0.03,
    )
    print(f"凯利仓位: {kelly:.2%}")
    
    # 波动率调整
    vol_pos = sizer.calc_volatility(
        base_size=0.3,
        current_volatility=0.25,
        target_volatility=0.15,
    )
    print(f"波动率调整仓位: {vol_pos:.2%}")
