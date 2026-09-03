"""可视化策略编辑器 —— 代码生成（codegen）。

把条件树（VisualRule）编译成可直接回测的 Backtrader 策略代码，
让可视化编辑器从「画完不能跑」变成完整闭环：

    拖拽配置条件 → 生成 Backtrader 代码 → 立即回测

设计要点
--------
1. **买卖信号成对生成**：每个方向性条件（金叉/上穿）同时生成买入与卖出
   表达式（金叉买入、死叉卖出），非方向性条件（如 RSI 介于）卖出用取反。
2. **指标按需实例化**：只有条件树里真正用到的指标才会出现在 ``__init__``，
   并且相同参数复用同一个实例（用签名去重），避免重复计算。
3. **生成代码即可执行**：输出遵循 custom_manager 的安全约束
   （仅 import backtrader，无 os/sys 等），可直接交给
   ``load_strategy_from_code()`` 动态加载。
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("visual_codegen")

# ==================== 指标编译 ====================
# 每个编译函数返回 (init_lines, expr)
#   init_lines: 写入 __init__ 的代码行
#   expr      : next() 中引用该指标当前值的表达式


def _num(value: Any, default: float = 0.0) -> float:
    """安全转数字（前端可能传 None 或字符串）。"""
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


class _CodegenContext:
    """编译上下文：管理变量命名、指标去重、初始化代码收集。"""

    def __init__(self) -> None:
        self.init_lines: list[str] = []
        self._indicator_cache: dict[str, str] = {}  # 指标签名 -> 变量名
        self._seq = 0
        # A-01：登记所有「退化」的条件（无法编译、被占位值悄悄替换的）。
        # 编译结束后若非空，generate_strategy_code 会直接报错，
        # 绝不交付一份看似正常、实则条件已被改写的策略。
        self.degraded: list[str] = []

    def next_var(self, prefix: str = "ind") -> str:
        self._seq += 1
        return f"self._{prefix}_{self._seq}"

    def get_or_create(self, signature: str, factory) -> str:
        """按签名复用指标实例，避免相同参数重复计算。

        factory 约定返回 ``(init_lines, var_name)``。
        """
        if signature in self._indicator_cache:
            return self._indicator_cache[signature]
        lines, var = factory(self.next_var())
        if isinstance(lines, str):  # 防御：单个字符串也接受
            lines = [lines]
        self.init_lines.extend(lines)
        self._indicator_cache[signature] = var
        return var


def _compile_ma(ctx: _CodegenContext, leaf: dict) -> str:
    period = _int(leaf.get("params", {}).get("period"), 5)
    return ctx.get_or_create(
        f"ma_{period}",
        lambda v: ([f"{v} = bt.indicators.SMA(self.data.close, period={period})"], v),
    )


def _compile_ema(ctx: _CodegenContext, leaf: dict) -> str:
    period = _int(leaf.get("params", {}).get("period"), 12)
    return ctx.get_or_create(
        f"ema_{period}",
        lambda v: ([f"{v} = bt.indicators.EMA(self.data.close, period={period})"], v),
    )


def _compile_macd(ctx: _CodegenContext, leaf: dict) -> str:
    """MACD：返回线表达式（dif / dea / histo）。"""
    p = leaf.get("params", {}) or {}
    fast = _int(p.get("fast"), 12)
    slow = _int(p.get("slow"), 26)
    signal = _int(p.get("signal"), 9)
    line = leaf.get("line", "dif")

    var = ctx.get_or_create(
        f"macd_{fast}_{slow}_{signal}",
        lambda v: ([
            f"{v} = bt.indicators.MACD("
            f"self.data.close, period_me1={fast}, period_me2={slow}, "
            f"period_signal={signal})"
        ], v),
    )
    # backtrader MACD 的线：macd=DIF, signal=DEA, histo=MACD柱
    attr = {"dif": "macd", "dea": "signal", "macd": "histo"}.get(line, "macd")
    return f"{var}.{attr}"


def _compile_kdj(ctx: _CodegenContext, leaf: dict) -> str:
    p = leaf.get("params", {}) or {}
    period = _int(p.get("period"), 9)
    k = _int(p.get("smooth_k"), 3)
    d = _int(p.get("smooth_d"), 3)
    line = leaf.get("line", "k")

    var = ctx.get_or_create(
        f"kdj_{period}_{k}_{d}",
        lambda v: ([
            f"{v} = bt.indicators.Stochastic("
            f"self.data, period={period}, period_dfast={k}, period_dslow={d})"
        ], v),
    )
    attr = {"k": "percK", "d": "percD", "j": "percK"}.get(line, "percK")
    return f"{var}.{attr}"


def _compile_boll(ctx: _CodegenContext, leaf: dict) -> str:
    p = leaf.get("params", {}) or {}
    period = _int(p.get("period"), 20)
    dev = _num(p.get("dev"), 2.0)
    line = leaf.get("line", "mid")

    var = ctx.get_or_create(
        f"boll_{period}_{dev}",
        lambda v: ([
            f"{v} = bt.indicators.BollingerBands("
            f"self.data.close, period={period}, devfactor={dev})"
        ], v),
    )
    attr = {"upper": "top", "mid": "mid", "lower": "bot"}.get(line, "mid")
    return f"{var}.{attr}"


def _compile_rsi(ctx: _CodegenContext, leaf: dict) -> str:
    period = _int(leaf.get("params", {}).get("period"), 14)
    return ctx.get_or_create(
        f"rsi_{period}",
        lambda v: ([f"{v} = bt.indicators.RSI(self.data.close, period={period})"], v),
    )


def _compile_cci(ctx: _CodegenContext, leaf: dict) -> str:
    period = _int(leaf.get("params", {}).get("period"), 14)
    return ctx.get_or_create(
        f"cci_{period}",
        lambda v: ([f"{v} = bt.indicators.CCI(self.data, period={period})"], v),
    )


def _compile_wr(ctx: _CodegenContext, leaf: dict) -> str:
    period = _int(leaf.get("params", {}).get("period"), 10)
    return ctx.get_or_create(
        f"wr_{period}",
        lambda v: ([f"{v} = bt.indicators.WilliamsR(self.data, period={period})"], v),
    )


def _compile_bias(ctx: _CodegenContext, leaf: dict) -> str:
    """乖离率：(收盘价 - MA) / MA * 100。"""
    period = _int(leaf.get("params", {}).get("period"), 6)
    ma_var = _compile_ma(ctx, {"params": {"period": period}})
    var = ctx.get_or_create(
        f"bias_{period}",
        lambda v: ([
            f"{v} = (self.data.close - {ma_var}) / {ma_var} * 100.0"
        ], v),
    )
    return var


def _compile_vol(ctx: _CodegenContext, leaf: dict) -> str:
    """成交量：line=ma 时为均量线，否则为当日成交量。"""
    if leaf.get("line") == "ma":
        period = _int(leaf.get("params", {}).get("period"), 5)
        return ctx.get_or_create(
            f"volma_{period}",
            lambda v: ([
                f"{v} = bt.indicators.SMA(self.data.volume, period={period})"
            ], v),
        )
    return "self.data.volume"


def _compile_vol_ratio(ctx: _CodegenContext, leaf: dict) -> str:
    """量比：当日成交量 / 过去 N 日均量。"""
    period = _int(leaf.get("params", {}).get("period"), 5)
    ma_var = ctx.get_or_create(
        f"volma_{period}",
        lambda v: ([f"{v} = bt.indicators.SMA(self.data.volume, period={period})"], v),
    )
    var = ctx.get_or_create(
        f"volratio_{period}",
        lambda v: ([
            f"{v} = self.data.volume / {ma_var}"
        ], v),
    )
    return var


def _compile_obv(ctx: _CodegenContext, leaf: dict) -> str:
    return ctx.get_or_create(
        "obv",
        lambda v: ([f"{v} = bt.indicators.OBV(self.data)"], v),
    )


def _compile_amt(ctx: _CodegenContext, leaf: dict) -> str:
    """成交额（近似）：成交量 × 收盘价。"""
    return ctx.get_or_create(
        "amt",
        lambda v: ([f"{v} = self.data.volume * self.data.close"], v),
    )


def _compile_turnover(ctx: _CodegenContext, leaf: dict) -> str:
    """换手率占位：数据无流通股本，用成交量/均量×100 近似。"""
    period = _int(leaf.get("params", {}).get("period"), 5)
    ma_var = ctx.get_or_create(
        f"volma_{period}",
        lambda v: ([f"{v} = bt.indicators.SMA(self.data.volume, period={period})"], v),
    )
    var = ctx.get_or_create(
        f"turnover_{period}",
        lambda v: ([f"{v} = self.data.volume / {ma_var} * 100.0"], v),
    )
    return var


def _compile_price(ctx: _CodegenContext, leaf: dict) -> str:
    line = leaf.get("line", "close")
    return {
        "close": "self.data.close",
        "open": "self.data.open",
        "high": "self.data.high",
        "low": "self.data.low",
    }.get(line, "self.data.close")


def _compile_high_low_range(ctx: _CodegenContext, leaf: dict) -> str:
    """振幅：(最高 - 最低) / 昨收 × 100。"""
    return ctx.get_or_create(
        "range",
        lambda v: ([
            f"{v} = (self.data.high - self.data.low) / self.data.close(-1) * 100.0"
        ], v),
    )


def _compile_rise_rate(ctx: _CodegenContext, leaf: dict) -> str:
    """涨跌幅：(今收 - 昨收) / 昨收 × 100。"""
    return ctx.get_or_create(
        "rise",
        lambda v: ([
            f"{v} = (self.data.close - self.data.close(-1)) / self.data.close(-1) * 100.0"
        ], v),
    )


def _compile_new_high(ctx: _CodegenContext, leaf: dict) -> str:
    """N 日新高：最高价 >= 过去 N 日最高（不含当日则用 -1 偏移）。"""
    period = _int(leaf.get("params", {}).get("period"), 20)
    return ctx.get_or_create(
        f"newhigh_{period}",
        lambda v: ([
            f"{v} = bt.indicators.Highest(self.data.high, period={period}, plot=False)"
        ], v),
    )


def _compile_new_low(ctx: _CodegenContext, leaf: dict) -> str:
    period = _int(leaf.get("params", {}).get("period"), 20)
    return ctx.get_or_create(
        f"newlow_{period}",
        lambda v: ([
            f"{v} = bt.indicators.Lowest(self.data.low, period={period}, plot=False)"
        ], v),
    )


def _compile_ma_arrangement(ctx: _CodegenContext, leaf: dict) -> str:
    """均线多头排列：MAfast > MAmid > MAslow，输出 1/0。"""
    p = leaf.get("params", {}) or {}
    fast = _int(p.get("fast"), 5)
    mid = _int(p.get("mid"), 10)
    slow = _int(p.get("slow"), 20)
    ma_fast = _compile_ma(ctx, {"params": {"period": fast}})
    ma_mid = _compile_ma(ctx, {"params": {"period": mid}})
    ma_slow = _compile_ma(ctx, {"params": {"period": slow}})
    var = ctx.get_or_create(
        f"arr_{fast}_{mid}_{slow}",
        lambda v: ([
            f"{v} = ({ma_fast} > {ma_mid}) * ({ma_mid} > {ma_slow})"
        ], v),
    )
    return var


# 指标 key -> 编译函数
_INDICATOR_COMPILERS = {
    "ma": _compile_ma,
    "ema": _compile_ema,
    "macd": _compile_macd,
    "macd_cross": _compile_macd,
    "kdj": _compile_kdj,
    "kdj_bull": _compile_kdj,
    "boll": _compile_boll,
    "rsi": _compile_rsi,
    "cci": _compile_cci,
    "wr": _compile_wr,
    "bias": _compile_bias,
    "vol": _compile_vol,
    "vol_ratio": _compile_vol_ratio,
    "obv": _compile_obv,
    "amt": _compile_amt,
    "turnover": _compile_turnover,
    "price": _compile_price,
    "high_low_range": _compile_high_low_range,
    "rise_rate": _compile_rise_rate,
    "new_high": _compile_new_high,
    "new_low": _compile_new_low,
    "ma_arrangement": _compile_ma_arrangement,
}


# ==================== 条件编译 ====================

def _parse_target_indicator(target: str) -> tuple[str, int | None]:
    """解析目标指标标识，如 ``ma20`` -> ``("ma", 20)``，``ma`` -> ``("ma", None)``。

    前端在「另一指标」下拉里用的是带周期的标识（ma5/ma10/ma20），
    需要从中还原出指标 key 与周期，否则 MA5 上穿 MA20 会被编译成
    MA5 上穿 MA5（复用同一个参数）。
    """
    import re

    m = re.match(r"^([a-zA-Z_]+?)(\d+)?$", target or "")
    if not m:
        return (target or "", None)
    key = m.group(1)
    period = int(m.group(2)) if m.group(2) else None
    return (key, period)


def _target_expr(ctx: _CodegenContext, leaf: dict, as_line: bool = False) -> str:
    """编译比较目标（右侧值）。

    Args:
        as_line: True 时返回 Line 对象表达式（不带 [0]），
                 用于 CrossOver 等需要 Line 而非数值的场合。
    """
    ttype = leaf.get("targetType", "value")

    if ttype == "price":
        return "self.data.close" if as_line else "self.data.close[0]"

    if ttype == "indicator":
        # 目标是另一个指标：用 targetIndicator 还原指标与周期
        key, period = _parse_target_indicator(leaf.get("targetIndicator", ""))
        target_params = {"period": period} if period is not None else (leaf.get("params") or {})
        target_leaf = {
            "indicator": key,
            "line": leaf.get("targetLine") or leaf.get("line", ""),
            "params": target_params,
        }
        compiler = _INDICATOR_COMPILERS.get(key)
        if compiler:
            expr = compiler(ctx, target_leaf)
            return expr if as_line else f"{expr}[0]"
        # A-01：无法编译的目标不再「静默」退化为常数 0。
        # 那会让 `MA5 > 0.0` 这类条件恒真（价格恒 > 0），策略退化成「有钱就买」，
        # 照样产出完整指标、资金曲线和交易明细，看起来完全正常
        # ——这是污染结论本身，不是锦上添花的降级。
        # 仍返回占位值以保证语法完整，但登记退化，由入口统一报错。
        ctx.degraded.append(
            f"比较目标「{leaf.get('targetIndicator') or key}」无法编译"
            f"（若取 0 会使条件恒真，已拒绝生成）"
        )
        return "0.0"

    # 常数
    return f"{_num(leaf.get('targetValue'), 0.0)}"


def _compile_leaf(ctx: _CodegenContext, leaf: dict) -> tuple[str, str]:
    """编译单个叶子条件，返回 (买入表达式, 卖出表达式)。"""
    indicator = leaf.get("indicator", "")
    operator = leaf.get("operator", "greater")
    compiler = _INDICATOR_COMPILERS.get(indicator)

    if compiler is None:
        # A-01：不支持的指标。仍返回恒不成立表达式以保证语法完整，
        # 但必须登记——多条件时若只有部分失效，整体 buy_expr 并非 "False"，
        # 入口那条检查抓不到，就会交付一份条件被悄悄改写的策略。
        ctx.degraded.append(f"不支持的指标「{indicator}」")
        logger.warning(f"codegen: 不支持的指标 {indicator}")
        return ("False", "False")

    left_base = compiler(ctx, leaf)
    left = f"{left_base}[0]"
    prev = f"{left_base}[-1]" if not left_base.startswith("self.data.") else f"{left_base}(-1)"

    # ---- 交叉类 ----
    if operator in ("cross_up", "cross_down"):
        # 常数目标：CrossOver 需要 Line 对象，常数不行，
        # 改用「前值在阈值一侧、当前值在另一侧」的比较实现。
        if _is_constant_target(leaf):
            tv = _num(leaf.get("targetValue"), 0.0)
            if operator == "cross_up":
                return (f"({prev} <= {tv} and {left} > {tv})",
                        f"({prev} >= {tv} and {left} < {tv})")
            return (f"({prev} >= {tv} and {left} < {tv})",
                    f"({prev} <= {tv} and {left} > {tv})")

        # 指标/价格目标：用真正的 CrossOver(Line, Line)
        target_line = _target_expr(ctx, leaf, as_line=True)
        sig = f"cross_{left_base}_{target_line}"
        cross_var = ctx.get_or_create(
            sig,
            lambda v: ([f"{v} = bt.indicators.CrossOver({left_base}, {target_line})"], v),
        )
        if operator == "cross_up":
            return (f"({cross_var}[0] > 0)", f"({cross_var}[0] < 0)")
        return (f"({cross_var}[0] < 0)", f"({cross_var}[0] > 0)")

    # ---- 金叉/死叉（equal + targetValue=1/-1）----
    if operator == "equal":
        tv = _num(leaf.get("targetValue"), 0.0)
        line = leaf.get("line", "")
        # MACD / KDJ 的 gold/death 语义：等价于 DIF 上穿 DEA / K 上穿 D
        if line in ("gold", "death") or (indicator in ("macd_cross", "kdj_bull")):
            buy, sell = _compile_golden_cross(ctx, leaf, indicator)
            if line == "death" or tv == -1:
                return (sell, buy)  # 死叉条件：买入=死叉，卖出=金叉
            return (buy, sell)
        return (f"({left} == {tv})", f"({left} != {tv})")

    # ---- 区间 ----
    if operator == "between":
        lo = _num(leaf.get("targetValue"), 0.0)
        hi = _num(leaf.get("targetParam2"), 0.0)
        if lo > hi:
            lo, hi = hi, lo
        return (f"({lo} <= {left} <= {hi})", f"not ({lo} <= {left} <= {hi})")

    # ---- 大小比较 ----
    target = _target_expr(ctx, leaf)
    if operator == "greater":
        return (f"({left} > {target})", f"({left} <= {target})")
    if operator == "less":
        return (f"({left} < {target})", f"({left} >= {target})")

    # A-01：兜底（运算符未覆盖）。同样登记，理由同上。
    ctx.degraded.append(f"不支持的运算符「{operator}」（指标 {indicator}）")
    return ("False", "False")


def _is_constant_target(leaf: dict) -> bool:
    """目标是否为常数（常数目标不能用 CrossOver(Line, float)）。"""
    return leaf.get("targetType", "value") == "value"


def _compile_golden_cross(ctx: _CodegenContext, leaf: dict, indicator: str) -> tuple[str, str]:
    """为金叉/死叉类条件生成 (金叉表达式, 死叉表达式)。"""
    if indicator in ("macd", "macd_cross"):
        dif_base = ctx.get_or_create(
            f"macd_{_int(leaf.get('params', {}).get('fast'), 12)}_"
            f"{_int(leaf.get('params', {}).get('slow'), 26)}_"
            f"{_int(leaf.get('params', {}).get('signal'), 9)}",
            lambda v: ([
                f"{v} = bt.indicators.MACD("
                f"self.data.close, "
                f"period_me1={_int(leaf.get('params', {}).get('fast'), 12)}, "
                f"period_me2={_int(leaf.get('params', {}).get('slow'), 26)}, "
                f"period_signal={_int(leaf.get('params', {}).get('signal'), 9)})"
            ], v),
        )
        sig = f"macdcross_{dif_base}"
        cross_var = ctx.get_or_create(
            sig,
            lambda v: ([f"{v} = bt.indicators.CrossOver({dif_base}.macd, {dif_base}.signal)"], v),
        )
        return (f"({cross_var}[0] > 0)", f"({cross_var}[0] < 0)")

    if indicator in ("kdj", "kdj_bull"):
        p = leaf.get("params", {}) or {}
        k_var = ctx.get_or_create(
            f"kdj_{_int(p.get('period'), 9)}_{_int(p.get('smooth_k'), 3)}_{_int(p.get('smooth_d'), 3)}",
            lambda v: ([
                f"{v} = bt.indicators.Stochastic("
                f"self.data, period={_int(p.get('period'), 9)}, "
                f"period_dfast={_int(p.get('smooth_k'), 3)}, "
                f"period_dslow={_int(p.get('smooth_d'), 3)})"
            ], v),
        )
        cross_var = ctx.get_or_create(
            f"kdjcross_{k_var}",
            lambda v: ([f"{v} = bt.indicators.CrossOver({k_var}.percK, {k_var}.percD)"], v),
        )
        return (f"({cross_var}[0] > 0)", f"({cross_var}[0] < 0)")

    # A-01：金叉/死叉分支未覆盖到，登记退化
    ctx.degraded.append(f"指标「{indicator}」不支持金叉/死叉比较")
    return ("False", "False")


def _compile_node(ctx: _CodegenContext, node: dict) -> tuple[str, str]:
    """递归编译节点（叶子或组合），返回 (买入表达式, 卖出表达式)。"""
    if not node:
        ctx.degraded.append("存在空的条件节点")
        return ("False", "False")

    # 组合节点
    if node.get("type") == "group" or "items" in node:
        items = node.get("items") or []
        if not items:
            ctx.degraded.append("存在空的条件组合（未添加子条件）")
            return ("False", "False")
        op = (node.get("operator") or "AND").upper()
        joiner = " and " if op == "AND" else " or "
        # 组合内：买入用 AND/OR 连接；卖出用反向连接词（德摩根）
        # AND 的否定是 OR，OR 的否定是 AND
        sell_joiner = " or " if op == "AND" else " and "
        buys, sells = [], []
        for it in items:
            b, s = _compile_node(ctx, it)
            buys.append(b)
            sells.append(s)
        return (
            "(" + joiner.join(buys) + ")",
            "(" + sell_joiner.join(sells) + ")",
        )

    # 叶子节点
    return _compile_leaf(ctx, node)


# ==================== 策略代码生成 ====================

def generate_strategy_code(
    rule: dict,
    name: str = "可视化策略",
    description: str = "",
    exit_mode: str = "reverse",
) -> str:
    """把可视化规则树编译成 Backtrader 策略代码。

    Args:
        rule: VisualRule，形如 {"operator": "AND", "items": [...], "global": {...}}
        name: 策略名称（写入 # Name: 注释）
        description: 策略描述（写入 # Description: 注释）
        exit_mode: 卖出方式
            - "reverse"：条件反向时卖出（默认，金叉买/死叉卖）
            - "hold"   ：只买不卖（买入持有）

    Returns:
        Backtrader 策略代码字符串，可直接交给 load_strategy_from_code()

    Raises:
        ValueError: 规则为空或无法生成有效条件
    """
    if not rule or not rule.get("items"):
        raise ValueError("可视化规则为空，请先添加至少一个条件")

    ctx = _CodegenContext()
    root = {"type": "group", "operator": rule.get("operator", "AND"), "items": rule["items"]}
    buy_expr, sell_expr = _compile_node(ctx, root)

    # A-01：只要有任何一处条件退化过，就拒绝生成。
    # 此前只检查 buy_expr 是否整体为 "False"，因此「多条件中仅部分失效」
    # 和「比较目标取 0 导致恒真」两种情况都抓不到，用户会拿到一份
    # status: ok、指标齐全、曲线完整，但买入条件已被悄悄改写的策略。
    if ctx.degraded:
        detail = "；".join(dict.fromkeys(ctx.degraded))  # 去重且保序
        raise ValueError(
            f"可视化规则中有 {len(ctx.degraded)} 处条件无法编译：{detail}。"
            f"为避免生成「看似正常实则错误」的策略，已拒绝生成代码，请修正这些条件后重试。"
        )

    if buy_expr in ("False", "(False)"):
        raise ValueError("未能从可视化规则生成有效的买入条件，请检查条件配置")

    safe_name = (name or "可视化策略").replace("\n", " ").strip()
    safe_desc = (description or "").replace("\n", " ").strip()

    init_block = "\n".join(f"        {line}" for line in ctx.init_lines) or "        pass"

    if exit_mode == "hold":
        next_block = f"""        if self.order:
            return

        if not self.position:
            if {buy_expr}:
                self.order = self.buy()"""
    else:
        # 卖出：条件反向成立时清仓（金叉买 → 死叉卖）
        next_block = f"""        if self.order:
            return

        if not self.position:
            # 买入信号：条件成立
            if {buy_expr}:
                self.order = self.buy()
        else:
            # 卖出信号：条件反向成立
            if {sell_expr}:
                self.order = self.sell(size=self.position.size)"""

    code = f'''# Name: {safe_name}
# Description: {safe_desc}
"""由可视化策略编辑器自动生成（codegen）。

