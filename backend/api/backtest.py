"""回测相关 API 路由。"""
from __future__ import annotations

import logging
import traceback
from pathlib import Path
from fastapi import APIRouter, HTTPException

from core.engine import run_backtest
from core.strategies.custom_manager import load_strategy_from_code
from core import backtest_store
from models.schemas import BacktestRequest, BacktestCodeRequest, CompareRequest

router = APIRouter()
logger = logging.getLogger("backtest")


# ==================== 回测历史（P0-9 持久化） ====================
# 注意：/history 路由必须定义在 /{xxx} 形式的路由之前，
# 否则会被路径参数路由抢先匹配。

@router.get("/history")
def list_history(limit: int = 100, symbol: str = ""):
    """列出回测历史（摘要，按时间倒序）。"""
    return {"status": "ok", "data": backtest_store.list_runs(limit=limit, symbol=symbol)}


@router.get("/history/{run_id}")
def get_history(run_id: str):
    """读取单条回测（含完整结果，可重新载入结果页复盘）。"""
    rec = backtest_store.get_run(run_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="回测记录不存在")
    return {"status": "ok", "data": rec}


@router.delete("/history/{run_id}")
def delete_history(run_id: str):
    """删除单条回测记录。"""
    if not backtest_store.delete_run(run_id):
        raise HTTPException(status_code=404, detail="回测记录不存在")
    return {"status": "ok", "message": "已删除"}


@router.delete("/history")
def clear_history():
    """清空全部回测历史。"""
    count = backtest_store.clear_runs()
    return {"status": "ok", "deleted": count}


@router.post("/run")
def run(req: BacktestRequest):
    """执行回测，返回指标、资金曲线、交易明细、K线数据。"""
    try:
        logger.info(f"收到回测请求: strategy={req.strategy}, symbol={req.symbol}, "
                    f"period={req.start_date}~{req.end_date}, params={req.params}")
        result = run_backtest(
            strategy_key=req.strategy,
            symbol=req.symbol,
            start_date=req.start_date,
            end_date=req.end_date,
            params=req.params,
            cash=req.cash,
            commission=req.commission,
            slippage=req.slippage,
            period=req.period,
            adjust=req.adjust,
            position_sizing=req.position_sizing,
            position_percent=req.position_percent,
            max_position=req.max_position,
            risk_percent=req.risk_percent,
            atr_multiplier=req.atr_multiplier,
            target_volatility=req.target_volatility,
        )
        logger.info("回测成功完成")

        # 持久化到 SQLite（P0-9）：保存失败不影响本次回测返回
        try:
            strat_info = None
            try:
                from core.strategies.registry import get_strategy

                strat_info = get_strategy(req.strategy)
            except Exception:
                pass
            result["run_id"] = backtest_store.save_run(
                result,
                strategy_key=req.strategy,
                strategy_name=getattr(strat_info, "name", "") or req.strategy,
                symbol=req.symbol,
                start_date=req.start_date,
                end_date=req.end_date,
                period=req.period,
                adjust=req.adjust,
                position_sizing=req.position_sizing,
                cash=req.cash,
                commission=req.commission,
                slippage=req.slippage,
                params=req.params,
            )
        except Exception as e:
            logger.warning(f"保存回测历史失败（不影响回测结果）: {e}")

        return {"status": "ok", "data": result}
    except ValueError as e:
        logger.error(f"ValueError: {e}")
        raise HTTPException(status_code=400, detail="回测参数无效，请检查输入")
    except Exception as e:
        logger.error(f"回测异常: {e}")
        logger.error(f"traceback:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="回测执行失败，请稍后重试")


@router.post("/run_code")
def run_code(req: BacktestCodeRequest):
    """执行自定义代码回测，动态加载策略类后运行回测。"""
    try:
        logger.info(f"收到自定义代码回测请求: symbol={req.symbol}, "
                    f"period={req.start_date}~{req.end_date}")
        # 从代码字符串中动态加载策略类
        strategy_cls = load_strategy_from_code(req.code)
        result = run_backtest(
            strategy_cls=strategy_cls,
            symbol=req.symbol,
            start_date=req.start_date,
            end_date=req.end_date,
            cash=req.cash,
            commission=req.commission,
            slippage=req.slippage,
            period=req.period,
            adjust=req.adjust,
        )
        logger.info("自定义代码回测成功完成")
        return {"status": "ok", "data": result}
    except ValueError as e:
        logger.error(f"ValueError: {e}")
        raise HTTPException(status_code=400, detail="策略代码无效，请检查语法")
    except Exception as e:
        logger.error(f"自定义代码回测异常: {e}")
        logger.error(f"traceback:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="自定义代码回测执行失败，请稍后重试")



@router.post("/compare")
def compare_strategies(req: CompareRequest):
    """比较多个策略的回测结果。"""
    import time as _time
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
    
    try:
        logger.info(f"收到策略比较请求: strategies={req.strategies}, symbol={req.symbol}")
        
        # 限制比较策略数量，防止超时
        max_compare = 5
        compare_list = req.strategies[:max_compare]
        if len(req.strategies) > max_compare:
            logger.warning(f"策略比较数量超过上限 {max_compare}，仅比较前 {max_compare} 个")
        
        results = []
        # 单策略回测超时 60s
        SINGLE_TIMEOUT = 60
        
        for strategy_key in compare_list:
            future = None
            executor = None
            try:
                executor = ThreadPoolExecutor(max_workers=1)
                future = executor.submit(
                    run_backtest,
                    strategy_key=strategy_key,
                    symbol=req.symbol,
                    start_date=req.start_date,
                    end_date=req.end_date,
                    params={},
                    cash=req.cash,
                    commission=req.commission,
                    slippage=req.slippage,
                    period=req.period,
                    adjust=req.adjust,
                )
                result = future.result(timeout=SINGLE_TIMEOUT)
                results.append({
                    "strategy": strategy_key,
                    "status": "ok",
                    "data": result
                })
            except FutureTimeoutError:
                logger.error(f"策略 {strategy_key} 回测超时 ({SINGLE_TIMEOUT}s)")
                # 超时后取消 future 并关闭 executor
                if future is not None:
                    future.cancel()
                if executor is not None:
                    executor.shutdown(wait=False, cancel_futures=True)
                results.append({
                    "strategy": strategy_key,
                    "status": "error",
                    "detail": "该策略回测超时"
                })
            except Exception as e:
                logger.error(f"策略 {strategy_key} 回测失败: {e}")
                results.append({
                    "strategy": strategy_key,
                    "status": "error",
                    "detail": "该策略回测执行失败"
                })
            finally:
                if executor is not None:
                    try:
                        executor.shutdown(wait=False, cancel_futures=True)
                    except Exception:
                        pass
        
        logger.info(f"策略比较完成: {len(results)} 个策略")
        return {"status": "ok", "data": results}
        
    except Exception as e:
        logger.error(f"策略比较异常: {e}")
        logger.error(f"traceback:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="策略比较执行失败，请稍后重试")
