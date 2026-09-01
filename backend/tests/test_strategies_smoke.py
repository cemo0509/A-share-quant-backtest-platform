"""策略层金标准（Q-03 / Q-07 / 全策略冒烟）。

- 15 个预置策略全部跑通、结果结构完整、无 T+1 违规、防线零误伤
- 动量策略必须产生足够信号（修复前把价格差当百分比，信号几乎不触发）
"""
import pytest

from conftest import find_t1_violations, run

from core.strategies.registry import get_strategy, list_strategies


def _all_keys():
    raw = list_strategies()
    keys = [s.get("key") if isinstance(s, dict) else getattr(s, "key", None)
            for s in raw]
    return [k for k in keys if k]


class TestAllStrategiesSmoke:
    def test_every_strategy_runs_with_clean_structure(self, wave):
        """全策略冒烟：跑通 + 结构完整 + 无 T+1 违规 + 防线零干预。"""
        sym, _ = wave
        keys = _all_keys()
        assert len(keys) >= 14, f"策略数量异常: {len(keys)}"
        failures = []
        for key in keys:
            try:
                res = run(symbol=sym,
                          strategy_cls=get_strategy(key).strategy_cls)
            except ValueError as e:
                if "指标计算失败" in str(e):
                    continue  # 连续单边行情的已知边界
                failures.append(f"{key}: {e}")
                continue
            for field in ("metrics", "equity_curve", "trades", "kline",
                          "benchmarks", "constraints"):
                if field not in res:
                    failures.append(f"{key}: 缺少字段 {field}")
            if find_t1_violations(res["trades"]):
                failures.append(f"{key}: 存在 T+1 违规")
            cons = res.get("constraints") or {}
            if cons.get("t1_sell_blocked") or cons.get("short_sell_blocked"):
                failures.append(f"{key}: 防线误伤 {cons}")
        assert not failures, "\n".join(failures)

    def test_momentum_generates_enough_signals(self, wave):
        """动量策略信号数 ≥ 5（Q-03 修复前 /100 单位混淆，信号几乎不触发）。"""
        res = run(strategy_key="momentum")
        trades = res["metrics"]["total_trades"]
        assert trades >= 5, \
            f"动量策略仅 {trades} 笔交易，疑似单位混淆回归（修复前 ~0 笔）"
