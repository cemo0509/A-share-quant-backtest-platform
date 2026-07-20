/** 策略模板代码集中管理模块。
 *
 * 包含所有预置策略的模板代码，供 StrategyEditor 和新建策略使用。
 * 从 StrategyEditor.tsx 中抽取，避免内联大量代码字符串。
 */

export const STRATEGY_TEMPLATES = {
  empty: {
    name: '空策略模板',
    code: `# Name: 我的策略
# Description: 请在这里编写策略描述

import backtrader as bt
import pandas as pd

class MyStrategy(bt.Strategy):
    params = (
        ('period', 20),
    )
    
    def __init__(self):
        # 在这里初始化指标
        self.sma = bt.indicators.SimpleMovingAverage(
            self.datas[0].close, period=self.params.period)
        
    def next(self):
        # 在这里编写交易逻辑
        if not self.position:
            if self.datas[0].close[0] > self.sma[0]:
                self.buy()
        else:
            if self.datas[0].close[0] < self.sma[0]:
                self.close()
`,
  },
  dual_ma: {
    name: '双均线策略模板',
    code: `# Name: 双均线策略
# Description: 短期均线上穿长期均线买入，下穿卖出

import backtrader as bt

class DualMAStrategy(bt.Strategy):
    params = (
        ('fast', 5),
        ('slow', 20),
    )
    
    def __init__(self):
        self.sma_fast = bt.indicators.SimpleMovingAverage(
            self.datas[0].close, period=self.params.fast)
        self.sma_slow = bt.indicators.SimpleMovingAverage(
            self.datas[0].close, period=self.params.slow)
        self.crossover = bt.indicators.CrossOver(self.sma_fast, self.sma_slow)
        
    def next(self):
        if not self.position:
            if self.crossover > 0:  # 金叉
                self.buy()
        else:
            if self.crossover < 0:  # 死叉
                self.close()
`,
  },
  adaptive: {
    name: '市场状态自适应策略模板',
    code: `# Name: 市场状态自适应策略
# Description: 根据市场状态（牛市/震荡/熊市）自动调整双均线参数和仓位

import backtrader as bt

class AdaptiveStrategy(bt.Strategy):
    params = (
        ('bull_fast', 5),
        ('bull_slow', 20),
        ('bear_fast', 10),
        ('bear_slow', 60),
        ('position_scale', True),
    )
    
    def __init__(self):
        self.order = None
        self.market_state = "normal"
        self.bull_sma_fast = bt.indicators.SimpleMovingAverage(
            self.datas[0].close, period=self.params.bull_fast)
        self.bull_sma_slow = bt.indicators.SimpleMovingAverage(
            self.datas[0].close, period=self.params.bull_slow)
        self.bull_crossover = bt.indicators.CrossOver(self.bull_sma_fast, self.bull_sma_slow)
        self.bear_sma_fast = bt.indicators.SimpleMovingAverage(
            self.datas[0].close, period=self.params.bear_fast)
        self.bear_sma_slow = bt.indicators.SimpleMovingAverage(
            self.datas[0].close, period=self.params.bear_slow)
        self.bear_crossover = bt.indicators.CrossOver(self.bear_sma_fast, self.bear_sma_slow)
        
    def _update_market_state(self):
        if len(self.data) >= 20:
            change_20d = (self.data.close[0] / self.data.close[-20] - 1) * 100
            if change_20d > 12:
                self.market_state = "bull"
            elif change_20d < -12:
                self.market_state = "bear"
            else:
                self.market_state = "normal"
        
    def next(self):
        if self.order:
            return
        self._update_market_state()
        if self.market_state == "bull":
            signal = self.bull_crossover > 0
            exit_signal = self.bull_crossover < 0
        elif self.market_state == "bear":
            signal = self.bear_crossover > 0
            exit_signal = self.bear_crossover < 0
        else:
            signal = self.bull_crossover > 0
            exit_signal = self.bull_crossover < 0
        if not self.position:
            if signal:
                if self.params.position_scale:
                    ratio = {"bull": 0.8, "bear": 0.3}.get(self.market_state, 0.5)
                else:
                    ratio = 0.5
                size = int(self.broker.getcash() / self.data.close[0] * ratio)
                if size > 0:
                    self.order = self.buy(size=size)
        else:
            if exit_signal:
                self.close()
`,
  },
  smart_exit: {
    name: '智能退出策略模板',
    code: `# Name: 智能退出策略
# Description: 基于双均线策略，集成追踪止损、时间退出、硬止损等多种退出机制

import backtrader as bt
from datetime import datetime, date

class SmartExitStrategy(bt.Strategy):
    params = (
        ('fast', 5), ('slow', 20),
        ('trailing_stop_pct', 8.0), ('time_exit_days', 45),
        ('hard_stop_pct', 12.0), ('profit_target', 0.2),
    )
    
    def __init__(self):
        self.order = None
        self.entry_price = None
        self.entry_date = None
        self.peak_price = None
        self.sma_fast = bt.indicators.SimpleMovingAverage(self.datas[0].close, period=self.params.fast)
        self.sma_slow = bt.indicators.SimpleMovingAverage(self.datas[0].close, period=self.params.slow)
        self.crossover = bt.indicators.CrossOver(self.sma_fast, self.sma_slow)
        
    def notify_order(self, order):
        if order.status == order.Completed and order.isbuy():
            self.entry_price = order.executed.price
            self.entry_date = self.data.datetime.date(0)
            self.peak_price = order.executed.price
                
    def next(self):
        if self.order:
            return
        current_price = self.data.close[0]
        if self.peak_price is None or current_price > self.peak_price:
            self.peak_price = current_price
        if not self.position:
            if self.crossover > 0:
                self.order = self.buy()
        else:
            exit_reason = None
            if self.crossover < 0:
                exit_reason = "死叉退出"
            if not exit_reason and self.peak_price and self.params.trailing_stop_pct > 0:
                if current_price < self.peak_price * (1 - self.params.trailing_stop_pct / 100):
                    exit_reason = "追踪止损"
            if not exit_reason and self.entry_price and self.params.hard_stop_pct > 0:
                if current_price < self.entry_price * (1 - self.params.hard_stop_pct / 100):
                    exit_reason = "硬止损"
            if not exit_reason and self.entry_price and self.params.profit_target > 0:
                if (current_price - self.entry_price) / self.entry_price >= self.params.profit_target:
                    exit_reason = "止盈退出"
            if not exit_reason and self.entry_date and self.params.time_exit_days > 0:
                if (self.data.datetime.date(0) - self.entry_date).days > self.params.time_exit_days:
                    exit_reason = "时间退出"
            if exit_reason:
                self.close()
`,
  },
  factor_score: {
    name: '因子评分选股策略模板',
    code: `# Name: 因子评分选股策略
# Description: 基于多因子评分（动量、波动率、成交量、均线）的选股策略

import backtrader as bt
import numpy as np

class FactorScoreStrategy(bt.Strategy):
    params = (
        ("factor_weights", [0.3, 0.3, 0.2, 0.2]),
        ("top_n", 5), ("rebalance_days", 20), ("printlog", False),
    )
    
    def __init__(self):
        self.order = None
        self.bar_count = 0
        self.volatility = bt.indicators.StdDev(self.data.close, period=20)
        self.volume_ma5 = bt.indicators.SMA(self.data.volume, period=5)
        self.volume_ma20 = bt.indicators.SMA(self.data.volume, period=20)
        self.volume_ratio = self.volume_ma5 / self.volume_ma20
        self.ma20 = bt.indicators.SMA(self.data.close, period=20)
        
    def _calc_composite_score(self) -> float:
        momentum_value = 0.0
        if len(self.data) >= 20 and self.data.close[-20] != 0:
            momentum_value = (self.data.close[0] / self.data.close[-20] - 1)
        momentum_score = 1.0 / (1.0 + np.exp(-momentum_value * 10)) if not np.isnan(momentum_value) else 0.5
        volatility_value = self.volatility[0]
        volatility_score = 1.0 - 1.0 / (1.0 + np.exp(-volatility_value * 100)) if not np.isnan(volatility_value) and volatility_value != 0 else 0.5
        volume_ratio_value = self.volume_ratio[0]
        volume_score = 1.0 / (1.0 + np.exp(-volume_ratio_value + 1)) if not np.isnan(volume_ratio_value) and volume_ratio_value != 0 else 0.5
        ma_value = self.ma20[0]
        ma_score = 1.0 if self.data.close[0] > ma_value else 0.0 if not np.isnan(ma_value) and ma_value != 0 else 0.5
        weights = self.params.factor_weights
        return momentum_score * weights[0] + volatility_score * weights[1] + volume_score * weights[2] + ma_score * weights[3]
        
    def next(self):
        if self.order:
            return
        self.bar_count += 1
        if self.bar_count % self.params.rebalance_days == 0:
            score = self._calc_composite_score()
            if not self.position:
                if score > 0.6:
                    self.order = self.buy()
            else:
                if score < 0.4:
                    self.close()
`,
  },
}

