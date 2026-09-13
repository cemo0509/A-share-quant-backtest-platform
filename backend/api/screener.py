"""自定义因子选股 API：按可视化条件组合筛选股票。

与 /stock-scan 的区别：
- /stock-scan 基于**预置策略** + backtrader 逐股回测（重、慢）。
- /screener 基于用户**自由组合的因子**，直接对本地缓存数据计算指标并布尔筛选
  （向量化、不跑回测）。配合数据预热，做到「首次下载慢、之后改条件秒级」。
"""
from __future__ import annotations

import logging
from datetime import datetime as dt, timedelta

from fastapi import APIRouter, HTTPException

from api.stock_scan import _get_scan_symbols
from core.data_loader import prefetch_klines
from core.screener import screen_symbols
from models.schemas import ScreenerRequest

router = APIRouter()
logger = logging.getLogger("screener_api")


def _extract_leaves(rule: dict) -> list[dict]:
    """从 VisualRule 提取所有叶子条件（扁平 AND）。

    同花顺式编辑器只产出扁平结构，但为兼容旧数据里可能存在的嵌套 group，
    这里递归收集全部 condition 叶子并统一按 AND 处理。
    """
    leaves: list[dict] = []

    def walk(node):
        if not isinstance(node, dict):
            return
        if node.get("type") == "condition":
            leaves.append(node)
            return
        for it in node.get("items") or []:
            walk(it)

    if not rule:
        return leaves
    if rule.get("type") == "condition":
        leaves.append(rule)
    else:
        for it in rule.get("items") or []:
            walk(it)
    return leaves


@router.post("/screener/run")
def run_screener(req: ScreenerRequest):
    """自定义因子选股。

    流程：提取条件叶子 → 解析日期/股票范围 → 可选预热数据 → 向量化筛选 → 返回结果。
    mock 数据与异常股票一律不返回（宁缺毋滥，不输出噪声）。
    """
    try:
        leaves = _extract_leaves(req.rule or {})
        if not leaves:
            raise HTTPException(status_code=400, detail="请至少添加一个筛选条件")

        # 日期范围：区间优先，否则单日（end=scan_date，start 向前推 400 天保证指标有足够历史）
        if req.start_date and req.end_date:
            start_date, end_date = req.start_date, req.end_date
        else:
            scan_date = req.scan_date or dt.now().strftime("%Y%m%d")
            end_date = scan_date
            start_date = (dt.strptime(scan_date, "%Y%m%d") - timedelta(days=400)).strftime("%Y%m%d")

        # 股票范围（复用选股池的范围解析：all/hs300/zz500/custom）
        symbols = _get_scan_symbols(req.stock_range, req.custom_stocks, req.max_stocks)
        if not symbols:
            raise HTTPException(status_code=400, detail="选股范围为空，请检查 stock_range")

        # 数据预热：首次把范围内股票 K 线批量下载到本地缓存（慢一次）；
        # 之后改条件直接命中缓存，秒级。预热失败不阻断——用已缓存部分继续筛。
        if req.prepare_first:
            try:
                prefetch_klines(
                    symbols=symbols,
                    start_date=start_date,
                    end_date=end_date,
                    period="daily",
                    max_workers=50,
                )
            except Exception as e:
                logger.warning(f"数据预热部分失败（继续用已缓存数据筛选）: {e}")

        # 向量化筛选（直接算指标 + 布尔判断，不跑回测）
        results = screen_symbols(
            symbols=symbols,
            leaves=leaves,
            start_date=start_date,
            end_date=end_date,
            max_workers=8,
        )

        return {
            "status": "ok",
            "data": results,
            "total_scanned": len(symbols),
            "matched": len(results),
            "condition_count": len(leaves),
            "start_date": start_date,
            "end_date": end_date,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"因子选股异常: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"因子选股执行失败: {e}")
