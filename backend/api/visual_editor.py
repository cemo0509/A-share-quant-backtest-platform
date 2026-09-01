"""可视化策略编辑器相关 API 路由。

提供：
- GET  /api/visual/indicators  — 返回指标分类树与通用选项
- POST /api/visual/save        — 保存可视化规则（JSON）
- GET  /api/visual/load/{key}  — 读取可视化规则
- GET  /api/visual/list        — 列出所有可视化规则
- DEL  /api/visual/{key}       — 删除可视化规则
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.visual_editor.indicators import get_indicator_tree
from core.visual_editor.codegen import generate_and_validate, generate_strategy_code
from core.visual_editor.store import (
    save_visual_rule,
    load_visual_rule,
    list_visual_rules,
    delete_visual_rule,
)
from core.strategies.registry import REGISTRY

router = APIRouter()


class SaveVisualRequest(BaseModel):
    key: str
    name: str
    description: str = ""
    rule: dict[str, Any] = Field(default_factory=dict)


class CodegenRequest(BaseModel):
    """生成策略代码请求（可视化规则 → Backtrader 代码）。"""
    rule: dict[str, Any] = Field(default_factory=dict)
    name: str = "可视化策略"
    description: str = ""
    exit_mode: str = "reverse"  # reverse=条件反向卖出 / hold=只买不卖


class RunVisualRequest(BaseModel):
    """直接运行可视化策略回测。"""
    rule: dict[str, Any] = Field(default_factory=dict)
    name: str = "可视化策略"
    description: str = ""
    exit_mode: str = "reverse"
    symbol: str = ""
    start_date: str = ""
    end_date: str = ""
    params: dict = Field(default_factory=dict)
    cash: float = 1_000_000
    commission: float = 0.0003
    slippage: float = 0.001
    period: str = "daily"
    adjust: str = "qfq"


@router.get("/indicators")
def api_indicators():
    """返回指标分类树与通用选项（周期/操作符/目标类型）。"""
    return {"status": "ok", "data": get_indicator_tree()}


@router.get("/presets")
def api_presets():
    """返回预置策略的「智能推荐」可视化默认规则映射。

    结构：{ presets: {key: {rule, name, recommended_indicators}}, names: {key: name} }
    - rule: 默认条件树（VisualRule），进入编辑器时自动预填
    - recommended_indicators: 该策略推荐的指标白名单（前端指标库两段式用，高亮+折叠）
    只包含注册表中配置了 visual_defaults 的策略。
    """
    presets: dict[str, dict] = {}
    for key, info in REGISTRY.items():
        if info.visual_defaults:
            vd = dict(info.visual_defaults)  # 浅拷贝，避免修改原始
            recommended = vd.pop("recommended_indicators", None)
            presets[key] = {
                "rule": {"operator": vd.get("operator", "AND"), "items": vd.get("items", [])},
                "name": info.name,
                "recommended_indicators": recommended or [],
            }
    return {"status": "ok", "data": {"presets": presets, "names": {k: v["name"] for k, v in presets.items()}}}


@router.get("/list")
def api_list():
    """列出所有可视化规则。"""
    return {"status": "ok", "data": list_visual_rules()}


@router.get("/load/{key}")
def api_load(key: str):
    """读取单个可视化规则（含 rule 树）。"""
    try:
        data = load_visual_rule(key)
        return {"status": "ok", "data": data}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/save")
def api_save(req: SaveVisualRequest):
    """保存可视化规则。"""
    try:
        info = save_visual_rule(req.key, req.name, req.description, req.rule)
        return {"status": "ok", "data": info}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{key}")
def api_delete(key: str):
    """删除可视化规则。"""
    try:
        delete_visual_rule(key)
        return {"status": "ok", "message": "已删除"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ==================== codegen：可视化规则 → 可回测代码 ====================

@router.post("/codegen")
def api_codegen(req: CodegenRequest):
    """把可视化规则树编译成 Backtrader 策略代码。

    让可视化编辑器形成闭环：画完条件即可生成代码并回测，
    而不是停在「保存了但跑不起来」的状态。
    """
    try:
        result = generate_and_validate(
            req.rule, name=req.name, description=req.description
        )
        if not result["valid"]:
            return {
                "status": "error",
                "detail": result["error"] or "无法生成策略代码",
                "data": {"code": result["code"]},
            }
        return {"status": "ok", "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"代码生成失败: {e}")


@router.post("/run")
def api_run_visual(req: RunVisualRequest):
    """直接运行可视化策略回测（生成代码 → 动态加载 → 执行）。

    复用自定义代码回测的路径：load_strategy_from_code() + run_backtest()。
    """
    from core.strategies.custom_manager import load_strategy_from_code
    from core.engine import run_backtest

    try:
        # 1. 生成代码
        gen = generate_and_validate(req.rule, name=req.name, description=req.description)
        if not gen["valid"]:
            raise HTTPException(
                status_code=400,
                detail=gen["error"] or "无法生成策略代码，请检查条件配置",
            )

        # 2. 动态加载策略类（含安全校验）
        try:
            strategy_cls = load_strategy_from_code(gen["code"])
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # 3. 执行回测
        try:
            result = run_backtest(
                strategy_cls=strategy_cls,
                symbol=req.symbol,
                start_date=req.start_date,
                end_date=req.end_date,
                params=req.params,
                cash=req.cash,
                commission=req.commission,
                slippage=req.slippage,
                period=req.period,
                adjust=req.adjust,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # 附带生成的代码，便于用户查看/复制到自定义策略
        result["generated_code"] = gen["code"]
        return {"status": "ok", "data": result}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"可视化策略回测失败: {e}")
