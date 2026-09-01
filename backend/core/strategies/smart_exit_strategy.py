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
        # 持仓期间的价格序列（ExitRules 的 Dead Drift 检查需要）
        self.prices: list[float] = []

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
                # A 股最小交易单位为 1 手 = 100 股，申报数量必须是 100 的整数倍。
                # 此前未取整到整百，会产生 137 股这类真实市场无法成交的委托。
                size = int(cash / price * 0.5) // 100 * 100
                if size > 0:
                    self.order = self.buy(size=size)
        else:
            # 死叉卖出（信号退出）
            if self.crossover < 0:
                if self.params.printlog:
                    self.log("信号退出：死叉")
                self.order = self.sell(size=self.position.size)
                return

            # 多种退出机制：统一走 core.exit_rules.ExitRules。
            #
            # 此前这里手写了 4 段重复逻辑，且与已存在的 ExitRules 模块重复，
            # 而 self.exit_rules 虽被实例化却从未调用（注释自承「简化版」）。
            # 更糟的是手写版硬止损漏了 /100，导致硬止损从未生效。
            # 现在统一委托给 ExitRules，消除重复并复用经过验证的实现。
            self.prices.append(current_price)

            should_exit, reason = self.exit_rules.should_exit(
                entry_price=self.entry_price,
                peak_price=self.peak_price,
                current_price=current_price,
                entry_date=self.entry_date,
                current_date=self.data.datetime.date(0),
                prices=self.prices,
                trailing_stop_pct=self.params.trailing_stop_pct,
                time_exit_days=self.params.time_exit_days,
                hard_stop_pct=self.params.hard_stop_pct,
                profit_target=self.params.profit_target,
            )

            if should_exit:
                if self.params.printlog:
                    self.log(f"触发退出: {reason}")
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
