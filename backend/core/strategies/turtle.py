"""海龟交易策略：价格突破N日最高点买入，跌破最低点卖出。

对应调研报告中的海龟交易法则。
"""
import backtrader as bt

from .base import BaseStrategy


class TurtleStrategy(BaseStrategy):
    """海龟交易策略。
    
    参数：
        n: 突破周期（默认20，即Donchian通道）
        add_n: 加仓周期（默认10）
        risk_percent: 风险比例（默认0.01，即1%）
    """
    
    params = (
        ("n", 20),
        ("add_n", 10),
        ("risk_percent", 0.01),
        ("printlog", False),
    )
    
    def __init__(self):
        super().__init__()
        # Donchian通道：上轨=最高价，下轨=最低价
        self.donchian_high = bt.indicators.Highest(
            self.data.high, period=self.params.n
        )
        self.donchian_low = bt.indicators.Lowest(
            self.data.low, period=self.params.n
        )
        
        # 加仓通道
        self.donchian_high_add = bt.indicators.Highest(
            self.data.high, period=self.params.add_n
        )
        self.donchian_low_add = bt.indicators.Lowest(
            self.data.low, period=self.params.add_n
        )
        
        # ATR 指标（在 __init__ 中创建，不能在 next 中创建）
        self.atr = bt.indicators.ATR(self.data, period=20)

        # 海龟加仓：最多加仓次数（经典海龟为 4 次）
        self.max_add = 3
        self.add_count = 0

        self.order = None

    def next(self):
        if self.order:
            return

        atr_val = self.atr[0]

        # 没有持仓：突破上轨买入（首仓）
        if not self.position:
            if self.data.high[0] >= self.donchian_high[-1]:
                # 计算仓位大小（基于ATR的风险管理）
                if atr_val > 0:
                    # A 股申报数量必须是 100 股（1 手）的整数倍
                    size = int(self.broker.getvalue() * self.params.risk_percent / atr_val) // 100 * 100
                    size = max(size, 100)  # 至少1手
                else:
                    size = 100

                self.add_count = 0
                self.order = self.buy(size=size)

        # 已有持仓：突破下轨清仓，或突破加仓通道则加仓
        else:
            # 跌破下轨：全部平仓
            if self.data.low[0] <= self.donchian_low[-1]:
                self.order = self.close()
                return

            # 加仓：价格再创新高（突破 add_n 周期高点）且未达加仓上限
            if (self.add_count < self.max_add
                    and atr_val > 0
                    and self.data.high[0] >= self.donchian_high_add[-1]):
                # A 股申报数量必须是 100 股（1 手）的整数倍
                size = int(self.broker.getvalue() * self.params.risk_percent / atr_val) // 100 * 100
                size = max(size, 100)  # 至少1手
                self.add_count += 1
                self.order = self.buy(size=size)
