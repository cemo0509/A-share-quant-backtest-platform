"""Backtrader 引擎封装层：统一回测入口，借鉴 Backtrader 的事件驱动架构。

提供 run_backtest() 函数，接收策略 key、股票代码、日期范围、参数，
返回回测结果（指标 + 资金曲线 + 交易明细）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import backtrader as bt
import pandas as pd

import logging

from core.data_loader import fetch_kline
from core.strategies.registry import get_strategy
from core.analyzers import compute_metrics, BacktestMetrics
from core.utils import safe_convert
from core.position_sizer import calc_atr_position, calc_volatility_position
from core.benchmark import compute_benchmarks

logger = logging.getLogger("engine")


def _apply_astock_rules(strategy_cls):
    """动态子类：A 股交易规则防线（Q-07 T+1 冻结 + 禁止做空）。

    实测结论（_test_t1.py Part A）：
    - 默认 Market 单**次日开盘成交**，卖出 size 又基于下单时持仓，
      15 个预置策略**天然满足 T+1**——防线对它们零干预、零误伤。
    - 但引擎**允许做空**（无持仓 `sell()` 直接开出负持仓，已实测复现），
      且 Close 单 / cheat 模式**当日成交**，可卖出当日买入的份额。
      这两条是真实缺口，必须在本层兜底（自定义代码回测同样经过这里）。

    规则实现：
    - 做空拦截：卖出数量裁剪到当前持仓；无持仓卖出直接拒绝。
    - T+1 冻结：仅对**当日成交**的单据（Close 单 / broker 开了 cheat-on-close）
      生效——当日买入的份额当日不可卖，超出部分裁剪。
      Market 单次日成交天然合规，不检查（避免误伤合法卖单）。
    """
    class _AStockGuarded(strategy_cls):
        def __init__(self):
            super().__init__()
            self._astock_buy_date = None
            self._astock_buy_size = 0.0
            self.astock_t1_blocked = 0      # T+1 冻结拦截/裁剪次数
            self.astock_short_blocked = 0   # 做空拦截/裁剪次数

        def notify_order(self, order):
            if order.status == order.Completed and order.isbuy():
                d = self.datas[0].datetime.date(0)
                if self._astock_buy_date != d:
                    self._astock_buy_date = d
                    self._astock_buy_size = 0.0
                self._astock_buy_size += abs(order.executed.size)
            # 必须调 super：BaseStrategy 在此清理 self.order，
            # 不调会让策略的「有单在手就不再下单」守卫永久卡死。
            super().notify_order(order)

        def sell(self, data=None, size=None, **kwargs):
            data = data if data is not None else self.datas[0]
            pos = self.getposition(data).size
            exectype = kwargs.get("exectype")
            same_day = (
                exectype == bt.Order.Close
                or bool(getattr(self.broker.p, "coc", False))
            )
            frozen = 0.0
            if same_day and self._astock_buy_date == data.datetime.date(0):
                frozen = self._astock_buy_size
            sellable = max(pos - frozen, 0.0)
            # size=None 时策略意图是全仓卖出（sizer 也是返回全仓），显式裁剪等价
            requested = pos if size is None else size
            req = min(requested, sellable)
            if req <= 0:
                if pos > 0:
                    self.astock_t1_blocked += 1
                    logger.debug(f"T+1 拦截：当日买入 {frozen:.0f} 股冻结，卖出被拒绝")
                else:
                    self.astock_short_blocked += 1
                    logger.debug("做空拦截：无持仓卖出被拒绝（A 股股票禁止做空）")
                return None
            if req < requested:
                if same_day and frozen > 0:
                    self.astock_t1_blocked += 1
                else:
                    self.astock_short_blocked += 1
            return super().sell(data=data, size=req, **kwargs)

    _AStockGuarded.__name__ = strategy_cls.__name__
    _AStockGuarded.__qualname__ = strategy_cls.__qualname__
    return _AStockGuarded


@dataclass
class BacktestResult:
    """完整回测结果。"""
    metrics: dict
    equity_curve: list[dict]      # [{date, value}]
    trades: list[dict]            # [{date, action, price, size, pnl}]
    kline: list[dict]             # 回测期间的K线数据

    def to_dict(self) -> dict:
        """安全地转换为字典，处理 numpy/非序列化类型。"""
        return {
            "metrics": safe_convert(self.metrics),
            "equity_curve": safe_convert(self.equity_curve),
            "trades": safe_convert(self.trades),
            "kline": safe_convert(self.kline),
        }


def run_backtest(
    strategy_key: Optional[str] = None,
    symbol: str = "",
    start_date: str = "",
    end_date: str = "",
    params: Optional[dict] = None,
    cash: float = 1_000_000,
    commission: float = 0.0003,
    slippage: float = 0.001,
    period: str = "daily",
    adjust: str = "qfq",
    position_sizing: str = "allin",
    position_percent: float = 95.0,
    max_position: float = 0.95,
    risk_percent: float = 0.01,
    atr_multiplier: float = 2.0,
    target_volatility: float = 0.15,
    strategy_cls: Optional[Any] = None,
) -> dict:
    """执行回测。

    Args:
        strategy_key: 策略 key，如 "dual_ma"（与 strategy_cls 二选一）
        strategy_cls: 策略类（直接传入，用于自定义代码回测）
        symbol: 股票代码，如 "000001"
        start_date: "YYYYMMDD"
        end_date: "YYYYMMDD"
        params: 策略参数 dict
        cash: 初始资金
        commission: 佣金费率（单边）
        slippage: 滑点
        period: K线周期
        adjust: 复权方式 "qfq"前复权 / "hfq"后复权 / ""不复权
        position_sizing: 仓位管理模式
            - "allin"      ：满仓（用 position_percent% 资金，默认 95%）
            - "fixed"      ：固定比例（用 position_percent% 资金）
            - "atr"        ：ATR 风险仓位（单笔风险不超过 risk_percent）
            - "volatility" ：目标波动率仓位（波动越大仓位越小）
        position_percent: allin/fixed/volatility 的基础仓位百分比
        max_position: 仓位上限（0-1）
        risk_percent: atr 模式的单笔风险比例（默认 1%）
        atr_multiplier: atr 模式的 ATR 乘数（默认 2 倍）
        target_volatility: volatility 模式的目标年化波动率（默认 0.15）

    Returns:
        BacktestResult.to_dict()
    """
    params = params or {}
    if strategy_cls is None:
        if not strategy_key:
            raise ValueError("必须提供 strategy_key 或 strategy_cls")
        strat_info = get_strategy(strategy_key)
        strategy_cls = strat_info.strategy_cls

    # 统一处理 symbol 前缀：去除 sh/sz 前缀（data_loader 需要纯数字代码）
    symbol = str(symbol).lower().replace('sh', '').replace('sz', '').strip()

    # 1. 获取数据（复权方式透传，此前恒为 qfq，用户无法对比不同复权口径）
    df = fetch_kline(symbol, start_date, end_date, period=period, adjust=adjust)
    if df.empty:
        raise ValueError("无法获取该股票在指定日期范围内的行情数据，请检查股票代码和日期")

    # 2. 构建 Backtrader 数据源
    #    name=symbol 让 Sizer 能识别板块（创业板/科创板涨跌停幅度不同）
    data = bt.feeds.PandasData(
        dataname=df,
        datetime="date",
        open="open",
        high="high",
        low="low",
        close="close",
        volume="volume",
        openinterest=-1,
        name=symbol,
    )

    # 3. 初始化引擎
    cerebro = bt.Cerebro()
    cerebro.adddata(data)
    cerebro.broker.setcash(cash)
    # A 股完整交易成本（见 _AStockCommissionInfo）：
    # 佣金双边 + 最低 5 元、印花税 0.05% 仅卖出、过户费 0.001% 双边。
    # 只设 commission 会漏掉印花税（单边卖出征收，是最重的一项），
    # 使高换手策略的年化收益系统性虚高。
    cerebro.broker.addcommissioninfo(
        _AStockCommissionInfo(commission=commission), symbol
    )
    # 滑点：固定百分比
    cerebro.broker.set_slippage_perc(slippage)

    # 仓位管理：支持多种模式（默认 allin 保持与历史行为一致）。
    # 若不设置 sizer，backtrader 默认每次只交易 1 股，导致回测资金几乎不动、
    # 收益率恒为 0、交易金额异常（这正是“交易情况不对”的根因）。
    cerebro.addsizer(
        _PositionSizerAdapter,
        mode=position_sizing,
        percent=position_percent,
        max_position=max_position,
        risk_percent=risk_percent,
        atr_multiplier=atr_multiplier,
        target_volatility=target_volatility,
        slippage=slippage,
    )

    # 4. 添加策略（注入参数）
    bt_params = {**params}
    
    # 过滤掉策略类没有定义的参数
    # Backtrader 使用元类系统，strategy_cls.params 是一个 AutoInfoClass
    # 我们需要正确获取策略类定义的参数列表
    if hasattr(strategy_cls, 'params'):
        params_attr = strategy_cls.params
        
        # 检查 params 是否是 AutoInfoClass（有 _getkeys 方法）
        if hasattr(params_attr, '_getkeys'):
            # AutoInfoClass: 使用 _getkeys() 获取参数名
            valid_param_names = list(params_attr._getkeys())
        elif isinstance(params_attr, (tuple, list)):
            # 原始元组格式: (("param1", default1), ("param2", default2), ...)
            valid_param_names = [p[0] for p in params_attr if isinstance(p, (tuple, list))]
        else:
            # 未知格式，不过滤
            valid_param_names = None
        
        if valid_param_names is not None:
            filtered_params = {k: v for k, v in bt_params.items() if k in valid_param_names}
            if len(filtered_params) != len(bt_params):
                removed = set(bt_params.keys()) - set(filtered_params.keys())
                logger.debug(f"Filtered unused params: {removed}")
            bt_params = filtered_params
    
    logger.debug(f"Running backtest: strategy={strategy_cls.__name__}, params={list(bt_params.keys())}")
    # Q-07：包装 A 股交易规则防线（T+1 冻结 + 禁止做空），对预置策略零行为变化
    cerebro.addstrategy(_apply_astock_rules(strategy_cls), **bt_params)

    # 5. 添加分析器
    # 夏普必须年化：backtrader 的 SharpeRatio 默认 annualize=False，
    # 日频数据下返回的是「日夏普」，只有真实年化夏普的 1/√252 ≈ 1/15.87。
    # 未年化会让所有策略的夏普被系统性低估，据此排序的参数优化选出的是噪声。
    cerebro.addanalyzer(
        bt.analyzers.SharpeRatio,
        _name="sharpe",
        timeframe=bt.TimeFrame.Days,
        riskfreerate=0.0,
        annualize=True,
        convertrate=True,
    )
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    cerebro.addanalyzer(bt.analyzers.AnnualReturn, _name="annualreturn")
    cerebro.addanalyzer(bt.analyzers.TimeReturn, _name="timereturn", timeframe=bt.TimeFrame.Days)

    # 用于记录资金曲线和交易明细的自定义分析器
    cerebro.addanalyzer(_EquityCurveAnalyzer, _name="equitycurve")
    cerebro.addanalyzer(_TradeRecordAnalyzer, _name="traderecord")

    # 6. 运行回测
    start_cash = cerebro.broker.getvalue()
    try:
        result = cerebro.run()
    except ZeroDivisionError as e:
        # backtrader 的 RSI 等指标在区间内出现「连续单边行情」时会除零崩溃
        # （平均跌幅/涨幅为 0）。这里转成明确的中文提示，
        # 避免以裸 ZeroDivisionError 冒泡成 500、用户完全无从判断原因。
        raise ValueError(
            "指标计算失败：所选区间内可能存在连续单边行情（如持续上涨/下跌），"
            "导致 RSI 等技术指标无法计算。请更换股票或调整回测区间后重试。"
        ) from e
    end_cash = cerebro.broker.getvalue()

    strat = result[0]

    # 8. 提取资金曲线和交易明细
    equity_curve = []
    if hasattr(strat.analyzers, "equitycurve"):
        equity_curve = strat.analyzers.equitycurve.equity_curve
    trades = []
    if hasattr(strat.analyzers, "traderecord"):
        trades = strat.analyzers.traderecord.trades

    # 7. 计算指标（依赖上面提取的 trades 与资金曲线，
    #    资金曲线用于波动率/Sortino/回撤修复期等扩展风险指标）
    metrics = compute_metrics(
        cerebro, result, trades_list=trades, equity_curve=equity_curve
    )

    # 9. K 线数据（前端展示用）
    kline = df.assign(date=df["date"].dt.strftime("%Y-%m-%d")).to_dict("records")

    # 数据来源标记：模拟数据 or 真实行情（用于前端提示）
    data_source = "mock" if df.attrs.get("is_mock") else "real"

    # 10. 基准对比（P0-10）：买入持有 + 沪深300
    #     没有基准的收益数字没有意义——策略年化 20% 但同期买入持有 25%
    #     说明策略是失败的，而这在没有基准时完全看不出来。
    #     基准计算失败不影响回测本身（内部已降级为 None）。
    benchmarks = compute_benchmarks(
        df=df,
        start_date=start_date,
        end_date=end_date,
        cash=start_cash,
        commission=commission,
        slippage=slippage,
        strategy_total_return=metrics.total_return,
    )

    return {
        "metrics": metrics.to_dict(),
        "equity_curve": equity_curve,
        "trades": trades,
        "kline": kline,
        "start_cash": start_cash,
        "end_cash": end_cash,
        "data_source": data_source,
        "benchmarks": benchmarks,
        # A 股规则防线计数（Q-07）：>0 说明策略试图进行违规交易被拦截
        "constraints": {
            "t1_sell_blocked": getattr(strat, "astock_t1_blocked", 0),
            "short_sell_blocked": getattr(strat, "astock_short_blocked", 0),
        },
    }


class _EquityCurveAnalyzer(bt.Analyzer):
    """记录每个交易日的账户总价值，用于绘制资金曲线。"""

    def start(self):
        self.equity_curve = []

    def next(self):
        date = self.strategy.datas[0].datetime.date(0)
        value = self.strategy.broker.getvalue()
        self.equity_curve.append({"date": date.isoformat(), "value": round(value, 2)})


class _AStockCommissionInfo(bt.CommInfoBase):
    """A 股真实交易成本模型。

    backtrader 内置的 setcommission(commission=rate) 只建模了「按比例双边佣金」，
    会漏掉 A 股两项真实且重要的成本：

    ==========  ============  ========  ======================================
    项目        费率           方向      说明
    ==========  ============  ========  ======================================
    佣金        约万 2.5~3    双边      不足 5 元按 5 元收
    印花税      0.05%（千五） 仅卖出    最重的一项，漏掉会显著虚高收益
    过户费      0.001%        双边      沪市收取，此处双边简化计入
    ==========  ============  ========  ======================================

    漏掉印花税对高换手策略是致命的：一年交易 20 次即少算约 1% 成本，
    对年化 15% 的策略意味着约 6.7% 的收益虚高。
    """

    params = (
        ("commission", 0.0003),   # 佣金费率（双边）
        ("min_commission", 5.0),  # 单笔最低佣金（元）
        ("stamp_duty", 0.0005),   # 印花税 0.05%，仅卖出
        ("transfer_fee", 0.00001),  # 过户费 0.001%，双边
        ("stocklike", True),
        ("commtype", bt.CommInfoBase.COMM_PERC),
        # percabs=True：声明 commission 是绝对比例（0.0003 = 万 3）。
        # 默认 False 时 backtrader 把 commission 当百分数再 ÷100，
        # 导致实际佣金被低估 100 倍（10 万成交额应收 30 元实收 0.3 元）。
        ("percabs", True),
    )

    def _getcommission(self, size, price, pseudoexec):
        """计算单笔佣金（不含印花税/过户费，那部分在 _getcommission 之外计）。"""
        turnover = abs(size) * price
        comm = turnover * self.p.commission
        return max(comm, self.p.min_commission) if turnover > 0 else 0.0

    def getcommission(self, size, price):
        """backtrader 在订单执行时调用此接口计算总成本。"""
        turnover = abs(size) * price
        if turnover <= 0:
            return 0.0
        # 佣金（双边，含最低 5 元）
        cost = max(turnover * self.p.commission, self.p.min_commission)
        # 过户费（双边）
        cost += turnover * self.p.transfer_fee
        # 印花税（仅卖出征收）
        if size < 0:
            cost += turnover * self.p.stamp_duty
        return cost


class _PositionSizerAdapter(bt.Sizer):
    """仓位管理适配器：把 core.position_sizer 的能力接入回测引擎。

    此前 ``position_sizer.py`` 已实现 Kelly / ATR / 目标波动率等仓位算法，
    但引擎从未引用（孤岛代码），所有策略都被迫使用「满仓 95%」一种模式。
    这里把它们统一接入，通过 ``position_sizing`` 参数切换。

    支持的模式：
      - ``allin``      满仓（等价旧的 _AllInSizer，保持默认行为不变）
      - ``fixed``      固定比例建仓
      - ``atr``        ATR 风险仓位：单笔亏损不超过 risk_percent
      - ``volatility`` 目标波动率：波动越大仓位越小

    所有模式最终结果都会取整到 100 股（A 股 1 手）。
    """

    params = (
        ("mode", "allin"),
        ("percent", 95.0),
        ("max_position", 0.95),
        ("risk_percent", 0.01),
        ("atr_multiplier", 2.0),
        ("target_volatility", 0.15),
        ("slippage", 0.001),
        ("enforce_limits", True),  # 是否启用涨跌停/停牌约束
    )

    def _getsizing(self, comminfo, cash, data, isbuy):
        # ---- A 股交易约束（P0-7）----
        # 不建模涨跌停是回测收益虚高最经典的来源：
        # 追涨停/突破类策略在真实市场根本买不到那些票，
        # 但回测里全都成交了，导致结果完全失去参考价值。
        if self.p.enforce_limits:
            if self._is_suspended(data):
                return 0  # 停牌：无法成交
            if isbuy and self._is_limit_up(data, self._symbol_of(data)):
                return 0  # 涨停：买单排不上队，买不到
            if not isbuy and self._is_limit_down(data, self._symbol_of(data)):
                return 0  # 跌停：卖单排不上队，卖不掉

        if not isbuy:
            # 卖出：清掉全部持仓（允许零股）
            return self.strategy.position.size

        price = data.close[0] * (1 + self.p.slippage)
        if price <= 0:
            return 0

        mode = (self.p.mode or "allin").lower()

        try:
            if mode == "atr":
                shares = calc_atr_position(
                    capital=cash,
                    atr_value=self._atr(data),
                    atr_multiplier=self.p.atr_multiplier,
                    risk_percent=self.p.risk_percent,
                    current_price=price,
                )
                return self._to_lots(shares, cash, price)

            if mode == "volatility":
                vol = self._annual_volatility(data)
                ratio = calc_volatility_position(
                    base_size=self.p.percent / 100.0,
                    current_volatility=vol,
                    target_volatility=self.p.target_volatility,
                    max_position=self.p.max_position,
                )
                target_cash = cash * ratio
            else:
                # allin / fixed：按资金百分比建仓
                target_cash = cash * self.p.percent / 100.0
        except Exception:
            # 任何计算异常都退化为满仓，避免回测直接失败
            target_cash = cash * self.p.percent / 100.0

        if target_cash <= 0:
            return 0
        return self._to_lots(int(target_cash / price), cash, price)

    def _to_lots(self, shares: int, cash: float, price: float) -> int:
        """取整到 100 股（A 股 1 手），并做资金/上限约束。"""
        try:
            size = int(shares) // 100 * 100
            # 上限：不超过 max_position 比例的资金
            max_shares = int(cash * float(self.p.max_position) / price) if price > 0 else 0
            max_shares = max_shares // 100 * 100
            if max_shares > 0:
                size = min(size, max_shares)
            if size <= 0 and cash >= price * 100:
                size = 100  # 资金够一手时至少买一手
            return max(size, 0)
        except Exception:
            return 0

    @staticmethod
    def _symbol_of(data) -> str:
        """取数据源名称（即股票代码），用于判断所属板块。"""
        try:
            return str(getattr(data, "_name", "") or "")
        except Exception:
            return ""

    @staticmethod
    def _limit_ratio(symbol: str) -> float:
        """按板块返回涨跌停幅度。

        - 创业板（300/301 开头）：±20%
        - 科创板（688 开头）：±20%
        - 其余主板：±10%
        （ST 股为 ±5%，但回测数据不含名称，此处按板块处理）
        """
        s = (symbol or "").strip().lower().replace("sh", "").replace("sz", "")
        if s.startswith(("300", "301", "688")):
            return 0.20
        return 0.10

    @classmethod
    def _is_suspended(cls, data) -> bool:
        """停牌：成交量为 0 的 K 线无法交易。"""
        try:
            return float(data.volume[0]) <= 0
        except Exception:
            return False

    @classmethod
    def _is_limit_up(cls, data, symbol: str) -> bool:
        """涨停：当日最高价（或收盘价）触及涨停价。

        真实市场中，一字涨停时买单排不上队，基本买不到。
        用「收盘价 >= 涨停价 - 容差」判断，避免浮点误差漏判。
        """
        try:
            prev_close = float(data.close[-1])
            cur_close = float(data.close[0])
            if prev_close <= 0:
                return False
            limit_price = round(prev_close * (1 + cls._limit_ratio(symbol)), 2)
            return cur_close >= limit_price - 0.005
        except Exception:
            return False

    @classmethod
    def _is_limit_down(cls, data, symbol: str) -> bool:
        """跌停：当日收盘价触及跌停价，卖单排不上队。"""
        try:
            prev_close = float(data.close[-1])
            cur_close = float(data.close[0])
            if prev_close <= 0:
                return False
            limit_price = round(prev_close * (1 - cls._limit_ratio(symbol)), 2)
            return cur_close <= limit_price + 0.005
        except Exception:
            return False

    @staticmethod
    def _atr(data, period: int = 14) -> float:
        """简易 ATR（平均真实波幅）。

        直接用 data 的历史 high/low/close 计算，避免在 Sizer 里创建
        backtrader 指标（Sizer 生命周期与指标不同步）。
        """
        try:
            highs = list(data.high.get(size=period + 1))
            lows = list(data.low.get(size=period + 1))
            closes = list(data.close.get(size=period + 1))
            n = min(len(highs), len(lows), len(closes))
            if n < 2:
                return 0.0
            trs = []
            for i in range(1, n):
                prev_close = closes[i - 1]
                tr = max(
                    highs[i] - lows[i],
                    abs(highs[i] - prev_close),
                    abs(lows[i] - prev_close),
                )
                trs.append(tr)
            return (sum(trs) / len(trs)) if trs else 0.0
        except Exception:
            return 0.0

    @staticmethod
    def _annual_volatility(data, period: int = 20) -> float:
        """年化波动率：日收益率标准差 × √252。"""
        try:
            closes = list(data.close.get(size=period + 1))
            if len(closes) < 3:
                return 0.0
            rets = []
            for i in range(1, len(closes)):
                prev = closes[i - 1]
                if prev > 0:
                    rets.append(closes[i] / prev - 1)
            if len(rets) < 2:
                return 0.0
            mean = sum(rets) / len(rets)
            var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
            return (var ** 0.5) * (252 ** 0.5)
        except Exception:
            return 0.0


class _AllInSizer(bt.Sizer):
    """满仓/清仓仓位管理。

    - 买入：用可用资金的 ``percents%`` 建仓，按收盘价*(1+滑点)估算，取整到整百股。
    - 卖出：返回当前全部持仓，实现干净清仓（避免 PercentSizer 卖出后残留尾巴）。

    这样策略里只需写 ``self.buy()`` / ``self.sell()`` 即可正确反映真实资金规模，
    不必每个策略单独处理下单数量。
    """

    params = (
        ("percents", 95),
        ("slippage", 0.001),
    )

    def _getsizing(self, comminfo, cash, data, isbuy):
        if isbuy:
            price = data.close[0] * (1 + self.p.slippage)
            if price <= 0:
                return 0
            affordable = (cash * self.p.percents / 100.0) / price
            if affordable <= 0:
                return 0
            # 整百股取整（A股一手=100股），但高价股资金不足一手时至少买一手，
            # 避免 size=0 导致订单被拒、回测 0 交易。
            size = int(affordable // 100) * 100
            if size <= 0 and affordable >= 1:
                size = 100
            return max(size, 0)
        # 卖出：清掉全部持仓（允许零股）
        return self.strategy.position.size


class _TradeRecordAnalyzer(bt.Analyzer):
    """记录每笔交易明细，用于展示交易记录表。"""

    def start(self):
        self.trades = []

    def notify_order(self, order: bt.Order):
        if order.status == order.Completed:
            date = self.strategy.datas[0].datetime.date(0)
            self.trades.append({
                "date": date.isoformat(),
                "action": "买入" if order.isbuy() else "卖出",
                "price": round(order.executed.price, 3),
                "size": round(order.executed.size, 0),
            })

    def notify_trade(self, trade: bt.Trade):
        if trade.isclosed:
            self.trades.append({
                "date": self.strategy.datas[0].datetime.date(0).isoformat(),
                "action": "平仓",
                "price": 0,
                "size": 0,
                "pnl": round(trade.pnlcomm, 2),
            })
