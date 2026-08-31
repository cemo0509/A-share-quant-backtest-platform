"""数据管理相关 API 路由。"""
from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.data_loader import (
    fetch_kline, list_cache, clear_cache, fetch_realtime_quote, clear_stale_cache,
)
from core import datasource
from core.net_errors import is_network_error
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
        # 下载是主动操作，失败需明确告知；网络类问题用 503 与真正的服务端错误区分，
        # 避免日志把「外部数据源不可用」记成服务端 bug。
        if is_network_error(e):
            logger.warning(f"数据拉取失败（网络/数据源）: {e}")
            raise HTTPException(
                status_code=503, detail="行情数据源暂时不可用，请检查网络后重试"
            )
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


@router.delete("/cache/stale")
def delete_stale_cache(max_age_days: float = 30.0):
    """清理长期未更新的缓存（默认 30 天）。

    全市场预热会产生数千个 parquet，磁盘无上限增长。
    按「最后更新时间」清理，近期活跃使用的数据不受影响。
    """
    count = clear_stale_cache(max_age_days)
    return {"status": "ok", "deleted": count, "max_age_days": max_age_days}


@router.post("/realtime")
def get_realtime_quotes(req: RealtimeQuoteRequest):
    """获取实时行情数据。"""
    # 实时行情是高频轮询接口，弱网环境下数据源降级链路可能耗时较长
    #（例如先尝试通达信再回退东财）。为防止前端长时间挂起，强制 12 秒
    # 内必须返回；超时则返回 degraded 空结果，前端自行提示。
    import concurrent.futures as _cf

    def _fetch():
        return fetch_realtime_quote(req.symbols)

    try:
        with _cf.ThreadPoolExecutor(max_workers=1) as pool:
            data = pool.submit(_fetch).result(timeout=12)
        return {"status": "ok", "data": data}
    except _cf.TimeoutError:
        logger.warning("实时行情获取超时（12s），降级返回空结果")
        return {
            "status": "ok",
            "data": [],
            "degraded": True,
            "reason": "实时行情获取超时，已显示空数据",
        }
    except Exception as e:
        # 网络抖动时降级为空结果，避免前端持续飘红；真正的代码缺陷仍走 500。
        if is_network_error(e):
            logger.warning(f"实时行情获取失败（网络/数据源）: {e}")
            return {
                "status": "ok",
                "data": [],
                "degraded": True,
                "reason": "实时行情暂不可用（网络或数据源问题）",
            }
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

