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
