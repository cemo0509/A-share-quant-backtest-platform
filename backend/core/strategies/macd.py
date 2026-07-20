"""MACD 策略：MACD 金叉买入，死叉卖出。

对应调研报告 2.3 节中的 MACD 策略。
"""
import backtrader as bt

from .base import BaseStrategy


class MACDStrategy(BaseStrategy):
    """MACD 金叉死叉策略。

    参数：
        fast_period: 快线EMA周期（默认12）
        slow_period: 慢线EMA周期（默认26）
        signal_period: 信号线周期（默认9）
    """

    params = (
        ("fast_period", 12),
        ("slow_period", 26),
        ("signal_period", 9),
        ("printlog", False),
    )

    def __init__(self):
        super().__init__()
        self.macd = bt.indicators.MACD(
            self.data.close,
            period_me1=self.params.fast_period,
            period_me2=self.params.slow_period,
            period_signal=self.params.signal_period,
        )
        # MACD 柱上穿 0 轴为金叉
        self.crossover = bt.indicators.CrossOver(self.macd.macd, self.macd.signal)

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
