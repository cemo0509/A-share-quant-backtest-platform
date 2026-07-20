"""盘中实时监控 API（CCI+MACD 选股需求新增）。

- POST /api/monitor/start   启动监控
- POST /api/monitor/stop    停止监控
- GET  /api/monitor/pool    获取当前动态股票池
- GET  /api/monitor/status  获取监控状态
- POST /api/monitor/refine  在结果内二次精筛
"""
from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

from core.realtime_monitor import get_monitor
from core.screen_factors import list_factor_defs, build_default_factor_config

logger = logging.getLogger("monitor")
router = APIRouter()


class MonitorStartRequest(BaseModel):
    interval: int = Field(60, description="扫描间隔（秒），最小10")
    period: str = Field("30", description="选股周期(分钟)，任意正整数，如 5/15/30/45/90/120/240")
    min_amount: float = Field(5.0, description="最小成交额(亿)")
    max_stocks: int = Field(200, description="单次扫描最多候选数")
    combine: str = Field("AND", description="多因子组合方式: AND 全部满足 / OR 任一满足")
    factors: dict = Field(default_factory=dict, description="因子配置 {key: {enabled, params}}")
    # 兼容旧版调用
    cci_threshold: float = Field(300, description="[兼容] CCI阈值")
    zero_line_band: float = Field(0.5, description="[兼容] MACD零线带宽")


class RefineRequest(BaseModel):
    symbols: list[str] = Field(default_factory=list, description="待精筛的股票代码列表；空表示对当前池精筛")
    min_cci: float = Field(0, description="CCI 下限")
    min_price: float = Field(0, description="现价下限")
    max_price: float = Field(0, description="现价上限，0表示不限")
    sector: str = Field("", description="行业关键词过滤")


@router.post("/monitor/start")
def start_monitor(req: MonitorStartRequest):
    """启动盘中实时监控。"""
    monitor = get_monitor()
    monitor.start(
        interval=req.interval,
        params={
            "factors": req.factors,
            "combine": req.combine,
            "period": req.period,
            "min_amount": req.min_amount,
            "max_stocks": req.max_stocks,
            "cci_threshold": req.cci_threshold,
            "zero_line_band": req.zero_line_band,
        },
    )
    return {"status": "ok", "message": "监控已启动", "data": monitor.status()}


@router.post("/monitor/stop")
def stop_monitor():
    """停止盘中实时监控。"""
    monitor = get_monitor()
    monitor.stop()
    return {"status": "ok", "message": "监控已停止", "data": monitor.status()}


@router.get("/monitor/status")
def monitor_status():
    """获取监控状态。"""
    return {"status": "ok", "data": get_monitor().status()}


@router.get("/monitor/pool")
def monitor_pool():
    """获取当前动态股票池。"""
    return {"status": "ok", "data": get_monitor().get_pool()}


@router.get("/monitor/factor-defs")
def monitor_factor_defs():
    """获取可选因子定义（供前端渲染勾选面板）。"""
    return {
        "status": "ok",
        "data": {
            "factors": list_factor_defs(),
            "defaults": build_default_factor_config(),
        },
    }


@router.post("/monitor/refine")
def refine_pool(req: RefineRequest):
    """在结果内二次精筛。

    对当前动态池（或指定 symbols 子集）按 CCI/价格/行业进一步过滤。
    """
    monitor = get_monitor()
    pool = monitor.get_pool().get("pool", [])

    # 限定子集
    if req.symbols:
        symset = set(req.symbols)
        pool = [p for p in pool if p.get("symbol") in symset]

    def _keep(item: dict) -> bool:
        if req.min_cci and item.get("cci", 0) < req.min_cci:
            return False
        price = item.get("price", 0)
        if req.min_price and price < req.min_price:
            return False
        if req.max_price and price > req.max_price:
            return False
        if req.sector and req.sector not in str(item.get("sector", "")):
            return False
        return True

    refined = [p for p in pool if _keep(p)]
    return {"status": "ok", "data": {"pool": refined, "count": len(refined)}}
