"""
数据源抽象层：支持 东方财富(akshare) / 通达信(pytdx) / 雪球(HTTP) 三种实时数据源。

设计要点：
- 所有数据源统一输出「东方财富风格」的字段格式，前端无需改动。
- 通过环境变量 QUANT_DATASOURCE（eastmoney|tongdaxin|xueqiu）或 set_active_source() 切换。
- 活跃源获取失败（异常或返回空）时自动降级到 东方财富，保证可用性。
- 雪球不支持全市场快照与分钟K线，这两类请求会自动回退到东财。
"""
from __future__ import annotations

import os
import time
import logging
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

logger = logging.getLogger("datasource")


# ---------------------------------------------------------------------------
# 公共：历史K线缓存（用于涨跌统计字段，与 data_loader 共用同一 parquet）
# ---------------------------------------------------------------------------
def _load_hist(symbol: str) -> Optional[pd.DataFrame]:
    """从 data_loader 的日线缓存读取历史K线（用于计算涨跌统计字段）。

    缓存文件名带复权标签，且存在无标签的旧版文件，统一走
    _resolve_cache_file 解析（该函数负责新旧路径兼容）。
    """
    try:
        from core.data_loader import _resolve_cache_file
        cache_file = _resolve_cache_file(symbol, "daily", "qfq")
        if cache_file.exists():
            df = pd.read_parquet(cache_file)
            df["date"] = pd.to_datetime(df["date"])
            return df
    except Exception:
        pass
    return None


def _enrich_realtime(core: dict, symbol: str, now: datetime) -> dict:
    """把各数据源返回的核心字段补齐为统一的 50+ 字段格式（与东财一致）。

    core 至少应提供：symbol 可选, name, price, open, high, low, pre_close,
    change_amount, change_pct, volume, amount, turnover_rate, volume_ratio。
    其余可选字段（盘口、市值、估值等）缺失时填 0。
    """
    from data.stock_names import get_stock_name, get_stock_sector
    from core.data_loader import _calc_change_stats, _empty_change_stats

    price = float(core.get("price") or 0)
    pre_close = float(core.get("pre_close") or 0)
    open_ = float(core.get("open") or 0)
    high = float(core.get("high") or 0)
    low = float(core.get("low") or 0)

    if pre_close > 0:
        change_amount = round(price - pre_close, 2)
        change_pct = round((price / pre_close - 1) * 100, 2)
    else:
        change_amount = float(core.get("change_amount") or 0)
        change_pct = float(core.get("change_pct") or 0)

    volume = int(core.get("volume") or 0)
    amount = float(core.get("amount") or 0)
    turnover_rate = float(core.get("turnover_rate") or 0)
    volume_ratio = float(core.get("volume_ratio") or 0)

    name = core.get("name") or get_stock_name(symbol)
    amplitude = round((high - low) / pre_close * 100, 2) if pre_close > 0 else 0
    avg_price = round(amount / (volume * 100), 2) if volume > 0 and amount > 0 else price
    limit_up = round(pre_close * 1.1, 2)
    limit_down = round(pre_close * 0.9, 2)
    if "ST" in str(name):
        limit_up = round(pre_close * 1.05, 2)
        limit_down = round(pre_close * 0.95, 2)
    sector = core.get("sector") or get_stock_sector(symbol)

    # 涨跌统计（基于历史日线，数据源无关）
    hist = _load_hist(symbol)
    change_stats = _calc_change_stats(hist, price, pre_close) if hist is not None else _empty_change_stats()

    item = {
        "symbol": symbol,
        "name": name,
        "sector": sector,
        "price": round(price, 2),
        "open": round(open_, 2),
        "high": round(high, 2),
        "low": round(low, 2),
        "pre_close": round(pre_close, 2),
        "change_amount": change_amount,
        "change_pct": change_pct,
        "amplitude": amplitude,
        "avg_price": avg_price,
        "volume": volume,
        "amount": round(amount, 2),
        "turnover_rate": round(turnover_rate, 2),
        "change_speed": round(float(core.get("change_speed") or 0), 2),
        "volume_ratio": round(volume_ratio, 2),
        "total_share": float(core.get("total_share") or 0),
        "float_share": float(core.get("float_share") or 0),
        "total_market_cap": float(core.get("total_market_cap") or 0),
        "float_market_cap": float(core.get("float_market_cap") or 0),
        "pe_ratio": round(float(core.get("pe_ratio") or 0), 2),
        "pb_ratio": round(float(core.get("pb_ratio") or 0), 2),
        "bid_price": round(float(core.get("bid_price") or 0), 2),
        "ask_price": round(float(core.get("ask_price") or 0), 2),
        "limit_up": limit_up,
        "limit_down": limit_down,
        **change_stats,
        "commission_ratio": round(float(core.get("commission_ratio") or 0), 2),
        "commission_diff": int(core.get("commission_diff") or 0),
        "inner_volume": int(core.get("inner_volume") or 0),
        "outer_volume": int(core.get("outer_volume") or 0),
        "bid1_volume": int(core.get("bid1_volume") or 0),
        "ask1_volume": int(core.get("ask1_volume") or 0),
        "update_time": now.strftime("%Y-%m-%d %H:%M:%S"),
    }
    item["io_ratio"] = round(item["inner_volume"] / item["outer_volume"], 2) if item.get("outer_volume", 0) > 0 else 0
    return item


