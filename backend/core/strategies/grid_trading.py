"""网格交易策略 - 适合震荡市场的策略"""
from __future__ import annotations
import logging

import backtrader as bt
import numpy as np


class GridTradingStrategy(bt.Strategy):
    """网格交易策略
    
    策略逻辑：
    1. 设置中枢价格（通常为当前价或均线）
    2. 在中枢上方设置卖出网格，下方设置买入网格
    3. 价格每下跌一个网格，买入一定数量
    4. 价格每上涨一个网格，卖出一定数量
    5. 震荡市场中持续获利
    
    适用场景：震荡市场（横盘）
    风险：趋势市场中可能满仓或空仓
    """
    
    params = (
        ("grid_count", 10),         # 网格数量（单边）
        ("grid_spacing", 0.01),    # 网格间距（1%）
        ("base_position", 0.5),    # 基准仓位比例
        ("single_position", 0.05), # 单格交易仓位
        ("center_type", "fixed"),   # 中枢类型：fixed（固定）/ dynamic（动态）
        ("center_price", 0.0),     # 固定中枢价格（0表示使用当前价）
        ("dynamic_period", 20),     # 动态中枢周期（均线周期）
        ("min_spread", 0.005),     # 最小价差（0.5%）
        ("max_position", 0.95),    # 最大仓位
        ("printlog", False),
    )
    
    def __init__(self):
        """初始化"""
        # 动态中枢（均线）
        if self.params.center_type == "dynamic":
            self.center_ma = bt.indicators.SimpleMovingAverage(
                self.data.close, period=self.params.dynamic_period
            )
            self.center = 0.0  # 延迟到 next() 首根有效数据时初始化
        else:
            self.center = 0.0

        # 交易记录
        self.grids = []   # 网格价格列表
        self.trade_count = 0
        self.order = None  # 当前挂起订单（用于挂单守卫）

        # 初始网格（fixed 用当前价；dynamic 在 next 首根时计算）
        if self.params.center_type == "fixed":
            if self.params.center_price > 0:
                self.center = self.params.center_price
            else:
                self.center = self.data.close[0]
            self._calculate_grids()

    def _calculate_grids(self):
        """计算网格价格"""
        if self.center == 0 or np.isnan(self.center):
            return
        # 确定中枢价格（dynamic 模式会在 next 中先赋值 self.center 再调用本方法）
        
        # 生成网格
        self.grids = []
        
        # 下方买入网格
        for i in range(1, self.params.grid_count + 1):
            buy_price = self.center * (1 - self.params.grid_spacing * i)
            self.grids.append({"price": buy_price, "type": "buy", "executed": False})
        
        # 上方卖出网格
        for i in range(1, self.params.grid_count + 1):
            sell_price = self.center * (1 + self.params.grid_spacing * i)
            self.grids.append({"price": sell_price, "type": "sell", "executed": False})
        
        # 按价格排序
        self.grids.sort(key=lambda x: x["price"])
        
        if self.params.printlog:
            self.log(f'网格计算完成: 中枢={self.center:.2f}, 网格数={len(self.grids)}')
            for grid in self.grids:
                self.log(f'  {grid["type"]}: {grid["price"]:.2f}')
    
    def _get_position_size(self, is_buy):
        """计算交易数量"""
        cash = self.broker.getcash()
        value = self.broker.getvalue()
        price = self.data.close[0]
        
        if is_buy:
            # 买入：使用单格仓位
            amount = value * self.params.single_position
            size = int(amount / price / 100) * 100
            size = max(100, size)
            
            # 检查现金是否足够
            if cash < size * price * 1.001:  # 加上手续费
                size = int(cash * 0.95 / price / 100) * 100
            
            return max(0, size)
        else:
            # 卖出：卖出持仓的一部分
            position = self.getposition(self.data)
            if position.size > 0:
                size = int(position.size * self.params.single_position)
                size = max(100, size)
                return min(size, position.size)
            
            return 0
    
    def next(self):
        """每个K线执行一次"""
        # 已有挂起订单时不重复发单（挂单守卫：避免极端行情下连续触发同一网格）
        if self.order:
            return

        # 数据不足或中枢均线尚未就绪时不交易
        if len(self.data) < self.params.dynamic_period:
            return

        # 如果是动态中枢，重新计算网格
        if self.params.center_type == "dynamic":
            new_center = self.center_ma[0]
            # 首次或中枢漂移过大时重算网格
            if self.center == 0 or np.isnan(self.center) or np.isnan(new_center):
                self.center = new_center
                self._calculate_grids()
            elif abs(new_center - self.center) / self.center > self.params.min_spread:
                self.center = new_center
                self._calculate_grids()
        
        current_price = self.data.close[0]
        
        # 检查网格
        for grid in self.grids:
            grid_price = grid["price"]
            grid_type = grid["type"]
            
            # 买入网格：当前价 <= 网格价
            if grid_type == "buy" and not grid["executed"]:
                if current_price <= grid_price:
                    size = self._get_position_size(is_buy=True)
                    if size > 0:
                        self.buy(size=size)
                        grid["executed"] = True
                        self.trade_count += 1
                        if self.params.printlog:
                            self.log(f'买入网格触发: 价格={current_price:.2f}, 网格={grid_price:.2f}, 数量={size}')
            
            # 卖出网格：当前价 >= 网格价
            elif grid_type == "sell" and not grid["executed"]:
                if current_price >= grid_price:
                    size = self._get_position_size(is_buy=False)
                    if size > 0:
                        self.sell(size=size)
                        grid["executed"] = True
                        self.trade_count += 1
                        if self.params.printlog:
                            self.log(f'卖出网格触发: 价格={current_price:.2f}, 网格={grid_price:.2f}, 数量={size}')
    
    def notify_order(self, order):
        """订单状态通知"""
        if order.status in [order.Completed]:
            if self.params.printlog:
                if order.isbuy():
                    self.log(f'买入完成: 价格={order.executed.price:.2f}')
                else:
                    self.log(f'卖出完成: 价格={order.executed.price:.2f}, 盈亏={order.executed.pnl:.2f}')
        
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            if self.params.printlog:
                self.log('订单取消/拒绝')

        # 订单了结后清除引用，允许下一根 K 线继续挂单
        if order.status in [order.Completed, order.Canceled, order.Margin, order.Rejected]:
            self.order = None
    
    def stop(self):
        """策略结束"""
        if self.params.printlog:
            self.log(f'策略结束: 交易次数={self.trade_count}')
    
    def log(self, txt, dt=None):
        """日志函数"""
        if self.params.printlog:
            dt = dt or self.datas[0].datetime.date(0)
            logging.getLogger("strategy.grid_trading").debug(f'{dt.isoformat()}, {txt}')
