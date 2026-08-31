"""数据加载模块：AKShare 拉取 A 股行情 + Parquet 本地缓存

借鉴 QuantSandbox 的 Parquet 缓存策略：数据一次下载本地永久使用。
"""
from __future__ import annotations

from pathlib import Path
from datetime import datetime
from typing import Optional
import hashlib
import logging
import os
import sys
import threading

import pandas as pd

logger = logging.getLogger("data_loader")


def _get_cache_dir() -> Path:
    """获取缓存目录。

    打包环境下 backend 目录可能只读，使用用户目录存储缓存。
    """
    project_cache = Path(__file__).resolve().parent.parent / "cache"

    # 尝试使用项目目录的 cache
    try:
        project_cache.mkdir(parents=True, exist_ok=True)
        # 测试是否可写
        test_file = project_cache / ".write_test"
        test_file.write_text("test")
        test_file.unlink()
        return project_cache
    except (PermissionError, OSError):
        pass

    # 项目目录不可写（打包环境），使用用户数据目录
    app_data = os.environ.get('APPDATA') or os.path.expanduser('~')
    cache_dir = Path(app_data) / 'A股量化回测平台' / 'cache'
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


CACHE_DIR = _get_cache_dir()

# 实时数据缓存（内存缓存，避免频繁请求）
_REALTIME_CACHE = {}
_REALTIME_CACHE_EXPIRY = 60  # 缓存有效期（秒）
_REALTIME_CACHE_LOCK = threading.Lock()  # 线程安全保护

# 股票代码→名称映射缓存（启动时加载一次）
_STOCK_NAME_MAP: dict[str, str] = {}
_STOCK_NAME_MAP_LOADED = False
_STOCK_NAME_MAP_LOCK = threading.Lock()  # 线程安全保护


def _cache_path(symbol: str, period: str) -> Path:
    """生成缓存文件路径：cache/{symbol}_{period}.parquet"""
    safe = symbol.replace("/", "_")
    return CACHE_DIR / f"{safe}_{period}.parquet"


def fetch_kline(
    symbol: str,
    start_date: str,
    end_date: str,
    period: str = "daily",
    adjust: str = "qfq",
    use_cache: bool = True,
) -> pd.DataFrame:
    """获取 A 股 K 线数据，带 Parquet 缓存。

    Args:
        symbol: 股票代码，如 "000001"（平安银行）
        start_date: 起始日期 "YYYYMMDD"
        end_date: 结束日期 "YYYYMMDD"
        period: "daily" / "weekly" / "monthly"
        adjust: "qfq"前复权 / "hfq"后复权 / ""不复权
        use_cache: 是否使用本地缓存

    Returns:
        DataFrame，列：date, open, high, low, close, volume，date 为 datetime
    """
    cache_file = _cache_path(symbol, period)
    raw = None

    # 1. 尝试读取缓存
    if use_cache and cache_file.exists():
        try:
            raw = pd.read_parquet(cache_file)
            raw["date"] = pd.to_datetime(raw["date"])
        except Exception:
            # 缓存文件损坏，删除后重新拉取
            cache_file.unlink(missing_ok=True)
            raw = None

    # 2. 缓存不存在/损坏，或缓存区间不覆盖用户所选范围，从 AKShare 拉取
    if raw is None or raw.empty:
        raw = _fetch_from_akshare(symbol, start_date, end_date, period, adjust)
    else:
        cached_mask = (
            raw["date"] >= pd.to_datetime(start_date)
        ) & (
            raw["date"] <= pd.to_datetime(end_date)
        )
        cached_hit = raw.loc[cached_mask]
        if cached_hit.empty:
            # 缓存存在但所选区间内没有数据（如缓存是更早/更晚的行情），
            # 不能返回空，应重新拉取；AKShare 失败时 _fetch_from_akshare 内部会 fallback 模拟数据。
            logger.info(
                f"缓存区间不覆盖所选范围 (缓存={raw['date'].min().date()}~{raw['date'].max().date()}, "
                f"请求={start_date}~{end_date})，重新拉取: symbol={symbol}"
            )
            raw = _fetch_from_akshare(symbol, start_date, end_date, period, adjust)

    if raw is None or raw.empty:
        return raw if raw is not None else pd.DataFrame()

    # 3. 按日期范围过滤
    mask = (raw["date"] >= pd.to_datetime(start_date)) & (raw["date"] <= pd.to_datetime(end_date))
    result = raw.loc[mask].reset_index(drop=True)

    # 4. 写回缓存：把本次拉到的全量数据落盘 parquet，
    #    供后续扫描/回测/「缓存数据」断点续传直接命中本地，零网络。
    #    （之前遗漏写盘，导致 fetch_kline 永远读不到缓存、每次都联网，
    #      表现就是「缓存不下来、也不报错」。仅当覆盖所选区间且非空时写。）
    if not result.empty and (raw is not None) and not raw.empty:
        try:
            to_write = raw.copy()
            to_write["date"] = pd.to_datetime(to_write["date"])
            cache_file = _cache_path(symbol, period)
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            to_write.to_parquet(cache_file, index=False)
            logger.debug(f"已写入缓存: {cache_file}（{len(to_write)} 行）")
        except Exception as e:
            logger.warning(f"写入缓存失败 {symbol}: {e}")
    return result


def _fetch_from_akshare(
    symbol: str, start_date: str, end_date: str, period: str, adjust: str
) -> pd.DataFrame:
    """从 AKShare 拉取 A 股行情并标准化列名。

    网络不可用时自动生成模拟数据，确保回测功能可用。
    """
    # 清除系统代理环境变量，避免 requests 误走到未运行的本地代理（如 Clash 7892）
    # 导致 AKShare 全部 ProxyError 失败、只能返回模拟数据。
    _proxy_keys = ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
                   "ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy"]
    _saved = {}
    for _k in _proxy_keys:
        if _k in os.environ:
            _saved[_k] = os.environ.pop(_k)
    try:
        return _fetch_from_akshare_inner(symbol, start_date, end_date, period, adjust)
    finally:
        # 还原环境变量，避免影响进程内其他逻辑
        os.environ.update(_saved)


