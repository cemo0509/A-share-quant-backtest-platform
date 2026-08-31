"""因子评分选股策略：基于多因子评分的选股策略。

计算多个因子（如动量、波动率、成交量等），合成综合评分，
选择评分最高的N只股票进行投资。
"""

from __future__ import annotations

import logging

import backtrader as bt
import numpy as np
import pandas as pd

from .base import BaseStrategy


class FactorScoreStrategy(BaseStrategy):
    """因子评分选股策略。
    
    注意：此策略需要多股票数据支持。在Backtrader中，需要使用adddata添加多个股票，
    或者使用自定义的DataFeed。
    
    简化版：假设只有一个股票，使用单个股票的多个因子进行评分。
    """
    
    params = (
        ("factor_weights", [0.4, 0.2, 0.2, 0.2]),  # 因子权重（增加动量权重）
        ("top_n", 5),                                # 选前N名
        ("rebalance_days", 5),                       # 调仓周期（天）- 降低到5天，更频繁检查
        ("buy_threshold", 0.5),                    # 买入阈值
        ("sell_threshold", 0.4),                    # 卖出阈值
        ("stop_loss", 0.08),                       # 止损比例
        ("printlog", False),
    )
    
    def __init__(self):
        self.order = None
        self.bar_count = 0
        
        # 定义因子指标
        # 1. 动量因子（20日收益率）- 在next()中计算
        # 不需要预先创建指标，直接在next()中计算: self.data.close[0] / self.data.close[-20] - 1
        
        # 2. 波动率因子（20日波动率）
        self.volatility = bt.indicators.StdDev(self.data.close, period=20)
        
        # 3. 成交量因子（5日均量/20日均量）
        self.volume_ma5 = bt.indicators.SMA(self.data.volume, period=5)
        self.volume_ma20 = bt.indicators.SMA(self.data.volume, period=20)
        self.volume_ratio = self.volume_ma5 / self.volume_ma20
        
        # 4. 均线因子（价格在20日均线上方）
        self.ma20 = bt.indicators.SMA(self.data.close, period=20)
        
    def next(self):
        if self.order:
            return
        
        # 数据有效性检查
        if len(self.data) < 20:
            return  # 数据不足，跳过（需要至少20天计算因子）
        
        self.bar_count += 1
        
        # 止损检查
        if self.position:
            entry_price = self.position.price
            current_price = self.data.close[0]
            stop_loss_price = entry_price * (1 - self.params.stop_loss)
            
            if current_price < stop_loss_price:
                if self.params.printlog:
                    self.log(f"触发止损! entry={entry_price:.2f}, current={current_price:.2f}, size={self.position.size}")
                self.order = self.sell(size=self.position.size)
                return
        
        # 定期调仓
        if self.bar_count % self.params.rebalance_days != 0:
            return
        
        # 计算因子评分
        score = self._calc_composite_score()
        
        if self.params.printlog:
            self.log(f"因子评分: {score:.4f}")
        
        # 根据评分决定买卖（使用优化后的阈值）
        has_position = self.position and self.position.size != 0
        
        if not has_position:
            # 评分大于买入阈值买入
            if score > self.params.buy_threshold:
                cash = self.broker.getcash()
                price = self.data.close[0]
                # A 股申报数量必须是 100 股（1 手）的整数倍
                size = int(cash / price * 0.5) // 100 * 100  # 提高仓位到50%
                if self.params.printlog:
                    self.log(f"买入信号! score={score:.4f}, cash={cash:.2f}, price={price:.2f}, size={size}")
                if size > 0:
                    self.order = self.buy(size=size)
        else:
            # 评分小于卖出阈值卖出（卖出全部持仓）
            if score < self.params.sell_threshold:
                if self.params.printlog:
                    self.log(f"卖出信号! score={score:.4f}, size={self.position.size}")
                self.order = self.sell(size=self.position.size)
    
    def _calc_composite_score(self) -> float:
        """计算综合评分。"""
        # 计算动量因子（20日收益率）
        momentum_value = 0.0
        if len(self.data) >= 20 and self.data.close[-20] != 0:
            momentum_value = (self.data.close[0] / self.data.close[-20] - 1)
        
        # 使用更健壮的归一化方法（Sigmoid函数）
        
        # 因子1：动量（越大越好，使用Sigmoid归一化到0-1）
        if not np.isnan(momentum_value):
            # Sigmoid: 1 / (1 + exp(-x * 10))，将[-0.5, 0.5]映射到[0, 1]
            momentum_score = 1.0 / (1.0 + np.exp(-momentum_value * 10))
        else:
            momentum_score = 0.5
        
        # 因子2：波动率（越小越好，反向处理）
        volatility_value = self.volatility[0]
        if not np.isnan(volatility_value) and volatility_value >= 0:
            # 波动率归一化：假设波动率范围[0, 0.5]，使用指数衰减
            volatility_score = np.exp(-volatility_value * 5)
        else:
            volatility_score = 0.5
        
        # 因子3：成交量比（越大越好，使用Sigmoid）
        volume_ratio_value = self.volume_ratio[0]
        if not np.isnan(volume_ratio_value) and volume_ratio_value >= 0:
            # 成交量比归一化：假设范围[0, 3]，使用Sigmoid
            volume_score = 1.0 / (1.0 + np.exp(-volume_ratio_value + 1.5))
        else:
            volume_score = 0.5
        
        # 因子4：均线位置（在均线上方为1，下方为0）
        if len(self.data) >= 20:
            ma_score = 1.0 if self.data.close[0] > self.ma20[0] else 0.0
        else:
            ma_score = 0.5
        
        # 加权合成
        weights = self.params.factor_weights
        composite_score = (
            momentum_score * weights[0] +
            volatility_score * weights[1] +
            volume_score * weights[2] +
            ma_score * weights[3]
        )
        
        return composite_score
    
    def log(self, txt, dt=None):
        """日志记录。"""
        dt = dt or self.data.datetime.date(0)
        logging.getLogger("strategy.factor").debug(f"[{dt}] {txt}")
    
    def notify_order(self, order):
        """订单状态通知。"""
        if self.params.printlog:
            if order.status == order.Completed:
                if order.isbuy():
                    self.log(f"买入订单完成! 价格={order.executed.price:.2f}, 数量={order.executed.size}")
                elif order.issell():
                    self.log(f"卖出订单完成! 价格={order.executed.price:.2f}, 数量={order.executed.size}")
            elif order.status in [order.Canceled, order.Margin, order.Rejected]:
                self.log(f"订单失败! status={order.status}")
        
        # 清除订单引用
        if order.status in [order.Completed, order.Canceled, order.Margin, order.Rejected]:
            self.order = None



if __name__ == "__main__":
    print("因子评分选股策略")

