"""分析功能金标准（P0-8 / P0-9 / P0-10 / Q-06 / 决策3）。

- 基准对比：没有基准的收益数字没有意义（kdj 赚 11% 实际跑输买入持有 21%）
- 样本外验证：参数搜索只用样本内，样本外判定过拟合
- 仓位管理：fixed 仓位必须明显小于 allin
- ExitRules 集成：时间退出必须在横盘时触发
- 持久化：回测历史 CRUD + 完整结果可复盘
"""
import numpy as np
import pandas as pd
import pytest

import core.data_loader as dl
from conftest import cleanup_cache, run


class TestBenchmark:
    def test_buy_hold_benchmark_present(self, wave):
        """买入持有基准必须存在（用同一份 K 线，复权口径一致）。"""
        res = run(strategy_key="dual_ma")
        bm = res.get("benchmarks") or {}
        bh = bm.get("buy_hold")
        assert bh is not None, "缺少买入持有基准"
        assert -100 < bh["total_return"] < 1000

    def test_excess_return_consistency(self, wave):
        """超额收益 = 策略收益 − 买入持有基准（最有价值的指标）。"""
        res = run(strategy_key="dual_ma")
        bm = res["benchmarks"]
        expect = res["metrics"]["total_return"] - bm["buy_hold"]["total_return"]
        assert bm["excess_vs_buy_hold"] == pytest.approx(expect, abs=0.05)


class TestOutOfSample:
    def test_danger_when_oos_negative(self):
        """样本内盈利但样本外亏损 → danger（最典型过拟合）。"""
        from api.optimize import _evaluate_overfit
        alert, level, _ = _evaluate_overfit(
            {"total_return": 211.31, "sharpe_ratio": 5.129},
            {"total_return": -71.85, "sharpe_ratio": -7.21})
        assert alert and level == "danger"

    def test_danger_when_retention_low(self):
        """收益保持率 < 30% → danger。"""
        from api.optimize import _evaluate_overfit
        alert, level, _ = _evaluate_overfit(
            {"total_return": 100.0, "sharpe_ratio": 2.0},
            {"total_return": 10.0, "sharpe_ratio": 2.0})
        assert alert and level == "danger"

    def test_none_when_consistent(self):
        """样本内外表现一致 → 不告警。"""
        from api.optimize import _evaluate_overfit
        alert, level, _ = _evaluate_overfit(
            {"total_return": 20.0, "sharpe_ratio": 1.5},
            {"total_return": 18.0, "sharpe_ratio": 1.4})
        assert not alert and level == "none"


class TestPositionSizing:
    def test_fixed_position_smaller_than_allin(self, wave):
        """fixed 30% 仓位的单笔买入必须明显小于 allin 95%（曾全平台只有满仓）。"""
        r_allin = run(strategy_key="kdj", position_sizing="allin")
        r_fixed = run(strategy_key="kdj", position_sizing="fixed",
                      position_percent=30.0)
        big_allin = max(t["size"] for t in r_allin["trades"] if t["action"] == "买入")
        big_fixed = max(t["size"] for t in r_fixed["trades"] if t["action"] == "买入")
        assert big_fixed < big_allin * 0.6, \
            f"fixed({big_fixed}) 未明显小于 allin({big_allin})，仓位管理失效"


class TestExitRulesIntegration:
    def test_smart_exit_time_exit_triggers(self, monkeypatch):
        """横盘无信号时，持仓超过 45 天必须被「时间退出」平仓。

        修复前 ExitRules 实例化了却从未调用，此测试无法通过。
        """
        sym = "__SE__"
        n = 200
        close = np.concatenate([
            np.linspace(10, 9.8, 20),    # 先跌：让 fast 均线位于 slow 下方
            np.linspace(9.8, 11.5, 40),  # 后涨：fast 明确上穿 slow（金叉买入）
            np.full(n - 60, 11.5),       # 长期横盘：无死叉、无止损、无止盈
        ])
        df = pd.DataFrame({
            "date": pd.bdate_range("2023-01-02", periods=n),
            "open": close * 0.995, "high": close * 1.005,
            "low": close * 0.99, "close": close,
            "volume": np.full(n, 1e6), "amount": close * 1e6,
        })
        monkeypatch.setattr(dl, "_fetch_from_akshare", lambda *a: df)
        try:
            res = run(symbol=sym, strategy_key="smart_exit")
        finally:
            cleanup_cache(sym)
        buys = [t for t in res["trades"] if t["action"] == "买入"]
        sells = [t for t in res["trades"] if t["action"] == "卖出"]
        assert buys and sells, "横盘场景应「买入 → 时间退出」各一次"
        gap_days = (pd.to_datetime(sells[0]["date"])
                    - pd.to_datetime(buys[0]["date"])).days
        # 45 个交易日 ≈ 63 自然日；时间退出被破坏时会持有到最后（>120 天）
        assert 45 <= gap_days <= 90, \
            f"持仓 {gap_days} 自然日后退出，不符合 45 交易日时间退出特征"


class TestBacktestStore:
    def test_store_crud(self, tmp_path, monkeypatch):
        """回测历史：保存 → 列表 → 复盘（完整结果）→ 删除。"""
        import core.backtest_store as store
        monkeypatch.setattr(store, "_get_db_path", lambda: tmp_path / "t.db")
        store.init_db()
        sample = {"metrics": {"total_return": 1.5, "total_trades": 3},
                  "trades": [{"date": "2024-01-02", "action": "买入",
                              "price": 10.0, "size": 100}],
                  "data_source": "real"}
        rid = store.save_run(sample, strategy_key="dual_ma", strategy_name="双均线",
                             symbol="000001", start_date="20230101",
                             end_date="20241231")
        assert rid, "保存应返回 run_id"
        runs = store.list_runs()
        assert len(runs) == 1 and runs[0]["id"] == rid
        assert "result" not in runs[0] or runs[0].get("result") is None, \
            "列表不应带完整结果（体积大）"
        full = store.get_run(rid)
        assert full["result"]["metrics"]["total_return"] == 1.5, "复盘结果不一致"
        assert store.delete_run(rid) is True
        assert store.get_run(rid) is None