生成时间：自动
策略名称：{safe_name}
生成说明：本文件由可视化条件树编译而来，可直接在「自定义代码回测」中运行。
"""
from __future__ import annotations

import backtrader as bt


class VisualGeneratedStrategy(bt.Strategy):
    """可视化编辑器生成的策略（{safe_name}）。"""

    params = (
        ("printlog", False),
    )

    def __init__(self):
        super().__init__()
        self.order = None
{init_block}

    def next(self):
{next_block}

    def log(self, txt: str) -> None:
        if self.params.printlog:
            dt = self.datas[0].datetime.date(0)
            print(f"{{dt.isoformat()}}, {{txt}}")

    def notify_order(self, order):
        if order.status in (order.Submitted, order.Accepted):
            return

        if order.status == order.Completed:
            if order.isbuy():
                self.log(
                    f"买入 价格={{order.executed.price:.2f}} "
                    f"数量={{order.executed.size:.0f}}"
                )
            elif order.issell():
                self.log(
                    f"卖出 价格={{order.executed.price:.2f}} "
                    f"数量={{order.executed.size:.0f}}"
                )
        elif order.status in (order.Canceled, order.Margin, order.Rejected):
            self.log("订单 取消/拒绝")

        self.order = None
'''
    return code


def generate_and_validate(rule: dict, name: str = "可视化策略", description: str = "") -> dict:
    """生成代码并做语法校验，返回 {code, lines, valid, error}。

    校验用 ast.parse，确保生成的代码不会因为语法错误
    在回测阶段才炸掉（提前暴露问题）。
    """
    import ast

    try:
        code = generate_strategy_code(rule, name=name, description=description)
    except ValueError as e:
        return {"code": "", "lines": 0, "valid": False, "error": str(e)}

    try:
        ast.parse(code)
    except SyntaxError as e:
        logger.error(f"codegen 生成的代码存在语法错误: {e}")
        return {"code": code, "lines": len(code.splitlines()), "valid": False,
                "error": f"生成的代码存在语法错误: {e}"}

    return {"code": code, "lines": len(code.splitlines()), "valid": True, "error": None}
