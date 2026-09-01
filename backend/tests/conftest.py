"""金标准回归测试套件（E-01）：共享 fixture。

目标不是覆盖率数字，而是「改坏会红」：每条测试对应一个真实出现过
的缺陷或一条不可破坏的业务规则（见 审计整改计划.md）。
"""
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import core.benchmark as bm  # noqa: E402
import core.data_loader as dl  # noqa: E402
from core.engine import run_backtest  # noqa: E402

SYM = "__GT__"


def make_wave_df(n=400, seed=7, start="2023-01-02"):
    """确定性波形数据：正弦（保证金叉死叉）+ 趋势 + 固定种子噪声。"""
    t = np.arange(n)
    rng = np.random.default_rng(seed)
    close = 10 + 2 * np.sin(2 * np.pi * t / 55) + 0.008 * t + rng.normal(0, 0.12, n)
    close = np.maximum(close, 1.0)
    return pd.DataFrame({
        "date": pd.bdate_range(start, periods=n),
        "open": close * 0.995, "high": close * 1.02, "low": close * 0.97,
        "close": close, "volume": np.full(n, 1e6), "amount": close * 1e6,
    })


def cleanup_cache(symbol=SYM):
    for adj in ("qfq", "hfq", "raw"):
        p = dl._cache_path(symbol, "daily", adj)
        if p.exists():
            p.unlink()
    lp = dl._legacy_cache_path(symbol, "daily")
    if lp.exists():
        lp.unlink()


@pytest.fixture(autouse=True)
def _no_index_network(monkeypatch):
    """沪深300 基准依赖网络；测试中一律置 None（买入持有基准不依赖网络）。"""
    monkeypatch.setattr(bm, "calc_index_benchmark", lambda *a, **k: None)


@pytest.fixture
def wave(monkeypatch):
    """合成波形数据源：monkeypatch 掉网络层，结束清理缓存文件。"""
    df = make_wave_df()
    monkeypatch.setattr(dl, "_fetch_from_akshare", lambda s, a, b, c, d: df)
    yield SYM, df
    cleanup_cache(SYM)


def run(symbol=SYM, **kw):
    """run_backtest 便捷封装（参数与专项脚本一致）。"""
    defaults = dict(
        symbol=symbol, start_date="20230101", end_date="20241231",
        params={}, cash=1_000_000, commission=0.0003, slippage=0.001,
        period="daily", adjust="qfq",
    )
    defaults.update(kw)
    return run_backtest(**defaults)


def find_t1_violations(trades):
    """精确 T+1 判据：某日累计卖出量 > 该日日初持仓 → 违规
    （卖出了当日才买入的份额）。返回违规日列表。"""
    daily = defaultdict(lambda: {"buy": 0.0, "sell": 0.0})
    for tr in trades:
        if tr.get("action") == "买入":
            daily[tr["date"]]["buy"] += tr.get("size", 0)
        elif tr.get("action") == "卖出":
            daily[tr["date"]]["sell"] += tr.get("size", 0)
    pos = 0.0
    violations = []
    for d in sorted(daily.keys()):
        if daily[d]["sell"] > pos + 1e-6:
            violations.append((d, daily[d]["sell"], pos))
        pos = pos + daily[d]["buy"] - daily[d]["sell"]
    return violations
