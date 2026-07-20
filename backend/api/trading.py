"""交易相关 API 路由。"""
from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from fastapi import APIRouter, HTTPException

from core.trading import TradingSimulator
from models.schemas import PlaceOrderRequest, ResetAccountRequest

router = APIRouter()
logger = logging.getLogger("trading")


def _get_trading_state_file() -> Path:
    """获取交易状态持久化文件路径。"""
    app_data = os.environ.get('APPDATA') or os.path.expanduser('~')
    data_dir = Path(app_data) / 'A股量化回测平台' / 'data'
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / 'trading_state.json'


def _save_trading_state(simulator: TradingSimulator):
    """持久化交易模拟器状态到文件。"""
    try:
        info = simulator.get_account_info()
        state_file = _get_trading_state_file()
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(info, f, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        logger.warning(f"保存交易状态失败: {e}")


def _load_trading_state() -> dict:
    """从文件加载交易状态。"""
    state_file = _get_trading_state_file()
    if not state_file.exists():
        return {}
    try:
        with open(state_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


# 全局交易模拟器（从持久化文件恢复状态）
_trading_simulator = TradingSimulator()
_trading_lock = threading.Lock()

# 尝试从持久化文件恢复初始资金
_saved_state = _load_trading_state()
if _saved_state and _saved_state.get('cash', 0) > 0:
    _trading_simulator = TradingSimulator(initial_cash=_saved_state['cash'])


@router.post("/order")
def place_order(req: PlaceOrderRequest):
    """下单（模拟交易）"""
    try:
        with _trading_lock:
            order = _trading_simulator.place_order(
                symbol=req.symbol,
                action=req.action,
                quantity=req.quantity,
                price=req.price
            )
            # 持久化状态
            _save_trading_state(_trading_simulator)
        return {
            "status": "ok",
            "data": {
                "order_id": order.order_id,
                "status": order.status,
                "filled_price": order.filled_price,
                "filled_quantity": order.filled_quantity,
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail="下单参数无效，请检查输入")
    except Exception as e:
        logger.error(f"下单异常: {e}")
        raise HTTPException(status_code=500, detail="下单失败，请稍后重试")


@router.get("/account")
def get_account():
    """获取账户信息"""
    try:
        info = _trading_simulator.get_account_info()
        return {"status": "ok", "data": info}
    except Exception as e:
        logger.error(f"获取账户信息异常: {e}")
        raise HTTPException(status_code=500, detail="账户信息获取失败，请稍后重试")


@router.post("/reset")
def reset_account(req: ResetAccountRequest):
    """重置账户"""
    global _trading_simulator
    with _trading_lock:
        _trading_simulator = TradingSimulator(initial_cash=req.initial_cash)
        _save_trading_state(_trading_simulator)
    return {"status": "ok", "message": "账户已重置"}


@router.get("/positions")
def get_positions():
    """获取持仓信息"""
    try:
        info = _trading_simulator.get_account_info()
        return {"status": "ok", "data": info["positions"]}
    except Exception as e:
        logger.error(f"获取持仓异常: {e}")
        raise HTTPException(status_code=500, detail="持仓信息获取失败，请稍后重试")


@router.get("/orders")
def get_orders():
    """获取订单历史"""
    try:
        info = _trading_simulator.get_account_info()
        return {"status": "ok", "data": info["orders"]}
    except Exception as e:
        logger.error(f"获取订单异常: {e}")
        raise HTTPException(status_code=500, detail="订单历史获取失败，请稍后重试")
