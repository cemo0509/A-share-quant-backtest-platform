"""可视化策略编辑器 —— 条件自然语言渲染。

把 ConditionLeaf（内部技术字段）渲染成用户可读的中文描述，
对标东方财富条件选股界面的「自然语言条件」。

输入示例：
    {
      "indicator": "macd_cross", "line": "gold",
      "params": {"fast": 12, "slow": 26, "signal": 9},
      "operator": "equal", "targetType": "value", "targetValue": 1
    }
输出示例：
    "MACD 金叉（DIF 上穿 DEA，快线12 慢线26 信号9）"
"""
from __future__ import annotations

from typing import Any


def _param_str(params: dict[str, Any] | None) -> str:
    """把参数渲染成 '快线12 慢线26 信号9' 形式。"""
    if not params:
        return ""
    label_map = {
        "fast": "快线", "slow": "慢线", "signal": "信号",
        "n": "N", "m1": "M1", "m2": "M2", "std": "std",
        "period": "周期", "dev": "标准差", "smooth_k": "K平滑", "smooth_d": "D平滑",
        "short": "短期", "mid": "中期", "long": "长期",
        "p": "周期", "k": "K",
    }
    parts = []
    for k, v in params.items():
        if v is None:
            continue
        parts.append(f"{label_map.get(k, k)}{v}")
    return " ".join(parts)


def _join_params(params: dict[str, Any] | None) -> str:
    s = _param_str(params)
    return f"（{s}）" if s else ""


# 自然语言模板表（覆盖方案 4.3 全表）。
# 每个模板：(指标key, line, operator) -> 渲染函数(leaf)-> str
# 通过 render_condition_natural 统一调度。
def _render(leaf: dict[str, Any]) -> str:
    indicator = leaf.get("indicator", "")
    line = leaf.get("line", "")
    operator = leaf.get("operator", "")
    params = leaf.get("params") or {}
    target_value = leaf.get("targetValue")
    target_param2 = leaf.get("targetParam2")
    target_indicator = leaf.get("targetIndicator")
    pstr = _join_params(params)

    # ---------- MACD ----------
    if indicator in ("macd", "macd_cross"):
        if line == "gold" or (operator == "equal" and target_value == 1 and line in ("gold", "dif_gold", "")):
            return f"MACD 金叉（DIF 上穿 DEA）{pstr}".rstrip()
        if line == "death" or (operator == "equal" and target_value == -1) or line == "dif_death":
            return f"MACD 死叉（DIF 下穿 DEA）{pstr}".rstrip()
        if operator == "greater":
            return f"DIF 大于 {target_value}{pstr}".rstrip()
        if operator == "less":
            return f"DIF 小于 {target_value}{pstr}".rstrip()
        if operator == "between":
            lo = target_value if target_value is not None else -target_param2
            hi = target_param2 if target_param2 is not None else -target_value
            return f"DIF 在零轴附近（带宽 {max(abs(lo), abs(hi))}）{pstr}".rstrip()
        return f"MACD 条件{_join_params(params)}".rstrip()

    # ---------- MA 均线 ----------
    if indicator == "ma" or indicator == "ema":
        if operator == "cross_up":
            if target_indicator:
                return f"{indicator.upper()} 上穿 {target_indicator.upper()}{pstr}".rstrip()
            return f"MA 上穿{pstr}".rstrip()
        if operator == "cross_down":
            if target_indicator:
                return f"{indicator.upper()} 下穿 {target_indicator.upper()}{pstr}".rstrip()
            return f"MA 下穿{pstr}".rstrip()
        if operator == "greater":
            if target_indicator:
                return f"{indicator.upper()} 大于 {target_indicator.upper()}{pstr}".rstrip()
            return f"{indicator.upper()} 大于 {target_value}{pstr}".rstrip()
        if operator == "less":
            return f"{indicator.upper()} 小于 {target_value}{pstr}".rstrip()
        return f"MA 条件{pstr}".rstrip()

    # 均线多头排列
    if indicator == "ma_arrangement":
        if line == "bull":
            return f"均线多头排列（MA5>MA10>MA20）{pstr}".rstrip()
        if line == "bear":
            return f"均线空头排列（MA5<MA10<MA20）{pstr}".rstrip()
        return f"均线排列{pstr}".rstrip()

    # ---------- KDJ ----------
    if indicator in ("kdj", "kdj_bull"):
        line_label = {"gold": "K 上穿 D（金叉）", "death": "K 下穿 D（死叉）",
                      "k": "K", "d": "D", "j": "J"}.get(line, line)
        if operator == "equal" and target_value == 1:
            return f"KDJ 金叉（K 上穿 D）{pstr}".rstrip()
        if operator == "equal" and target_value == -1:
            return f"KDJ 死叉（K 下穿 D）{pstr}".rstrip()
        if operator == "greater":
            return f"KDJ {line_label} 大于 {target_value}{pstr}".rstrip()
        if operator == "less":
            return f"KDJ {line_label} 小于 {target_value}{pstr}".rstrip()
        return f"KDJ 条件{pstr}".rstrip()

    # ---------- RSI ----------
    if indicator == "rsi":
        if operator == "between":
            if target_value is not None and target_param2 is not None:
                return f"RSI 介于 {target_value} ~ {target_param2}{pstr}".rstrip()
            return f"RSI 介于（未设上下限）{pstr}".rstrip()
        if operator == "cross_up":
            return f"RSI 上穿 {target_value}{pstr}".rstrip()
        if operator == "cross_down":
            return f"RSI 下穿 {target_value}{pstr}".rstrip()
        if operator == "greater":
            return f"RSI 大于 {target_value}{pstr}".rstrip()
        if operator == "less":
            return f"RSI 小于 {target_value}{pstr}".rstrip()
        return f"RSI 条件{pstr}".rstrip()

    # ---------- CCI ----------
    if indicator == "cci":
        if operator == "between":
            if target_value is not None and target_param2 is not None:
                return f"CCI 介于 {target_value} ~ {target_param2}{pstr}".rstrip()
            return f"CCI 介于（未设上下限）{pstr}".rstrip()
        if operator == "greater":
            return f"CCI 大于 {target_value}{pstr}".rstrip()
        if operator == "less":
            return f"CCI 小于 {target_value}{pstr}".rstrip()
        if operator == "cross_up":
            return f"CCI 上穿 {target_value}{pstr}".rstrip()
        if operator == "cross_down":
            return f"CCI 下穿 {target_value}{pstr}".rstrip()
        return f"CCI 条件{pstr}".rstrip()

    # ---------- BOLL ----------
    if indicator == "boll":
        tgt = {"boll_upper": "上轨", "boll_mid": "中轨", "boll_lower": "下轨"}.get(
            target_indicator or line, target_indicator or line)
        if operator == "cross_up":
            return f"价格 上穿 BOLL{tgt}{pstr}".rstrip()
        if operator == "cross_down":
            return f"价格 下穿 BOLL{tgt}{pstr}".rstrip()
        if operator == "greater":
            return f"价格 大于 BOLL{tgt}{pstr}".rstrip()
        if operator == "less":
            return f"价格 小于 BOLL{tgt}{pstr}".rstrip()
        return f"BOLL 条件{pstr}".rstrip()

    # ---------- VOL 成交量 ----------
    if indicator in ("vol", "vol_ratio"):
        if operator == "greater":
            if target_value and target_value >= 1:
                return f"成交量 放量（>{target_value}倍均量）{pstr}".rstrip()
            return f"成交量 大于 {target_value} 日均量{pstr}".rstrip()
        if operator == "less":
            return f"成交量 小于 {target_value} 日均量{pstr}".rstrip()
        return f"成交量 条件{pstr}".rstrip()

    # ---------- 成交额 ----------
    if indicator == "amt":
        if operator == "greater":
            return f"成交额 大于 {target_value} 元".rstrip()
        if operator == "less":
            return f"成交额 小于 {target_value} 元".rstrip()
        return "成交额 条件"

    # ---------- 价格 ----------
    if indicator == "price":
        if operator == "cross_up":
            return "价格 上穿"
        if operator == "cross_down":
            return "价格 下穿"
        if operator == "greater":
            return f"收盘价 大于 {target_value}"
        if operator == "less":
            return f"收盘价 小于 {target_value}"
        return "价格 条件"

    # 兜底：直接展示内部字段，保证不崩
    return f"{indicator}/{line} {operator} {target_value if target_value is not None else ''}".strip()


