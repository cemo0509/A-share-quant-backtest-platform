"""股票搜索相关 API 路由（计划书要求）。"""
from __future__ import annotations

import logging
import numpy as np
import akshare as ak
from fastapi import APIRouter, HTTPException, Query

from core.market_state import MarketStateDetector, get_index_data
from core.net_errors import is_network_error, degraded_payload
from data.stock_names import search_stocks as search_stocks_cache

router = APIRouter()
logger = logging.getLogger("stocks")

# 市场状态检测器（全局单例）
_market_detector = MarketStateDetector()


@router.get("/search")
def search_stocks(keyword: str = Query(..., description="搜索关键词（股票名称或代码）")):
    """搜索A股股票（计划书要求：/api/stocks/search?keyword=茅台）。

    v3.0 升级：优先使用本地缓存，失败时降级为 akshare 在线搜索。
    """
    try:
        # 1. 先尝试本地缓存搜索（速度快，离线可用）
        local_results = search_stocks_cache(keyword, limit=20)
        if local_results:
            return {"status": "ok", "data": local_results}

        # 2. 缓存无结果时，尝试 akshare 在线搜索
        try:
            df = ak.stock_info_a_code_name()
            result = df[
                df['code'].str.contains(keyword, na=False) |
                df['name'].str.contains(keyword, na=False)
            ].head(20)

            data = [
                {
                    "symbol": f"sh{row['code']}" if row['code'].startswith(('60', '68', '9')) else f"sz{row['code']}",
                    "code": row['code'],
                    "name": row['name'],
                    "sector": row.get('industry', '未知') if 'industry' in row else '未知',
                }
                for _, row in result.iterrows()
            ]
            return {"status": "ok", "data": data}
        except Exception as e:
            # akshare 也失败，返回兜底数据
            logger.warning(f"AKShare 在线搜索失败: {e}，使用兜底数据")
            return {
                "status": "ok",
                "data": [
                    {"symbol": "sh600000", "code": "600000", "name": "浦发银行", "sector": "银行"},
                    {"symbol": "sh600016", "code": "600016", "name": "民生银行", "sector": "银行"},
                    {"symbol": "sh601398", "code": "601398", "name": "工商银行", "sector": "银行"},
                    {"symbol": "sz000001", "code": "000001", "name": "平安银行", "sector": "银行"},
                    {"symbol": "sz000858", "code": "000858", "name": "五粮液", "sector": "白酒"},
                ]
            }
    except Exception as e:
        # 网络/数据源不可用是常态（弱网、代理、限流），降级返回空结果而非 500
        if is_network_error(e):
            return degraded_payload("搜索服务", e, empty=[])
        logger.error(f"股票搜索异常: {e}")
        raise HTTPException(status_code=500, detail="搜索服务暂时不可用")


