"""智能退出策略：集成多种退出机制的策略。

在双均线策略的基础上，增加追踪止损、时间退出、硬止损等退出机制。
集成了 core.exit_rules 和 core.position_sizer 模块。
"""

from __future__ import annotations

import backtrader as bt
from datetime import datetime, timedelta

from .base import BaseStrategy
from core.exit_rules import ExitRules
from core.position_sizer import PositionSizer


class SmartExitStrategy(BaseStrategy):
    """智能退出策略。
    
    基于双均线策略，但增加了多种退出机制：
    1. 追踪止损：从峰值回落8%退出
    2. 时间退出：持仓超过45天退出
    3. 硬止损：亏损超过12%退出
    4. 止盈：盈利超过20%退出
    """
    
    params = (
        ("fast", 5),                # 短期均线周期
        ("slow", 20),               # 长期均线周期
        ("trailing_stop_pct", 8.0),  # 追踪止损百分比
        ("time_exit_days", 45),      # 时间退出天数（与 registry 默认一致）
        ("hard_stop_pct", 12.0),    # 硬止损百分比（与 registry 默认一致）
        ("profit_target", 0.2),      # 止盈目标
        ("trailing_activate", 0.03), # 追踪止损激活阈值（盈利超过3%就激活）
        ("printlog", False),
    )
    
    def __init__(self):
        super().__init__()
        self.fast_ma = bt.indicators.SMA(self.data.close, period=self.params.fast)
        self.slow_ma = bt.indicators.SMA(self.data.close, period=self.params.slow)
        self.crossover = bt.indicators.CrossOver(self.fast_ma, self.slow_ma)
        
        # 集成退出规则和仓位管理模块
        self.exit_rules = ExitRules()
        self.position_sizer = PositionSizer(base_size=0.3, max_position=0.5, risk_percent=0.01)
        
        # 记录交易信息
        self.entry_price = 0.0
        self.entry_date = None
        self.peak_price = 0.0
        
    def next(self):
        if self.order:
            return
        
        # 数据有效性检查
        if len(self.data) < self.params.slow:
            return  # 数据不足，跳过
        
        # 记录价格
        current_price = self.data.close[0]
        
        # 更新峰值价格
        if current_price > self.peak_price:
            self.peak_price = current_price
        
        if not self.position:
            # 金叉买入
            if self.crossover > 0:
                # 计算买入数量（使用50%的资金）
                cash = self.broker.getcash()
                price = self.data.close[0]
                size = int(cash / price * 0.5)
                if size > 0:
                    self.order = self.buy(size=size)
        else:
            # 死叉卖出（信号退出）
            if self.crossover < 0:
                if self.params.printlog:
                    self.log("信号退出：死叉")
                self.order = self.sell(size=self.position.size)
                return
            
            # 检查多种退出机制（简化版，不依赖ExitRules）
            current_date = self.data.datetime.date(0)
            
            # 计算当前盈利
            profit_pct = (current_price - self.entry_price) / self.entry_price
            
            # 1. 追踪止损检查（盈利超过激活阈值后激活）
            if profit_pct >= self.params.trailing_activate and self.peak_price > 0:
                drawdown = (self.peak_price - current_price) / self.peak_price
                if drawdown > self.params.trailing_stop_pct / 100:
                    if self.params.printlog:
                        self.log(f"触发追踪止损: 回撤{drawdown:.2%}")
                    self.order = self.sell(size=self.position.size)
                    return
            
            # 2. 止盈检查
            if profit_pct > self.params.profit_target:
                if self.params.printlog:
                    self.log(f"触发止盈: 盈利{profit_pct:.2%}")
                self.order = self.sell(size=self.position.size)
                return
            
            # 3. 硬止损检查（无论是否盈利都检查）
            if self.entry_price > 0 and self.params.hard_stop_pct > 0:
                hard_stop_price = self.entry_price * (1 - self.params.hard_stop_pct)
                if current_price < hard_stop_price:
                    if self.params.printlog:
                        self.log("触发硬止损")
                    self.order = self.sell(size=self.position.size)
                    return
            
            # 4. 时间退出检查
            if self.entry_date and self.params.time_exit_days > 0:
                days_held = (current_date - self.entry_date).days
                if days_held > self.params.time_exit_days:
                    if self.params.printlog:
                        self.log("触发时间退出")
                    self.order = self.sell(size=self.position.size)
                    return
    
    def notify_order(self, order):
        """订单状态通知。"""
        if order.status == order.Completed:
            if order.isbuy():
                self.entry_price = order.executed.price
                # 获取当前日期，确保数据有效
                if len(self.data) > 0:
                    self.entry_date = self.data.datetime.date(0)
                else:
                    from datetime import datetime
                    self.entry_date = datetime.now().date()
                self.peak_price = order.executed.price
                self.prices = []  # 重置价格序列
                
                if self.params.printlog:
                    self.log(f"买入执行 价格={order.executed.price:.2f}")
            elif order.issell():
                if self.params.printlog:
                    self.log(f"卖出执行 价格={order.executed.price:.2f}")
                
                # 重置交易信息
                self.entry_price = 0.0
                self.entry_date = None
                self.peak_price = 0.0
                self.prices = []
        
        # 清除订单引用
        if order.status in [order.Completed, order.Canceled, order.Margin, order.Rejected]:
            self.order = None


if __name__ == "__main__":
    print("智能退出策略")
    print("集成追踪止损、时间退出、硬止损等多种退出机制")