# ---------------------------------------------------------------------------
# 数据源基类
# ---------------------------------------------------------------------------
class DataSource:
    name = "base"

    def fetch_realtime_quotes(self, symbols: list[str]) -> list[dict]:
        raise NotImplementedError

    def fetch_spot_snapshot(self) -> pd.DataFrame:
        """返回全市场快照（东方财富列名：代码/名称/...）。不支持则抛 NotImplementedError。"""
        raise NotImplementedError

    def fetch_minute_kline(self, symbol: str, period: int, limit: int) -> pd.DataFrame:
        """返回指定周期分钟K线（标准列：date/open/high/low/close/volume/amount）。"""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# 东方财富（默认，复用现有 akshare 逻辑）
# ---------------------------------------------------------------------------
class EastMoneySource(DataSource):
    name = "eastmoney"

    def fetch_realtime_quotes(self, symbols: list[str]) -> list[dict]:
        from core.data_loader import _fetch_realtime_from_akshare, _generate_mock_realtime
        now = datetime.now(timezone.utc)
        result = _fetch_realtime_from_akshare(symbols, now)
        if not result:
            logger.warning("东方财富实时行情获取失败，使用模拟数据")
            result = _generate_mock_realtime(symbols, datetime.now())
        return result

    def fetch_spot_snapshot(self) -> pd.DataFrame:
        import akshare as ak
        return ak.stock_zh_a_spot_em()

    def fetch_minute_kline(self, symbol: str, period: int, limit: int) -> pd.DataFrame:
        from core.data_loader import _fetch_minute_from_akshare
        return _fetch_minute_from_akshare(symbol, period, limit)


# ---------------------------------------------------------------------------
# 通达信（pytdx，直连行情服务器，真正的推模式低延迟源）
# ---------------------------------------------------------------------------
_TDX_HOSTS = [
    ("119.147.212.81", 7709),
    ("119.147.212.83", 7709),
    ("124.74.242.206", 7709),
    ("218.108.98.244", 7709),
    ("114.80.63.12", 7709),
]


def _connect_tdx(timeout_per_host: float = 2.0, max_total: float = 6.0):
    """连接通达信行情服务器，返回已连接的 api 或 None。

    策略：
    1. 优先使用固定 IP 列表，每个连接限时 2 秒；
    2. pytdx 底层 connect 在网络差时可能忽略 timeout 参数，
       因此把整个连接过程放到线程中，强制 max_total 秒内必须返回，否则放弃；
    3. 超时直接返回 None，让上层快速降级到东方财富。
    """
    import time as _time
    from concurrent.futures import ThreadPoolExecutor, TimeoutError
    from pytdx.hq import TdxHq_API

    start = _time.time()

    def _try_one(host: str, port: int):
        try:
            api = TdxHq_API(raise_exception=False, auto_retry=False)
            if api.connect(host, port, timeout=timeout_per_host):
                return api
            try:
                api.disconnect()
            except Exception:
                pass
        except Exception:
            pass
        return None

    # 固定 IP 列表快速轮询
    for host, port in _TDX_HOSTS:
        if _time.time() - start >= max_total:
            break
        remain = max(0.5, max_total - (_time.time() - start))
        with ThreadPoolExecutor(max_workers=1) as pool:
            try:
                api = pool.submit(_try_one, host, port).result(timeout=min(timeout_per_host, remain))
                if api is not None:
                    return api
            except TimeoutError:
                pass

    return None