def _fetch_from_akshare_inner(
    symbol: str, start_date: str, end_date: str, period: str, adjust: str
) -> pd.DataFrame:
    """实际执行 AKShare 拉取（调用方已临时清除代理环境变量）。

    数据源说明：
    - 优先使用新浪源 `stock_zh_a_daily`（接口 host 为 finance.sina.com.cn），
      因为部分网络环境下东方财富源（push2his.eastmoney.com）的行情 API 会被
      代理/防火墙针对性阻断，导致只能降级为模拟数据。新浪源更稳定。
    - 仅 daily 周期支持新浪源；weekly/monthly 回退到东方财富源。
    """
    import akshare as ak

    # 拼回 sh/sz 前缀（AKShare 新浪源需要带市场前缀）
    if symbol.startswith(("sh", "sz", "bj")):
        sina_symbol = symbol
    elif symbol.startswith("6"):
        sina_symbol = "sh" + symbol
    elif symbol.startswith(("0", "3")):
        sina_symbol = "sz" + symbol
    elif symbol.startswith(("4", "8")):
        sina_symbol = "bj" + symbol
    else:
        sina_symbol = "sh" + symbol

    ak_adjust = adjust if adjust in ("qfq", "hfq") else ""

    if period in ("weekly", "monthly"):
        # 周/月线新浪源不支持，仍用东方财富源
        try:
            ak_period = "weekly" if period == "weekly" else "monthly"
            raw = ak.stock_zh_a_hist(
                symbol=symbol, period=ak_period,
                start_date=start_date, end_date=end_date, adjust=adjust,
            )
            if not raw.empty:
                rename_map = {
                    "日期": "date", "开盘": "open", "最高": "high",
                    "最低": "low", "收盘": "close", "成交量": "volume",
                    "成交额": "amount",
                }
                df = raw.rename(columns=rename_map)
                df["date"] = pd.to_datetime(df["date"])
                cols = ["date", "open", "high", "low", "close", "volume", "amount"]
                return df[[c for c in cols if c in df.columns]].copy()
        except Exception as e:
            logger.warning(f"东方财富源拉取失败 symbol={symbol}: {e}")
    else:
        # 日线：新浪源（更稳定）
        try:
            raw = ak.stock_zh_a_daily(
                symbol=sina_symbol,
                start_date=start_date,
                end_date=end_date,
                adjust=ak_adjust,
            )
            if not raw.empty:
                df = raw.copy()
                df["date"] = pd.to_datetime(df["date"])
                cols = ["date", "open", "high", "low", "close", "volume", "amount"]
                return df[[c for c in cols if c in df.columns]].copy()
        except Exception as e:
            logger.warning(f"新浪源拉取失败 symbol={symbol}: {e}")

    # 所有源失败，生成模拟 K 线数据
    logger.warning(
        f"所有数据源均失败，降级为模拟数据: symbol={symbol} "
        f"（该数据为随机生成，不代表真实行情）"
    )
    return _generate_mock_kline(symbol, start_date, end_date, period)


