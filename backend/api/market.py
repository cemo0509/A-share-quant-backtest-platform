"""市场状态相关 API 路由。"""

from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from core.market_state import MarketStateDetector, get_index_data

router = APIRouter()
logger = logging.getLogger("market")

# 市场状态检测器（全局单例）
_market_detector = MarketStateDetector()


@router.get("/state")
def get_market_state(
    symbol: str = Query("000001", description="指数代码（000001=上证指数）"),
):
    """获取市场状态（计划书要求：GET /api/market/state）。
    
    返回当前市场状态（bull/normal/bear）、波动率、多周期趋势等。
    """
    try:
        # 获取指数数据
        index_data = get_index_data(symbol)
        
        if index_data.empty:
            return {
                "status": "ok",
                "data": {
                    "trend": "normal",
                    "trend_20d": 0.0,
                    "volatility": "normal",
                    "multi_trend": {},
                    "message": "指数数据不可用，返回默认状态",
                }
            }
        
        # 获取市场状态
        state = _market_detector.get_market_state(index_data)
        
        return {
            "status": "ok",
            "data": state,
        }
    except Exception as e:
        logger.error(f"市场状态获取异常: {e}")
        raise HTTPException(status_code=500, detail="市场状态获取失败，请稍后重试")


@router.get("/trend")
def get_market_trend(
    symbol: str = Query("000001", description="指数代码"),
    bull_threshold: float = Query(10.0, description="牛市阈值（20日涨幅%）"),
    bear_threshold: float = Query(-10.0, description="熊市阈值（20日跌幅%）"),
):
    """获取市场趋势（简化版，只返回趋势）。"""
    try:
        index_data = get_index_data(symbol)
        
        if len(index_data) < 20:
            return {"status": "ok", "data": {"trend": "normal", "change_20d": 0.0}}
        
        trend = _market_detector.detect_trend(index_data, bull_threshold, bear_threshold)
        change_20d = (index_data.iloc[-1] / index_data.iloc[-20] - 1) * 100
        
        return {
            "status": "ok",
            "data": {
                "trend": trend,
                "change_20d": round(change_20d, 2),
            }
        }
    except Exception as e:
        logger.error(f"市场趋势获取异常: {e}")
        raise HTTPException(status_code=500, detail="市场趋势获取失败，请稍后重试")