@router.get("/kline")
def get_kline_data(
    symbol: str = Query(..., description="股票代码（如 sh600519）"),
    start_date: str = Query(None, description="开始日期（YYYYMMDD）"),
    end_date: str = Query(None, description="结束日期（YYYYMMDD）"),
    adjust: str = Query("qfq", description="复权类型（qfq前复权, hfq后复权, 空为不复权）"),
    period: str = Query("daily", description="K线周期: daily/weekly/monthly/5min/15min/30min/60min"),
    limit: int = Query(200, description="返回最近N条"),
):
    """获取K线数据（v3.0 升级：支持多周期，带 Parquet 缓存+模拟数据降级）。"""
    try:
        import akshare as ak
        import pandas as pd
        from datetime import datetime

        # 转换symbol格式（sh600519 -> 600519）
        code = symbol.replace("sh", "").replace("sz", "")

        # 默认结束日期为今天
        default_end_date = datetime.now().strftime("%Y%m%d")

        # 分钟级数据使用不同接口（不支持缓存，原样保留）
        if period in ("5min", "15min", "30min", "60min"):
            try:
                period_map = {"5min": "5", "15min": "15", "30min": "30", "60min": "60"}
                df = ak.stock_zh_a_hist_min_em(
                    symbol=code, period=period_map[period], adjust=""
                )
                if not df.empty:
                    df = df.rename(columns={
                        "时间": "date", "开盘": "open", "最高": "high",
                        "最低": "low", "收盘": "close", "成交量": "volume", "成交额": "amount",
                    })
                    df = df.tail(limit)
            except Exception:
                df = pd.DataFrame()
        else:
            # 日线/周线/月线：使用 data_loader.fetch_kline() 带 Parquet 缓存 + 模拟数据降级
            from core.data_loader import fetch_kline

            ak_period = {"daily": "daily", "weekly": "weekly", "monthly": "monthly"}.get(period, "daily")
            df = fetch_kline(
                symbol=code,
                start_date=start_date or "20200101",
                end_date=end_date or default_end_date,
                period=ak_period,
                adjust=adjust,
                use_cache=True,
            )
            if not df.empty:
                df = df.tail(limit)

        # 转换数据格式
        data = []
        for _, row in df.iterrows():
            item = {
                "date": str(row.get("date", "")),
                "open": float(row.get("open", 0) or 0),
                "high": float(row.get("high", 0) or 0),
                "low": float(row.get("low", 0) or 0),
                "close": float(row.get("close", 0) or 0),
                "volume": int(float(row.get("volume", 0) or 0)),
                "amount": float(row.get("amount", row.get("amount", 0)) or 0),
            }
            data.append(item)

        return {"status": "ok", "data": data}
    except Exception as e:
        if is_network_error(e):
            return degraded_payload("K线数据", e)
        logger.error(f"K线数据获取异常: {e}")
        raise HTTPException(status_code=500, detail="K线数据获取失败，请稍后重试")


@router.get("/intraday")
def get_intraday_data(
    symbol: str = Query(..., description="股票代码（如 sz002558）"),
):
    """获取分时数据（v3.0 新增）。

    返回当日5分钟K线，用于绘制分时图。
    """
    try:
        import akshare as ak
        import pandas as pd

        code = symbol.replace("sh", "").replace("sz", "")

        df = ak.stock_zh_a_hist_min_em(symbol=code, period="5", adjust="")

        if df.empty:
            return {"status": "ok", "data": []}

        # 只取当日数据
        from datetime import datetime
        today_str = datetime.now().strftime("%Y-%m-%d")
        df = df[df["时间"].astype(str).str.startswith(today_str)]

        data = []
        for _, row in df.iterrows():
            vol = int(float(row.get("成交量", 0) or 0))
            amt = float(row.get("成交额", 0) or 0)
            item = {
                "time": str(row["时间"]),
                "price": float(row.get("收盘", 0) or 0),
                "volume": vol,
                "avg_price": round(amt / (vol * 100), 2) if vol > 0 else 0,
            }
            data.append(item)

        return {"status": "ok", "data": data}
    except Exception as e:
        # 弱网/代理/非交易时段下 akshare 常抛连接类异常，不应以 500 刷红前端，
        # 降级为空数据并带 degraded 标记，由前端友好提示。
        if is_network_error(e):
            return degraded_payload("分时数据", e)
        logger.error(f"分时数据获取异常: {e}")
        raise HTTPException(status_code=500, detail="分时数据获取失败，请稍后重试")


@router.get("/indicators")
def get_indicators(
    symbol: str = Query(..., description="股票代码（如 sz002558）"),
    start_date: str = Query(None, description="开始日期"),
    end_date: str = Query(None, description="结束日期"),
):
    """获取技术指标数据（v3.0 新增）。

    返回 MACD/KDJ/RSI/BOLL/WR/OBV/BIAS/CCI 等所有指标。
    使用 data_loader.fetch_kline() 带 Parquet 缓存 + 模拟数据降级。
    """
    try:
        import pandas as pd
        from datetime import datetime
        from core.indicators import calc_all_indicators
        from core.data_loader import fetch_kline

        code = symbol.replace("sh", "").replace("sz", "")
        default_end_date = datetime.now().strftime("%Y%m%d")

        # 使用带缓存的 fetch_kline
        df = fetch_kline(
            symbol=code,
            start_date=start_date or "20250101",
            end_date=end_date or default_end_date,
            period="daily",
            adjust="qfq",
            use_cache=True,
        )

        if df.empty:
            return {"status": "ok", "data": {"dates": []}}

        # 计算所有指标
        indicators = calc_all_indicators(df)
        indicators["dates"] = [str(d) for d in df["date"].tolist()]

        return {"status": "ok", "data": indicators}
    except Exception as e:
        if is_network_error(e):
            return degraded_payload("技术指标", e, empty={"dates": []})
        logger.error(f"技术指标计算异常: {e}")
        raise HTTPException(status_code=500, detail="技术指标计算失败，请稍后重试")


