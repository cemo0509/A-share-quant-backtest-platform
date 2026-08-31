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

logger = logging.getLogger("engine")


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

    # 1. 获取数据
    df = fetch_kline(symbol, start_date, end_date, period=period)
    if df.empty:
        raise ValueError("无法获取该股票在指定日期范围内的行情数据，请检查股票代码和日期")

    # 2. 构建 Backtrader 数据源
    data = bt.feeds.PandasData(
        dataname=df,
        datetime="date",
        open="open",
        high="high",
        low="low",
        close="close",
        volume="volume",
        openinterest=-1,
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

    # 仓位管理：默认买入时用可用资金的 95% 建仓（整百股），卖出时清仓。
    # 若不设置 sizer，backtrader 默认每次只交易 1 股，导致回测资金几乎不动、
    # 收益率恒为 0、交易金额异常（这正是“交易情况不对”的根因）。
    cerebro.addsizer(_AllInSizer, percents=95, slippage=slippage)

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
    cerebro.addstrategy(strategy_cls, **bt_params)

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

    # 7. 计算指标（依赖上面提取的 trades）
    metrics = compute_metrics(cerebro, result, trades_list=trades)

    # 9. K 线数据（前端展示用）
    kline = df.assign(date=df["date"].dt.strftime("%Y-%m-%d")).to_dict("records")

    # 数据来源标记：模拟数据 or 真实行情（用于前端提示）
    data_source = "mock" if df.attrs.get("is_mock") else "real"

    return {
        "metrics": metrics.to_dict(),
        "equity_curve": equity_curve,
        "trades": trades,
        "kline": kline,
        "start_cash": start_cash,
        "end_cash": end_cash,
        "data_source": data_source,
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
