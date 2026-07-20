"""市场状态识别模块：判断大盘趋势和市场结构。

用于智能策略根据用户所处的市场环境（牛市/震荡/熊市）自动调整参数。
"""

from __future__ import annotations

import logging
import numpy as np
import pandas as pd

from enum import Enum

logger = logging.getLogger("market_state")


class MarketTrend(Enum):
    """市场趋势枚举。"""
    BULL = "bull"       # 牛市：上涨趋势
    NORMAL = "normal"   # 震荡：横盘整理
    BEAR = "bear"       # 熊市：下跌趋势


class MarketStructure(Enum):
    """市场结构枚举。"""
    CONCENTRATED = "concentrated"   # 资金集中：龙头行情
    ROTATING = "rotating"           # 板块轮动：热点切换
    DISPERSED = "dispersed"         # 资金分散：普涨/普跌


class MarketStateDetector:
    """市场状态检测器。
    
    通过分析大盘指数和个股表现，判断当前市场状态。
    """
    
    def __init__(self):
        pass
    
    def detect_trend(
        self, 
        close_prices: pd.Series,
        bull_threshold: float = 10.0,
        bear_threshold: float = -10.0,
    ) -> str:
        """判断大盘趋势。
        
        基于20日涨跌幅判断市场处于牛市、震荡还是熊市。
        
        Args:
            close_prices: 收盘价序列（按时间排序）
            bull_threshold: 牛市阈值（20日涨幅%，默认10%）
            bear_threshold: 熊市阈值（20日跌幅%，默认-10%）
            
        Returns:
            "bull" / "normal" / "bear"
        """
        if len(close_prices) < 20:
            return MarketTrend.NORMAL.value
        
        # 计算20日涨跌幅
        base = close_prices.iloc[-20]
        if base == 0 or pd.isna(base) or pd.isna(close_prices.iloc[-1]):
            return MarketTrend.NORMAL.value
        change_20d = (close_prices.iloc[-1] / base - 1) * 100
        
        if change_20d > bull_threshold:
            return MarketTrend.BULL.value
        elif change_20d < bear_threshold:
            return MarketTrend.BEAR.value
        else:
            return MarketTrend.NORMAL.value
    
    def detect_trend_multi(
        self,
        close_prices: pd.Series,
        windows: list[int] = [5, 10, 20, 60],
    ) -> dict:
        """多周期趋势判断。
        
        Args:
            close_prices: 收盘价序列
            windows: 观察窗口列表（交易日）
            
        Returns:
            {"5d": "bull", "10d": "normal", ...}
        """
        result = {}
        for window in windows:
            if len(close_prices) >= window:
                base = close_prices.iloc[-window]
                if base == 0 or pd.isna(base) or pd.isna(close_prices.iloc[-1]):
                    result[f"{window}d"] = MarketTrend.NORMAL.value
                    continue
                change = (close_prices.iloc[-1] / base - 1) * 100
                if change > 5:
                    result[f"{window}d"] = MarketTrend.BULL.value
                elif change < -5:
                    result[f"{window}d"] = MarketTrend.BEAR.value
                else:
                    result[f"{window}d"] = MarketTrend.NORMAL.value
            else:
                result[f"{window}d"] = MarketTrend.NORMAL.value
        return result
    
    def detect_structure(
        self,
        stock_returns: pd.DataFrame,
        concentration_threshold: float = 0.6,
        dispersion_threshold: float = 0.4,
    ) -> str:
        """判断市场结构。
        
        基于资金集中度和截面收益离散度判断市场结构。
        
        Args:
            stock_returns: 个股收益率DataFrame，列为股票代码，行为日期
            concentration_threshold: 资金集中度阈值（默认0.6）
            dispersion_threshold: 资金分散度阈值（默认0.4）
            
        Returns:
            "concentrated" / "rotating" / "dispersed"
        """
        if stock_returns.empty:
            return MarketStructure.DISPERSED.value
        
        # 计算最新一天的收益率
        latest_returns = stock_returns.iloc[-1]
        
        # 资金集中度：收益率前20%的股票占全部收益的比例
        sorted_returns = latest_returns.sort_values(ascending=False)
        top_20_pct = int(len(sorted_returns) * 0.2)
        top_gain = sorted_returns.iloc[:top_20_pct].sum()
        total_gain = sorted_returns.sum()
        
        concentration = top_gain / total_gain if total_gain != 0 else 0
        
        # 截面收益离散度：收益率的标准差
        dispersion = latest_returns.std()
        
        if concentration > concentration_threshold:
            return MarketStructure.CONCENTRATED.value
        elif dispersion < dispersion_threshold:
            return MarketStructure.DISPERSED.value
        else:
            return MarketStructure.ROTATING.value
    
    def detect_volatility(self, close_prices: pd.Series, window: int = 20) -> str:
        """判断市场波动率状态。
        
        Args:
            close_prices: 收盘价序列
            window: 计算窗口
            
        Returns:
            "high" / "normal" / "low"
        """
        if len(close_prices) < window:
            return "normal"
        
        # 计算收益率
        returns = close_prices.pct_change().dropna()
        
        # 计算波动率（年化）
        volatility = returns.tail(window).std() * np.sqrt(252)
        
        if volatility > 0.4:  # 高波动：年化40%以上
            return "high"
        elif volatility < 0.15:  # 低波动：年化15%以下
            return "low"
        else:
            return "normal"
    
    def get_market_state(
        self,
        index_prices: pd.Series,
        stock_returns: pd.DataFrame = None,
    ) -> dict:
        """获取完整市场状态。
        
        Args:
            index_prices: 大盘指数收盘价
            stock_returns: 个股收益率（可选）
            
        Returns:
            {
                "trend": "bull",
                "trend_20d": 10.5,  # 20日涨幅%
                "volatility": "high",
                "structure": "concentrated",  # 仅当stock_returns提供时
            }
        """
        result = {}
        
        # 趋势判断
        if len(index_prices) >= 20:
            result["trend"] = self.detect_trend(index_prices)
            result["trend_20d"] = round(
                (index_prices.iloc[-1] / index_prices.iloc[-20] - 1) * 100, 2
            )
        
        # 多周期趋势
        multi_trend = self.detect_trend_multi(index_prices)
        result["multi_trend"] = multi_trend
        
        # 波动率
        result["volatility"] = self.detect_volatility(index_prices)
        
        # 市场结构（需要个股数据）
        if stock_returns is not None and not stock_returns.empty:
            result["structure"] = self.detect_structure(stock_returns)
        
        return result


