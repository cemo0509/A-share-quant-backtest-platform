"""选股池相关 API 路由（v3.0 新增）。

提供：
- POST /api/stock-scan — 选股扫描
- GET  /api/stock-scan/progress — SSE 进度推送
- GET/POST/DELETE /api/watchlist — 自选池管理
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from data.stock_names import (
    get_stock_name, get_stock_sector, get_all_codes, get_all_stock_symbols,
    refresh_stock_names,
)
from core.engine import run_backtest
from core.data_loader import prefetch_klines
from core.strategies.registry import get_strategy, list_strategies
from models.schemas import (
    StockScanRequest, StockScanResult, StockScanResponse, WatchlistItem,
    DataPrepareRequest,
)

logger = logging.getLogger("stock_scan")

router = APIRouter()

# 全局扫描进度存储（按 scan_id 索引）
_SCAN_PROGRESS: dict[str, dict] = {}
_SCAN_PROGRESS_LOCK = threading.Lock()

# 扫描进度过期时间（秒），超时自动清理
_SCAN_PROGRESS_TTL = 600  # 10 分钟

# 取消事件字典：scan_id → threading.Event，用于中止正在运行的下载/扫描任务
_CANCEL_EVENTS: dict[str, threading.Event] = {}
_CANCEL_EVENTS_LOCK = threading.Lock()

# backtrader 在并发场景下存在模块级非线程安全状态（Cerebro / 指标注册 /
# 部分 C 扩展），多线程同时 run() 在资源紧张时可能导致进程级崩溃。
# 用一把全局锁把 run_backtest 串行化，避免进程被杀后扫描结果（内存）丢失。
_BT_RUN_LOCK = threading.Lock()
# 等待回测锁的超时时间。超时后跳过该标的而不是无限排队，
# 避免僵尸线程持锁导致整轮扫描假死（Python 无法从外部终止线程）。
_BT_LOCK_TIMEOUT = 30.0

# 扫描结果持久化文件：进程崩溃/重启后仍能找回结果，避免前端 404
_SCAN_STORE_DIR = Path(__file__).resolve().parent.parent / "data" / "scan_results"
_SCAN_STORE_DIR.mkdir(parents=True, exist_ok=True)


def _scan_store_path(scan_id: str) -> Path:
    return _SCAN_STORE_DIR / f"{scan_id}.json"


def _persist_scan(scan_id: str):
    """将内存中的扫描进度异步落盘。"""
    try:
        with _SCAN_PROGRESS_LOCK:
            progress = _SCAN_PROGRESS.get(scan_id)
            if progress is None:
                return
            data = dict(progress)
        # 去掉内部字段（非 JSON 可序列化，且无需持久化）
        data.pop("_finished_at", None)
        with open(_scan_store_path(scan_id), "w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"持久化扫描结果失败 {scan_id}: {e}")


def _load_persisted_scan(scan_id: str) -> Optional[dict]:
    """从磁盘恢复已持久化的扫描结果（用于进程重启/被杀后找回）。

    注意：尊重磁盘上的 finished 字段——若扫描中途被杀（增量持久化时
    finished=False），恢复后仍标记为未完成，前端可以据此重试或继续，
    而不是误报「已完成」（之前强制 True 是为了防 404，但现在有了两阶段
    预热 + 增量持久化，更准确的未完成状态更安全）。
    """
    p = _scan_store_path(scan_id)
    if not p.exists():
        return None
    try:
        with open(p, "r", encoding="utf-8") as fp:
            data = json.load(fp)
        # 仅当磁盘上确实标记为未完成时才置 _restored_incomplete，
        # 让前端区分「正常完成」与「被杀中断」。已完成结果保持 finished=True。
        data["_restored"] = True
        return data
    except Exception:
        return None


def _restore_scans_on_boot():
    """进程启动时恢复上一次未清理的已完成扫描结果。"""
    try:
        for f in _SCAN_STORE_DIR.glob("*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                sid = f.stem
                data.setdefault("finished", True)
                data["_restored"] = True
                with _SCAN_PROGRESS_LOCK:
                    _SCAN_PROGRESS.setdefault(sid, data)
                logger.info(f"启动时恢复扫描结果: {sid}")
            except Exception:
                continue
    except Exception as e:
        logger.warning(f"恢复扫描结果失败: {e}")


# 进程启动时尝试恢复（模块加载即执行一次）
_restore_scans_on_boot()


def _cleanup_expired_progress():
    """清理过期的扫描进度数据，防止内存泄漏。"""
    now = time.time()
    with _SCAN_PROGRESS_LOCK:
        expired_ids = [
            sid for sid, p in _SCAN_PROGRESS.items()
            if p.get("finished") and (now - p.get("_finished_at", 0) > _SCAN_PROGRESS_TTL)
        ]
        for sid in expired_ids:
            _SCAN_PROGRESS.pop(sid, None)
            # 同时清理磁盘上的持久化文件
            try:
                _scan_store_path(sid).unlink(missing_ok=True)
            except Exception:
                pass
        if expired_ids:
            logger.debug(f"清理了 {len(expired_ids)} 个过期扫描进度")
    # 同步清理对应的取消事件
    with _CANCEL_EVENTS_LOCK:
        for sid in expired_ids:
            _CANCEL_EVENTS.pop(sid, None)


# ==================== 自选池存储 ====================

def _get_watchlist_file() -> Path:
    """获取自选池存储文件路径。"""
    app_data = os.environ.get('APPDATA') or os.path.expanduser('~')
    data_dir = Path(app_data) / 'A股量化回测平台' / 'data'
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / 'watchlist.json'


def _load_watchlist() -> list[dict]:
    """加载自选池。"""
    f = _get_watchlist_file()
    if not f.exists():
        return []
    try:
        with open(f, 'r', encoding='utf-8') as fp:
            return json.load(fp)
    except Exception:
        return []


def _save_watchlist(data: list[dict]):
    """保存自选池。"""
    f = _get_watchlist_file()
    with open(f, 'w', encoding='utf-8') as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)


# ==================== 选股扫描 API ====================

@router.post("/stock-scan")
def scan_stocks(req: StockScanRequest):
    """选股扫描：对全市场/指定范围的股票执行策略筛选。

    流程：
    1. 获取扫描范围的股票列表
    2. 并发加载K线数据并运行策略（ThreadPoolExecutor）
    3. 有交易信号的股票加入结果
    4. 返回匹配的股票列表 + scan_id（供前端轮询/SSE）
    """
    import uuid
    from datetime import datetime as dt, timedelta

    try:
        # 1. 验证策略存在且是选股策略
        strat_info = get_strategy(req.strategy_type)
        if strat_info.category not in ("screening", "hybrid"):
            return {
                "status": "error",
                "detail": f"策略 '{strat_info.name}' 的类别是 '{strat_info.category}'，不是选股策略。请选择 screening 或 hybrid 类型的策略。",
            }

        strategy_cls = strat_info.strategy_cls
        if strategy_cls is None:
            raise HTTPException(status_code=400, detail=f"策略 {req.strategy_type} 不可用")

        # 2. 确定扫描日期范围
        #    区间模式：显式传入 start_date / end_date
        #    单日模式：仅传入 scan_date，end_date 取该日，start_date 向前推 400 天作为回测窗口
        if req.start_date and req.end_date:
            start_date = req.start_date
            end_date = req.end_date
            scan_date = end_date
            date_mode = "range"
        else:
            scan_date = req.scan_date or dt.now().strftime("%Y%m%d")
            end_date = scan_date
            start_date = (dt.strptime(scan_date, "%Y%m%d") - timedelta(days=400)).strftime("%Y%m%d")
            date_mode = "single"

        # 3. 获取扫描范围的股票列表
        symbols = _get_scan_symbols(req.stock_range, req.custom_stocks, req.max_stocks)

        # 4. 生成 scan_id 并初始化进度
        scan_id = uuid.uuid4().hex[:12]
        cancel_evt = threading.Event()
        with _CANCEL_EVENTS_LOCK:
            _CANCEL_EVENTS[scan_id] = cancel_evt
        with _SCAN_PROGRESS_LOCK:
            _SCAN_PROGRESS[scan_id] = {
                "total": len(symbols),
                "scanned": 0,
                "matched": 0,
                "results": [],
                "finished": False,
                "scan_date": scan_date,
                "start_date": start_date,
                "end_date": end_date,
                "date_mode": date_mode,
                "strategy_name": strat_info.name,
                "stock_range": req.stock_range,
                # 两阶段：prepare（数据下载）→ scan（本地筛选）
                "phase": "prepare" if (req.prepare_first and not req.prepare_only) else ("scan" if not req.prepare_only else "prepare"),
                "prepare_total": len(symbols) if (req.prepare_first or req.prepare_only) else 0,
                "prepare_done": 0,
                "prepare_fetched": 0,
                "prepare_cached": 0,
                "prepare_failed": 0,
                "prepare_cancelled": False,
            }

        # 5. 在线程池中执行：先批量预热数据，再本地扫描
        #    prepare_only=True 时只预热数据不扫描（用于提前缓存）
        #    prepare_first=False 时跳过预热直接进入扫描（数据已缓存的场景）
        _run_scan_pipeline(
            scan_id=scan_id,
            symbols=symbols,
            strategy_cls=strategy_cls,
            strategy_type=req.strategy_type,
            params=req.strategy_params,
            start_date=start_date,
            end_date=end_date,
            prepare_first=req.prepare_first,
            prepare_only=req.prepare_only,
        )

        return {
            "status": "success",
            "scan_id": scan_id,
            "scan_date": scan_date,
            "start_date": start_date,
            "end_date": end_date,
            "date_mode": date_mode,
            "strategy_name": strat_info.name,
            "total_stocks": len(symbols),
            "progress_url": f"/api/stock-scan/progress?scan_id={scan_id}",
            "result_url": f"/api/stock-scan/result?scan_id={scan_id}",
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"选股扫描异常: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="选股扫描执行失败，请稍后重试")


@router.post("/stock-scan/cancel")
def cancel_scan(scan_id: str = Query(..., description="要取消的 scan_id / prepare_id")):
    """取消正在运行的扫描或数据缓存任务。

    调用后：
    - 数据缓存任务会在当前批次完成后立即中止（已下载的数据仍写入缓存）；
    - 扫描任务会在当前预热阶段完成后跳过后续扫描；
    - 前端 SSE 会收到 finished=true 的最终进度。
    """
    with _CANCEL_EVENTS_LOCK:
        evt = _CANCEL_EVENTS.get(scan_id)
    if evt is None:
        raise HTTPException(status_code=404, detail=f"任务 {scan_id} 不存在或已完成")

    evt.set()
    logger.info(f"[{scan_id}] 收到取消请求，已设置取消信号")
    return {"status": "success", "detail": f"已发送取消信号给任务 {scan_id}"}


@router.post("/stock-scan/prepare")
def prepare_data(req: DataPrepareRequest):
    """独立的数据缓存入口：批量把指定范围内股票的 K 线下载到本地缓存。

    与扫描解耦，用户可提前把全市场/沪深300的数据缓存好，之后所有扫描
    （以及回测）都直接命中本地缓存，零网络、秒级完成，且不再有并发联网
    导致后端崩溃的风险。

    进度通过 scan_id 复用 /stock-scan/progress（SSE）与 /stock-scan/result
    （轮询）两个端点查看；phase 固定为 "prepare"，prepare_only=True。
    """
    import uuid
    from datetime import datetime as dt, timedelta

    try:
        # 1. 确定日期范围
        start_date = req.start_date
        end_date = req.end_date
        if not start_date or not end_date:
            end_date = dt.now().strftime("%Y%m%d")
            start_date = (dt.strptime(end_date, "%Y%m%d") - timedelta(days=400)).strftime("%Y%m%d")

        # 2. 获取股票列表（复用扫描的范围解析）
        symbols = _get_scan_symbols(req.stock_range, req.custom_stocks, req.max_stocks)

        # 3. 初始化进度和取消事件
        prepare_id = uuid.uuid4().hex[:12]
        cancel_evt = threading.Event()
        with _CANCEL_EVENTS_LOCK:
            _CANCEL_EVENTS[prepare_id] = cancel_evt
        with _SCAN_PROGRESS_LOCK:
            _SCAN_PROGRESS[prepare_id] = {
                "total": len(symbols),
                "scanned": 0,
                "matched": 0,
                "results": [],
                "finished": False,
                "scan_date": end_date,
                "start_date": start_date,
                "end_date": end_date,
                "date_mode": "range",
                "strategy_name": "数据缓存",
                "stock_range": req.stock_range,
                "phase": "prepare",
                "prepare_total": len(symbols),
                "prepare_done": 0,
                "prepare_fetched": 0,
                "prepare_cached": 0,
                "prepare_failed": 0,
                "prepare_cancelled": False,
                "_prepare_only": True,
            }

        # 4. 后台线程执行预热
        def _do():
            try:
                def _on_prepare(done, total, sym, ok):
                    with _SCAN_PROGRESS_LOCK:
                        prog = _SCAN_PROGRESS.get(prepare_id)
                        if prog is None:
                            return
                        prog["prepare_done"] = done
                        prog["prepare_total"] = total
                        if ok:
                            prog["prepare_fetched"] = prog.get("prepare_fetched", 0) + 1
                        else:
                            prog["prepare_failed"] = prog.get("prepare_failed", 0) + 1
                    if done % 100 == 0:
                        _persist_scan(prepare_id)
                    if done % 50 == 0 or done == total:
                        logger.info(f"[{prepare_id}] 数据缓存进度: {done}/{total}")

                stats = prefetch_klines(
                    symbols=symbols,
                    start_date=start_date,
                    end_date=end_date,
                    period=req.period or "daily",
                    max_workers=50,
                    on_progress=_on_prepare,
                    cancel_event=cancel_evt,
                )
                with _SCAN_PROGRESS_LOCK:
                    prog = _SCAN_PROGRESS.get(prepare_id)
                    if prog is not None:
                        prog["prepare_fetched"] = stats["fetched"]
                        prog["prepare_cached"] = stats["cached"]
                        prog["prepare_failed"] = stats["failed"]
                        prog["prepare_cancelled"] = stats.get("cancelled", False)
            except Exception as e:
                logger.error(f"[{prepare_id}] 数据缓存异常: {e}", exc_info=True)
            finally:
                with _SCAN_PROGRESS_LOCK:
                    prog = _SCAN_PROGRESS.get(prepare_id)
                    if prog is not None:
                        prog["finished"] = True
                        prog["_finished_at"] = time.time()
                _persist_scan(prepare_id)
                # 清理取消事件
                with _CANCEL_EVENTS_LOCK:
                    _CANCEL_EVENTS.pop(prepare_id, None)
                logger.info(f"[{prepare_id}] 数据缓存{'已取消' if cancel_evt.is_set() else '完成'}")

        threading.Thread(target=_do, daemon=True).start()

        return {
            "status": "success",
            "prepare_id": prepare_id,
            "total": len(symbols),
            "start_date": start_date,
            "end_date": end_date,
            "period": req.period or "daily",
            "progress_url": f"/api/stock-scan/progress?scan_id={prepare_id}",
            "result_url": f"/api/stock-scan/result?scan_id={prepare_id}",
        }
    except Exception as e:
        logger.error(f"数据缓存请求异常: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="数据缓存启动失败，请稍后重试")


def _run_scan_pipeline(
    scan_id: str,
    symbols: list[str],
    strategy_cls,
    strategy_type: str,
    params: dict,
    start_date: str,
    end_date: str,
    prepare_first: bool = True,
    prepare_only: bool = False,
):
    """统一扫描流水线：先批量预热数据到本地缓存，再进入纯本地扫描。

    阶段切换通过 _SCAN_PROGRESS[scan_id]["phase"] 标记：
    - "prepare"：串行限速下载时间范围内全部股票 K 线（零并发网络压力）
    - "scan"：基于本地缓存并发回测筛选（零网络，不会再因联网崩溃）

    预热阶段同样增量持久化，进程被杀后重启可断点续传（已缓存的跳过）。
    """
    def _do():
        # 获取取消事件
        with _CANCEL_EVENTS_LOCK:
            cancel_evt = _CANCEL_EVENTS.get(scan_id)
        
        def _check_cancelled():
            return cancel_evt and cancel_evt.is_set()

        # ---------- 阶段一：数据预热 ----------
        if prepare_first or prepare_only:
            logger.info(f"[{scan_id}] 开始数据预热: {len(symbols)} 只 ({start_date}~{end_date})")
            try:
                def _on_prepare(done, total, sym, ok):
                    with _SCAN_PROGRESS_LOCK:
                        prog = _SCAN_PROGRESS.get(scan_id)
                        if prog is None:
                            return
                        prog["phase"] = "prepare"
                        prog["prepare_done"] = done
                        prog["prepare_total"] = total
                        if not ok:
                            prog["prepare_failed"] = prog.get("prepare_failed", 0) + 1
                    # 每 100 只落盘一次，崩溃可恢复
                    if done % 100 == 0:
                        _persist_scan(scan_id)
                    if done % 50 == 0 or done == total:
                        logger.info(f"[{scan_id}] 数据预热进度: {done}/{total}")

                stats = prefetch_klines(
                    symbols=symbols,
                    start_date=start_date,
                    end_date=end_date,
                    period="daily",
                    max_workers=50,
                    on_progress=_on_prepare,
                    cancel_event=cancel_evt,
                )
                with _SCAN_PROGRESS_LOCK:
                    prog = _SCAN_PROGRESS.get(scan_id)
                    if prog is not None:
                        prog["prepare_fetched"] = stats["fetched"]
                        prog["prepare_cached"] = stats["cached"]
                        prog["prepare_failed"] = stats["failed"]
                        prog["prepare_cancelled"] = stats.get("cancelled", False)
                logger.info(
                    f"[{scan_id}] 数据预热{'已取消' if stats.get('cancelled') else '完成'}: 共 {stats['total']} 只，"
                    f"本次下载 {stats['fetched']}，已缓存 {stats['cached']}，失败 {stats['failed']}"
                )
            except Exception as e:
                logger.error(f"[{scan_id}] 数据预热异常: {e}", exc_info=True)

            _persist_scan(scan_id)

            # 如果被取消，直接结束（不进入扫描阶段）
            if _check_cancelled():
                logger.info(f"[{scan_id}] 预热阶段被取消，跳过后续扫描")
                with _SCAN_PROGRESS_LOCK:
                    prog = _SCAN_PROGRESS.get(scan_id)
                    if prog is not None:
                        prog["finished"] = True
                        prog["_finished_at"] = time.time()
                _persist_scan(scan_id)
                with _CANCEL_EVENTS_LOCK:
                    _CANCEL_EVENTS.pop(scan_id, None)
                return

            # 仅预热模式：到此结束
            if prepare_only:
                with _SCAN_PROGRESS_LOCK:
                    prog = _SCAN_PROGRESS.get(scan_id)
                    if prog is not None:
                        prog["finished"] = True
                        prog["_finished_at"] = time.time()
                        prog["phase"] = "prepare"
                logger.info(f"[{scan_id}] 仅预热数据完成")
                _persist_scan(scan_id)
                with _CANCEL_EVENTS_LOCK:
                    _CANCEL_EVENTS.pop(scan_id, None)
                return

        # ---------- 阶段二：本地扫描 ----------
        with _SCAN_PROGRESS_LOCK:
            prog = _SCAN_PROGRESS.get(scan_id)
            if prog is not None:
                prog["phase"] = "scan"

        if strategy_type == "cci_macd_selection":
            _run_cci_macd_scan(scan_id=scan_id, symbols=symbols, params=params or {})
        else:
            _run_concurrent_scan(
                scan_id=scan_id,
                symbols=symbols,
                strategy_cls=strategy_cls,
                params=params,
                start_date=start_date,
                end_date=end_date,
            )

        # 扫描正常完成后清理取消事件
        with _CANCEL_EVENTS_LOCK:
            _CANCEL_EVENTS.pop(scan_id, None)

    t = threading.Thread(target=_do, daemon=True)
    t.start()


def _run_concurrent_scan(
    scan_id: str,
    symbols: list[str],
    strategy_cls,
    params: dict,
    start_date: str,
    end_date: str,
    max_workers: int = 8,
):
    """在独立线程中并发执行扫描，结果写入 _SCAN_PROGRESS。
    
    注意：max_workers 限制并发数，防止全市场扫描时创建过多线程导致内存飙升。
    扫描过程中会定期把进度增量持久化到磁盘，即使后端进程因故被杀死，
    重启后也能从磁盘恢复已完成的结果（避免前端一直 404）。
    """
    # 硬上限：最大并发数不超过 8，兼顾速度与稳定性
    # （backtrader 并发 run() 在资源紧张时有进程级崩溃风险，且每只股票
    #  还要网络拉取 K 线，过高并发会触发连接重置/内存暴涨）
    effective_workers = min(max_workers, 8)

    def _do():
        results = []
        total = len(symbols)
        try:
            with ThreadPoolExecutor(max_workers=effective_workers) as executor:
                # 提交所有任务
                future_map = {}
                for symbol in symbols:
                    future = executor.submit(
                        _run_single_scan,
                        symbol=symbol,
                        strategy_cls=strategy_cls,
                        params=params,
                        start_date=start_date,
                        end_date=end_date,
                        timeout=15,
                    )
                    future_map[future] = symbol

                # 逐个收集结果，同步更新进度
                scanned = 0
                matched = 0
                for future in as_completed(future_map):
                    symbol = future_map[future]
                    scanned += 1
                    try:
                        result = future.result(timeout=30)  # 含内部超时的总超时
                        if result and result.get("has_signal"):
                            name = get_stock_name(symbol)
                            sector = get_stock_sector(symbol)
                            item = {
                                "symbol": symbol,
                                "name": name,
                                "price": result.get("last_price", 0),
                                "change_pct": result.get("change_pct", 0),
                                "signal_strength": result.get("signal_strength", 0),
                                "signal_detail": result.get("signal_detail", {}),
                                "sector": sector,
                                "market_cap": result.get("market_cap", 0),
                            }
                            results.append(item)
                            matched += 1
                    except Exception:
                        logger.debug(f"扫描 {symbol} 失败或超时")

                    # 更新进度
                    with _SCAN_PROGRESS_LOCK:
                        progress = _SCAN_PROGRESS.get(scan_id)
                        if progress:
                            progress["scanned"] = scanned
                            progress["matched"] = matched
                            progress["results"] = list(results)  # 快照

                    # 增量持久化：每扫 50 只就把当前进度落盘，
                    # 防止进程中途被杀导致已完成结果全部丢失（前端 404）。
                    if scanned % 50 == 0:
                        _persist_scan(scan_id)

                    # 进度日志
                    if scanned % 20 == 0:
                        logger.info(f"[{scan_id}] 扫描进度: {scanned}/{total}，已匹配 {matched} 只")

            # 按信号强度排序
            results.sort(key=lambda x: x.get("signal_strength", 0), reverse=True)
        except Exception as e:
            # 扫描主流程异常也要兜底，避免 daemon 线程未捕获异常影响进程稳定
            logger.error(f"[{scan_id}] 扫描主流程异常: {e}", exc_info=True)

        # 标记完成
        with _SCAN_PROGRESS_LOCK:
            progress = _SCAN_PROGRESS.get(scan_id)
            if progress:
                progress["scanned"] = len(symbols)
                progress["matched"] = len(results)
                progress["results"] = results
                progress["finished"] = True
                progress["_finished_at"] = time.time()

        logger.info(f"[{scan_id}] 扫描完成: {total} 只，匹配 {len(results)} 只")
        _persist_scan(scan_id)

    t = threading.Thread(target=_do, daemon=True)
    t.start()


def _run_cci_macd_scan(scan_id: str, symbols: list[str], params: dict, max_workers: int = 8):
    """CCI+MACD 专用并发扫描：前置过滤 + 直接指标计算。"""
    from core.cci_macd_scanner import check_cci_macd
    from core.filters import get_spot_snapshot, passes_prefilter

    cci_threshold = float(params.get("cci_threshold", 300))
    zero_line_band = float(params.get("zero_line_band", 0.5))
    golden_gap = float(params.get("golden_gap", 0.1))
    period = str(params.get("period", "30"))
    # 前端传的是"亿"，转成元
    min_amount = float(params.get("min_amount", 5.0)) * 1e8

    effective_workers = min(max_workers, 16)

    def _do():
        results = []
        total = len(symbols)
        # 预取一次全市场快照供前置过滤复用
        spot_df = get_spot_snapshot()

        def _scan_one(symbol: str):
            name = get_stock_name(symbol)
            ok, _reason = passes_prefilter(
                symbol, name=name, spot_df=spot_df, min_amount=min_amount,
                exclude_st=True, exclude_suspended=True,
            )
            if not ok:
                return None
            hit = check_cci_macd(symbol, period=period,
                                 cci_threshold=cci_threshold, zero_line_band=zero_line_band,
                                 golden_gap=golden_gap)
            if not hit:
                return None
            return {
                "symbol": symbol,
                "name": name,
                "price": hit["price"],
                "change_pct": 0,
                "signal_strength": min(round((hit["cci"] - cci_threshold) / 200 + 0.5, 2), 1.0),
                "signal_detail": {
                    "cci": hit["cci"],
                    "dif": hit["dif"],
                    "dea": hit["dea"],
                    "macd_cross": hit["macd_cross"],
                    "period": hit["period"],
                    "kline_time": hit["kline_time"],
                },
                "sector": get_stock_sector(symbol),
                "market_cap": 0,
                "cci": hit["cci"],
                "trigger_time": hit["kline_time"],
            }

        with ThreadPoolExecutor(max_workers=effective_workers) as executor:
            future_map = {executor.submit(_scan_one, s): s for s in symbols}
            scanned = 0
            matched = 0
            for future in as_completed(future_map):
                scanned += 1
                try:
                    item = future.result(timeout=30)
                    if item:
                        results.append(item)
                        matched += 1
                except Exception:
                    logger.debug(f"CCI+MACD 扫描 {future_map[future]} 失败")

                with _SCAN_PROGRESS_LOCK:
                    progress = _SCAN_PROGRESS.get(scan_id)
                    if progress:
                        progress["scanned"] = scanned
                        progress["matched"] = matched
                        progress["results"] = list(results)

        results.sort(key=lambda x: x.get("cci", 0), reverse=True)

        with _SCAN_PROGRESS_LOCK:
            progress = _SCAN_PROGRESS.get(scan_id)
            if progress:
                progress["scanned"] = len(symbols)
                progress["matched"] = len(results)
                progress["results"] = results
                progress["finished"] = True
                progress["_finished_at"] = time.time()

        logger.info(f"[{scan_id}] CCI+MACD 扫描完成: {total} 只，匹配 {len(results)} 只")
        _persist_scan(scan_id)

    t = threading.Thread(target=_do, daemon=True)
    t.start()


@router.get("/stock-scan/progress")
async def get_scan_progress(scan_id: str = Query(..., description="扫描任务 ID")):
    """SSE 端点：实时推送扫描进度。

    前端通过 EventSource 连接此端点获取实时进度。
    首次连接立即返回当前进度，之后仅在进度变化时推送。
    扫描完成后自动关闭连接。
    """
    async def event_stream():
        last_scanned = -1
        last_prepare_done = -1
        first_push = True
        while True:
            with _SCAN_PROGRESS_LOCK:
                progress = _SCAN_PROGRESS.get(scan_id)

            if progress is None:
                yield f"data: {json.dumps({'error': 'scan_id 不存在'})}\n\n"
                break

            scanned = progress["scanned"]
            total = progress["total"]
            finished = progress["finished"]
            phase = progress.get("phase", "scan")
            prepare_done = progress.get("prepare_done", 0)

            # 首次连接立即推送当前进度，之后仅在变化时推送。
            # 缓存阶段（phase="prepare"）scanned 始终为 0，需用 prepare_done 判断变化。
            if first_push or scanned != last_scanned or prepare_done != last_prepare_done or finished:
                first_push = False
                last_scanned = scanned
                last_prepare_done = prepare_done
                payload = {
                    "scanned": scanned,
                    "total": total,
                    "matched": progress["matched"],
                    "progress_pct": round(scanned / total * 100, 1) if total > 0 else 0,
                    "finished": finished,
                    "scan_date": progress.get("scan_date", ""),
                    "start_date": progress.get("start_date", ""),
                    "end_date": progress.get("end_date", ""),
                    "date_mode": progress.get("date_mode", "single"),
                    "strategy_name": progress.get("strategy_name", ""),
                    "stock_range": progress.get("stock_range", ""),
                    # 两阶段进度（数据预热 / 本地扫描）
                    "phase": phase,
                    "prepare_total": progress.get("prepare_total", 0),
                    "prepare_done": progress.get("prepare_done", 0),
                    "prepare_fetched": progress.get("prepare_fetched", 0),
                    "prepare_cached": progress.get("prepare_cached", 0),
                    "prepare_failed": progress.get("prepare_failed", 0),
                    "prepare_cancelled": progress.get("prepare_cancelled", False),
                }
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

            if finished:
                # 保持进度数据 TTL 秒后清理
                _cleanup_expired_progress()
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/stock-scan/result")
def get_scan_result(scan_id: str = Query(..., description="扫描任务 ID")):
    """轮询端点：获取已完成扫描的结果。

    后端进程重启后内存数据会丢失，这里先从磁盘恢复已持久化的结果，
    避免前端拿到旧 scan_id 时直接 404。
    """
    with _SCAN_PROGRESS_LOCK:
        progress = _SCAN_PROGRESS.get(scan_id)

    if progress is None:
        # 进程可能重启过：尝试从磁盘恢复
        restored = _load_persisted_scan(scan_id)
        if restored is not None:
            with _SCAN_PROGRESS_LOCK:
                _SCAN_PROGRESS.setdefault(scan_id, restored)
            progress = restored
        else:
            raise HTTPException(status_code=404, detail="scan_id 不存在或已过期")

    if not progress["finished"]:
        return {
            "status": "pending",
            "scanned": progress["scanned"],
            "total": progress["total"],
            "matched": progress["matched"],
            "progress_pct": round(progress["scanned"] / progress["total"] * 100, 1) if progress["total"] > 0 else 0,
            # 两阶段信息（数据预热 / 本地扫描）
            "phase": progress.get("phase", "scan"),
            "prepare_total": progress.get("prepare_total", 0),
            "prepare_done": progress.get("prepare_done", 0),
            "prepare_fetched": progress.get("prepare_fetched", 0),
            "prepare_cached": progress.get("prepare_cached", 0),
            "prepare_failed": progress.get("prepare_failed", 0),
        }

    return {
        "status": "success",
        "scanned": progress["scanned"],
        "total": progress["total"],
        "matched": progress["matched"],
        "results": progress["results"],
    }


def _get_scan_symbols(stock_range: str, custom_stocks: list[str], max_stocks: int) -> list[str]:
    """获取扫描范围的股票列表（优先使用本地缓存，避免网络阻塞）。

    max_stocks <= 0 时表示不限制，扫描范围内全部股票（全市场扫描）。
    """
    # max_stocks<=0 不截断；否则截断到指定数量
    _limit = (lambda s: s) if max_stocks <= 0 else (lambda s: s[:max_stocks])

    if stock_range == "custom" and custom_stocks:
        return _limit(custom_stocks)

    if stock_range == "hs300":
        # 沪深300成分股：优先使用本地缓存筛选，失败再在线获取
        cached = _get_hs300_from_cache()
        if cached:
            return _limit(cached)
        try:
            import akshare as ak
            df = ak.index_stock_cons(symbol="000300")
            codes = [f"sh{row['品种代码']}" if str(row['品种代码']).startswith(('60', '68')) else f"sz{row['品种代码']}"
                     for _, row in df.iterrows()]
            return _limit(codes)
        except Exception:
            logger.warning("获取沪深300成分股失败，降级为全市场扫描")

    if stock_range == "zz500":
        # 中证500成分股：优先使用本地缓存筛选，失败再在线获取
        cached = _get_zz500_from_cache()
        if cached:
            return _limit(cached)
        try:
            import akshare as ak
            df = ak.index_stock_cons(symbol="000905")
            codes = [f"sh{row['品种代码']}" if str(row['品种代码']).startswith(('60', '68')) else f"sz{row['品种代码']}"
                     for _, row in df.iterrows()]
            return _limit(codes)
        except Exception:
            logger.warning("获取中证500成分股失败，降级为全市场扫描")

    # 默认：全市场
    # 若本地缓存明显少于全市场（全 A 股应有 5000+ 只），同步强制刷新一次，
    # 避免扫描只覆盖缓存里的部分股票（如 696 只）。
    all_symbols = get_all_stock_symbols()
    if len(all_symbols) < 4000:
        logger.warning(f"股票名称缓存仅 {len(all_symbols)} 只（全市场应 5000+），全市场扫描前先刷新缓存")
        try:
            from data.stock_names import refresh_stock_names
            if refresh_stock_names():
                all_symbols = get_all_stock_symbols()
                logger.info(f"刷新后股票名称缓存: {len(all_symbols)} 只")
        except Exception as e:
            logger.warning(f"刷新股票名称缓存失败，使用现有 {len(all_symbols)} 只: {e}")

    # 缓存为空时使用硬编码兜底列表，不阻塞等待网络请求
    if not all_symbols:
        logger.warning("股票名称缓存为空，使用兜底列表")
        # 从 StockNameCache 的硬编码映射生成列表
        from data.stock_names import _stock_name_cache
        all_symbols = _stock_name_cache.get_all_symbols()

    # 最终兜底：更全面的 A 股列表（覆盖主要板块）
    if not all_symbols:
        all_symbols = [
            # 上证主板
            "sh600000", "sh600016", "sh600028", "sh600030", "sh600036", "sh600048",
            "sh600050", "sh600085", "sh600104", "sh600111", "sh600196", "sh600276",
            "sh600309", "sh600346", "sh600406", "sh600436", "sh600519", "sh600585",
            "sh600588", "sh600690", "sh600703", "sh600745", "sh600809", "sh600837",
            "sh600887", "sh600900", "sh601006", "sh601012", "sh601088", "sh601111",
            "sh601166", "sh601211", "sh601225", "sh601238", "sh601288", "sh601318",
            "sh601328", "sh601398", "sh601601", "sh601628", "sh601668", "sh601688",
            "sh601728", "sh601766", "sh601818", "sh601857", "sh601888", "sh601899",
            "sh601919", "sh601939", "sh601985", "sh601988", "sh601998", "sh603259",
            "sh603288", "sh603501", "sh603986",
            # 深证主板
            "sz000001", "sz000002", "sz000063", "sz000069", "sz000100", "sz000157",
            "sz000333", "sz000338", "sz000425", "sz000538", "sz000568", "sz000596",
            "sz000625", "sz000651", "sz000661", "sz000725", "sz000776", "sz000792",
            "sz000858", "sz000876", "sz000895", "sz000977", "sz001979",
            # 中小板/创业板/科创板
            "sz002001", "sz002007", "sz002024", "sz002027", "sz002049", "sz002142",
            "sz002230", "sz002236", "sz002241", "sz002271", "sz002304", "sz002311",
            "sz002352", "sz002410", "sz002415", "sz002456", "sz002459", "sz002460",
            "sz002466", "sz002475", "sz002493", "sz002555", "sz002594", "sz002601",
            "sz002714", "sz300015", "sz300059", "sz300124", "sz300274", "sz300413",
            "sz300433", "sz300450", "sz300454", "sz300496", "sz300498", "sz300502",
            "sz300529", "sz300750", "sz300760", "sz300782", "sz300896", "sh688036",
            "sh688111", "sh688169", "sh688187", "sh688223", "sh688256", "sh688561",
            "sh688981",
        ]

    return _limit(all_symbols)


# 沪深300 / 中证500 成分股缓存（避免每次扫描都联网）
_HS300_CACHE: Optional[list[str]] = None
_ZZ500_CACHE: Optional[list[str]] = None


def _get_hs300_from_cache() -> Optional[list[str]]:
    """从本地文件缓存获取沪深300成分股。"""
    global _HS300_CACHE
    if _HS300_CACHE is not None:
        return _HS300_CACHE
    try:
        f = Path(__file__).resolve().parent.parent / 'data' / 'hs300_cache.json'
        if f.exists():
            with open(f, 'r', encoding='utf-8') as fp:
                _HS300_CACHE = json.load(fp)
            return _HS300_CACHE
    except Exception:
        pass
    return None


def _get_zz500_from_cache() -> Optional[list[str]]:
    """从本地文件缓存获取中证500成分股。"""
    global _ZZ500_CACHE
    if _ZZ500_CACHE is not None:
        return _ZZ500_CACHE
    try:
        f = Path(__file__).resolve().parent.parent / 'data' / 'zz500_cache.json'
        if f.exists():
            with open(f, 'r', encoding='utf-8') as fp:
                _ZZ500_CACHE = json.load(fp)
            return _ZZ500_CACHE
    except Exception:
        pass
    return None


def _run_single_scan(
    symbol: str,
    strategy_cls,
    params: dict,
    start_date: str,
    end_date: str,
    timeout: int = 10,
) -> Optional[dict]:
    """对单只股票执行选股策略扫描。

    直接运行 Backtrader 回测引擎判断是否有买入信号。
    使用 threading.Timer 实现超时控制（兼容 Windows）。

    Returns:
        dict 或 None（无信号/错误）
    """
    result_container: list = []

    def _do_scan():
        try:
            result_container.append(_scan_inner(symbol, strategy_cls, params, start_date, end_date))
        except Exception as e:
            logger.debug(f"单只股票扫描异常 {symbol}: {e}")

    thread = threading.Thread(target=_do_scan, daemon=True)
    thread.start()
    thread.join(timeout=timeout)

    if thread.is_alive():
        logger.debug(f"扫描 {symbol} 超时 ({timeout}s)")
        return None

    return result_container[0] if result_container else None


def _scan_inner(
    symbol: str,
    strategy_cls,
    params: dict,
    start_date: str,
    end_date: str,
) -> Optional[dict]:
    """_run_single_scan 的实际扫描逻辑（运行在子线程中）。"""
    # 去掉市场前缀获取纯代码
    code = symbol.replace('sh', '').replace('sz', '').replace('SH', '').replace('SZ', '')

    # 运行回测（加全局锁串行化 backtrader，防止并发 run() 触发进程级崩溃；
    # 同时 try 兜底，任何单只股票异常都不应冒泡杀掉扫描线程/进程）
    #
    # 关键：锁必须带超时。Python 无法从外部终止线程，超时后的僵尸线程会
    # 一直持有 _BT_RUN_LOCK；若此处无限等待，后续所有扫描都会排队在僵尸
    # 线程之后，界面表现为「扫描中…」永久假死。带超时后改为快速跳过。
    acquired = _BT_RUN_LOCK.acquire(timeout=_BT_LOCK_TIMEOUT)
    if not acquired:
        logger.warning(
            f"等待回测锁超时({_BT_LOCK_TIMEOUT}s)，跳过 {symbol} "
            f"（可能有前一次超时的回测线程仍在执行）"
        )
        return None

    try:
        bt_result = run_backtest(
            strategy_cls=strategy_cls,
            symbol=code,
            start_date=start_date,
            end_date=end_date,
            params=params,
            cash=1000000,
            commission=0.0003,
            period="daily",
        )
    except Exception as e:
        logger.debug(f"回测 {symbol} 异常: {e}")
        return None
    finally:
        _BT_RUN_LOCK.release()

    # 关键防护：模拟数据（网络失败时的随机兜底数据）绝不能产生选股信号。
    # 否则弱网/离线时，随机游走生成的假K线会被策略判定为「有买入信号」，
    # 导致扫描结果全是噪声，而用户无从分辨。
    if bt_result.get("data_source") == "mock":
        logger.debug(f"跳过 {symbol}：该股行情为模拟数据（真实数据获取失败）")
        return None

    # 判断是否有买入信号（交易记录中有买入操作）
    trades = bt_result.get("trades", [])
    buy_signals = [t for t in trades if t.get("action") in ("买入",)]
    has_signal = len(buy_signals) > 0

    if not has_signal:
        return None

    # 获取最后价格
    kline = bt_result.get("kline", [])
    last_price = kline[-1]["close"] if kline else 0

    # 计算涨跌幅
    if len(kline) >= 2:
        change_pct = round((kline[-1]["close"] - kline[-2]["close"]) / kline[-2]["close"] * 100, 2)
    else:
        change_pct = 0

    # 信号强度：基于买入信号数量
    signal_strength = min(round(len(buy_signals) / 5, 2), 1.0)

    # 信号详情
    signal_detail = {
        "total_trades": len(trades),
        "buy_count": len(buy_signals),
        "sell_count": len(trades) - len(buy_signals),
    }

    # 添加回测指标
    metrics = bt_result.get("metrics", {})
    if metrics:
        signal_detail["total_return"] = metrics.get("total_return", 0)
        signal_detail["win_rate"] = metrics.get("win_rate", 0)

    return {
        "has_signal": True,
        "last_price": last_price,
        "change_pct": change_pct,
        "signal_strength": signal_strength,
        "signal_detail": signal_detail,
        "market_cap": 0,
    }


# ==================== 自选池 API ====================

@router.get("/watchlist")
def get_watchlist():
    """获取自选池列表。"""
    try:
        data = _load_watchlist()
        return {"status": "ok", "data": data}
    except Exception as e:
        logger.error(f"获取自选池异常: {e}")
        raise HTTPException(status_code=500, detail="自选池获取失败，请稍后重试")


@router.post("/watchlist")
def add_to_watchlist(item: WatchlistItem):
    """添加股票到自选池。"""
    try:
        data = _load_watchlist()
        # 检查是否已存在
        existing = [s for s in data if s["symbol"] == item.symbol]
        if existing:
            # 更新已有项
            for s in data:
                if s["symbol"] == item.symbol:
                    s.update(item.model_dump(exclude_unset=True))
                    break
        else:
            from datetime import datetime
            item_dict = item.model_dump()
            if not item_dict.get("added_at"):
                item_dict["added_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if not item_dict.get("name"):
                item_dict["name"] = get_stock_name(item.symbol)
            data.append(item_dict)

        _save_watchlist(data)
        return {"status": "ok", "message": f"已添加 {item.symbol} 到自选池"}
    except Exception as e:
        logger.error(f"添加自选池异常: {e}")
        raise HTTPException(status_code=500, detail="自选池添加失败，请稍后重试")


@router.delete("/watchlist/{symbol}")
def remove_from_watchlist(symbol: str):
    """从自选池删除股票。"""
    try:
        data = _load_watchlist()
        data = [s for s in data if s["symbol"] != symbol]
        _save_watchlist(data)
        return {"status": "ok", "message": f"已从自选池删除 {symbol}"}
    except Exception as e:
        logger.error(f"删除自选池异常: {e}")
        raise HTTPException(status_code=500, detail="自选池删除失败，请稍后重试")
