"""均线多头排列策略：5日/10日/20日三线向上排列时买入。

均线多头排列定义：
    - 5日均线 > 10日均线 > 20日均线
    - 且三条均线都向上倾斜（当前值大于前一日值）

当均线走平或死叉时卖出。
"""
import backtrader as bt

from .base import BaseStrategy


class MABullishStrategy(BaseStrategy):
    """均线多头排列策略。

    参数：
        fast: 短期均线周期（默认5）
        mid: 中期均线周期（默认10）
        slow: 长期均线周期（默认20）
        hold_days: 最小持有天数（默认3）
    """

    params = (
        ("fast", 5),
        ("mid", 10),
        ("slow", 20),
        ("hold_days", 3),
        ("printlog", False),
    )

    def __init__(self):
        super().__init__()
        self.ma_fast = bt.indicators.SimpleMovingAverage(
            self.data.close, period=self.params.fast
        )
        self.ma_mid = bt.indicators.SimpleMovingAverage(
            self.data.close, period=self.params.mid
        )
        self.ma_slow = bt.indicators.SimpleMovingAverage(
            self.data.close, period=self.params.slow
        )
        self.bar_count = 0

    def next(self):
        if self.order:
            return

        self.bar_count += 1

        # 均线多头排列条件：fast > mid > slow
        bullish = (
            self.ma_fast[0] > self.ma_mid[0]
            and self.ma_mid[0] > self.ma_slow[0]
        )

        # 均线向上倾斜（当前值大于前一日值）
        ma_rising = (
            self.ma_fast[0] > self.ma_fast[-1]
            and self.ma_mid[0] > self.ma_mid[-1]
            and self.ma_slow[0] > self.ma_slow[-1]
        )

        if not self.position:
            # 多头排列且均线向上时买入
            if bullish and ma_rising:
                self.order = self.buy()
        else:
            # 持有至少 hold_days 天后，多头排列破坏或均线向下时卖出
            if self.bar_count > self.params.hold_days:
                bearish = (
                    self.ma_fast[0] < self.ma_mid[0]
                    or self.ma_mid[0] < self.ma_slow[0]
                )
                ma_falling = self.ma_fast[0] < self.ma_fast[-1]
                if bearish or ma_falling:
                    self.order = self.close()