def _tdx_market(symbol: str) -> int:
    """0=深圳, 1=上海。"""
    return 1 if symbol.startswith(("6", "9", "5", "1", "0")) and symbol[0] in ("6", "9", "5", "1") else 0


class TongdaxinSource(DataSource):
    name = "tongdaxin"

    def fetch_realtime_quotes(self, symbols: list[str]) -> list[dict]:
        from pytdx.hq import TdxHq_API
        now = datetime.now(timezone.utc)
        api = _connect_tdx()
        if api is None:
            raise RuntimeError("无法连接通达信行情服务器")
        try:
            batch = [(_tdx_market(s), s) for s in symbols]
            raw = api.get_security_quotes(batch)
            result = []
            for r in raw:
                code = str(r.get("code", ""))
                if not code:
                    continue
                price = float(r.get("price") or 0)
                pre_close = float(r.get("last_close") or 0)
                core = {
                    "symbol": code,
                    "name": r.get("name", ""),
                    "price": price,
                    "open": float(r.get("open") or 0),
                    "high": float(r.get("high") or 0),
                    "low": float(r.get("low") or 0),
                    "pre_close": pre_close,
                    "change_amount": price - pre_close,
                    "change_pct": (price / pre_close - 1) * 100 if pre_close else 0,
                    "volume": int(r.get("volume") or 0) * 100,  # 手 -> 股
                    "amount": float(r.get("amount") or 0),
                    "bid_price": float(r.get("bid_price1") or 0),
                    "ask_price": float(r.get("ask_price1") or 0),
                    "bid1_volume": int(r.get("bid_vol1") or 0),
                    "ask1_volume": int(r.get("ask_vol1") or 0),
                    "inner_volume": int(r.get("volume", 0)) * 100 // 2,
                    "outer_volume": int(r.get("volume", 0)) * 100 // 2,
                }
                result.append(_enrich_realtime(core, code, now))
            return result
        finally:
            try:
                api.disconnect()
            except Exception:
                pass

    def fetch_spot_snapshot(self) -> pd.DataFrame:
        # 通达信没有干净的全市场快照接口，交给上层回退到东财
        raise NotImplementedError("通达信不支持全市场快照，请使用东方财富源")

    def fetch_minute_kline(self, symbol: str, period: int, limit: int) -> pd.DataFrame:
        from pytdx.hq import TdxHq_API
        # pytdx 周期映射：0=5分钟,1=15分钟,2=30分钟,3=1分钟
        cat_map = {1: 3, 3: 3, 5: 0, 15: 1, 30: 2, 60: 2}
        cat = cat_map.get(period, 3)
        api = _connect_tdx()
        if api is None:
            raise RuntimeError("无法连接通达信行情服务器")
        try:
            market = _tdx_market(symbol)
            count = max(limit, 240)
            bars = api.get_security_bars(cat, market, symbol, 0, count)
            if not bars:
                raise RuntimeError("通达信返回空K线")
            df = pd.DataFrame(bars)
            df = df.rename(columns={
                "datetime": "date", "open": "open", "high": "high",
                "low": "low", "close": "close", "volume": "volume", "amount": "amount",
            })
            keep = ["date", "open", "high", "low", "close", "volume", "amount"]
            df = df[[c for c in keep if c in df.columns]].copy()
            df["date"] = df["date"].astype(str).str.slice(0, 19)
            df["volume"] = (df["volume"] * 100).astype("int64")  # 手 -> 股
            # 若目标周期比实际拉取的更粗，做一次聚合
            if period != (1 if cat == 3 else {0: 5, 1: 15, 2: 30}[cat]):
                from core.data_loader import _resample_minute
                df = _resample_minute(df, period)
            return df.tail(limit).reset_index(drop=True)
        finally:
            try:
                api.disconnect()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# 雪球（HTTP，按代码获取实时报价，不支持快照/分钟K线）
