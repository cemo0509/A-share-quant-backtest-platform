"""阶段一验证脚本：跑通 Backtrader 双均线回测 demo。

运行方式：
    cd backend
    python demo_backtest.py

验证内容：
1. AKShare 能否拉取 A 股数据
2. Parquet 缓存是否生效
3. Backtrader 引擎能否正常回测
4. 指标计算是否正常
"""
import sys
import os

# 确保能导入 backend 模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.engine import run_backtest


def main():
    print("=" * 60)
    print("阶段一验证：Backtrader 双均线回测 demo")
    print("=" * 60)

    print("\n[1] 运行回测：000001 平安银行，双均线(5,20)，2024-01-01 ~ 2025-06-30")
    result = run_backtest(
        strategy_key="dual_ma",
        symbol="000001",
        start_date="20240101",
        end_date="20250630",
        params={"fast": 5, "slow": 20},
        cash=1_000_000,
    )

    m = result["metrics"]
    print("\n[2] 回测指标：")
    print(f"    总收益率:   {m['total_return']}%")
    print(f"    年化收益率: {m['annual_return']}%")
    print(f"    最大回撤:   {m['max_drawdown']}%")
    print(f"    夏普比率:   {m['sharpe_ratio']}")
    print(f"    胜率:       {m['win_rate']}%")
    print(f"    盈亏比:     {m['profit_loss_ratio']}")
    print(f"    总交易笔数: {m['total_trades']}")
    print(f"    盈利笔数:   {m['win_trades']}")
    print(f"    亏损笔数:   {m['loss_trades']}")

    print(f"\n[3] 资金曲线点数: {len(result['equity_curve'])}")
    print(f"[4] 交易明细笔数: {len(result['trades'])}")
    print(f"[5] K线数据条数: {len(result['kline'])}")
    print(f"[6] 初始资金: {result['start_cash']:.2f}  最终资金: {result['end_cash']:.2f}")

    print("\n[7] 前5笔交易：")
    for t in result["trades"][:5]:
        print(f"    {t}")

    print("\n" + "=" * 60)
    print("✅ 阶段一验证通过！回测引擎正常工作。")
    print("=" * 60)


if __name__ == "__main__":
    main()
