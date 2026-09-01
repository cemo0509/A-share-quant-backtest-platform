"""A 股交易规则金标准（P0-7 涨跌停/停牌 + Q-07 T+1/禁止做空）。

核心结论（实测验证）：
- 默认 Market 单次日开盘成交天然满足 T+1，防线对预置策略零干预
- Close 单当日成交可卖出当日买入份额 → 必须被 T+1 冻结拦截
- 无持仓 sell() 会开出负持仓（做空）→ 必须被拦截
"""
import backtrader as bt
import numpy as np
import pandas as pd
import pytest

import core.data_loader as dl
from conftest import cleanup_cache, find_t1_violations, run

from core.engine import _PositionSizerAdapter
from core.strategies.registry import get_strategy


class TestLimitRatio:
    """板块差异化涨跌停幅度：创业板/科创板 ±20%，其余 ±10%。"""

    @pytest.mark.parametrize("symbol,expect", [
        ("000001", 0.10), ("600519", 0.10), ("sh600519", 0.10),
        ("300750", 0.20), ("301001", 0.20), ("688981", 0.20),
    ])
    def test_board_limit_ratio(self, symbol, expect):
        assert _PositionSizerAdapter._limit_ratio(symbol) == expect


def _make_limit_df():
    """25% 交易日涨停 + 1 个停牌日的构造数据。"""
    n = 300
    t = np.arange(n)
    rng = np.random.default_rng(3)
    base = 10 + 2 * np.sin(2 * np.pi * t / 50) + 0.01 * t
    close = []
    for i in range(n):
        c = base[i] + rng.normal(0, 0.05)
        if i > 0 and rng.random() < 0.25:
            c = round(close[-1] * 1.10, 2)
        close.append(round(max(c, 1.0), 2))
    close = np.array(close)
    volume = np.full(n, 1e6)
    volume[150] = 0  # 停牌日
    dates = pd.bdate_range("2024-01-01", periods=n)
    df = pd.DataFrame({
        "date": dates, "open": close * 0.99, "high": close * 1.001,
        "low": close * 0.999, "close": close, "volume": volume,
        "amount": close * volume,
    })
    limit_up_dates = set()
    for i in range(1, n):
        if close[i] >= round(close[i - 1] * 1.10, 2) - 0.005:
            limit_up_dates.add(str(dates[i].date()))
    return df, limit_up_dates, str(dates[150].date())


@pytest.fixture
def limit_data(monkeypatch):
    df, limit_up_dates, halt_date = _make_limit_df()
    sym = "__LIM__"
    monkeypatch.setattr(dl, "_fetch_from_akshare", lambda *a: df)
    yield sym, limit_up_dates, halt_date
    cleanup_cache(sym)


class TestLimitUpDown:
    def test_no_buy_on_limit_up_day(self, limit_data):
        """涨停日买单排不上队：开启约束后涨停日不得有买入成交。

        不建模时收益虚高约 5 倍（专项实测 181% vs 37%）。
        """
        sym, limit_up_dates, _ = limit_data
        assert limit_up_dates, "构造数据必须包含涨停日，否则测试失效"
        res = run(symbol=sym, strategy_cls=get_strategy("macd").strategy_cls,
                  start_date="20240101", end_date="20241231")
        bad = [t for t in res["trades"]
               if t["action"] == "买入" and t["date"] in limit_up_dates]
        assert not bad, f"涨停日买入 {len(bad)} 次: {bad[:2]}"

    def test_no_trade_on_halt_day(self, limit_data):
        """停牌日（成交量为 0）不得有任何成交。"""
        sym, _, halt_date = limit_data
        res = run(symbol=sym, strategy_cls=get_strategy("macd").strategy_cls,
                  start_date="20240101", end_date="20241231")
        on_halt = [t for t in res["trades"] if t["date"] == halt_date]
        assert not on_halt, f"停牌日成交: {on_halt}"


class TestT1AndShortGuard:
    def test_close_order_same_day_roundtrip_blocked(self, wave):
        """Close 单当日反手：当日买入份额当日不可卖，全部拦截。"""
        sym, _ = wave

        class CheatCloseStrategy(bt.Strategy):
            def __init__(self):
                self.order = None
                self.day = 0

            def notify_order(self, order):
                if order.status in (order.Completed, order.Canceled,
                                    order.Margin, order.Rejected):
                    self.order = None

            def next(self):
                self.day += 1
                if self.order:
                    return
                if not self.position:
                    self.order = self.buy(exectype=bt.Order.Close)
                elif self.day % 7 == 0:
                    # 同日收盘加仓 + 全仓卖出（含当日新买份额）→ 违规
                    self.buy(exectype=bt.Order.Close, size=100)
                    self.order = self.sell(exectype=bt.Order.Close,
                                           size=self.position.size + 100)
                elif self.day % 11 == 0:
                    self.order = self.sell(exectype=bt.Order.Close,
                                           size=self.position.size)

        res = run(symbol=sym, strategy_cls=CheatCloseStrategy)
        assert not find_t1_violations(res["trades"])
        cons = res["constraints"]
        assert cons["t1_sell_blocked"] > 0, "防线应拦截到 T+1 违规"

    def test_short_selling_blocked(self, wave):
        """无持仓卖出（做空）必须被拦截，不得出现负持仓成交。"""
        sym, _ = wave

        class ShortStrategy(bt.Strategy):
            def __init__(self):
                self.order = None
                self.day = 0

            def notify_order(self, order):
                if order.status in (order.Completed, order.Canceled,
                                    order.Margin, order.Rejected):
                    self.order = None

            def next(self):
                self.day += 1
                if self.order:
                    return
                if self.day == 10:
                    self.order = self.sell(size=1000)  # 无持仓 → 做空
                elif self.day == 50:
                    self.order = self.buy(size=1000)

        res = run(symbol=sym, strategy_cls=ShortStrategy)
        sells = [t for t in res["trades"] if t["action"] == "卖出"]
        assert not sells, f"做空成交: {sells}"
        assert res["constraints"]["short_sell_blocked"] > 0
