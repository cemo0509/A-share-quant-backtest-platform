"""动量策略 - 基于价格动量的趋势策略"""
from __future__ import annotations
import logging

import backtrader as bt
import numpy as np


class MomentumStrategy(bt.Strategy):
    """动量策略
    
    策略逻辑：
    1. 计算动量指标（N日收益率）
    2. 动量 > 阈值时买入（上涨趋势）
    3. 动量 < -阈值时卖出（下跌趋势）
    4. 结合均线确认趋势
    
    适用场景：趋势市场
    风险：震荡市场中频繁交易
    """
    
    params = (
        ("momentum_period", 20),    # 动量计算周期
        ("ma_period", 50),          # 趋势确认均线
        ("momentum_threshold", 0.02),  # 动量阈值（2%）
        ("profit_target", 0.05),    # 止盈目标（5%）
        ("stop_loss", 0.03),        # 止损比例（3%）
        ("trailing_stop", 0.02),    # 追踪止损（2%）
        ("max_hold_days", 30),      # 最大持有天数
        ("position_size", 0.3),     # 仓位比例
        ("printlog", False),
    )
    
    def __init__(self):
        """初始化指标"""
        # 动量指标（N日收益率）
        self.momentum = bt.indicators.Momentum(
            self.data.close, period=self.params.momentum_period
        )
        
        # 动量变化率（加速度）：不使用 bt.indicators.RateOfChange，
        # 因为其内部 (v - v_prev)/v_prev 在动量值为 0 时会触发 ZeroDivisionError。
        # 改用动量自身的环比变化判断动能是否增强（在 next() 中以安全方式比较）。
        self._prev_momentum = None

        # 趋势确认均线
        self.ma = bt.indicators.SimpleMovingAverage(
            self.data.close, period=self.params.ma_period
        )
        
        # ATR（用于动态止损）
        self.atr = bt.indicators.AverageTrueRange(period=14)
        
        # 记录
        self.buy_price = None
        self.highest_price = None
        self.hold_days = 0
        self.order = None
        
    def notify_order(self, order):
        """订单状态通知"""
        if order.status in [order.Submitted, order.Accepted]:
            return
        
        if order.status in [order.Completed]:
            if order.isbuy():
                self.buy_price = order.executed.price
                self.highest_price = order.executed.price
                self.hold_days = 0
                if self.params.printlog:
                    self.log(f'买入执行: 价格={order.executed.price:.2f}, 数量={order.executed.size:.0f}')
            else:
                if self.params.printlog:
                    self.log(f'卖出执行: 价格={order.executed.price:.2f}, 数量={order.executed.size:.0f}, 收益={order.executed.pnl:.2f}')
                self.buy_price = None
                self.highest_price = None
                self.hold_days = 0
                
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            if self.params.printlog:
                self.log('订单取消/拒绝')
        
        self.order = None
    
    def _momentum_pct(self) -> float:
        """动量收益率（小数，如 0.0526 表示 5.26%）。

        backtrader 的 ``Momentum`` 指标 = ``close[0] - close[-period]``，
        单位是**价格差（元）**，不是百分比。此前代码用 ``momentum / 100``
        与 0.02（2%）阈值比较：股价 10 元、20 日涨 0.5 元时得 0.005，
        远小于 0.02，导致买入信号几乎永不触发。

        正确算法是相对 N 日前收盘价的收益率。
        """
        try:
            period = int(self.params.momentum_period)
            if period <= 0 or len(self.data) <= period:
                return 0.0
            prev_close = self.data.close[-period]
            if prev_close and prev_close > 0:
                return (self.data.close[0] - prev_close) / prev_close
        except Exception:
            pass
        return 0.0

    def next(self):
        """每个K线执行一次"""
        # 如果有未完成的订单，不执行
        if self.order:
            return
        
        # 更新持有天数和最高价
        if self.position:
            self.hold_days += 1
            if self.data.high[0] > self.highest_price:
                self.highest_price = self.data.high[0]
        
        # 如果没有持仓
        if not self.position:
            # 买入信号：
            # 1. 动量 > 阈值（上涨动能）
            # 2. 价格在均线上方（确认上升趋势）
            # 3. 动量加速度 > 0（动能增强）

            momentum_pct = self._momentum_pct()
            momentum_buy = momentum_pct > self.params.momentum_threshold
            trend_buy = self.data.close[0] > self.ma[0]
            # 动能增强：当前动量大于上一根动量（环比上升），安全无除零风险
            if self._prev_momentum is None:
                acceleration_buy = True
            else:
                acceleration_buy = self.momentum[0] > self._prev_momentum
            self._prev_momentum = self.momentum[0]
            
            if momentum_buy and trend_buy and acceleration_buy:
                # 计算仓位
                cash = self.broker.getcash()
                position_value = cash * self.params.position_size
                size = int(position_value / self.data.close[0] / 100) * 100
                size = max(100, size)
                
                if size >= 100 and cash > position_value:
                    self.order = self.buy(size=size)
                    if self.params.printlog:
                        self.log(f'买入信号: 动量={momentum_pct:.2%}, 趋势=上升')
        
        # 如果有持仓
        else:
            sell_signal = False
            sell_reason = ""
            
            # 卖出信号1：动量 < -阈值（下跌动能）
            momentum_pct = self._momentum_pct()
            if momentum_pct < -self.params.momentum_threshold:
                sell_signal = True
                sell_reason = f"动量转负 {momentum_pct:.2%}"
            
            # 卖出信号2：价格跌破均线（趋势反转）
            elif self.data.close[0] < self.ma[0]:
                sell_signal = True
                sell_reason = "跌破均线"
            
            # 卖出信号3：达到止盈目标
            elif self.buy_price and self.data.close[0] >= self.buy_price * (1 + self.params.profit_target):
                sell_signal = True
                sell_reason = f"止盈 {self.params.profit_target*100:.1f}%"
            
            # 卖出信号4：触发止损
            elif self.buy_price and self.data.close[0] <= self.buy_price * (1 - self.params.stop_loss):
                sell_signal = True
                sell_reason = f"止损 {self.params.stop_loss*100:.1f}%"
            
            # 卖出信号5：追踪止损
            elif self.highest_price and self.data.close[0] < self.highest_price * (1 - self.params.trailing_stop):
                sell_signal = True
                sell_reason = f"追踪止损 {self.params.trailing_stop*100:.1f}%"
            
            # 卖出信号6：超过最大持有天数
            elif self.hold_days >= self.params.max_hold_days:
                sell_signal = True
                sell_reason = f"持有{self.hold_days}天"
            
            if sell_signal:
                self.order = self.close()
                if self.params.printlog:
                    self.log(f'卖出信号: {sell_reason}')
    
    def log(self, txt, dt=None):
        """日志函数"""
        if self.params.printlog:
            dt = dt or self.datas[0].datetime.date(0)
            logging.getLogger("strategy.momentum").debug(f'{dt.isoformat()}, {txt}')