def _generate_mock_kline(
    symbol: str, start_date: str, end_date: str, period: str
) -> pd.DataFrame:
    """生成模拟 K 线数据（网络不可用时的 fallback）。"""
    import numpy as np

    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)

    # 根据周期生成日期序列
    if period == "weekly":
        dates = pd.date_range(start, end, freq="W-FRI")
    elif period == "monthly":
        dates = pd.date_range(start, end, freq="ME")
    else:
        dates = pd.bdate_range(start, end)  # 工作日

    if len(dates) == 0:
        return pd.DataFrame()

    # 根据股票代码确定基础价格
    base_prices = {
        "000001": 12.50, "000002": 8.80, "600000": 7.20, "600036": 32.50,
        "600519": 1650.00, "000858": 145.00, "601318": 42.30, "600276": 28.50,
    }
    base_price = base_prices.get(symbol, 10.0)

    # 生成带周期性波动的收盘价（确定性随机，便于复现）
    # 使用 SHA256 哈希生成种子，避免 hash() 的碰撞和平台差异问题
    seed = int(hashlib.sha256(symbol.encode()).hexdigest(), 16) % 2**32
    np.random.seed(seed)
    n = len(dates)
    # 趋势项（缓慢上涨/下跌）+ 周期项（正弦波段，制造均线交叉）+ 噪声
    t = np.arange(n)
    # 固定多周期波段（不依赖随机方向，确保任何股票都产生均线交叉）
    wave1 = 0.18 * np.sin(2 * np.pi * t / max(12, n // 2))      # 主波段：覆盖半区间
    wave2 = 0.10 * np.sin(2 * np.pi * t / max(6, n // 5))       # 次级波段
    wave3 = 0.06 * np.sin(2 * np.pi * t / max(3, n // 12))      # 短期波动
    # 小幅随机扰动（仅作噪声，不影响整体波段结构）
    np.random.seed(seed + 99)
    noise = np.random.normal(0, 0.008, n)
    daily_growth = (wave1 + wave2 + wave3 + noise) / n
    close_prices = base_price * np.cumprod(1 + daily_growth)
    close_prices = np.maximum(close_prices, 0.5)  # 防止负值

    # 重新设置种子以保证各数组使用独立但确定性的随机序列
    np.random.seed(seed + 1)
    opens = close_prices * (1 + np.random.uniform(-0.01, 0.01, len(dates)))
    np.random.seed(seed + 2)
    highs = np.maximum(opens, close_prices) * (1 + np.random.uniform(0, 0.02, len(dates)))
    np.random.seed(seed + 3)
    lows = np.minimum(opens, close_prices) * (1 - np.random.uniform(0, 0.02, len(dates)))
    np.random.seed(seed + 4)
    volumes = np.random.randint(1000000, 50000000, len(dates))

    df = pd.DataFrame({
        "date": dates,
        "open": np.round(opens, 2),
        "high": np.round(highs, 2),
        "low": np.round(lows, 2),
        "close": np.round(close_prices, 2),
        "volume": volumes,
        "amount": np.round(volumes * close_prices / 100, 2),  # 模拟成交额
    })

    # 降级为模拟数据是「静默失败」：用户会以为拿到的是真实行情，
    # 并据此判断策略有效性。必须用 warning 级别而非 info，保证可追溯。
    logger.warning(
        f"生成 {len(df)} 条模拟K线数据（随机生成，非真实行情）: symbol={symbol} "
        f"period={period} —— 基于该数据的回测/选股结果不可作为策略有效性依据"
    )
    df.attrs["is_mock"] = True
    return df


def list_cache() -> list[dict]:
    """列出所有缓存的数据文件，并标注是否为模拟数据。

    ``is_mock`` 来自 parquet 中的 pandas attrs 标记（由 _generate_mock_kline 写入）。
    暴露该字段是为了让「数据管理」页能区分真实行情与降级生成的随机数据，
    避免用户把模拟数据当成真实行情使用。
    """
    result = []
    for f in sorted(CACHE_DIR.glob("*.parquet")):
        try:
            df = pd.read_parquet(f, columns=["date"])
            is_mock = False
            try:
                # 只读取 attrs 元数据，避免为了拿标记而加载整份数据
                full = pd.read_parquet(f)
                is_mock = bool(full.attrs.get("is_mock"))
            except Exception:
                pass
            result.append({
                "file": f.name,
                "symbol": f.stem.rsplit("_", 1)[0],
                "period": f.stem.rsplit("_", 1)[1] if "_" in f.stem else "daily",
                "rows": len(df),
                "start": str(df["date"].min().date()) if not df.empty else None,
                "end": str(df["date"].max().date()) if not df.empty else None,
                "size_kb": round(f.stat().st_size / 1024, 1),
                "is_mock": is_mock,
            })
        except Exception:
            pass
    return result


def clear_cache(symbol: Optional[str] = None) -> int:
    """清理缓存。symbol 为空则清空全部，返回删除文件数。"""
    if symbol:
        files = list(CACHE_DIR.glob(f"{symbol}_*.parquet")) + list(CACHE_DIR.glob(f"{symbol.replace('/', '_')}_*.parquet"))
    else:
        files = list(CACHE_DIR.glob("*.parquet"))
    count = 0
    for f in files:
        f.unlink(missing_ok=True)
        count += 1
    return count


# 常用 A 股代码→名称硬编码映射（保底，仅当 StockNameCache 不可用时使用）
# 主映射请使用 data.stock_names.StockNameCache
_STOCK_NAME_HARDCODED = {
    '600103': '青山纸业', '600000': '浦发银行', '600036': '招商银行', '600519': '贵州茅台',
    '601318': '中国平安', '600276': '恒瑞医药', '600887': '伊利股份', '601166': '兴业银行',
    '600030': '中信证券', '000001': '平安银行', '000002': '万科A', '000858': '五粮液',
    '000333': '美的集团', '000651': '格力电器', '002594': '比亚迪', '300750': '宁德时代',
    '688981': '中芯国际', '601012': '隆基绿能', '600309': '万华化学', '601888': '中国中免',
    '002415': '海康威视', '000725': '京东方A', '002475': '立讯精密', '300059': '东方财富',
    '600016': '民生银行', '601328': '交通银行', '601398': '工商银行', '601288': '农业银行',
    '601988': '中国银行', '600048': '保利发展', '001979': '招商蛇口', '000069': '华侨城A',
    '002304': '洋河股份', '603288': '海天味业', '600809': '山西汾酒', '000568': '泸州老窖',
    '600741': '华域汽车', '601238': '广汽集团', '002230': '科大讯飞', '300124': '汇川技术',
    '688111': '金山办公', '300496': '中科创达', '002410': '广联达', '300454': '深信服',
}

def _load_builtin_stock_map():
    """加载随应用打包的内置股票名称映射文件。"""
    import json
    from pathlib import Path

    # 查找内置的 stock_name_map.json 文件（可能位于多个位置）
    possible_paths = [
        Path(__file__).parent.parent / "data" / "stock_name_map.json",  # backend/data/
        Path(__file__).parent.parent.parent / "backend" / "data" / "stock_name_map.json",  # 打包后
    ]

    for p in possible_paths:
        if p.exists():
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                logger.info(f"从内置文件加载股票名称映射: {len(data)} 只 ({p})")
                return data
            except Exception as e:
                logger.warning(f"读取内置股票名称映射失败 ({p}): {e}")

    return {}


def _ensure_stock_name_map():
    """确保股票名称映射已加载。

    优先级：
    1. StockNameCache（统一映射源）
    2. 本地 JSON 缓存
    3. AKShare 在线获取
    4. 硬编码保底
    """
    global _STOCK_NAME_MAP, _STOCK_NAME_MAP_LOADED

    with _STOCK_NAME_MAP_LOCK:
        if _STOCK_NAME_MAP_LOADED:
            return

        # 1. 尝试从 StockNameCache 获取（统一数据源）
        try:
            from data.stock_names import _stock_name_cache
            _stock_name_cache._load_cache()
            if _stock_name_cache.names:
                for code, info in _stock_name_cache.names.items():
                    _STOCK_NAME_MAP[code] = info.get('name', f'股票{code}')
                _STOCK_NAME_MAP_LOADED = True
                logger.info(f"从 StockNameCache 加载股票名称映射: {len(_STOCK_NAME_MAP)} 只")
                return
        except ImportError:
            logger.debug("StockNameCache 不可用，使用内置加载逻辑")

        # 2. 降级：加载硬编码 + 本地缓存
        _STOCK_NAME_MAP = dict(_STOCK_NAME_HARDCODED)

        builtin_map = _load_builtin_stock_map()
        if builtin_map:
            _STOCK_NAME_MAP.update(builtin_map)

        cache_file = CACHE_DIR.parent / "stock_name_map.json"
        if cache_file.exists():
            try:
                import json
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cached = json.load(f)
                _STOCK_NAME_MAP.update(cached)
                _STOCK_NAME_MAP_LOADED = True
                logger.info(f"从本地缓存加载股票名称映射: {len(_STOCK_NAME_MAP)} 只")
                return
            except Exception as e:
                logger.warning(f"读取用户缓存失败: {e}")

        # 3. 从 AKShare 获取
        import time
        for attempt in range(3):
            try:
                import akshare as ak
                import json
                logger.info(f"正在从 AKShare 获取股票名称映射（尝试 {attempt + 1}/3）...")
                df = ak.stock_zh_a_spot_em()
                count = 0
                for _, row in df.iterrows():
                    code = str(row['代码'])
                    name = str(row['名称'])
                    _STOCK_NAME_MAP[code] = name
                    count += 1

                cache_file.parent.mkdir(parents=True, exist_ok=True)
                with open(cache_file, 'w', encoding='utf-8') as f:
                    json.dump(_STOCK_NAME_MAP, f, ensure_ascii=False)

                _STOCK_NAME_MAP_LOADED = True
                logger.info(f"从 AKShare 加载股票名称映射: {count} 只")
                return
            except Exception as e:
                logger.warning(f"从 AKShare 加载股票名称映射失败（尝试 {attempt + 1}/3）: {e}")
                if attempt < 2:
                    time.sleep(2)

        # 所有尝试都失败，使用硬编码
        _STOCK_NAME_MAP_LOADED = True
        logger.warning(f"使用硬编码股票名称映射: {len(_STOCK_NAME_MAP)} 只")


def fetch_realtime_quote(symbols: list[str]) -> list[dict]:
    """获取实时行情数据（真实数据，AKShare接口）。

    先尝试 AKShare 批量接口获取真实数据，失败则逐个拉取，
    全部失败才降级为模拟数据。

    返回 50+ 字段的完整行情数据（v3.0 升级）。

    Args:
        symbols: 股票代码列表，如 ["000001", "000002"]

    Returns:
        实时行情数据列表，每个元素包含完整字段
    """
    from datetime import datetime, timezone

    # 确保股票名称映射已加载
    _ensure_stock_name_map()

    now = datetime.now(timezone.utc)

    # 1. 检查缓存（缓存有效期 60 秒，线程安全，使用 UTC 时间避免时区问题）
    cache_key = ",".join(sorted(symbols))
    with _REALTIME_CACHE_LOCK:
        if cache_key in _REALTIME_CACHE:
            cached_data, cached_time = _REALTIME_CACHE[cache_key]
            if (now - cached_time).total_seconds() < _REALTIME_CACHE_EXPIRY:
                logger.debug(f"使用缓存实时行情: {symbols}")
                return cached_data

    # 2. 通过数据源抽象层获取（默认东财，可切换通达信/雪球，失败自动降级到东财）
    import core.datasource as datasource
    result = datasource.fetch_realtime_quotes(symbols)

    # 3. 更新缓存（线程安全）
    with _REALTIME_CACHE_LOCK:
        _REALTIME_CACHE[cache_key] = (result, now)
    return result


def _fetch_realtime_from_akshare(symbols: list[str], now: datetime) -> list[dict]:
    """通过 AKShare 获取真实实时行情（50+ 字段，v3.0 升级）。"""
    result = []
    try:
        import akshare as ak
        import numpy as np
        import json

        # 使用东方财富即时行情接口（返回全市场数据，本地过滤）
        df = ak.stock_zh_a_spot_em()

        # 把所有返回的股票名称更新到映射表
        global _STOCK_NAME_MAP
        new_count = 0
        for _, row in df.iterrows():
            code = str(row['代码'])
            name = str(row['名称'])
            if code not in _STOCK_NAME_MAP:
                new_count += 1
            _STOCK_NAME_MAP[code] = name

        # 如果有新股票名称，保存到缓存文件
        if new_count > 0:
            try:
                cache_file = CACHE_DIR.parent / "stock_name_map.json"
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                with open(cache_file, 'w', encoding='utf-8') as f:
                    json.dump(_STOCK_NAME_MAP, f, ensure_ascii=False)
                logger.info(f"股票名称映射已更新并保存: +{new_count} 只 (共 {len(_STOCK_NAME_MAP)} 只)")
            except Exception as e:
                logger.warning(f"保存股票名称映射失败: {e}")

        # 批量获取历史K线用于计算涨跌统计字段（3/6/20/250日）
        hist_cache = {}
        for symbol in symbols:
            try:
                # 尝试从缓存读取K线
                cache_file = CACHE_DIR / f"{symbol}_daily.parquet"
                if cache_file.exists():
                    hist_df = pd.read_parquet(cache_file)
                    hist_df["date"] = pd.to_datetime(hist_df["date"])
                    hist_cache[symbol] = hist_df
            except Exception:
                pass

        for symbol in symbols:
            row_df = df[df['代码'] == symbol]
            if row_df.empty:
                continue
            row = row_df.iloc[0]

            # 基础价格字段
            price = float(row.get('最新价', 0) or 0)
            pre_close = float(row.get('昨收', 0) or 0)
            open_price = float(row.get('今开', 0) or 0)
            high = float(row.get('最高', 0) or 0)
            low = float(row.get('最低', 0) or 0)
            change = float(row.get('涨跌额', 0) or 0)
            pct = float(row.get('涨跌幅', 0) or 0)
            volume = int(float(row.get('成交量', 0) or 0))
            amount = float(row.get('成交额', 0) or 0)

            # 计算字段
            amplitude = round((high - low) / pre_close * 100, 2) if pre_close > 0 else 0

            # 市值相关
            total_share = float(row.get('总市值', np.nan) or np.nan)
            float_share = float(row.get('流通市值', np.nan) or np.nan)
            total_market_cap = float(row.get('总市值', 0) or 0)
            float_market_cap = float(row.get('流通市值', 0) or 0)
            total_share_val = round(total_market_cap / price, 2) if price > 0 and total_market_cap > 0 else 0
            float_share_val = round(float_market_cap / price, 2) if price > 0 and float_market_cap > 0 else 0

            # 市盈率/市净率
            pe_ratio = float(row.get('市盈率-动态', 0) or 0)
            pb_ratio = float(row.get('市净率', 0) or 0)

            # 换手率
            turnover_rate = float(row.get('换手率', 0) or 0)

            # 量比（如果有）
            volume_ratio = float(row.get('量比', 0) or 0)

            # 涨速（5分钟涨幅，估算）
            change_speed = float(row.get('涨速', 0) or 0)

            # 盘口数据
            bid_price = float(row.get('买入', 0) or 0)
            ask_price = float(row.get('卖出', 0) or 0)

            # 均价
            avg_price = round(amount / (volume * 100), 2) if volume > 0 and amount > 0 else price

            # 涨停跌停
            limit_up = round(pre_close * 1.1, 2)
            limit_down = round(pre_close * 0.9, 2)
            if 'ST' in str(row.get('名称', '')):
                limit_up = round(pre_close * 1.05, 2)
                limit_down = round(pre_close * 0.95, 2)

            # 从 StockNameCache 获取行业信息
            from data.stock_names import get_stock_sector
            sector = get_stock_sector(symbol)

            # ===== 涨跌统计字段（基于历史K线计算） =====
            hist_df = hist_cache.get(symbol)
            change_stats = _calc_change_stats(hist_df, price, pre_close) if hist_df is not None else _empty_change_stats()

            # 构建完整行情数据（50+ 字段）
            item = {
                # === 基本信息 ===
                "symbol": symbol,
                "name": str(row.get('名称', symbol)),
                "sector": sector,

                # === 价格信息 ===
                "price": round(price, 2),
                "open": round(open_price, 2),
                "high": round(high, 2),
                "low": round(low, 2),
                "pre_close": round(pre_close, 2),
                "change_amount": round(change, 2),
                "change_pct": round(pct, 2),
                "amplitude": amplitude,
                "avg_price": avg_price,

                # === 成交量 ===
                "volume": volume,
                "amount": round(amount, 2),
                "turnover_rate": round(turnover_rate, 2),
                "change_speed": round(change_speed, 2),
                "volume_ratio": round(volume_ratio, 2),

                # === 市值 ===
                "total_share": total_share_val,
                "float_share": float_share_val,
                "total_market_cap": total_market_cap,
                "float_market_cap": float_market_cap,
                "pe_ratio": round(pe_ratio, 2),
                "pb_ratio": round(pb_ratio, 2),

                # === 盘口 ===
                "bid_price": round(bid_price, 2),
                "ask_price": round(ask_price, 2),
                "limit_up": limit_up,
                "limit_down": limit_down,

                # === 涨跌统计 ===
                **change_stats,

                # === 更新时间 ===
                "update_time": now.strftime("%Y-%m-%d %H:%M:%S"),
            }

            # 尝试获取更多字段（不同版本的 akshare 返回字段可能不同）
            try:
                item["commission_ratio"] = round(float(row.get('委比', 0) or 0), 2)
            except (ValueError, TypeError):
                item["commission_ratio"] = 0
            try:
                item["commission_diff"] = int(float(row.get('委差', 0) or 0))
            except (ValueError, TypeError):
                item["commission_diff"] = 0
            try:
                item["inner_volume"] = int(float(row.get('内盘', 0) or 0))
            except (ValueError, TypeError):
                item["inner_volume"] = 0
            try:
                item["outer_volume"] = int(float(row.get('外盘', 0) or 0))
            except (ValueError, TypeError):
                item["outer_volume"] = 0
            if item.get("outer_volume", 0) > 0:
                item["io_ratio"] = round(item.get("inner_volume", 0) / item.get("outer_volume", 0), 2)
            else:
                item["io_ratio"] = 0

            try:
                item["bid1_volume"] = int(float(row.get('买一量', 0) or 0))
            except (ValueError, TypeError):
                item["bid1_volume"] = 0
            try:
                item["ask1_volume"] = int(float(row.get('卖一量', 0) or 0))
            except (ValueError, TypeError):
                item["ask1_volume"] = 0

            result.append(item)

        logger.info(f"AKShare 实时行情获取成功: {len(result)}/{len(symbols)} 只")
    except Exception as e:
        logger.warning(f"AKShare 实时行情获取失败: {e}")

    return result


def _empty_change_stats() -> dict:
    """返回空的涨跌统计字段。"""
    return {
        "change_3d": 0, "change_6d": 0,
        "turnover_3d": 0, "turnover_6d": 0,
        "consecutive_up": 0, "change_mtd": 0,
        "change_ytd": 0, "change_1m": 0,
        "change_1y": 0,
    }


def _calc_change_stats(hist_df, current_price: float, pre_close: float) -> dict:
    """基于历史K线数据计算涨跌统计字段。

    计算：3日/6日/近20日/近250日/本月/今年涨幅，
    以及连涨天数、3日/6日换手率（基于成交量估算）。
    """
    if hist_df is None or hist_df.empty:
        return _empty_change_stats()

    try:
        closes = hist_df["close"].values
        volumes = hist_df["volume"].values

        n = len(closes)
        result = {}

        # 3日涨幅：当前价相对于3个交易日前的收盘价
        if n >= 3:
            result["change_3d"] = round((current_price / closes[-3] - 1) * 100, 2)
        else:
            result["change_3d"] = 0

        # 6日涨幅：当前价相对于6个交易日前的收盘价
        if n >= 6:
            result["change_6d"] = round((current_price / closes[-6] - 1) * 100, 2)
        else:
            result["change_6d"] = 0

        # 近一月涨幅（约20个交易日）
        m1_idx = max(0, n - 20)
        if m1_idx < n:
            result["change_1m"] = round((current_price / closes[m1_idx] - 1) * 100, 2)
        else:
            result["change_1m"] = 0

        # 近一年涨幅（约250个交易日）
        y1_idx = max(0, n - 250)
        if y1_idx < n:
            result["change_1y"] = round((current_price / closes[y1_idx] - 1) * 100, 2)
        else:
            result["change_1y"] = 0

        # 本月涨幅（从当月第一天或最近一条开始）
        result["change_mtd"] = _calc_mtd_change(hist_df, current_price)

        # 今年涨幅
        result["change_ytd"] = _calc_ytd_change(hist_df, current_price)

        # 连涨天数
        result["consecutive_up"] = _calc_consecutive_up(closes, pre_close)

        # 3日/6日换手率：基于成交量与总股本估算
        # Parquet 缓存中通常没有 total_share 字段，因此使用
        # 成交量/最近250日均量 作为活跃度估算（不再返回始终为0的值）
        if n >= 250:
            avg_vol_250 = float(volumes[-250:].mean()) if volumes[-250:].mean() > 0 else 1.0
            result["turnover_3d"] = round(volumes[-3:].sum() / avg_vol_250 * 100, 2) if n >= 3 else 0
            result["turnover_6d"] = round(volumes[-6:].sum() / avg_vol_250 * 100, 2) if n >= 6 else 0
        elif n >= 20:
            avg_vol = float(volumes.mean()) if volumes.mean() > 0 else 1.0
            result["turnover_3d"] = round(volumes[-3:].sum() / avg_vol * 100, 2) if n >= 3 else 0
            result["turnover_6d"] = round(volumes[-6:].sum() / avg_vol * 100, 2) if n >= 6 else 0
        else:
            result["turnover_3d"] = 0
            result["turnover_6d"] = 0

        return result
    except Exception as e:
        logger.debug(f"计算涨跌统计字段失败: {e}")
        return _empty_change_stats()


def _calc_mtd_change(hist_df, current_price: float) -> float:
    """计算本月涨幅。"""
    from datetime import datetime
    try:
        today = datetime.now()
        # 本月第一天
        month_start = today.replace(day=1)
        df_month = hist_df[hist_df["date"] >= pd.to_datetime(month_start)]
        if len(df_month) > 0:
            first_close = df_month.iloc[0]["close"]
            if first_close > 0:
                return round((current_price / first_close - 1) * 100, 2)
    except Exception:
        pass
    return 0


def _calc_ytd_change(hist_df, current_price: float) -> float:
    """计算今年涨幅。"""
    from datetime import datetime
    try:
        today = datetime.now()
        year_start = today.replace(month=1, day=1)
        df_year = hist_df[hist_df["date"] >= pd.to_datetime(year_start)]
        if len(df_year) > 0:
            first_close = df_year.iloc[0]["close"]
            if first_close > 0:
                return round((current_price / first_close - 1) * 100, 2)
    except Exception:
        pass
    return 0


def _calc_consecutive_up(closes, pre_close: float) -> int:
    """计算连涨天数（从最近一天往前数连续阳线的天数）。"""
    count = 0
    prev = pre_close
    for c in reversed(closes):
        if c > prev:
            count += 1
            prev = c
        else:
            break
    return count


def _generate_mock_realtime(symbols: list[str], now: datetime) -> list[dict]:
    """生成模拟实时行情（AKShare 失败时的降级方案，v3.0 50+ 字段）。"""
    import random

    # 常用股票的基础价格
    stock_info = {
        '000001': {'name': '平安银行', 'base_price': 12.50, 'sector': '银行'},
        '000002': {'name': '万科A', 'base_price': 8.80, 'sector': '房地产'},
        '600000': {'name': '浦发银行', 'base_price': 7.20, 'sector': '银行'},
        '600036': {'name': '招商银行', 'base_price': 32.50, 'sector': '银行'},
        '600519': {'name': '贵州茅台', 'base_price': 1650.00, 'sector': '白酒'},
        '000858': {'name': '五粮液', 'base_price': 145.00, 'sector': '白酒'},
        '601318': {'name': '中国平安', 'base_price': 42.30, 'sector': '保险'},
        '600276': {'name': '恒瑞医药', 'base_price': 28.50, 'sector': '医药'},
    }

    result = []
    for symbol in symbols:
        # 优先从名称映射表获取名称和行业
        from data.stock_names import get_stock_name, get_stock_sector
        name = get_stock_name(symbol)
        sector = get_stock_sector(symbol)
        if name.startswith('股票'):
            name = stock_info.get(symbol, {}).get('name', name)
        if sector == '未知':
            sector = stock_info.get(symbol, {}).get('sector', '未知')

        base_price = stock_info.get(symbol, {'base_price': random.uniform(5, 100)}).get('base_price', random.uniform(5, 100))
        if not isinstance(base_price, (int, float)):
            base_price = random.uniform(5, 100)

        price = base_price * random.uniform(0.95, 1.05)
        pre_close = base_price
        change = price - pre_close
        pct_change = (change / pre_close) * 100
        open_price = base_price * random.uniform(0.98, 1.02)
        high = max(price, open_price) * random.uniform(1.0, 1.02)
        low = min(price, open_price) * random.uniform(0.98, 1.0)
        volume = random.randint(1000000, 50000000)
        amount = price * volume * 100

        result.append({
            "symbol": symbol,
            "name": name,
            "sector": sector,
            "price": round(price, 2),
            "open": round(open_price, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "pre_close": round(pre_close, 2),
            "change_amount": round(change, 2),
            "change_pct": round(pct_change, 2),
            "amplitude": round((high - low) / pre_close * 100, 2),
            "avg_price": round(amount / (volume * 100), 2),
            "volume": volume,
            "amount": int(amount),
            "turnover_rate": round(random.uniform(0.5, 5.0), 2),
            "change_speed": round(random.uniform(-1, 1), 2),
            "volume_ratio": round(random.uniform(0.5, 2.0), 2),
            "total_share": round(random.uniform(1, 50), 2),
            "float_share": round(random.uniform(0.8, 45), 2),
            "total_market_cap": round(price * random.uniform(5, 500), 2),
            "float_market_cap": round(price * random.uniform(4, 400), 2),
            "pe_ratio": round(random.uniform(10, 50), 2),
            "pb_ratio": round(random.uniform(1, 8), 2),
            "bid_price": round(price - 0.01, 2),
            "ask_price": round(price + 0.01, 2),
            "limit_up": round(pre_close * 1.1, 2),
            "limit_down": round(pre_close * 0.9, 2),
            "commission_ratio": round(random.uniform(-10, 10), 2),
            "commission_diff": random.randint(-5000, 5000),
            "inner_volume": int(volume * random.uniform(0.3, 0.7)),
            "outer_volume": int(volume * random.uniform(0.3, 0.7)),
            "io_ratio": round(random.uniform(0.5, 1.5), 2),
            "bid1_volume": random.randint(100, 5000),
            "ask1_volume": random.randint(100, 5000),
            # === 涨跌统计（模拟数据） ===
            "change_3d": round(random.uniform(-5, 5), 2),
            "change_6d": round(random.uniform(-8, 8), 2),
            "change_1m": round(random.uniform(-15, 15), 2),
            "change_1y": round(random.uniform(-30, 50), 2),
            "change_mtd": round(random.uniform(-8, 8), 2),
            "change_ytd": round(random.uniform(-20, 30), 2),
            "consecutive_up": random.randint(0, 5),
            "turnover_3d": round(random.uniform(1, 10), 2),
            "turnover_6d": round(random.uniform(2, 20), 2),
            "update_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        })

    return result


def fetch_realtime_quotes_batch(symbols: list[str]) -> list[dict]:
    """批量获取实时行情（真实数据）。

    与 fetch_realtime_quote 逻辑一致，复用同一缓存。
    """
    return fetch_realtime_quote(symbols)


# ==================== 东方财富直连高速下载（跳过 AKShare 中间层） ====================

import aiohttp as _aiohttp
import asyncio as _asyncio

# 东方财富日K线 API
_EM_KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
_EM_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://quote.eastmoney.com/",
}

# 全局 aiohttp ClientSession（异步连接池）
_EM_ASYNC_SESSION: _aiohttp.ClientSession | None = None
_EM_SESSION_LOCK = threading.Lock()
# 写缓存专用线程池（避免磁盘 IO 阻塞事件循环）
_CACHE_EXECUTOR = None


def _get_cache_executor():
    """获取写缓存专用线程池（懒加载）。"""
    global _CACHE_EXECUTOR
    if _CACHE_EXECUTOR is None:
        from concurrent.futures import ThreadPoolExecutor
        _CACHE_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="cache_writer")
    return _CACHE_EXECUTOR


async def _get_em_async_session() -> _aiohttp.ClientSession:
    """获取/创建全局 aiohttp ClientSession（连接池复用，自动管理 TCP 连接）。"""
    global _EM_ASYNC_SESSION
    if _EM_ASYNC_SESSION is None or _EM_ASYNC_SESSION.closed:
        connector = _aiohttp.TCPConnector(
            limit=100,          # 总连接数上限
            limit_per_host=50,  # 同一 host 连接数上限
            ttl_dns_cache=300,  # DNS 缓存 5 分钟
            force_close=False,  # 复用连接
        )
        timeout = _aiohttp.ClientTimeout(total=15, connect=5)
        _EM_ASYNC_SESSION = _aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers=_EM_HEADERS,
        )
    return _EM_ASYNC_SESSION


def _secid_from_symbol(symbol: str) -> str:
    """将股票代码转为东方财富 secid 格式。

    例: sh600519 → 1.600519, sz000001 → 0.000001, bj430047 → 0.430047
    """
    code = symbol
    market = 1  # 默认上海
    if code.startswith("sh"):
        code = code[2:]
        market = 1
    elif code.startswith("sz"):
        code = code[2:]
        market = 0
    elif code.startswith("bj"):
        code = code[2:]
        market = 0
    elif code.startswith("6"):
        market = 1
    else:
        market = 0
    return f"{market}.{code}"


async def _fetch_kline_direct_eastmoney(
    symbol: str,
    start_date: str,
    end_date: str,
    period: str = "daily",
    adjust: str = "qfq",
) -> pd.DataFrame:
    """用 aiohttp 异步调东方财富 API 下载 K 线（跳过 AKShare 中间层）。

    核心优化：
    1. aiohttp 真异步 IO — 单线程事件循环管理数百并发请求，无 GIL 瓶颈
    2. TCPConnector 连接池 — 复用 TCP 连接，避免重复握手
    3. 直接 JSON 解析 → DataFrame，路径最短

    Args:
        symbol: 带前缀代码如 "sh600519"
        start_date/end_date: YYYYMMDD
        period: daily/weekly/monthly
        adjust: qfq/hfq/空字符串

    Returns:
        标准化 DataFrame: date, open, high, low, close, volume, amount
        失败返回空 DataFrame
    """
    secid = _secid_from_symbol(symbol)

    klt_map = {"daily": 101, "weekly": 102, "monthly": 103}
    klt = klt_map.get(period, 101)

    fqt_map = {"qfq": 1, "hfq": 2, "": 0}
    fqt = fqt_map.get(adjust, 1)

    params = {
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "ut": "7eea3edcaed734bea9c4e5e9b7f7b28c",
        "klt": klt,
        "fqt": fqt,
        "secid": secid,
        "beg": start_date,
        "end": end_date,
        "lmt": 10000,
        "_": str(int(datetime.now().timestamp() * 1000)),
    }

    try:
        session = await _get_em_async_session()
        async with session.get(_EM_KLINE_URL, params=params) as resp:
            if resp.status != 200:
                return pd.DataFrame()
            data = await resp.json()

        if data is None or data.get("data") is None:
            return pd.DataFrame()

        klines_raw = data["data"].get("klines")
        if not klines_raw:
            return pd.DataFrame()

        # 解析 K 线字符串列表
        rows = []
        for line in klines_raw:
            parts = line.split(",")
            if len(parts) < 7:
                continue
            rows.append({
                "date": parts[0],
                "open": float(parts[1]),
                "close": float(parts[2]),
                "high": float(parts[3]),
                "low": float(parts[4]),
                "volume": float(parts[5]),
                "amount": float(parts[6]),
            })

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        return df[["date", "open", "high", "low", "close", "volume", "amount"]]

    except Exception as e:
        logger.debug(f"东方财富直连失败 {symbol}: {e}")
        return pd.DataFrame()


def _write_to_cache_sync(symbol: str, period: str, df: pd.DataFrame) -> None:
    """同步写入 parquet 缓存（由线程池执行，避免阻塞事件循环）。"""
    if df is None or df.empty:
        return
    try:
        to_write = df.copy()
        to_write["date"] = pd.to_datetime(to_write["date"])
        cache_file = _cache_path(symbol, period)
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        to_write.to_parquet(cache_file, index=False)
    except Exception as e:
        logger.warning(f"写入缓存失败 {symbol}: {e}")


async def _write_to_cache_async(symbol: str, period: str, df: pd.DataFrame) -> None:
    """异步写入 parquet 缓存（将磁盘 IO 卸载到线程池）。"""
    loop = _asyncio.get_running_loop()
    executor = _get_cache_executor()
    await loop.run_in_executor(executor, _write_to_cache_sync, symbol, period, df)


# ==================== 批量预热（扫描前一次性下载时间范围内数据） ====================

def prefetch_klines(
    symbols: list[str],
    start_date: str,
    end_date: str,
    period: str = "daily",
    rate_limit: float = 0.05,
    on_progress=None,
    max_workers: int = 50,
    cancel_event: threading.Event | None = None,
) -> dict:
    """批量预热 K 线到本地 parquet 缓存（asyncio 异步并发下载）。

    用于全市场扫描前的「数据准备」阶段：先把范围内全部股票的历史 K 线
    下载到本地缓存，扫描阶段即可纯本地零网络运行。

    设计要点：
    - 使用 asyncio + aiohttp 真异步 IO 并发下载（默认 50 并发），远超线程方案；
    - Semaphore 精确控流，避免触发数据源限流；
    - 已缓存且区间覆盖的跳过（断点续传），再次预热不会重复下载；
    - on_progress(done, total, symbol, ok) 回调用于上报进度（SSE/持久化）；
    - 单只失败不影响整体，自动降级为模拟数据写入缓存（保证后续扫描有数据）；
    - 磁盘写缓存卸载到线程池，不阻塞事件循环；
    - cancel_event：外部可通过 threading.Event.set() 中止下载（已下载的仍写入缓存）；
    - 返回统计：{total, cached, fetched, failed, cancelled}。

    Args:
        symbols: 纯代码列表（可带 sh/sz 前缀，内部自动处理）
        start_date/end_date: YYYYMMDD
        period: daily/weekly/monthly
        rate_limit: 保留参数（兼容），当前不使用
        on_progress: 回调函数(done, total, symbol, ok)
        max_workers: 异步并发上限（Semaphore），默认 50
        cancel_event: 可选 threading.Event，外部 set() 后立即中止剩余下载
    """
    # 第一步：预处理所有 symbol，分离已缓存和待下载
    total = len(symbols)
    cached = 0
    to_fetch: list[tuple[int, str, str]] = []  # (原始索引, 原始symbol, 带前缀sym)

    for i, symbol in enumerate(symbols):
        sym = symbol
        if not sym.startswith(("sh", "sz", "bj")):
            if sym.startswith("6"):
                sym = "sh" + sym
            elif sym.startswith(("0", "3")):
                sym = "sz" + sym
            elif sym.startswith(("4", "8")):
                sym = "bj" + sym

        cache_file = _cache_path(sym, period)
        skip = False
        if cache_file.exists():
            try:
                df_tmp = pd.read_parquet(cache_file)
                if not df_tmp.empty:
                    dts = pd.to_datetime(df_tmp["date"])
                    if (dts.min() <= pd.to_datetime(start_date)) and (dts.max() >= pd.to_datetime(end_date)):
                        skip = True
            except Exception:
                pass

        if skip:
            cached += 1
            if on_progress:
                on_progress(cached, total, sym, True)
        else:
            to_fetch.append((i, symbol, sym))

    if not to_fetch:
        return {"total": total, "cached": cached, "fetched": 0, "failed": 0}

    # 第二步：asyncio 异步并发下载
    fetched = 0
    failed = 0
    completed = cached
    progress_lock = threading.Lock()

    async def _download_one_async(
        sem: _asyncio.Semaphore, idx: int, sym: str,
    ) -> tuple[int, str, bool]:
        """异步下载单只股票：优先东财直连 → 回退 AKShare → 写缓存。"""
        async with sem:
            # 获取 semaphore 后立即检查取消信号
            if cancel_event and cancel_event.is_set():
                return (idx, sym, False)

            # 策略1：aiohttp 直连东方财富（极快）
            try:
                df = await _fetch_kline_direct_eastmoney(
                    sym, start_date, end_date, period=period, adjust="qfq",
                )
                if df is not None and not df.empty:
                    await _write_to_cache_async(sym, period, df)
                    return (idx, sym, True)
            except Exception:
                pass

            # 策略2：回退到 AKShare（同步调用，卸载到线程池避免阻塞事件循环）
            try:
                loop = _asyncio.get_running_loop()
                df = await loop.run_in_executor(
                    None, fetch_kline, sym, start_date, end_date, period, "qfq", False,
                )
                if df is not None and not df.empty:
                    return (idx, sym, True)
            except Exception as e2:
                logger.debug(f"AKShare 回退也失败 {sym}: {e2}")

            logger.warning(f"预热拉取失败 {sym}: 东财直连和 AKShare 均失败")
            return (idx, sym, False)

    async def _run_all():
        nonlocal fetched, failed, completed
        sem = _asyncio.Semaphore(max_workers)

        tasks = [
            _download_one_async(sem, idx, sym)
            for idx, _raw, sym in to_fetch
        ]

        # as_completed 模式：完成一个就上报一个进度
        for coro in _asyncio.as_completed(tasks):
            idx, sym, ok = await coro
            with progress_lock:
                if ok:
                    fetched += 1
                else:
                    failed += 1
                completed += 1
                if on_progress:
                    on_progress(completed, total, sym, ok)
            # 每个任务完成后检查是否被取消
            if cancel_event and cancel_event.is_set():
                logger.info(f"prefetch_klines 收到取消信号，已处理 {completed}/{total}，中止剩余任务")
                break

    # 在新的事件循环中运行（兼容可能存在的现有事件循环）
    try:
        loop = _asyncio.get_running_loop()
    except RuntimeError:
        # 没有运行中的事件循环，创建新的
        _asyncio.run(_run_all())
    else:
        # 已有运行中的事件循环（如 uvicorn），用 run_coroutine_threadsafe
        import concurrent.futures as _cf
        future = _asyncio.run_coroutine_threadsafe(_run_all(), loop)
        future.result(timeout=600)  # 10 分钟超时

    return {
        "total": total,
        "cached": cached,
        "fetched": fetched,
        "failed": failed,
        "cancelled": bool(cancel_event and cancel_event.is_set()),
    }


# ==================== 分钟级 K 线（CCI+MACD 选股用） ====================

# 分钟级 K 线内存缓存：{symbol_period: (timestamp, DataFrame)}
_MINUTE_CACHE: dict[str, tuple[float, "pd.DataFrame"]] = {}
_MINUTE_CACHE_TTL = 120  # 分钟数据缓存 2 分钟，兼顾盘中实时性与限速
_MINUTE_CACHE_LOCK = threading.Lock()


# 东财接口支持的分钟档位（用于向上取最接近的官方周期再聚合）
_OFFICIAL_MINUTE_PERIODS = [1, 5, 15, 30, 60]


def _pick_base_period(target: int) -> int:
    """为自定义分钟数挑选最接近的官方支持周期（向下取可用的档位）。"""
    if target in _OFFICIAL_MINUTE_PERIODS:
        return target
    for p in reversed(_OFFICIAL_MINUTE_PERIODS):
        if target >= p:
            return p
    return 1


def _resample_minute(df: "pd.DataFrame", target: int) -> "pd.DataFrame":
    """将小周期分钟 K 线聚合为更大的自定义分钟周期。

    规则：按 target 分钟窗口分组，open=首根开盘，close=末根收盘，
    high/low 取极值，volume/amount 累加；时间取窗口首根时间。

    分组采用「累计有效交易分钟 + 午休断点」方式：相邻两根时间间隔
    超过 target 分钟（休市/午休）时断开计数，避免跨午休错误拼接。
    """
    if target <= 1:
        return df.reset_index(drop=True)
    import numpy as np

    step = int(target)
    df = df.reset_index(drop=True)
    dates = pd.to_datetime(df["date"])

    # 与上一根的时间差（分钟），首根视为一个独立窗口起点
    delta = dates.diff().dt.total_seconds() / 60.0
    # 差 > step 视为跨越休市（午休/隔夜），重置累计；否则累加
    acc = 0
    groups = []
    for d in delta.fillna(step + 1):
        if d > step + 1e-6:
            acc = 0
        groups.append(acc // step)
        acc += d
    group = np.array(groups, dtype="int64")

    agg = df.copy()
    agg["_group"] = group
    agg["_date"] = dates.values

    out = agg.groupby("_group", sort=True).agg(
        date=("_date", "first"),
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        amount=("amount", "sum"),
    ).reset_index(drop=True)
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    return out


def fetch_minute_kline(
    symbol: str,
    period: str = "30",
    limit: int = 200,
    use_cache: bool = True,
) -> "pd.DataFrame":
    """获取分钟级 K 线（东财接口），带内存缓存 + 模拟数据降级。

    支持自定义分钟周期：period 可为任意正整数分钟（如 45/90/240）。
    实现方式：向上挑选最接近的官方周期（1/5/15/30/60）拉数据，
    再用 ``_resample_minute`` 聚合为自定义周期；非官方档位时自动合成。

    Args:
        symbol: 股票代码（可带 sh/sz 前缀，内部会去除）
        period: 分钟周期，任意正整数（如 "30"/"45"/"90"/"240"）
        limit: 返回最近 N 根
        use_cache: 是否使用内存缓存（盘中监控频繁调用时避免限速）

    Returns:
        DataFrame，列：date, open, high, low, close, volume, amount
        列名已标准化为英文；网络失败时返回模拟数据。
    """
    import time as _time

    code = symbol.replace("sh", "").replace("sz", "").replace("SH", "").replace("SZ", "")
    # 解析目标周期
    try:
        target_period = int(period)
    except (TypeError, ValueError):
        target_period = 30
    if target_period < 1:
        target_period = 30
    # 取最接近的官方周期拉取
    base_period = _pick_base_period(target_period)

    cache_key = f"{code}_{base_period}"

    # 1. 命中内存缓存
    if use_cache:
        with _MINUTE_CACHE_LOCK:
            cached = _MINUTE_CACHE.get(cache_key)
            if cached and (_time.time() - cached[0] < _MINUTE_CACHE_TTL):
                return cached[1].tail(limit).copy()

    # 2. 通过数据源抽象层拉取（默认东财，可切换通达信/雪球，失败自动降级）
    import core.datasource as datasource
    df = datasource.fetch_minute_kline(code, base_period, max(limit, 240))

    # 3. 写入缓存（缓存基础周期数据，避免重复合成）
    if use_cache and not df.empty:
        with _MINUTE_CACHE_LOCK:
            _MINUTE_CACHE[cache_key] = (_time.time(), df)

    # 5. 聚合为自定义目标周期（非官方档位时合成）
    if not df.empty and base_period != target_period:
        df = _resample_minute(df, target_period)
        # 重新缓存聚合后的结果，便于重复按目标周期读取
        if use_cache:
            with _MINUTE_CACHE_LOCK:
                _MINUTE_CACHE[f"{code}_{target_period}"] = (_time.time(), df)

    return df.tail(limit).reset_index(drop=True)


def _fetch_minute_from_akshare(code: str, base_period: int, count: int = 240) -> "pd.DataFrame":
    """通过 AKShare（东方财富）拉取分钟K线，失败降级为模拟数据。

    供数据源抽象层的东方财富源复用；返回基础周期的标准列 DataFrame。
    """
    df = pd.DataFrame()
    try:
        import akshare as ak
        raw = ak.stock_zh_a_hist_min_em(symbol=code, period=str(base_period), adjust="")
        if not raw.empty:
            df = raw.rename(columns={
                "时间": "date", "开盘": "open", "最高": "high",
                "最低": "low", "收盘": "close", "成交量": "volume", "成交额": "amount",
            })
            keep = ["date", "open", "high", "low", "close", "volume", "amount"]
            df = df[[c for c in keep if c in df.columns]].copy()
    except Exception as e:
        logger.warning(f"分钟K线 AKShare 拉取失败 symbol={code} period={base_period}: {e}")
    if df.empty:
        df = _generate_mock_minute(code, str(base_period), max(count, 200))
    return df


def _generate_mock_minute(symbol: str, period: str, count: int) -> "pd.DataFrame":
    """生成模拟分钟级 K 线（网络不可用时的 fallback）。确定性随机游走。"""
    import numpy as np
    from datetime import datetime, timedelta

    step = int(period) if period.isdigit() else 30
    now = datetime.now()
    start = now - timedelta(minutes=step * count)
    times = [start + timedelta(minutes=step * i) for i in range(count)]

    seed = int(hashlib.sha256(symbol.encode()).hexdigest(), 16) % 2**32
    np.random.seed(seed)
    base = 10.0 + (seed % 50)
    returns = np.random.normal(0.0002, 0.004, count)
    close_prices = base * np.cumprod(1 + returns)

    np.random.seed(seed + 7)
    opens = close_prices * (1 + np.random.uniform(-0.003, 0.003, count))
    highs = np.maximum(opens, close_prices) * (1 + np.random.uniform(0, 0.004, count))
    lows = np.minimum(opens, close_prices) * (1 - np.random.uniform(0, 0.004, count))
    vols = np.random.randint(100, 8000, count)

    return pd.DataFrame({
        "date": [t.strftime("%Y-%m-%d %H:%M:%S") for t in times],
        "open": opens.round(2),
        "high": highs.round(2),
        "low": lows.round(2),
        "close": close_prices.round(2),
        "volume": vols,
        "amount": (vols * close_prices * 100).round(2),
    })
