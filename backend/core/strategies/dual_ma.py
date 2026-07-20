"""双均线策略：短期均线上穿长期均线买入（金叉），下穿卖出（死叉）。

对应调研报告 2.3 节「常见策略类型」中的双均线策略。
"""
import backtrader as bt

from .base import BaseStrategy


class DualMAStrategy(BaseStrategy):
    """双均线交叉策略。

    参数：
        fast: 短期均线周期（默认5）
        slow: 长期均线周期（默认20）
    """

    params = (
        ("fast", 5),
        ("slow", 20),
        ("printlog", False),
    )

    def __init__(self):
        super().__init__()
        self.fast_ma = bt.indicators.SMA(self.data.close, period=self.params.fast)
        self.slow_ma = bt.indicators.SMA(self.data.close, period=self.params.slow)
        # 金叉信号：fast 上穿 slow
        self.crossover = bt.indicators.CrossOver(self.fast_ma, self.slow_ma)

    def next(self):
        if self.order:
            return

        if not self.position:
            # 金叉买入
            if self.crossover > 0:
                self.order = self.buy()
        else:
            # 死叉卖出
            if self.crossover < 0:
                self.order = self.sell()
