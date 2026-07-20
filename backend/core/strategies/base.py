"""策略基类：统一预置策略的接口规范。

借鉴 Backtrader 的策略 API 设计（__init__ 定义指标，next 定义买卖逻辑），
所有预置策略继承此类，便于引擎层统一加载。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import logging

import backtrader as bt

_logger = logging.getLogger("strategy.base")


class BaseStrategy(bt.Strategy):
    """所有预置策略的基类。

    子类需实现 params 和 __init__（定义指标）、可选重写 next（默认空）。
    """

    params = (
        ("printlog", False),
    )

    def log(self, txt: str, dt: Any = None):
        dt = dt or self.datas[0].datetime.date(0)
        _logger.debug(f"[{dt}] {txt}")

    def notify_order(self, order: bt.Order):
        if order.status in [order.Completed]:
            if self.params.printlog:
                action = "买入" if order.isbuy() else "卖出"
                self.log(f"{action} 执行 价格={order.executed.price:.2f} 数量={order.executed.size:.0f}")
        # 订单完成后清除
        if order.status in [order.Completed, order.Canceled, order.Margin, order.Rejected]:
            self.order = None

    def notify_trade(self, trade: bt.Trade):
        if trade.isclosed and self.params.printlog:
            self.log(f"交易利润 毛利={trade.pnl:.2f} 净利={trade.pnlcomm:.2f}")

    def __init__(self):
        self.order = None

    def next(self):
        pass
