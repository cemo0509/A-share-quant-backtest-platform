"""RSI 超买超卖策略：RSI<30 买入，RSI>70 卖出。

对应调研报告 2.3 节中的 RSI 超买超卖策略。
"""
import backtrader as bt

from .base import BaseStrategy


class RSIStrategy(BaseStrategy):
    """RSI 超买超卖策略。

    参数：
        period: RSI 周期（默认14）
        oversold: 超卖阈值（默认30）
        overbought: 超买阈值（默认70）
    """

    params = (
        ("period", 14),
        ("oversold", 30),
        ("overbought", 70),
        ("printlog", False),
    )

    def __init__(self):
        super().__init__()
        self.rsi = bt.indicators.RSI(self.data.close, period=self.params.period)

    def next(self):
        if self.order:
            return

        if not self.position:
            # RSI 低于超卖线买入
            if self.rsi[0] < self.params.oversold:
                self.order = self.buy()
        else:
            # RSI 高于超买线卖出
            if self.rsi[0] > self.params.overbought:
                self.order = self.sell()
