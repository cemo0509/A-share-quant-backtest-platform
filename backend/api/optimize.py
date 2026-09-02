"""参数优化相关 API 路由。"""
from __future__ import annotations

import itertools
import csv
import io
import logging
from typing import Any, List, Optional

import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from core.engine import run_backtest
from core.strategies.registry import get_strategy
from models.schemas import (
    OptimizeRequest, OptimizeResultItem, OptimizeResponse, OutSampleValidation,
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

# ==================== 样本外验证（P0-8） ====================
# 样本内占比：在样本内做参数搜索，样本外只用于检验
DEFAULT_TRAIN_RATIO = 0.7
# 样本外最少需要的交易日数；少于此值则跳过验证（数据太少验证无意义）
MIN_TEST_BARS = 60


def _split_date(symbol: str, start_date: str, end_date: str,
                train_ratio: float = DEFAULT_TRAIN_RATIO) -> tuple[str | None, str | None]:
    """按时间把区间切分为样本内/样本外，返回 (切分日, 未执行原因)。

    用实际交易日序列切分（而非按自然日），保证两段的数据量可控。
    """
    try:
        from core.data_loader import fetch_kline

        df = fetch_kline(symbol, start_date, end_date, period="daily")
        if df is None or df.empty or "date" not in df.columns:
            return None, "无法获取行情数据，跳过样本外验证"

        dates = pd.to_datetime(df["date"]).sort_values()
        n = len(dates)
        if n < MIN_TEST_BARS * 2:
            return None, (
                f"数据仅 {n} 个交易日，不足以支撑样本内外切分"
                f"（至少需要 {MIN_TEST_BARS * 2} 个交易日）"
            )

        split_idx = int(n * train_ratio)
        # 保证样本外至少有 MIN_TEST_BARS 根
        split_idx = min(split_idx, n - MIN_TEST_BARS)
        if split_idx <= 0:
            return None, "样本内区间过短，跳过样本外验证"

        return dates.iloc[split_idx].strftime("%Y%m%d"), None
    except Exception as e:
        return None, f"切分失败，跳过样本外验证: {e}"


def _retention(in_val, out_val) -> float | None:
    """计算保持率：样本外 / 样本内。样本内为 0 或负时无意义，返回 None。"""
    try:
        if in_val is None or out_val is None:
            return None
        iv, ov = float(in_val), float(out_val)
        if iv <= 0:
            return None  # 样本内为负谈不上保持率
        return round(ov / iv, 3)
    except Exception:
        return None


def _evaluate_overfit(in_m: dict, out_m: dict) -> tuple[bool, str, str]:
    """判断是否过拟合，返回 (是否告警, 级别, 说明)。

    判定依据（满足任一即告警）：
    1. 样本内盈利但样本外亏损 —— 最典型的过拟合
    2. 关键指标保持率过低（收益 < 30% 或夏普 < 30%）—— 参数严重依赖历史
    """
    in_ret = in_m.get("total_return")
    out_ret = out_m.get("total_return")
    in_sharpe = in_m.get("sharpe_ratio")
    out_sharpe = out_m.get("sharpe_ratio")

    ret_r = _retention(in_ret, out_ret)
    sharpe_r = _retention(in_sharpe, out_sharpe)

    # 情形1：样本内赚、样本外亏
    if in_ret is not None and out_ret is not None and in_ret > 0 and out_ret < 0:
        return True, "danger", (
            f"样本内盈利 {in_ret:.2f}% 但样本外亏损 {out_ret:.2f}%，"
            f"典型的过拟合特征：该参数高度依赖历史数据，不可直接用于实盘。"
        )

    # 情形2：保持率过低
    if ret_r is not None and ret_r < 0.3:
        return True, "danger", (
            f"样本外收益仅为样本内的 {ret_r * 100:.1f}%，衰减严重，"
            f"该参数很可能是对历史噪声的拟合。"
        )
    if sharpe_r is not None and sharpe_r < 0.3:
        return True, "warn", (
            f"样本外夏普仅为样本内的 {sharpe_r * 100:.1f}%，"
            f"风险调整后收益大幅下滑，建议谨慎使用。"
        )
    if ret_r is not None and ret_r < 0.6:
        return True, "warn", (
            f"样本外收益为样本内的 {ret_r * 100:.1f}%，"
            f"存在一定衰减，建议结合更长区间验证。"
        )

    return False, "none", "样本外表现与样本内基本一致，未检测到明显过拟合。"


def _run_validation(req: OptimizeRequest, best_params: dict,
                    best_metrics: dict | None = None) -> OutSampleValidation:
    """对最优参数执行样本外验证。

    流程：
    1. 按时间切分区间（样本内 70% / 样本外 30%）
    2. 样本内指标：优先复用搜索阶段已有的结果，避免重复回测
    3. 样本外：用**同一组**参数跑一次（绝不重新调优）
    4. 对比两者，判定是否过拟合
    """
    split_date, reason = _split_date(req.symbol, req.start_date, req.end_date)
    if split_date is None:
        return OutSampleValidation(enabled=False, reason=reason)

    try:
        # 样本内：优先复用搜索阶段结果
        in_m = dict(best_metrics) if best_metrics else None
        if not in_m:
            in_raw = run_backtest(
                strategy_key=req.strategy, symbol=req.symbol,
                start_date=req.start_date, end_date=split_date,
                params=best_params, cash=req.cash,
                commission=req.commission, slippage=req.slippage,
            )
            in_m = _extract_metrics(in_raw)

        # 样本外：split ~ end（同一组参数，绝不重新调优）
        out_raw = run_backtest(
            strategy_key=req.strategy, symbol=req.symbol,
            start_date=split_date, end_date=req.end_date,
            params=best_params, cash=req.cash,
            commission=req.commission, slippage=req.slippage,
        )
        out_m = _extract_metrics(out_raw)

        warn, level, message = _evaluate_overfit(in_m, out_m)

        return OutSampleValidation(
            enabled=True,
            train_ratio=DEFAULT_TRAIN_RATIO,
            split_date=split_date,
            train_range=f"{req.start_date} ~ {split_date}",
            test_range=f"{split_date} ~ {req.end_date}",
            in_sample=in_m,
            out_sample=out_m,
            retention={
                "total_return": _retention(in_m.get("total_return"), out_m.get("total_return")),
                "annual_return": _retention(in_m.get("annual_return"), out_m.get("annual_return")),
                "sharpe_ratio": _retention(in_m.get("sharpe_ratio"), out_m.get("sharpe_ratio")),
            },
            overfit_warning=warn,
            warning_level=level,
            warning_message=message,
        )
    except Exception as e:
        logger.warning(f"样本外验证失败（不影响优化结果）: {e}")
        return OutSampleValidation(enabled=False, reason=f"验证过程出错: {e}")


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

        # ---- 样本内外切分（P0-8）----
        # 参数搜索只在**样本内**进行，样本外留作检验。
        # 若在全区间搜索再用后段验证，样本外数据已被参数"看过"，
        # 验证就失去意义（数据泄露）。
        split_date, split_reason = _split_date(req.symbol, req.start_date, req.end_date)
        search_end = split_date or req.end_date
        if split_date:
            logger.info(f"样本内外切分: 搜索区间 {req.start_date}~{search_end}，"
                        f"验证区间 {split_date}~{req.end_date}")
        else:
            logger.warning(f"未启用样本外验证: {split_reason}")

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
                    end_date=search_end,  # 只在样本内搜索
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
                    # F-01：透传每组参数的数据源，让前端能识别
                    # 「最优参数是不是从 mock 数据里跑出来的」
                    data_source=raw.get("data_source", "unknown"),
                ))
            except Exception as e:
                logger.debug(f"参数组合回测失败 {params}: {e}")
                continue

            # 每10%输出一次进度日志
            if total_combos > 10 and (idx + 1) % max(1, total_combos // 10) == 0:
                logger.info(f"参数优化进度: {idx + 1}/{total_combos} ({round((idx + 1) / total_combos * 100)}%)")

        logger.info(f"参数优化完成: 有效结果 {len(results)}/{total_combos}，耗时 {round(time.time() - start_time, 1)}s")

        if not results:
            return OptimizeResponse(
                status="ok", data=[], best_params=None, best_metric_value=None,
                validation=OutSampleValidation(
                    enabled=False, reason=split_reason or "无有效回测结果"
                ),
            )

        # 按目标指标排序（max_drawdown 越小越好，metric_value 已取负）
        results.sort(key=lambda x: x.metric_value, reverse=True)

        best = results[0]

        # 用最优参数做样本外验证（P0-8）
        validation = _run_validation(
            req,
            best.params,
            best_metrics={
                "total_return": best.total_return,
                "annual_return": best.annual_return,
                "sharpe_ratio": best.sharpe_ratio,
                "max_drawdown": best.max_drawdown,
                "win_rate": best.win_rate,
                "total_trades": best.total_trades,
            },
        )
        if validation.enabled and validation.overfit_warning:
            logger.warning(f"过拟合告警[{validation.warning_level}]: "
                           f"{validation.warning_message}")

        return OptimizeResponse(
            status="ok",
            data=results,
            best_params=best.params,
            best_metric_value=best.metric_value,
            validation=validation,
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
