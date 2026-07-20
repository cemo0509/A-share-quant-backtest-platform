"""市场状态自适应策略：根据市场状态自动调整参数。

当市场处于牛市时，使用更灵敏的参数（短期均线）；
当市场处于熊市时，使用更保守的参数（长期均线）。
"""

from __future__ import annotations

import backtrader as bt

from .base import BaseStrategy
from core.market_state import MarketStateDetector, MarketTrend


class AdaptiveStrategy(BaseStrategy):
    """市场状态自适应策略。
    
    根据市场状态自动调整双均线参数：
    - 牛市：使用短期参数（fast=5, slow=20），更灵敏地捕捉上涨
    - 熊市/震荡：使用长期参数（fast=10, slow=60），避免过度交易
    
    同时结合仓位管理：牛市满仓，震荡市7成仓，熊市3成仓。
    """
    
    params = (
        ("bull_fast", 5),           # 牛市短期均线周期
        ("bull_slow", 20),          # 牛市长期均线周期
        ("bear_fast", 10),          # 熊市短期均线周期
        ("bear_slow", 60),          # 熊市长期均线周期
        ("position_scale", True),   # 是否根据市场状态调整仓位
        ("trend_confirm", True),   # 是否添加趋势确认
        ("stop_loss", 0.05),      # 止损比例
        ("printlog", False),
    )
    
    def __init__(self):
        super().__init__()
        self.market_detector = MarketStateDetector()
        
        # 预先计算所有均线组合（避免动态创建指标）
        self.bull_fast_ma = bt.indicators.SMA(self.data.close, period=self.params.bull_fast)
        self.bull_slow_ma = bt.indicators.SMA(self.data.close, period=self.params.bull_slow)
        
        self.bear_fast_ma = bt.indicators.SMA(self.data.close, period=self.params.bear_fast)
        self.bear_slow_ma = bt.indicators.SMA(self.data.close, period=self.params.bear_slow)
        
        # 预先创建60日均线（用于趋势确认）
        self.ma60 = bt.indicators.SMA(self.data.close, period=60)
        
        # 记录当前市场状态
        self.current_market_state = MarketTrend.NORMAL.value
        
        # 用于计算市场状态的缓存
        self.bar_count = 0
        self._state_buffer = []
        
    def next(self):
        if self.order:
            return
        
        # 数据有效性检查
        if len(self.data) < max(self.params.bull_slow, self.params.bear_slow):
            return  # 数据不足，跳过
        
        self.bar_count += 1
        
        # 每20个bar检测一次市场状态（避免频繁计算）
        if self.bar_count >= 20 and self.bar_count % 20 == 0:
            self._update_market_state()
        
        # 根据市场状态选择使用哪组均线
        if self.current_market_state == MarketTrend.BULL.value:
            fast_ma = self.bull_fast_ma
            slow_ma = self.bull_slow_ma
        else:
            fast_ma = self.bear_fast_ma
            slow_ma = self.bear_slow_ma
        
        # 计算金叉死叉
        crossover = fast_ma[0] - slow_ma[0]
        crossover_prev = fast_ma[-1] - slow_ma[-1]
        
        # 金叉：fast_ma上穿slow_ma
        golden_cross = crossover > 0 and crossover_prev <= 0
        # 死叉：fast_ma下穿slow_ma
        death_cross = crossover < 0 and crossover_prev >= 0
        
        # 止损检查
        if self.position:
            entry_price = self.position.price
            current_price = self.data.close[0]
            stop_loss_price = entry_price * (1 - self.params.stop_loss)
            
            if current_price < stop_loss_price:
                self.order = self.sell()
                if self.params.printlog:
                    self.log(f"触发止损: 入场价={entry_price:.2f}, 当前价={current_price:.2f}")
                return
        
        if not self.position:
            # 金叉买入（添加趋势确认）
            if golden_cross:
                # 趋势确认：价格在60日均线上方
                if self.params.trend_confirm:
                    if len(self.data) >= 60 and len(self.ma60) > 0:
                        if self.data.close[0] < self.ma60[0]:
                            return  # 趋势不确认，不买入
                
                # 根据市场状态调整仓位（更保守）
                if self.params.position_scale:
                    if self.current_market_state == MarketTrend.BULL.value:
                        size_pct = 0.8  # 降低为80%
                    elif self.current_market_state == MarketTrend.NORMAL.value:
                        size_pct = 0.5  # 降低为50%
                    else:  # BEAR
                        size_pct = 0.2  # 降低为20%
                else:
                    size_pct = 0.3
                
                size = int(self.broker.getcash() * size_pct / self.data.close[0])
                if size > 0:
                    self.order = self.buy(size=size)
        else:
            # 死叉卖出
            if death_cross:
                self.order = self.sell()
    
    def _update_market_state(self):
        """更新市场状态（优化版：使用多重确认）。"""
        # 使用20日涨跌幅判断 + 均线趋势确认
        if len(self.data) >= 20:
            change_20d = (self.data.close[0] / self.data.close[-20] - 1) * 100
            
            # 使用60日均线作为趋势确认（预先计算，避免动态创建指标）
            if len(self.data) >= 60:
                # 预先在__init__中创建ma60指标
                if not hasattr(self, 'ma60'):
                    self.ma60 = bt.indicators.SMA(self.data.close, period=60)
                
                # 确保ma60有足够的数据
                if len(self.ma60) > 0:
                    price_above_ma60 = self.data.close[0] > self.ma60[0]
                else:
                    price_above_ma60 = True  # 数据不足时默认True
            else:
                price_above_ma60 = True  # 数据不足时默认True
            
            # 更严格的判断条件
            if change_20d > 12 and price_above_ma60:
                new_state = MarketTrend.BULL.value
            elif change_20d < -12 and not price_above_ma60:
                new_state = MarketTrend.BEAR.value
            else:
                new_state = MarketTrend.NORMAL.value
            
            # 只有连续2次判断为同一状态才切换（避免频繁切换）
            if not hasattr(self, '_state_buffer'):
                self._state_buffer = []
            
            self._state_buffer.append(new_state)
            if len(self._state_buffer) > 2:
                self._state_buffer.pop(0)
            
            # 缓冲区内状态一致才切换
            if len(self._state_buffer) == 2 and self._state_buffer[0] == self._state_buffer[1]:
                confirmed_state = self._state_buffer[0]
                if confirmed_state != self.current_market_state:
                    self.current_market_state = confirmed_state
                    if self.params.printlog:
                        self.log(f"市场状态切换: {confirmed_state}, 20日涨幅: {change_20d:.2f}%")


if __name__ == "__main__":
    # 测试代码
    print("市场状态自适应策略")
    print("根据市场状态自动调整双均线参数和仓位")