def get_index_data(symbol: str = "000001") -> pd.Series:
    """获取大盘指数数据。
    
    Args:
        symbol: 指数代码（000001=上证指数，399001=深证成指）
        
    Returns:
        收盘价序列
    """
    try:
        import akshare as ak
        
        # 获取指数历史数据
        df = ak.stock_zh_index_daily(symbol=symbol)
        
        if not df.empty:
            df["date"] = pd.to_datetime(df["日期"])
            df = df.sort_values("date")
            return df.set_index("date")["收盘"]
    except Exception as e:
        logger.warning(f"获取指数数据失败: {e}")
    
    # 返回模拟数据
    dates = pd.date_range(end=pd.Timestamp.now(), periods=252, freq="B")
    return pd.Series(np.random.normal(0, 1, len(dates)).cumsum() + 3000, index=dates)


if __name__ == "__main__":
    # 测试
    detector = MarketStateDetector()
    
    # 模拟数据
    dates = pd.date_range(end=pd.Timestamp.now(), periods=252, freq="B")
    
    # 牛市场景
    bull_prices = pd.Series(np.linspace(3000, 4000, len(dates)) + np.random.normal(0, 50, len(dates)), index=dates)
    print(f"牛市判断: {detector.detect_trend(bull_prices)}")
    
    # 熊市场景
    bear_prices = pd.Series(np.linspace(4000, 3000, len(dates)) + np.random.normal(0, 50, len(dates)), index=dates)
    print(f"熊市判断: {detector.detect_trend(bear_prices)}")
    
    # 震荡场景
    normal_prices = pd.Series(3000 + np.random.normal(0, 100, len(dates)).cumsum(), index=dates)
    print(f"震荡判断: {detector.detect_trend(normal_prices)}")
    
    # 完整状态
    state = detector.get_market_state(bull_prices)
    print(f"市场状态: {state}")
