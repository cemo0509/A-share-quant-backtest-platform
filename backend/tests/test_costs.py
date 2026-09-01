"""成本与数值正确性金标准（P0-6 / Q-01 / Q-04 / Q-05）。

每条对应一个曾真实导致收益失真的缺陷：
- 漏印花税 → 高换手策略收益系统性虚高
- 下单非整百股 → 真实市场无法成交的委托
- 夏普未年化 → 参数优化按日夏普排序选出噪声
- 年化按自然年数量开方 → 不足一年时年化虚高
"""
import numpy as np
import pytest

from conftest import run  # noqa: E402（tests 目录已在 sys.path）

from core.engine import _AStockCommissionInfo


class TestCommission:
    def test_min_commission_five_yuan(self):
        """小额交易佣金不足 5 元按 5 元收（A 股券商通行规则）。"""
        ci = _AStockCommissionInfo(commission=0.0003)
        # 100 股 × 2 元 = 200 元成交额，万 3 佣金仅 0.06 元 → 按 5 元收
        cost = ci.getcommission(100, 2.0)
        assert cost == pytest.approx(5.0 + 200 * 0.00001, abs=1e-6)

    def test_stamp_duty_only_on_sell(self):
        """印花税 0.05% 仅卖出征收：买卖成本差必须恰为印花税。"""
        ci = _AStockCommissionInfo(commission=0.0003)
        turnover = 10_000 * 10.0
        buy_cost = ci.getcommission(10_000, 10.0)
        sell_cost = ci.getcommission(-10_000, 10.0)
        # 买入：佣金 + 过户费，无印花税
        assert buy_cost == pytest.approx(
            turnover * 0.0003 + turnover * 0.00001, rel=1e-9)
        # 卖出比买入多出且仅多出印花税
        assert sell_cost - buy_cost == pytest.approx(turnover * 0.0005, rel=1e-9)


class TestOrderSizing:
    def test_all_buys_rounded_to_100(self, wave):
        """所有买入成交必须是整百股（A 股一手 = 100 股）。"""
        res = run(strategy_key="kdj")
        buys = [t for t in res["trades"] if t["action"] == "买入"]
        assert buys, "波形数据应产生买入，否则测试失效"
        bad = [t for t in buys if t["size"] % 100 != 0]
        assert not bad, f"非整百股买入: {bad[:3]}"


class TestAnnualization:
    def test_sharpe_is_annualized(self, wave):
        """夏普必须年化：与资金曲线手工计算的年化夏普一致。

        若 annualize=True 被删掉，日夏普只有年化的 1/√252 ≈ 1/15.87 → 红。
        """
        res = run(strategy_key="macd")
        sharpe = res["metrics"]["sharpe_ratio"]
        assert sharpe is not None
        values = np.array([p["value"] for p in res["equity_curve"]])
        rets = np.diff(values) / values[:-1]
        manual = rets.mean() / rets.std(ddof=1) * np.sqrt(252)
        assert sharpe == pytest.approx(manual, rel=0.05)

    def test_annual_return_uses_actual_days(self, wave):
        """年化必须按实际天数/365 开方，而非自然年数量。

        区间 547 自然日（1.498 年）：反推年化年数应 ≈ 1.5；
        若退化为按「自然年数量 = 1」开方，反推值 = 1 → 红。
        """
        res = run(strategy_key="dual_ma", start_date="20230101", end_date="20240630")
        m = res["metrics"]
        assert m["total_return"] != 0, "测试数据应产生非零收益"
        total, annual = m["total_return"] / 100, m["annual_return"] / 100
        if total <= -1 or annual <= -1:
            pytest.skip("收益 ≤ -100% 无法反推")
        implied_years = np.log(1 + total) / np.log(1 + annual)
        actual_years = 547 / 365.0
        assert implied_years == pytest.approx(actual_years, rel=0.10)