@router.get("/signals")
def get_strategy_signals(
    symbol: str = Query(..., description="股票代码（如 sh600519）"),
    strategy: str = Query("macd", description="策略类型: macd, kdj, rsi, ma_cross, bollinger"),
    start_date: str = Query(None, description="开始日期"),
    end_date: str = Query(None, description="结束日期"),
):
    """获取策略买卖信号点（v3.0 新增：K线图叠加策略信号）。

    基于技术指标直接计算买卖点，不依赖 Backtrader 回测引擎。
    返回信号列表，每个信号包含日期、类型(buy/sell)、价格。
    使用 data_loader.fetch_kline() 带 Parquet 缓存 + 模拟数据降级。
    """
    try:
        import pandas as pd
        from datetime import datetime
        from core.data_loader import fetch_kline

        code = symbol.replace("sh", "").replace("sz", "")
        default_end_date = datetime.now().strftime("%Y%m%d")

        # 使用带缓存的 fetch_kline
        df = fetch_kline(
            symbol=code,
            start_date=start_date or "20230101",
            end_date=end_date or default_end_date,
            period="daily",
            adjust="qfq",
            use_cache=True,
        )

        if df.empty:
            return {"status": "ok", "data": []}

        closes = df["close"].values
        highs = df["high"].values
        lows = df["low"].values
        volumes = df["volume"].values
        dates = df["date"].astype(str).tolist()

        signals = _compute_signals(closes, highs, lows, volumes, dates, strategy)
        return {"status": "ok", "data": signals}
    except Exception as e:
        if is_network_error(e):
            return degraded_payload("策略信号", e)
        logger.error(f"策略信号计算异常: {e}")
        raise HTTPException(status_code=500, detail="策略信号计算失败，请稍后重试")