# ---------------------------------------------------------------------------
_xueqiu_cookie: Optional[str] = None


def _xueqiu_symbol(symbol: str) -> str:
    return ("SH" + symbol) if symbol.startswith(("6", "9")) else ("SZ" + symbol)


def _xueqiu_session() -> str:
    global _xueqiu_cookie
    if _xueqiu_cookie:
        return _xueqiu_cookie
    import requests
    try:
        r = requests.get("https://xueqiu.com/", headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }, timeout=10)
        _xueqiu_cookie = "; ".join(f"{k}={v}" for k, v in r.cookies.items())
    except Exception as e:
        logger.warning(f"雪球 Cookie 获取失败: {e}")
    return _xueqiu_cookie or ""


def _xueqiu_get(url: str) -> dict:
    import requests
    cookie = _xueqiu_session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://xueqiu.com/",
    }
    if cookie:
        headers["Cookie"] = cookie
    r = requests.get(url, headers=headers, timeout=10)
    return r.json()


class XueqiuSource(DataSource):
    name = "xueqiu"

    def fetch_realtime_quotes(self, symbols: list[str]) -> list[dict]:
        now = datetime.now(timezone.utc)
        result = []
        for s in symbols:
            xq = _xueqiu_symbol(s)
            try:
                data = _xueqiu_get(
                    f"https://stock.xueqiu.com/v5/stock/quote.json?symbol={xq}&_={int(time.time() * 1000)}"
                )
                d = data.get("data") or {}
                price = float(d.get("current") or 0)
                pre = float(d.get("last_close") or 0)
                core = {
                    "symbol": s,
                    "name": d.get("name", ""),
                    "price": price,
                    "open": float(d.get("open") or 0),
                    "high": float(d.get("high") or 0),
                    "low": float(d.get("low") or 0),
                    "pre_close": pre,
                    "change_amount": price - pre,
                    "change_pct": float(d.get("percent") or 0),
                    "volume": int(d.get("volume") or 0),
                    "amount": float(d.get("amount") or 0),
                    "turnover_rate": float(d.get("turnover_rate") or 0),
                    "volume_ratio": float(d.get("volume_ratio") or 0),
                    "pe_ratio": float(d.get("pe_ttm") or 0),
                    "pb_ratio": float(d.get("pb") or 0),
                    "total_market_cap": float(d.get("market_capital") or 0) / 1e8,
                    "float_market_cap": float(d.get("float_market_capital") or 0) / 1e8,
                    "limit_up": float(d.get("limit_up") or 0),
                    "limit_down": float(d.get("limit_down") or 0),
                }
                result.append(_enrich_realtime(core, s, now))
            except Exception as e:
                logger.warning(f"雪球行情获取失败 {s}: {e}")
        return result

    def fetch_spot_snapshot(self) -> pd.DataFrame:
        raise NotImplementedError("雪球不支持全市场快照，请使用东方财富源")

    def fetch_minute_kline(self, symbol: str, period: int, limit: int) -> pd.DataFrame:
        raise NotImplementedError("雪球不支持分钟K线，请使用东方财富/通达信源")


