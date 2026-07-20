"""验证：动量策略修复 + 缓存内外区间均正常。"""
import sys, traceback
sys.path.insert(0, ".")

from core.engine import run_backtest

cases = [
    ("000001", "20240101", "20241231", "缓存覆盖区间(曾500)"),
    ("000001", "20230101", "20231231", "缓存外区间(曾400)"),
    ("600519", "20250601", "20260701", "缓存覆盖区间2"),
    ("600519", "20230101", "20231231", "缓存外区间2"),
    ("600036", "20240101", "20241231", "缓存覆盖区间3"),
]
for sym, s, e, label in cases:
    print("=" * 20, label, sym, s, e)
    try:
        r = run_backtest(strategy_key="momentum", symbol=sym,
                         start_date=s, end_date=e, params={}, cash=1_000_000)
        m = r["metrics"]
        print("OK ret=", m.get("total_return"), "trades=", len(r["trades"]))
    except Exception as ex:
        print("FAILED:", type(ex).__name__, repr(ex))
