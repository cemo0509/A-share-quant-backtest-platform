"""多退出机制模块：提供多种退出策略，包括追踪止损、时间退出、硬止损等。

用于在策略中集成多种退出机制，提高风险控制能力。
"""

from __future__ import annotations

import logging

import backtrader as bt
from typing import Optional


class ExitRules:
    """退出规则检查器。
    
    提供多种退出机制，可在策略的next()方法中调用。
    """
    
    def __init__(self):
        pass
    
    def check_trailing_stop(
        self,
        entry_price: float,
        peak_price: float,
        current_price: float,
        pct: float = 8.0,
    ) -> bool:
        """追踪止损：从峰值回落pct%。
        
        Args:
            entry_price: 入场价格
            peak_price: 峰值价格（持仓期间最高价）
            current_price: 当前价格
            pct: 回撤百分比（默认8%）
            
        Returns:
            是否触发追踪止损
        """
        if peak_price == 0:
            return False
        
        drawdown = (peak_price - current_price) / peak_price * 100
        return drawdown > pct
    
    def check_time_exit(
        self,
        entry_date,
        current_date,
        max_days: int = 45,
    ) -> bool:
        """时间退出：持仓超过max_days。
        
        Args:
            entry_date: 入场日期（datetime对象或date对象）
            current_date: 当前日期（datetime对象或date对象）
            max_days: 最大持仓天数（默认45天）
            
        Returns:
            是否触发时间退出
        """
        from datetime import datetime, date
        
        # 转换为date对象进行比较
        if isinstance(entry_date, datetime):
            entry_date = entry_date.date()
        if isinstance(current_date, datetime):
            current_date = current_date.date()
        
        # 如果已经是date对象，直接使用
        if not isinstance(entry_date, date):
            entry_date = bt.num2date(entry_date).date()
        if not isinstance(current_date, date):
            current_date = bt.num2date(current_date).date()
        
        days_held = (current_date - entry_date).days
        return days_held > max_days
    
    def check_dead_drift(
        self,
        prices: list[float],
        threshold: float = -8.0,
        days: int = 15,
    ) -> bool:
        """Dead Drift：一段时间内累计跌幅超过阈值。
        
        Args:
            prices: 价格序列（按时间排序）
            threshold: 跌幅阈值（默认-8%）
            days: 观察天数（默认15天）
            
        Returns:
            是否触发Dead Drift退出
        """
        if len(prices) < days:
            return False
        
        # 计算days天累计涨跌幅
        start_price = prices[-days]
        end_price = prices[-1]
        
        cumulative_return = (end_price - start_price) / start_price * 100
        
        return cumulative_return < threshold
    
    def check_hard_stop(
        self,
        entry_price: float,
        current_price: float,
        pct: float = 12.0,
    ) -> bool:
        """硬止损：跌破入场价pct%。
        
        Args:
            entry_price: 入场价格
            current_price: 当前价格
            pct: 止损百分比（默认12%）
            
        Returns:
            是否触发硬止损
        """
        if entry_price == 0:
            return False
        
        loss = (current_price - entry_price) / entry_price * 100
        return loss < -pct
    
    def check_profit_target(
        self,
        entry_price: float,
        current_price: float,
        target: float = 0.2,
    ) -> bool:
        """止盈：达到目标收益率。
        
        Args:
            entry_price: 入场价格
            current_price: 当前价格
            target: 目标收益率（默认0.2，即20%）
            
        Returns:
            是否触止盈
        """
        if entry_price == 0:
            return False
        
        profit = (current_price - entry_price) / entry_price
        return profit > target
    
    def check_volatility_stop(
        self,
        entry_price: float,
        current_price: float,
        atr_value: float,
        atr_multiplier: float = 2.0,
    ) -> bool:
        """波动率止损：基于ATR的动态止损。
        
        Args:
            entry_price: 入场价格
            current_price: 当前价格
            atr_value: ATR值
            atr_multiplier: ATR乘数（默认2.0）
            
        Returns:
            是否触发波动率止损
        """
        if entry_price == 0 or atr_value == 0:
            return False
        
        # 计算动态止损价
        # 对于多头仓位，止损价 = 入场价 - ATR * multiplier
        stop_price = entry_price - atr_value * atr_multiplier
        
        # 检查是否触发止损
        return current_price < stop_price
    
    def should_exit(
        self,
        entry_price: float,
        peak_price: float,
        current_price: float,
        entry_date: bt.date,
        current_date: bt.date,
        prices: list[float] = None,
        trailing_stop_pct: float = 8.0,
        time_exit_days: int = 45,
        hard_stop_pct: float = 12.0,
        profit_target: float = 0.2,
    ) -> tuple[bool, str]:
        """综合退出检查。
        
        Args:
            entry_price: 入场价格
            peak_price: 峰值价格
            current_price: 当前价格
            entry_date: 入场日期
            current_date: 当前日期
            prices: 价格序列（用于Dead Drift检查）
            trailing_stop_pct: 追踪止损百分比
            time_exit_days: 时间退出天数
            hard_stop_pct: 硬止损百分比
            profit_target: 止盈目标
            
        Returns:
            (是否退出, 退出原因)
        """
        # 1. 止盈检查（优先级最高）
        if self.check_profit_target(entry_price, current_price, profit_target):
            return True, "profit_target"
        
        # 2. 硬止损
        if self.check_hard_stop(entry_price, current_price, hard_stop_pct):
            return True, "hard_stop"
        
        # 3. 追踪止损
        if self.check_trailing_stop(entry_price, peak_price, current_price, trailing_stop_pct):
            return True, "trailing_stop"
        
        # 4. 时间退出
        if self.check_time_exit(entry_date, current_date, time_exit_days):
            return True, "time_exit"
        
        # 5. Dead Drift检查（需要价格序列）
        if prices and self.check_dead_drift(prices):
            return True, "dead_drift"
        
        return False, ""


