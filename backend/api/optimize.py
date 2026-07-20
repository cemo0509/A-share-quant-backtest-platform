"""参数优化相关 API 路由。"""
from __future__ import annotations

import itertools
import csv
import io
import logging
from typing import Any, List, Optional
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from core.engine import run_backtest
from core.strategies.registry import get_strategy
from models.schemas import (
    OptimizeRequest, OptimizeResultItem, OptimizeResponse,
    ExportJsonRequest, ExportCsvRequest,
)

router = APIRouter()
logger = logging.getLogger("optimize")

# 最大参数组合数（防止穷举搜索无限超时）
MAX_COMBINATIONS = 2000
# 单次回测超时时间（秒）
SINGLE_BACKTEST_TIMEOUT = 30
# 优化总超时时间（秒）
OPTIMIZE_TOTAL_TIMEOUT = 300


def _extract_metrics(result: dict) -> dict:
    """从 run_backtest 返回结果中提取指标字典。

    run_backtest 返回 {"metrics": {...}, "equity_curve": [...], ...}
    指标在 metrics 嵌套层中。
    """
    metrics = result.get("metrics", {})
    # 兼容直接用 result 作为指标的情况
    if not metrics and any(k in result for k in ("sharpe_ratio", "total_return")):
        return result
    return metrics


@router.post("")
def optimize_params(req: OptimizeRequest):
    """参数优化扫描。

    对参数网格进行穷举搜索，返回每组参数的回测结果，
    并按优化目标排序，找出最优参数组合。
    """
    import time
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

    try:
        get_strategy(req.strategy)  # 验证策略存在

        param_names = list(req.param_grid.keys())
        param_values = list(req.param_grid.values())
        param_combinations = list(itertools.product(*param_values))

        # 限制组合数，防止无限超时
        total_combos = len(param_combinations)
        if total_combos > MAX_COMBINATIONS:
            raise HTTPException(
                status_code=400,
                detail=f"参数组合数过多（{total_combos}），超过上限 {MAX_COMBINATIONS}。请减少参数范围。"
            )

        results = []
        start_time = time.time()
        logger.info(f"开始参数优化: {req.strategy} {req.symbol}, 共 {total_combos} 组参数")

        def _run_single(params):
            """在独立线程中运行单次回测，带超时保护。"""
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    run_backtest,
                    strategy_key=req.strategy,
                    symbol=req.symbol,
                    start_date=req.start_date,
                    end_date=req.end_date,
                    cash=req.cash,
                    commission=req.commission,
                    slippage=req.slippage,
                    params=params,
                )
                try:
                    return future.result(timeout=SINGLE_BACKTEST_TIMEOUT)
                except FutureTimeoutError:
                    logger.warning(f"单次回测超时: params={params}")
                    return None

        for idx, combo in enumerate(param_combinations):
            # 总超时检查
            elapsed = time.time() - start_time
            if elapsed > OPTIMIZE_TOTAL_TIMEOUT:
                logger.warning(f"参数优化总超时（{OPTIMIZE_TOTAL_TIMEOUT}s），已处理 {idx}/{total_combos}")
                break

            params = dict(zip(param_names, combo))
            try:
                raw = _run_single(params)
                if raw is None:
                    continue

                m = _extract_metrics(raw)

                # 根据优化目标提取 metric_value
                if req.metric == "sharpe_ratio":
                    metric_value = m.get("sharpe_ratio", 0)
                elif req.metric == "total_return":
                    metric_value = m.get("total_return", 0)
                elif req.metric == "max_drawdown":
                    metric_value = -abs(m.get("max_drawdown", 100))  # 越小越好，取负
                elif req.metric == "annual_return":
                    metric_value = m.get("annual_return", 0)
                elif req.metric == "win_rate":
                    metric_value = m.get("win_rate", 0)
                else:
                    metric_value = m.get("sharpe_ratio", 0)

                results.append(OptimizeResultItem(
                    params=params,
                    metric_value=metric_value,
                    total_return=m.get("total_return", 0),
                    annual_return=m.get("annual_return", 0),
                    sharpe_ratio=m.get("sharpe_ratio", 0),
                    max_drawdown=m.get("max_drawdown", 0),
                    win_rate=m.get("win_rate", 0),
                    total_trades=m.get("total_trades", 0),
                ))
            except Exception as e:
                logger.debug(f"参数组合回测失败 {params}: {e}")
                continue

            # 每10%输出一次进度日志
            if total_combos > 10 and (idx + 1) % max(1, total_combos // 10) == 0:
                logger.info(f"参数优化进度: {idx + 1}/{total_combos} ({round((idx + 1) / total_combos * 100)}%)")

        logger.info(f"参数优化完成: 有效结果 {len(results)}/{total_combos}，耗时 {round(time.time() - start_time, 1)}s")

        if not results:
            return OptimizeResponse(status="ok", data=[], best_params=None, best_metric_value=None)

        # 按目标指标排序（max_drawdown 越小越好，metric_value 已取负）
        results.sort(key=lambda x: x.metric_value, reverse=True)

        best = results[0]
        return OptimizeResponse(
            status="ok",
            data=results,
            best_params=best.params,
            best_metric_value=best.metric_value,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"参数优化异常: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="参数优化执行失败，请稍后重试")


@router.get("/metrics")
def get_optimize_metrics():
    """返回支持的优化目标列表。"""
    return {
        "status": "ok",
        "data": [
            {"key": "sharpe_ratio", "name": "夏普比率", "description": "风险调整后收益（越高越好）"},
            {"key": "total_return", "name": "总收益率", "description": "累计收益率（越高越好）"},
            {"key": "annual_return", "name": "年化收益率", "description": "年化收益（越高越好）"},
            {"key": "max_drawdown", "name": "最大回撤", "description": "最大亏损幅度（越小越好）"},
            {"key": "win_rate", "name": "胜率", "description": "盈利交易占比（越高越好）"},
        ],
    }


# ==================== 回测结果导出 ====================

@router.post("/export/json")
def export_json(req: ExportJsonRequest):
    """导出回测结果为 JSON 文件下载。"""
    import json
    from datetime import datetime

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # json.dumps 自动处理 datetime 等类型
    content = json.dumps(req.result, ensure_ascii=False, indent=2, default=str)
    buf = io.BytesIO(content.encode("utf-8"))

    return StreamingResponse(
        buf,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=backtest_result_{timestamp}.json"},
    )


@router.post("/export/csv")
def export_csv(req: ExportCsvRequest):
    """导出回测交易明细为 CSV 文件下载。"""
    from datetime import datetime

    if not req.trades:
        raise HTTPException(status_code=400, detail="没有交易明细可导出")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(req.trades[0].keys()))
    writer.writeheader()
    writer.writerows(req.trades)

    bytes_buf = io.BytesIO(output.getvalue().encode("utf-8-sig"))

    return StreamingResponse(
        bytes_buf,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=backtest_trades_{timestamp}.csv"},
    )
