"""KDJ 策略：K线和D线金叉死叉买入卖出。

K线从下方向上穿过D线为金叉，买入信号；
K线从上方向下穿过D线为死叉，卖出信号。
"""
import backtrader as bt

from .base import BaseStrategy


class KDJStrategy(BaseStrategy):
    """KDJ 金叉死叉策略。

    参数：
        period: KDJ周期（默认9）
        smooth_k: K值平滑参数（默认3）
        smooth_d: D值平滑参数（默认3）
        oversold: 超卖阈值（默认20）
        overbought: 超买阈值（默认80）
    """

    params = (
        ("period", 9),
        ("smooth_k", 3),
        ("smooth_d", 3),
        ("oversold", 20),
        ("overbought", 80),
        ("printlog", False),
    )

    def __init__(self):
        super().__init__()
        # Backtrader 的 Stochastic 指标返回 %K 和 %D
        self.stoch = bt.indicators.Stochastic(
            self.data,
            period=self.params.period,
            period_dfast=self.params.smooth_k,
            period_dslow=self.params.smooth_d,
        )
        # self.stoch.percK 是 K 线，self.stoch.percD 是 D 线
        self.crossover = bt.indicators.CrossOver(self.stoch.percK, self.stoch.percD)

    def next(self):
        if self.order:
            return

        if not self.position:
            # K线上穿D线（金叉）时买入
            if self.crossover > 0:
                self.order = self.buy()
        else:
            # K线下穿D线（死叉）或K线在超买区，卖出
            if self.crossover < 0 or self.stoch.percK[0] > self.params.overbought:
                self.order = self.close()
