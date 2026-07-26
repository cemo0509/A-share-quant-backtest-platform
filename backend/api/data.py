"""数据管理相关 API 路由。"""
from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.data_loader import fetch_kline, list_cache, clear_cache, fetch_realtime_quote
from core import datasource
from models.schemas import FetchDataRequest, RealtimeQuoteRequest

router = APIRouter()
logger = logging.getLogger("data")


class SetSourceRequest(BaseModel):
    source: str = "eastmoney"


@router.post("/fetch")
def fetch_data(req: FetchDataRequest):
    """下载并缓存股票数据，返回数据摘要。"""
    try:
        df = fetch_kline(req.symbol, req.start_date, req.end_date, period=req.period)
        if df.empty:
            raise HTTPException(status_code=404, detail=f"未获取到 {req.symbol} 的数据")
        return {
            "status": "ok",
            "data": {
                "symbol": req.symbol,
                "rows": len(df),
                "start": str(df["date"].min().date()),
                "end": str(df["date"].max().date()),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"数据拉取异常: {e}")
        raise HTTPException(status_code=500, detail="数据获取失败，请稍后重试")


@router.get("/cache")
def get_cache():
    """列出所有本地缓存的数据文件。"""
    return {"status": "ok", "data": list_cache()}


@router.delete("/cache")
def delete_cache(symbol: str = ""):
    """清理缓存。symbol 为空则清空全部。"""
    count = clear_cache(symbol or None)
    return {"status": "ok", "deleted": count}


@router.post("/realtime")
def get_realtime_quotes(req: RealtimeQuoteRequest):
    """获取实时行情数据。"""
    try:
        data = fetch_realtime_quote(req.symbols)
        return {"status": "ok", "data": data}
    except Exception as e:
        logger.error(f"实时行情获取异常: {e}")
        raise HTTPException(status_code=500, detail="实时行情获取失败，请稍后重试")


@router.get("/source")
def get_source():
    """查看当前数据源及可用源。"""
    return {"status": "ok", "data": datasource.get_source_status()}


@router.post("/source")
def set_source(req: SetSourceRequest):
    """切换实时数据源（eastmoney / tongdaxin / xueqiu）。失败自动降级东方财富。"""
    ok = datasource.set_active_source(req.source)
    if not ok:
        raise HTTPException(status_code=400, detail="不支持的数据源，可选: eastmoney/tongdaxin/xueqiu")
    return {"status": "ok", "data": datasource.get_source_status()}

