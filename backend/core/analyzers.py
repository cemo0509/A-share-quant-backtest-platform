"""回测指标分析：计算年化收益、最大回撤、夏普比率、胜率、盈亏比。

对应调研报告 2.2 节「回测的关键指标」。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Optional

import backtrader as bt

from core.utils import safe_convert


@dataclass
class BacktestMetrics:
    """回测结果指标。"""
    # 收益类
    total_return: float          # 总收益率 %
    annual_return: float         # 年化收益率 %
    # 风险类
    max_drawdown: float          # 最大回撤 %
    # 风险调整（数据不足时夏普无法计算，为 None 而非 0，
    # 避免把「算不出来」与「夏普为 0」混为一谈）
    sharpe_ratio: Optional[float]  # 夏普比率（已年化）
    # 交易类
    win_rate: float              # 胜率 %
    profit_loss_ratio: float     # 盈亏比
    total_trades: int            # 总交易笔数
    win_trades: int              # 盈利笔数
    loss_trades: int             # 亏损笔数

    def to_dict(self) -> dict:
        """安全地转换为字典，处理 numpy/非序列化类型。"""
        result = {}
        for field_name in self.__dataclass_fields__:
            value = getattr(self, field_name)
            result[field_name] = safe_convert(value)
        return result


def compute_metrics(cerebro: bt.Cerebro, result: Any, trades_list: Optional[list] = None) -> BacktestMetrics:
    """从 Backtrader 回测结果计算指标。

    Args:
        cerebro: 回测引擎实例（用于读取 broker 价值）
        result: cerebro.run() 返回值
        trades_list: 交易明细列表（来自 _TradeRecordAnalyzer），优先用于交易统计。
                     每一项可为 {..., "pnl": x}（平仓记录）或 backtrader Trade 对象。
    """
    strat = result[0] if isinstance(result, list) else result

    # 1. 收益类
    final_value = cerebro.broker.getvalue()
    start_cash = cerebro.broker.startingcash
    total_return = (final_value - start_cash) / start_cash * 100

    # 2. 交易统计
    # 优先使用交易明细列表（已含每笔平仓的真实 pnl，且与前端展示一致）；
    # 若未传入，则回退到 backtrader 内部 _trades 接口。
    trade_records = _extract_pnl_from_trades_list(trades_list) if trades_list else _extract_trades(strat)

    total_trades = len(trade_records)
    wins = [t for t in trade_records if t > 0]
    losses = [t for t in trade_records if t <= 0]
    win_trades = len(wins)
    loss_trades = len(losses)

    win_rate = (win_trades / total_trades * 100) if total_trades > 0 else 0
    avg_win = (sum(wins) / win_trades) if win_trades > 0 else 0
    avg_loss = (abs(sum(losses) / loss_trades)) if loss_trades > 0 else 0
    profit_loss_ratio = (avg_win / avg_loss) if avg_loss > 0 else 0

    # 3. 回撤（从 analyzer 获取）
    drawdown = strat.analyzers.drawdown.get_analysis()
    max_drawdown = drawdown.max.drawdown if hasattr(drawdown, "max") and drawdown.max.drawdown is not None else 0

    # 4. 夏普比率（从 analyzer 获取）
    # 注意：数据不足时 backtrader 会返回 None。此前写法 `sharpe.get(...) or 0`
    # 会把「算不出来」静默变成 0，与「夏普确实为 0」在界面上无法区分。
    # 这里保留 None，由前端显示为「—」。
    sharpe = strat.analyzers.sharpe.get_analysis()
    sharpe_raw = sharpe.get("sharperatio", None)
    sharpe_ratio = float(sharpe_raw) if sharpe_raw is not None else None

    # 5. 年化收益率（从 analyzer 获取）
    # 用「实际天数/365」而非「自然年个数」作为年数：
    # 回测 2024-06-01~2025-05-31（整 1 年）跨 2 个自然年，用自然年个数会把
    # 1 年的收益开平方，年化收益被严重低估。
    annual = strat.analyzers.annualreturn.get_analysis()
    if annual:
        prod = 1.0
        for r in annual.values():
            prod *= (1 + r)
        years = _years_from_data(strat)
        annual_return = (prod ** (1 / years) - 1) * 100 if years > 0 else 0
    else:
        annual_return = 0

    return BacktestMetrics(
        total_return=round(total_return, 2),
        annual_return=round(annual_return, 2),
        max_drawdown=round(max_drawdown, 2),
        sharpe_ratio=round(sharpe_ratio, 3) if sharpe_ratio is not None else None,
        win_rate=round(win_rate, 2),
        profit_loss_ratio=round(profit_loss_ratio, 3),
        total_trades=total_trades,
        win_trades=win_trades,
        loss_trades=loss_trades,
    )


def _years_from_data(strat: Any) -> float:
    """按回测实际跨越天数计算年数（而非自然年个数）。

    AnnualReturn 返回 {年份: 收益率}，若直接用 len(annual) 当「年数」，
    会把「跨越的自然年个数」误当作「实际年数」：
      回测 2024-06-01 ~ 2025-05-31（整 1 年）→ 跨 2 个自然年 → years=2
      → 1 年的收益被开平方 → 年化收益被系统性低估。

    正确做法是用数据源首尾日期的实际天数 / 365。
    """
    try:
        d = strat.datas[0]
        n = len(d)
        if n <= 1:
            return 0.0
        start_dt = d.datetime.datetime(-(n - 1))
        end_dt = d.datetime.datetime(0)
        days = (end_dt - start_dt).days
        return days / 365.0 if days > 0 else 0.0
    except Exception:
        return 0.0


def _extract_pnl_from_trades_list(trades_list: list) -> list[float]:
    """从交易明细列表（_TradeRecordAnalyzer 记录）中提取每笔平仓的净盈亏。

    只统计 action 为「平仓」且带 pnl 字段的记录，避免把开仓/平仓两条
    重复计入（开仓记录无 pnl）。
    """
    pnls: list[float] = []
    for t in trades_list:
        if not isinstance(t, dict):
            # 兼容直接传入 backtrader Trade 对象
            if getattr(t, "isclosed", False):
                pnls.append(float(getattr(t, "pnlcomm", 0) or 0))
            continue
        action = str(t.get("action", ""))
        if action == "平仓" and "pnl" in t:
            pnls.append(float(t["pnl"]))
    return pnls


def _extract_trades(strat: bt.Strategy) -> list[float]:
    """从策略的交易记录中提取每笔净盈亏。

    注意：backtrader 的 strat._trades 是内部接口（带下划线前缀），
    但 backtrader 官方文档和社区示例均使用此方式获取交易记录。
    此处已做充分的类型检查和异常防护。

    backtrader 的 strat._trades 结构：
    {data_feed: [trade1, trade2, ...]}
    每个 trade 是 backtrader.Trade 对象。
    """
    trades = []
    try:
        raw = strat._trades
    except AttributeError:
        return trades

    if isinstance(raw, dict):
        # _trades 是 {data: [Trade, ...]} 字典
        for trade_list in raw.values():
            if isinstance(trade_list, list):
                for trade in trade_list:
                    if hasattr(trade, 'isclosed') and trade.isclosed:
                        trades.append(trade.pnlcomm)
            elif hasattr(trade_list, 'isclosed') and trade_list.isclosed:
                trades.append(trade_list.pnlcomm)
    elif isinstance(raw, list):
        # _trades 是 [Trade, ...] 列表
        for trade in raw:
            if hasattr(trade, 'isclosed') and trade.isclosed:
                trades.append(trade.pnlcomm)

    return trades