class SmartExitStrategy(bt.Strategy):
    """集成多种退出机制的策略基类。
    
    子类可以继承此类，自动获得多种退出机制。
    """
    
    params = (
        ("trailing_stop_pct", 8.0),   # 追踪止损百分比
        ("time_exit_days", 45),         # 时间退出天数
        ("hard_stop_pct", 12.0),        # 硬止损百分比
        ("profit_target", 0.2),         # 止盈目标
        ("printlog", False),
    )
    
    def __init__(self):
        super().__init__()
        self.exit_rules = ExitRules()
        self.entry_price = 0.0
        self.entry_date = None
        self.peak_price = 0.0
        self.prices = []  # 记录价格序列
        
    def notify_order(self, order):
        """订单状态通知。"""
        if order.status == order.Completed:
            if order.isbuy():
                self.entry_price = order.executed.price
                self.entry_date = self.data.datetime.date(0)
                self.peak_price = order.executed.price
                self.prices = []  # 重置价格序列
                
                if self.params.printlog:
                    self.log(f"买入执行 价格={order.executed.price:.2f}")
    
    def next(self):
        """每日检查退出条件。"""
        if not self.position:
            return
        
        # 记录当前价格
        current_price = self.data.close[0]
        current_date = self.data.datetime.date(0)
        self.prices.append(current_price)
        
        # 更新峰值价格
        if current_price > self.peak_price:
            self.peak_price = current_price
        
        # 检查退出条件
        should_exit, reason = self.exit_rules.should_exit(
            entry_price=self.entry_price,
            peak_price=self.peak_price,
            current_price=current_price,
            entry_date=self.entry_date,
            current_date=current_date,
            prices=self.prices,
            trailing_stop_pct=self.params.trailing_stop_pct,
            time_exit_days=self.params.time_exit_days,
            hard_stop_pct=self.params.hard_stop_pct,
            profit_target=self.params.profit_target,
        )
        
        if should_exit:
            if self.params.printlog:
                self.log(f"触发退出: {reason}")
            self.close()
            
    def log(self, txt, dt=None):
        """日志记录。"""
        dt = dt or self.data.datetime.date(0)
        logging.getLogger("strategy.exit_rules").debug(f"[{dt}] {txt}")


if __name__ == "__main__":
    # 测试退出规则
    rules = ExitRules()
    
    # 测试追踪止损
    print("=== 退出规则测试 ===")
    
    # 场景1：追踪止损
    entry = 100.0
    peak = 120.0
    current = 110.0
    result = rules.check_trailing_stop(entry, peak, current, pct=8.0)
    print(f"追踪止损 (峰值120, 当前110): {result}")  # True: 回落8.3%
    
    # 场景2：时间退出
    from datetime import datetime, timedelta
    entry_date = datetime.now() - timedelta(days=50)
    current_date = datetime.now()
    result = rules.check_time_exit(entry_date, current_date, max_days=45)
    print(f"时间退出 (持仓50天): {result}")  # True
    
    # 场景3：硬止损
    result = rules.check_hard_stop(entry, current, pct=12.0)
    print(f"硬止损 (入场100, 当前110): {result}")  # False
    
    result = rules.check_hard_stop(entry, 87.0, pct=12.0)
    print(f"硬止损 (入场100, 当前87): {result}")  # True: 亏损13%
    
    # 场景4：止盈
    result = rules.check_profit_target(entry, 125.0, target=0.2)
    print(f"止盈 (入场100, 当前125): {result}")  # True: 盈利25%