def render_condition_natural(condition: dict[str, Any]) -> str:
    """把单个 ConditionLeaf 渲染成自然语言描述。

    入参：ConditionLeaf 字典（含 indicator/line/params/operator/targetType/
          targetValue/targetParam2/targetIndicator 等）。
    返回：用户可读的中文条件，例如 "MACD 金叉（DIF 上穿 DEA，快线12 慢线26 信号9）"。
    """
    try:
        return _render(condition)
    except Exception:
        # 渲染失败绝不抛异常，避免前端白屏
        return f"{condition.get('indicator', '未知指标')} 条件"


def render_rule_natural(rule: dict[str, Any]) -> list[dict[str, Any]]:
    """把整条规则树渲染成自然语言列表（供预览区使用）。

    返回：[{ id, text, type, operator, items? }]，递归展开组合。
    """
    def walk(node: dict[str, Any]) -> dict[str, Any] | list[dict[str, Any]]:
        if node.get("type") == "group" or ("operator" in node and "items" in node):
            children = [walk(it) for it in node.get("items", [])]
            flat: list[dict[str, Any]] = []
            for c in children:
                if isinstance(c, list):
                    flat.extend(c)
                elif c:
                    flat.append(c)
            return {
                "id": node.get("id", ""),
                "type": "group",
                "operator": node.get("operator", "AND"),
                "items": flat,
            }
        # 叶子
        return {
            "id": node.get("id", ""),
            "type": "condition",
            "text": render_condition_natural(node),
            "indicator": node.get("indicator", ""),
        }

    res = walk(rule)
    if isinstance(res, dict) and res.get("type") == "group":
        return res.get("items", [])
    if isinstance(res, list):
        return res
    return []
