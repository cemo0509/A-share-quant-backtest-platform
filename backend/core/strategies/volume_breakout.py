"""成交量突破策略：放量突破前高时买入。

买入条件：
    - 当日收盘价 > N日内最高价（突破前高）
    - 当日成交量 > M日均量的 K 倍（放量）

卖出条件：
    - 收盘价跌破入场价的止损线
    - 或持有达到最大天数
"""
import backtrader as bt

from .base import BaseStrategy


class VolumeBreakoutStrategy(BaseStrategy):
    """成交量突破策略。

    参数：
        lookback: 突破观察周期（默认20）
        volume_ma_period: 均量线周期（默认5）
        volume_ratio: 放量倍数（默认1.5）
        stop_loss: 止损比例（默认0.95，即5%止损）
        max_hold: 最大持有天数（默认20）
    """

    params = (
        ("lookback", 20),
        ("volume_ma_period", 5),
        ("volume_ratio", 1.5),
        ("stop_loss", 0.95),
        ("max_hold", 20),
        ("printlog", False),
    )

    def __init__(self):
        super().__init__()
        # 前N日最高价（不含当日），使用 -1 获取前一个bar的值
        self.highest = bt.indicators.Highest(
            self.data.high, period=self.params.lookback
        )
        # 均量线
        self.vol_ma = bt.indicators.SimpleMovingAverage(
            self.data.volume, period=self.params.volume_ma_period
        )
        self.bar_count = 0
        self.entry_bar = 0
        self.entry_price = 0

    def next(self):
        if self.order:
            return

        self.bar_count += 1

        if not self.position:
            # 突破前高（当日最高价 > N日内最高价）+ 放量
            breakout = self.data.high[0] > self.highest[0]
            volume_surge = self.data.volume[0] > self.vol_ma[0] * self.params.volume_ratio

            if breakout and volume_surge:
                self.order = self.buy()
                self.entry_bar = self.bar_count
                self.entry_price = self.data.close[0]
        else:
            # 止损：收盘价跌破入场价的止损线
            if self.data.close[0] < self.entry_price * self.params.stop_loss:
                self.order = self.close()
                return

            # 最大持有天数止损
            if self.bar_count - self.entry_bar >= self.params.max_hold:
                self.order = self.close()
                return

            # 收盘价跌破近期最低点（可选卖出信号）
            # 这里使用入场后的最低价作为跟踪止损
            if not hasattr(self, 'lowest_since_entry'):
                self.lowest_since_entry = self.data.low[0]
            else:
                self.lowest_since_entry = min(self.lowest_since_entry, self.data.low[0])
            
            # 收盘价跌破入场后最低价的5%时卖出（跟踪止损）
            if self.data.close[0] < self.lowest_since_entry * 1.05:
                self.order = self.close()
