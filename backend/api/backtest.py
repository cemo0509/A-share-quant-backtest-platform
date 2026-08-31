"""回测相关 API 路由。"""
from __future__ import annotations

import logging
import traceback
from pathlib import Path
from fastapi import APIRouter, HTTPException

from core.engine import run_backtest
from core.strategies.custom_manager import load_strategy_from_code
from models.schemas import BacktestRequest, BacktestCodeRequest, CompareRequest

router = APIRouter()
logger = logging.getLogger("backtest")


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
        )
        logger.info("回测成功完成")
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
