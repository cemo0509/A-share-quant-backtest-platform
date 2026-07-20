"""布林带策略：价格触及下轨买入，触及上轨卖出。

对应调研报告 2.3 节中的布林带策略。
"""
import backtrader as bt

from .base import BaseStrategy


class BollingerStrategy(BaseStrategy):
    """布林带策略。

    参数：
        period: 布林带周期（默认20）
        dev: 标准差倍数（默认2）
    """

    params = (
        ("period", 20),
        ("dev", 2.0),
        ("printlog", False),
    )

    def __init__(self):
        super().__init__()
        self.boll = bt.indicators.BollingerBands(
            self.data.close, period=self.params.period, devfactor=self.params.dev
        )

    def next(self):
        if self.order:
            return

        if not self.position:
            # 价格触及下轨买入
            if self.data.close[0] < self.boll.lines.bot[0]:
                self.order = self.buy()
        else:
            # 价格触及上轨卖出
            if self.data.close[0] > self.boll.lines.top[0]:
                self.order = self.sell()
