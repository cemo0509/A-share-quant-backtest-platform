"""均值回归策略 - 基于价格偏离均值的反转策略"""
from __future__ import annotations
import logging

import backtrader as bt
import numpy as np


class MeanReversionStrategy(bt.Strategy):
    """均值回归策略
    
    策略逻辑：
    1. 计算价格与均值的偏离度（Z-Score）
    2. 当价格低于均值一定标准差时买入（超卖）
    3. 当价格高于均值一定标准差时卖出（超买）
    4. 结合RSI指标确认
    
    适用场景：震荡市场
    风险：趋势市场中可能持续亏损
    """
    
    params = (
        ("period", 20),           # 均值计算周期
        ("std_dev", 2.0),         # 标准差倍数
        ("rsi_period", 14),       # RSI周期
        ("rsi_oversold", 30),     # RSI超卖线
        ("rsi_overbought", 70),   # RSI超买线
        ("max_hold_days", 10),    # 最大持有天数
        ("profit_target", 0.03),  # 止盈目标（3%）
        ("stop_loss", 0.02),      # 止损比例（2%）
        ("printlog", False),
    )
    
    def __init__(self):
        """初始化指标"""
        # 均线
        self.sma = bt.indicators.SimpleMovingAverage(
            self.data.close, period=self.params.period
        )
        
        # 标准差
        self.std = bt.indicators.StandardDeviation(
            self.data.close, period=self.params.period
        )
        
        # Z-Score（标准化分数）
        self.zscore = (self.data.close - self.sma) / self.std
        
        # RSI
        self.rsi = bt.indicators.RelativeStrengthIndex(
            self.data.close, period=self.params.rsi_period
        )
        
        # 记录买入价格
        self.buy_price = None
        self.hold_days = 0
        
        # 订单
        self.order = None
        
    def notify_order(self, order):
        """订单状态通知"""
        if order.status in [order.Submitted, order.Accepted]:
            return
        
        if order.status in [order.Completed]:
            if order.isbuy():
                self.buy_price = order.executed.price
                self.hold_days = 0
                if self.params.printlog:
                    self.log(f'买入执行: 价格={order.executed.price:.2f}, 数量={order.executed.size:.0f}')
            else:
                if self.params.printlog:
                    self.log(f'卖出执行: 价格={order.executed.price:.2f}, 数量={order.executed.size:.0f}, 收益={order.executed.pnl:.2f}')
                self.buy_price = None
                self.hold_days = 0
                
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            if self.params.printlog:
                self.log('订单取消/拒绝')
        
        self.order = None
    
    def next(self):
        """每个K线执行一次"""
        # 如果有未完成的订单，不执行
        if self.order:
            return
        
        # 更新持有天数
        if self.position:
            self.hold_days += 1
        
        # 如果没有持仓
        if not self.position:
            # 买入信号：
            # 1. Z-Score < -std_dev（价格低于均值）
            # 2. RSI < 超卖线
            zscore_buy = self.zscore[0] < -self.params.std_dev
            rsi_buy = self.rsi[0] < self.params.rsi_oversold
            
            if zscore_buy and rsi_buy:
                # 计算仓位（基于波动率调整）
                volatility = self.std[0] / self.data.close[0]
                position_size = int(self.broker.getcash() * 0.1 / (self.data.close[0] * (1 + volatility)))
                position_size = max(100, position_size // 100 * 100)  # 整百股
                
                if position_size >= 100:
                    self.order = self.buy(size=position_size)
                    if self.params.printlog:
                        self.log(f'买入信号: Z-Score={self.zscore[0]:.2f}, RSI={self.rsi[0]:.1f}')
        
        # 如果有持仓
        else:
            sell_signal = False
            sell_reason = ""
            
            # 卖出信号1：Z-Score > std_dev（价格高于均值）
            if self.zscore[0] > self.params.std_dev:
                sell_signal = True
                sell_reason = f"Z-Score={self.zscore[0]:.2f}"
            
            # 卖出信号2：RSI > 超买线
            elif self.rsi[0] > self.params.rsi_overbought:
                sell_signal = True
                sell_reason = f"RSI={self.rsi[0]:.1f}"
            
            # 卖出信号3：达到止盈目标
            elif self.buy_price and self.data.close[0] >= self.buy_price * (1 + self.params.profit_target):
                sell_signal = True
                sell_reason = f"止盈 {self.params.profit_target*100:.1f}%"
            
            # 卖出信号4：触发止损
            elif self.buy_price and self.data.close[0] <= self.buy_price * (1 - self.params.stop_loss):
                sell_signal = True
                sell_reason = f"止损 {self.params.stop_loss*100:.1f}%"
            
            # 卖出信号5：超过最大持有天数
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
            logging.getLogger("strategy.mean_reversion").debug(f'{dt.isoformat()}, {txt}')