# ---------------------------------------------------------------------------
# 管理器：选择 / 降级 / 状态
# ---------------------------------------------------------------------------
class DataSourceManager:
    def __init__(self):
        self._active: Optional[DataSource] = None
        self._active_name: str = os.environ.get("QUANT_DATASOURCE", "eastmoney").lower()
        self._eastmoney = EastMoneySource()
        self._last_error: Optional[str] = None
        self._build_active()

    def _build_active(self) -> None:
        name = self._active_name
        if name == "tongdaxin":
            try:
                import pytdx  # noqa: F401
                self._active = TongdaxinSource()
            except ImportError:
                self._last_error = "未安装 pytdx，已回退到东方财富"
                self._active = self._eastmoney
        elif name == "xueqiu":
            self._active = XueqiuSource()
        else:
            self._active = self._eastmoney

    def set_active(self, name: str) -> bool:
        name = (name or "eastmoney").lower()
        if name not in ("eastmoney", "tongdaxin", "xueqiu"):
            return False
        self._active_name = name
        self._last_error = None
        self._build_active()
        return True

    @property
    def active_name(self) -> str:
        # 若实际生效的不是配置名（例如 pytdx 缺失），返回真实源
        return self._active.name if self._active else self._active_name

    def available(self) -> list[str]:
        out = ["eastmoney", "xueqiu"]
        try:
            import pytdx  # noqa: F401
            out.insert(1, "tongdaxin")
        except ImportError:
            pass
        return out

    def status(self) -> dict:
        return {
            "active": self.active_name,
            "configured": self._active_name,
            "available": self.available(),
            "fallback": "eastmoney",
            "last_error": self._last_error,
        }

    def _demote_to_eastmoney(self, reason: str) -> None:
        """降级到东方财富并记录原因。

        降级具有「粘性」：一旦活跃源失败就把 _active 复位为东方财富，
        避免每次请求都重试已确认不可用的源（既拖慢响应，也会刷屏日志）。
        用户下次显式 set_active() 时才会重新启用该源。

        注意：调用方必须在入口快照当前配置源名再传入 reason，
        避免并发 set_active() 修改 _active_name 后，错误归属到错误的源。
        """
        self._last_error = reason
        logger.warning(reason)
        if self._active is not self._eastmoney:
            self._active = self._eastmoney

    # ---- 路由方法（带降级） ----
    def fetch_realtime_quotes(self, symbols: list[str]) -> list[dict]:
        # 入口快照：避免请求处理过程中被并发 set_active() 修改源名，
        # 导致错误日志文案张冠李戴（例如显示 eastmoney 失败: 无法连接通达信）。
        source_name = self._active_name
        try:
            res = self._active.fetch_realtime_quotes(symbols)
            if res:
                return res
            self._demote_to_eastmoney(f"数据源 {source_name} 返回空，已降级东方财富")
        except Exception as e:
            self._demote_to_eastmoney(f"数据源 {source_name} 实时行情失败: {e}，已降级东方财富")
        return self._eastmoney.fetch_realtime_quotes(symbols)

    def fetch_spot_snapshot(self) -> pd.DataFrame:
        source_name = self._active_name
        try:
            return self._active.fetch_spot_snapshot()
        except NotImplementedError:
            # 该源本身不支持快照（如雪球/通达信），不属于故障，不触发降级
            try:
                return self._eastmoney.fetch_spot_snapshot()
            except Exception as e:
                logger.warning(f"东方财富快照获取失败: {e}")
                return pd.DataFrame()
        except Exception as e:
            self._last_error = f"数据源 {source_name} 快照失败: {e}"
            logger.warning(self._last_error)
            return pd.DataFrame()

    def fetch_minute_kline(self, symbol: str, period: int, limit: int) -> pd.DataFrame:
        source_name = self._active_name
        try:
            return self._active.fetch_minute_kline(symbol, period, limit)
        except NotImplementedError:
            # 该源本身不支持分钟K线，不属于故障，不触发降级
            return self._eastmoney.fetch_minute_kline(symbol, period, limit)
        except Exception as e:
            self._demote_to_eastmoney(f"数据源 {source_name} 分钟K线失败: {e}，已降级东方财富")
            return self._eastmoney.fetch_minute_kline(symbol, period, limit)


_manager: Optional[DataSourceManager] = None


def get_manager() -> DataSourceManager:
    global _manager
    if _manager is None:
        _manager = DataSourceManager()
    return _manager


def set_active_source(name: str) -> bool:
    return get_manager().set_active(name)


def get_source_status() -> dict:
    return get_manager().status()


def fetch_realtime_quotes(symbols: list[str]) -> list[dict]:
    return get_manager().fetch_realtime_quotes(symbols)


def fetch_spot_snapshot() -> pd.DataFrame:
    return get_manager().fetch_spot_snapshot()


def fetch_minute_kline(symbol: str, period: int, limit: int) -> pd.DataFrame:
    return get_manager().fetch_minute_kline(symbol, period, limit)
