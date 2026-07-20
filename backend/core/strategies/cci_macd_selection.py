"""CCI+MACD 双因子短线选股策略（30分钟周期）。

选股条件（同时满足）：
    - CCI(14) > 阈值（默认 300）
    - MACD 在零线附近上穿（金叉），|MACD| <= 零线带宽

注意：本策略 category=screening，只用于选股池扫描与盘中监控，不进入回测页面。
实际选股判断走 stock_scan.py 的 _scan_cci_macd（直接指标计算），此类作为注册规范与备用。
"""
import backtrader as bt

from .base import BaseStrategy


class CCIMACDSelectionStrategy(BaseStrategy):
    """CCI+MACD 双因子选股策略。

    参数：
        cci_period: CCI 周期（默认14，系统默认不修改）
        cci_threshold: CCI 阈值（默认300）
        macd_fast/macd_slow/macd_signal: MACD 参数
        zero_line_band: 零线附近判定带宽
        min_amount: 成交额阈值（元）
    """

    params = (
        ("cci_period", 14),
        ("cci_threshold", 300),
        ("macd_fast", 12),
        ("macd_slow", 26),
        ("macd_signal", 9),
        ("zero_line_band", 0.5),
        ("min_amount", 500000000),
        ("exclude_st", True),
        ("exclude_suspended", True),
        ("printlog", False),
    )

    def __init__(self):
        super().__init__()
        self.cci = bt.indicators.CommodityChannelIndex(
            self.data, period=self.p.cci_period
        )
        self.macd = bt.indicators.MACD(
            self.data.close,
            period_me1=self.p.macd_fast,
            period_me2=self.p.macd_slow,
            period_signal=self.p.macd_signal,
        )
        self.macd_cross = bt.indicators.CrossOver(self.macd.macd, self.macd.signal)

    def next(self):
        if self.order:
            return

        cci_ok = self.cci[0] > self.p.cci_threshold
        macd_ok = (
            self.macd_cross[0] > 0
            and abs(self.macd.macd[0]) <= self.p.zero_line_band
        )

        if not self.position:
            if cci_ok and macd_ok:
                self.order = self.buy()
        else:
            # 简单退出：MACD 死叉即离场（选股场景通常不触发）
            if self.macd_cross[0] < 0:
                self.order = self.close()