/** 所有预置策略的代码映射（供 StrategyEditor 查看代码使用） */
export const PRESET_STRATEGY_CODES: Record<string, string> = {
  'dual_ma': STRATEGY_TEMPLATES.dual_ma.code,
  'macd': `# Name: MACD策略\n# Description: MACD金叉买入，死叉卖出\n\nimport backtrader as bt\n\nclass MACDStrategy(bt.Strategy):\n    params = (("fast_period", 12), ("slow_period", 26), ("signal_period", 9),)\n    \n    def __init__(self):\n        self.macd = bt.indicators.MACD(\n            self.data.close,\n            period_me1=self.params.fast_period,\n            period_me2=self.params.slow_period,\n            period_signal=self.params.signal_period,\n        )\n        self.crossover = bt.indicators.CrossOver(self.macd.macd, self.macd.signal)\n        \n    def next(self):\n        if not self.position:\n            if self.crossover > 0:\n                self.buy()\n        else:\n            if self.crossover < 0:\n                self.close()\n`,
  'rsi': `# Name: RSI策略\n# Description: RSI超买超卖\n\nimport backtrader as bt\n\nclass RSIStrategy(bt.Strategy):\n    params = (("period", 14), ("oversold", 30), ("overbought", 70),)\n    \n    def __init__(self):\n        self.rsi = bt.indicators.RSI(self.data.close, period=self.params.period)\n        \n    def next(self):\n        if not self.position:\n            if self.rsi < self.params.oversold:\n                self.buy()\n        else:\n            if self.rsi > self.params.overbought:\n                self.close()\n`,
  'bollinger': `# Name: 布林带策略\n# Description: 价格触及下轨买入，触及上轨卖出\n\nimport backtrader as bt\n\nclass BollingerStrategy(bt.Strategy):\n    params = (("period", 20), ("dev", 2.0),)\n    \n    def __init__(self):\n        self.boll = bt.indicators.BollingerBands(\n            self.data.close, period=self.params.period, devfactor=self.params.dev)\n        \n    def next(self):\n        if not self.position:\n            if self.data.close[0] < self.boll.lines.bot[0]:\n                self.buy()\n        else:\n            if self.data.close[0] > self.boll.lines.top[0]:\n                self.close()\n`,
  'turtle': `# Name: 海龟交易策略\n# Description: 价格突破N日最高点买入，跌破最低点卖出\n\nimport backtrader as bt\n\nclass TurtleStrategy(bt.Strategy):\n    params = (("n", 20), ("add_n", 10), ("risk_percent", 0.01),)\n    \n    def __init__(self):\n        self.donchian_high = bt.indicators.Highest(self.data.high, period=self.params.n)\n        self.donchian_low = bt.indicators.Lowest(self.data.low, period=self.params.n)\n        \n    def next(self):\n        if not self.position:\n            if self.data.high[0] >= self.donchian_high[-1]:\n                self.buy()\n        else:\n            if self.data.low[0] <= self.donchian_low[-1]:\n                self.close()\n`,
  'kdj': `# Name: KDJ策略\n# Description: KDJ指标金叉死叉\n\nimport backtrader as bt\n\nclass KDJStrategy(bt.Strategy):\n    params = (("period", 9), ("signal_period", 3), ("oversold", 20), ("overbought", 80),)\n    \n    def __init__(self):\n        self.k = bt.indicators.Stochastic(self.data, period=self.params.period)\n        self.d = bt.indicators.Stochastic(self.data, period=self.params.signal_period)\n        self.j = self.k - 2 * (self.k - self.d)\n        \n    def next(self):\n        if not self.position:\n            if self.k > self.d and self.k < self.params.oversold:\n                self.buy()\n        else:\n            if self.k < self.d and self.k > self.params.overbought:\n                self.close()\n`,
  'momentum': `# Name: 动量策略\n# Description: 基于价格动量\n\nimport backtrader as bt\n\nclass MomentumStrategy(bt.Strategy):\n    params = (("period", 20),)\n    \n    def __init__(self):\n        self.momentum = self.data.close - self.data.close(-self.params.period)\n        \n    def next(self):\n        if not self.position:\n            if self.momentum > 0:\n                self.buy()\n        else:\n            if self.momentum < 0:\n                self.close()\n`,
  'grid_trading': `# Name: 网格交易策略\n# Description: 在价格区间内网格交易\n\nimport backtrader as bt\n\nclass GridTradingStrategy(bt.Strategy):\n    params = (("grid_num", 10), ("price_range", 0.1),)\n    \n    def __init__(self):\n        self.grid_prices = []\n        \n    def next(self):\n        # 网格交易逻辑\n        pass\n`,
  'volume_breakout': `# Name: 放量突破策略\n# Description: 成交量放大且价格突破\n\nimport backtrader as bt\n\nclass VolumeBreakoutStrategy(bt.Strategy):\n    params = (("volume_ratio", 2.0), ("period", 20),)\n    \n    def __init__(self):\n        self.volume_ma = bt.indicators.SimpleMovingAverage(self.data.volume, period=self.params.period)\n        \n    def next(self):\n        if not self.position:\n            if self.data.volume[0] > self.volume_ma[0] * self.params.volume_ratio:\n                if self.data.close[0] > self.data.close[-1]:\n                    self.buy()\n        else:\n            if self.data.close[0] < self.data.close[-1]:\n                self.close()\n`,
  'ma_bullish': `# Name: 均线多头排列策略\n# Description: 短期均线 > 中期均线 > 长期均线\n\nimport backtrader as bt\n\nclass MABullishStrategy(bt.Strategy):\n    params = (("fast", 5), ("middle", 10), ("slow", 20),)\n    \n    def __init__(self):\n        self.ma_fast = bt.indicators.SimpleMovingAverage(self.data.close, period=self.params.fast)\n        self.ma_middle = bt.indicators.SimpleMovingAverage(self.data.close, period=self.params.middle)\n        self.ma_slow = bt.indicators.SimpleMovingAverage(self.data.close, period=self.params.slow)\n        \n    def next(self):\n        if not self.position:\n            if self.ma_fast > self.ma_middle > self.ma_slow:\n                self.buy()\n        else:\n            if self.ma_fast < self.ma_middle or self.ma_middle < self.ma_slow:\n                self.close()\n`,
  'mean_reversion': `# Name: 均值回归策略\n# Description: 价格偏离均值后回归\n\nimport backtrader as bt\n\nclass MeanReversionStrategy(bt.Strategy):\n    params = (("period", 20), ("dev", 2.0),)\n    \n    def __init__(self):\n        self.mean = bt.indicators.SimpleMovingAverage(self.data.close, period=self.params.period)\n        self.std = bt.indicators.StandardDeviation(self.data.close, period=self.params.period)\n        \n    def next(self):\n        if not self.position:\n            if self.data.close[0] < self.mean[0] - self.std[0] * self.params.dev:\n                self.buy()\n        else:\n            if self.data.close[0] > self.mean[0] + self.std[0] * self.params.dev:\n                self.close()\n`,
  'adaptive': STRATEGY_TEMPLATES.adaptive.code,
  'smart_exit': STRATEGY_TEMPLATES.smart_exit.code,
  'factor_score': STRATEGY_TEMPLATES.factor_score.code,
  'cci_macd_selection': `# Name: CCI+MACD双因子选股
# Description: 30分钟周期 CCI(14)>阈值（先行动量爆发）且 MACD出现"即将在零线附近金叉"的预兆（DIF在DEA下方但已拐头向上逼近DEA），剔除停牌/ST/成交额过小。短线选股，仅用于选股池与盘中监控，不进回测。

import backtrader as bt

class CCIMACDSelectionStrategy(bt.Strategy):
    params = (
        ("cci_period", 14),
        ("cci_threshold", 300),
        ("macd_fast", 12),
        ("macd_slow", 26),
        ("macd_signal", 9),
        ("zero_line_band", 0.5),
        ("min_amount", 500000000),
        ("exclude_st", True),
        ("exclude_suspended", True),
    )

    def __init__(self):
        self.cci = bt.indicators.CommodityChannelIndex(self.data, period=self.p.cci_period)
        self.macd = bt.indicators.MACD(
            self.data.close,
            period_me1=self.p.macd_fast,
            period_me2=self.p.macd_slow,
            period_signal=self.p.macd_signal,
        )
        self.macd_cross = bt.indicators.CrossOver(self.macd.macd, self.macd.signal)

    def next(self):
        if self.order:
            return
        cci_ok = self.cci[0] > self.p.cci_threshold
        macd_ok = self.macd_cross[0] > 0 and abs(self.macd.macd[0]) <= self.p.zero_line_band
        if not self.position:
            if cci_ok and macd_ok:
                self.order = self.buy()
        else:
            if self.macd_cross[0] < 0:
                self.order = self.close()
`,
}