def _compute_signals(
    closes, highs, lows, volumes, dates, strategy: str
) -> list[dict]:
    """基于技术指标计算买卖信号点。

    复用 core/indicators.py 中的指标计算函数，消除代码重复。
    """
    from core.indicators import calc_macd, calc_kdj, calc_rsi, calc_ma, calc_boll

    signals = []
    n = len(closes)

    if n < 2:
        return signals

    # 构造临时 DataFrame 供 calc_* 函数使用
    import pandas as pd
    df = pd.DataFrame({
        "close": closes,
        "high": highs,
        "low": lows,
        "volume": volumes,
    })

    if strategy == "macd":
        # MACD: DIF 上穿 DEA 买入，下穿 DEA 卖出
        macd = calc_macd(df["close"])
        dif = np.array(macd["dif"])
        dea = np.array(macd["dea"])
        for i in range(1, n):
            if np.isnan(dif[i]) or np.isnan(dea[i]) or np.isnan(dif[i-1]) or np.isnan(dea[i-1]):
                continue
            if dif[i] > dea[i] and dif[i-1] <= dea[i-1]:
                signals.append({"date": str(dates[i]), "type": "buy", "price": round(float(closes[i]), 2)})
            elif dif[i] < dea[i] and dif[i-1] >= dea[i-1]:
                signals.append({"date": str(dates[i]), "type": "sell", "price": round(float(closes[i]), 2)})

    elif strategy == "kdj":
        # KDJ: K上穿D买入，K下穿D卖出
        kdj = calc_kdj(df["high"], df["low"], df["close"])
        k = np.array(kdj["k"])
        d = np.array(kdj["d"])
        for i in range(1, n):
            if np.isnan(k[i]) or np.isnan(d[i]) or np.isnan(k[i-1]) or np.isnan(d[i-1]):
                continue
            if k[i] > d[i] and k[i-1] <= d[i-1]:
                signals.append({"date": str(dates[i]), "type": "buy", "price": round(float(closes[i]), 2)})
            elif k[i] < d[i] and k[i-1] >= d[i-1]:
                signals.append({"date": str(dates[i]), "type": "sell", "price": round(float(closes[i]), 2)})

    elif strategy == "rsi":
        # RSI: RSI < 30 超卖买入, RSI > 70 超买卖出
        rsi_series = calc_rsi(df["close"], 14)
        rsi = rsi_series.values
        for i in range(1, n):
            if np.isnan(rsi[i]) or np.isnan(rsi[i-1]):
                continue
            if rsi[i-1] >= 30 and rsi[i] < 30:
                signals.append({"date": str(dates[i]), "type": "buy", "price": round(float(closes[i]), 2)})
            elif rsi[i-1] <= 70 and rsi[i] > 70:
                signals.append({"date": str(dates[i]), "type": "sell", "price": round(float(closes[i]), 2)})

    elif strategy == "ma_cross":
        # 双均线: MA5 上穿 MA20 买入，下穿卖出
        ma = calc_ma(df["close"], [5, 20])
        ma5 = np.array(ma["ma5"])
        ma20 = np.array(ma["ma20"])
        for i in range(1, n):
            if np.isnan(ma5[i]) or np.isnan(ma20[i]) or np.isnan(ma5[i-1]) or np.isnan(ma20[i-1]):
                continue
            if ma5[i] > ma20[i] and ma5[i-1] <= ma20[i-1]:
                signals.append({"date": str(dates[i]), "type": "buy", "price": round(float(closes[i]), 2)})
            elif ma5[i] < ma20[i] and ma5[i-1] >= ma20[i-1]:
                signals.append({"date": str(dates[i]), "type": "sell", "price": round(float(closes[i]), 2)})

    elif strategy == "bollinger":
        # 布林带: 价格跌破下轨买入，突破上轨卖出
        boll = calc_boll(df["close"])
        upper = np.array(boll["upper"])
        lower = np.array(boll["lower"])
        for i in range(1, n):
            if np.isnan(lower[i]) or np.isnan(lower[i-1]) or np.isnan(upper[i]) or np.isnan(upper[i-1]):
                continue
            if closes[i-1] >= lower[i-1] and closes[i] < lower[i]:
                signals.append({"date": str(dates[i]), "type": "buy", "price": round(float(closes[i]), 2)})
            elif closes[i-1] <= upper[i-1] and closes[i] > upper[i]:
                signals.append({"date": str(dates[i]), "type": "sell", "price": round(float(closes[i]), 2)})

    return signals


# ==================== 市场状态API ====================

@router.get("/market/state")
def get_market_state(
    symbol: str = Query("000001", description="指数代码（000001=上证指数）"),
):
    """获取市场状态（计划书要求：GET /api/market/state）。
    
    返回当前市场状态（bull/normal/bear）、波动率、多周期趋势等。
    """
    try:
        # 获取指数数据（模块级函数，非实例方法）
        index_data = get_index_data(symbol)
        
        if index_data.empty:
            return {
                "status": "ok",
                "data": {
                    "trend": "normal",
                    "trend_20d": 0.0,
                    "volatility": "normal",
                    "multi_trend": {},
                    "message": "指数数据不可用，返回默认状态",
                }
            }
        
        # 获取市场状态
        state = _market_detector.get_market_state(index_data)
        
        return {
            "status": "ok",
            "data": state,
        }
    except Exception as e:
        if is_network_error(e):
            return degraded_payload("市场状态", e, empty={
                "trend": "normal",
                "trend_20d": 0.0,
                "volatility": "normal",
                "multi_trend": {},
            })
        logger.error(f"市场状态获取异常: {e}")
        raise HTTPException(status_code=500, detail="市场状态获取失败，请稍后重试")

