"""盘中实时监控引擎（CCI+MACD 选股需求新增）。

定时线程：交易时段每隔 interval 秒扫描全市场，把符合 CCI+MACD 条件的
股票写入动态池。无弹窗，前端轮询获取。
"""
from __future__ import annotations

import logging
import threading
import time as _time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, time as dtime
from typing import Optional

import numpy as np

logger = logging.getLogger("realtime_monitor")


class RealtimeMonitor:
    """盘中实时监控引擎（单例）。"""

    def __init__(self):
        self.interval = 60          # 扫描间隔（秒）
        self.running = False
        self.pool: list[dict] = []  # 当前动态股票池
        self.last_scan: Optional[str] = None
        self.scan_count = 0
        self.error: Optional[str] = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._candidates_: int = 0   # 最近一次扫描候选数
        self._logs: list[str] = []   # 最近扫描日志（最多 20 条）

        # 选股参数（可通过 start 覆盖）
        self.period = "30"
        self.min_amount = 5e8
        self.max_stocks = 200  # 单次扫描最多候选数，控制耗时
        # 因子配置：{ key: {"enabled": bool, "params": {...}} }
        self.factor_cfg = None
        self.combine = "AND"  # AND 全部满足 / OR 任一满足

    # ---------- 生命周期 ----------
    def start(self, interval: int = 60, params: Optional[dict] = None):
        """启动监控。若已运行则仅更新参数。

        params 兼容两种调用：
            - 旧版：cci_threshold / zero_line_band / period / min_amount
            - 新版：factors(因子配置) / combine / period / min_amount
        """
        params = params or {}
        self.interval = max(int(interval or 60), 10)
        self.period = str(params.get("period", "30"))
        self.min_amount = float(params.get("min_amount", 5.0)) * 1e8
        self.max_stocks = int(params.get("max_stocks", 200))

        # 因子配置：优先用新版 factors，否则由旧参数推导为 cci+macd
        factors = params.get("factors")
        if factors:
            self.factor_cfg = factors
            self.combine = params.get("combine", "AND")
        else:
            # 兼容旧调用：构造 cci + macd(金叉,零线附近) 组合
            self.factor_cfg = {
                "cci": {
                    "enabled": True,
                    "params": {
                        "period": 14, "direction": "above",
                        "threshold": float(params.get("cci_threshold", 300)),
                    },
                },
                "macd": {
                    "enabled": True,
                    "params": {
                        "signal": "golden",
                        "zero_band": float(params.get("zero_line_band", 0.5)),
                        "fast": 12, "slow": 26, "signal_p": 9,
                    },
                },
            }
            self.combine = "AND"

        if self.running:
            logger.info("监控已在运行，更新参数")
            return

        self.running = True
        self.error = None
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info(f"实时监控已启动 interval={self.interval}s period={self.period}min")

    def stop(self):
        self.running = False
        logger.info("实时监控已停止")

    def status(self) -> dict:
        with self._lock:
            return {
                "running": self.running,
                "interval": self.interval,
                "last_scan": self.last_scan,
                "scan_count": self.scan_count,
                "pool_size": len(self.pool),
                "error": self.error,
                "params": {
                    "period": self.period,
                    "min_amount_yi": round(self.min_amount / 1e8, 1),
                    "combine": self.combine,
                    "factors": self.factor_cfg,
                },
            }

    def get_pool(self) -> dict:
        with self._lock:
            return {
                "pool": list(self.pool),
                "last_scan": self.last_scan,
                "running": self.running,
                "scan_count": self.scan_count,
                "candidates": self._candidates_,
                "logs": list(self._logs),
                "error": self.error,
            }

    # ---------- 内部 ----------
    def _loop(self):
        # 启动后立即扫一次（不管是否交易时段，便于用户即时看到效果）
        try:
            self._scan_once(force=True)
        except Exception as e:
            logger.error(f"首次扫描失败: {e}")
            self.error = str(e)

        while self.running:
            _time.sleep(self.interval)
            if not self.running:
                break
            if self._is_trading_time():
                try:
                    self._scan_once()
                except Exception as e:
                    logger.error(f"扫描异常: {e}")
                    self.error = str(e)

    @staticmethod
    def _is_trading_time() -> bool:
        """判断当前是否为 A 股交易时段（9:30-11:30, 13:00-15:00，工作日）。"""
        now = datetime.now()
        if now.weekday() >= 5:  # 周六日
            return False
        t = now.time()
        return (
            (dtime(9, 30) <= t <= dtime(11, 30))
            or (dtime(13, 0) <= t <= dtime(15, 0))
        )

    def _scan_once(self, force: bool = False):
        """单次全市场扫描。"""
        from core.filters import get_spot_snapshot, passes_prefilter
        from core.data_loader import fetch_minute_kline
        from core.screen_factors import eval_factors
        from data.stock_names import get_stock_name, get_stock_sector, get_all_stock_symbols

        spot_df = get_spot_snapshot(force_refresh=True)

        # 候选股票：优先用全市场列表，控制数量
        symbols = get_all_stock_symbols() or []
        symbols = symbols[: self.max_stocks]

        factor_cfg = self.factor_cfg or {}
        combine = self.combine

        results = []

        def _scan_one(symbol: str):
            name = get_stock_name(symbol)
            ok, _reason = passes_prefilter(
                symbol, name=name, spot_df=spot_df, min_amount=self.min_amount,
                exclude_st=True, exclude_suspended=True,
            )
            if not ok:
                return None
            # 取分钟K线，按因子配置判定
            try:
                df = fetch_minute_kline(symbol, period=self.period, limit=200)
            except Exception:
                return None
            if df is None or df.empty or len(df) < 35:
                return None
            if not eval_factors(df, factor_cfg, combine):
                return None

            close = df["close"]
            price = float(close.iloc[-1])
            # 收集命中因子的关键指标用于展示
            extra = {}
            try:
                from core.indicators import calc_cci, calc_macd
                cci = calc_cci(df["high"], df["low"], df["close"], 14)
                if len(cci) and not np.isnan(float(cci.iloc[-1])):
                    extra["cci"] = round(float(cci.iloc[-1]), 2)
                macd = calc_macd(df["close"])
                extra["dif"] = round(float(np.array(macd["dif"])[-1]), 4)
                extra["dea"] = round(float(np.array(macd["dea"])[-1]), 4)
            except Exception:
                pass

            # 涨跌幅：优先实时快照，否则用分钟K线倒数第二根估算（离线也有值）
            change_pct = 0.0
            try:
                if spot_df is not None and not spot_df.empty and "涨跌幅" in spot_df.columns:
                    sym_col = "代码" if "代码" in spot_df.columns else spot_df.columns[0]
                    row = spot_df[spot_df[sym_col].astype(str).str.replace("sh", "", case=False).str.replace("sz", "", case=False) == symbol]
                    if not row.empty:
                        v = row["涨跌幅"].iloc[0]
                        if v is not None and not (isinstance(v, float) and np.isnan(v)):
                            change_pct = float(v)
                if change_pct == 0.0 and len(close) >= 2:
                    prev = float(close.iloc[-2])
                    if prev:
                        change_pct = round((price - prev) / prev * 100, 2)
            except Exception:
                pass

            return {
                "symbol": symbol,
                "name": name,
                "price": round(price, 2),
                "change_pct": round(change_pct, 2),
                "cci": extra.get("cci", 0),
                "dif": extra.get("dif", 0),
                "dea": extra.get("dea", 0),
                "sector": get_stock_sector(symbol),
                "trigger_time": datetime.now().strftime("%H:%M:%S"),
                "kline_time": str(df["date"].iloc[-1]),
            }

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {executor.submit(_scan_one, s): s for s in symbols}
            for fut in as_completed(futures):
                try:
                    item = fut.result(timeout=30)
                    if item:
                        results.append(item)
                except Exception:
                    pass

        results.sort(key=lambda x: x.get("cci", 0), reverse=True)

        # 诊断日志
        diag = [
            f"扫描完成（#{self.scan_count + 1}）",
            f"候选股票: {len(symbols)} 只",
            f"因子配置: {list(factor_cfg.keys())}  combine={combine}",
            f"命中结果: {len(results)} 只",
        ]
        if not results and len(symbols) > 0:
            diag.append("⚠ 无股票满足当前因子条件，建议放宽 CCI 阈值或改用 OR 模式")
        self._logs = diag

        with self._lock:
            self.pool = results
            self._candidates_ = len(symbols)
            self.last_scan = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.scan_count += 1
            self.error = None

        logger.info(f"监控扫描完成，命中 {len(results)} 只（候选 {len(symbols)}）")


# 全局单例
_monitor: Optional[RealtimeMonitor] = None
_monitor_lock = threading.Lock()


def get_monitor() -> RealtimeMonitor:
    global _monitor
    if _monitor is None:
        with _monitor_lock:
            if _monitor is None:
                _monitor = RealtimeMonitor()
    return _monitor
