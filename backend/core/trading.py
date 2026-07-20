"""实盘交易模块：模拟交易执行、订单管理、账户管理。

由于实盘交易需要对接券商API（通常需要特定权限），
本模块先实现模拟交易功能，后续可扩展为实盘对接。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import uuid


@dataclass
class Order:
    """订单"""
    order_id: str
    symbol: str
    action: str  # 'buy' or 'sell'
    price: float
    quantity: int
    status: str = 'pending'  # pending, filled, cancelled, rejected
    filled_price: Optional[float] = None
    filled_quantity: int = 0
    created_at: str = ""
    updated_at: str = ""
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        self.updated_at = self.created_at


@dataclass
class Position:
    """持仓"""
    symbol: str
    quantity: int
    available_quantity: int  # 可卖数量
    cost_price: float
    current_price: float = 0.0
    
    @property
    def market_value(self) -> float:
        return self.quantity * self.current_price
    
    @property
    def cost_value(self) -> float:
        return self.quantity * self.cost_price
    
    @property
    def profit_loss(self) -> float:
        return self.market_value - self.cost_value
    
    @property
    def profit_loss_ratio(self) -> float:
        if self.cost_value == 0:
            return 0.0
        return (self.profit_loss / self.cost_value) * 100


@dataclass
class Account:
    """账户信息"""
    total_assets: float = 1000000.0  # 总资产
    available_cash: float = 1000000.0  # 可用资金
    frozen_cash: float = 0.0  # 冻结资金
    positions: list[Position] = field(default_factory=list)
    orders: list[Order] = field(default_factory=list)
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """获取指定股票的持仓"""
        for pos in self.positions:
            if pos.symbol == symbol:
                return pos
        return None
    
    def update_position(self, symbol: str, quantity: int, price: float, action: str):
        """更新持仓（仅管理持仓数量和成本价，不涉及资金变动）。

        资金变动由 TradingSimulator.place_order 统一处理。
        """
        position = self.get_position(symbol)
        
        if action == 'buy':
            if position:
                # 加仓：重新计算加权平均成本
                total_quantity = position.quantity + quantity
                total_cost = position.cost_price * position.quantity + price * quantity
                position.cost_price = total_cost / total_quantity
                position.quantity = total_quantity
                position.available_quantity += quantity
            else:
                # 新建持仓
                new_position = Position(
                    symbol=symbol,
                    quantity=quantity,
                    available_quantity=quantity,
                    cost_price=price,
                    current_price=price,
                )
                self.positions.append(new_position)
            
        elif action == 'sell':
            if not position or position.quantity < quantity:
                raise ValueError("持仓不足，无法完成卖出操作")
            
            # 减仓
            position.quantity -= quantity
            position.available_quantity -= quantity
            
            # 如果清仓，移除持仓
            if position.quantity == 0:
                self.positions.remove(position)
    
    def calculate_total_assets(self, current_prices: dict[str, float]) -> float:
        """计算总资产"""
        total = self.available_cash
        for position in self.positions:
            current_price = current_prices.get(position.symbol, position.cost_price)
            total += position.quantity * current_price
        return total


class TradingSimulator:
    """交易模拟器"""
    
    def __init__(self, initial_cash: float = 1000000.0):
        self.account = Account(
            total_assets=initial_cash,
            available_cash=initial_cash
        )
        self.commission_rate = 0.0003  # 佣金率
        self.slippage = 0.001  # 滑点
        
        # 风险管理参数
        self.max_position_ratio = 0.1  # 单个股票最大持仓比例（10%）
        self.stop_loss_ratio = 0.05  # 止损比例（5%）
        self.take_profit_ratio = 0.10  # 止盈比例（10%）
        self.max_drawdown_ratio = 0.2  # 最大回撤比例（20%）
        
        # 风险监控
        self.initial_assets = initial_cash
        self.max_assets = initial_cash
        self.min_assets = initial_cash
        
    def place_order(self, symbol: str, action: str, quantity: int, price: float) -> Order:
        """下单"""
        # 创建订单
        order_id = str(uuid.uuid4())
        order = Order(
            order_id=order_id,
            symbol=symbol,
            action=action,
            price=price,
            quantity=quantity
        )
        
        try:
            # 模拟成交（按指定价格，含滑点调整）
            filled_price = price * (1 + self.slippage if action == 'buy' else 1 - self.slippage)
            
            # 计算佣金
            commission = filled_price * quantity * self.commission_rate
            
            # 更新持仓（仅负责持仓数量和成本价管理，不再涉及资金变动）
            self.account.update_position(symbol, quantity, filled_price, action)
            
            # 统一处理资金变动：买入扣钱（含佣金），卖出加钱（扣佣金）
            if action == 'buy':
                self.account.available_cash -= (quantity * filled_price + commission)
            else:
                self.account.available_cash += (quantity * filled_price - commission)
            
            # 更新当前价格（确保持仓市值计算准确）
            position = self.account.get_position(symbol)
            if position:
                position.current_price = filled_price
            
            # 更新订单状态
            order.status = 'filled'
            order.filled_price = filled_price
            order.filled_quantity = quantity
            order.updated_at = datetime.now().isoformat()
            
        except ValueError as e:
            order.status = 'rejected'
            order.updated_at = datetime.now().isoformat()
            import logging
            _trade_logger = logging.getLogger("trading")
            _trade_logger.warning(f"订单被拒绝: {order.order_id}, 原因: {e}")
            
        self.account.orders.append(order)
        return order
    
    def get_account_info(self) -> dict:
        """获取账户信息"""
        # 更新总资产（使用当前价格）
        current_prices = {}
        # 这里应该从市场数据获取当前价格，暂时使用成本价
        for pos in self.account.positions:
            current_prices[pos.symbol] = pos.current_price if pos.current_price > 0 else pos.cost_price
        
        self.account.total_assets = self.account.available_cash
        for pos in self.account.positions:
            current_price = current_prices.get(pos.symbol, pos.cost_price)
            self.account.total_assets += pos.quantity * current_price
        
        # 更新最大最小资产
        if self.account.total_assets > self.max_assets:
            self.max_assets = self.account.total_assets
        if self.account.total_assets < self.min_assets:
            self.min_assets = self.account.total_assets
        
        return {
            'total_assets': self.account.total_assets,
            'available_cash': self.account.available_cash,
            'frozen_cash': self.account.frozen_cash,
            'initial_assets': self.initial_assets,
            'max_assets': self.max_assets,
            'min_assets': self.min_assets,
            'max_drawdown': self.calculate_max_drawdown(),
            'positions': [
                {
                    'symbol': pos.symbol,
                    'quantity': pos.quantity,
                    'available_quantity': pos.available_quantity,
                    'cost_price': pos.cost_price,
                    'current_price': pos.current_price,
                    'market_value': pos.market_value,
                    'profit_loss': pos.profit_loss,
                    'profit_loss_ratio': pos.profit_loss_ratio,
                    'position_ratio': (pos.market_value / self.account.total_assets * 100) if self.account.total_assets > 0 else 0,
                }
                for pos in self.account.positions
            ],
            'orders': [
                {
                    'order_id': order.order_id,
                    'symbol': order.symbol,
                    'action': order.action,
                    'price': order.price,
                    'quantity': order.quantity,
                    'status': order.status,
                    'filled_price': order.filled_price,
                    'filled_quantity': order.filled_quantity,
                    'created_at': order.created_at,
                    'updated_at': order.updated_at,
                }
                for order in self.account.orders[-10:]  # 最近10笔订单
            ]
        }
    
    def calculate_max_drawdown(self) -> float:
        """计算最大回撤"""
        if self.max_assets == 0:
            return 0.0
        return (self.max_assets - self.account.total_assets) / self.max_assets * 100
    
    def check_risk_management(self, symbol: str, action: str, quantity: int, price: float) -> tuple[bool, str]:
        """检查风险管理规则"""
        # 检查持仓比例
        if action == 'buy':
            position_value = quantity * price
            position_ratio = position_value / self.account.total_assets
            if position_ratio > self.max_position_ratio:
                return False, f"单个股票持仓比例不能超过 {self.max_position_ratio*100}%"
        
        # 检查止损止盈
        position = self.account.get_position(symbol)
        if position:
            profit_loss_ratio = position.profit_loss_ratio
            if profit_loss_ratio <= -self.stop_loss_ratio * 100:
                return False, f"触发止损: 亏损 {profit_loss_ratio:.2f}%"
            if profit_loss_ratio >= self.take_profit_ratio * 100:
                return False, f"触发止盈: 盈利 {profit_loss_ratio:.2f}%"
        
        # 检查最大回撤
        max_drawdown = self.calculate_max_drawdown()
        if max_drawdown > self.max_drawdown_ratio * 100:
            return False, f"触发最大回撤限制: {max_drawdown:.2f}%"
        
        return True, "通过风险检查"
    
    def update_current_prices(self, prices: dict[str, float]):
        """更新当前价格"""
        for pos in self.account.positions:
            if pos.symbol in prices:
                pos.current_price = prices[pos.symbol]
    
    def set_risk_parameters(self, max_position_ratio: float = None, stop_loss_ratio: float = None, 
                          take_profit_ratio: float = None, max_drawdown_ratio: float = None):
        """设置风险管理参数"""
        if max_position_ratio is not None:
            self.max_position_ratio = max_position_ratio
        if stop_loss_ratio is not None:
            self.stop_loss_ratio = stop_loss_ratio
        if take_profit_ratio is not None:
            self.take_profit_ratio = take_profit_ratio
        if max_drawdown_ratio is not None:
            self.max_drawdown_ratio = max_drawdown_ratio
