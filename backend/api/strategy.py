"""策略管理相关 API 路由。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from core.strategies.registry import list_strategies, get_strategy
from core.strategies.custom_manager import (
    save_custom_strategy,
    get_custom_strategy_code,
    delete_custom_strategy,
    list_custom_strategies,
)
from core.strategies.variant_manager import save_variant, delete_variant, get_variant
from models.schemas import SaveStrategyRequest, VariantSaveRequest

router = APIRouter()


@router.get("/list")
def get_strategies():
    """返回所有策略（预置 + 自定义）及其可配置参数。"""
    return {"status": "ok", "data": list_strategies()}


@router.post("/variant/save")
def save_variant_api(req: VariantSaveRequest):
    """保存参数化策略变体：预置策略 key + 参数字典 → 一条新策略。

    原预置策略保持不变（「另存为」语义），新策略可被列表返回、可被回测调用。
    """
    try:
        info = save_variant(req.key, req.name, req.base_key, req.params, req.description)
        return {"status": "ok", "data": info}
    except ValueError as e:
        # 参数/命名问题属调用方可修正，用 400 明确告知而非 500
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/variant/{key}")
def delete_variant_api(key: str):
    """删除参数化策略变体。"""
    try:
        delete_variant(key)
        return {"status": "ok", "message": "策略已删除"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{key}")
def get_strategy_detail(key: str):
    """返回单个策略的详细信息。"""
    try:
        info = get_strategy(key)
        return {
            "status": "ok",
            "data": {
                "key": info.key,
                "name": info.name,
                "description": info.description,
                "category": info.category,
                "params": info.params,
                "is_custom": info.is_custom,
            },
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail="策略不存在")


@router.get("/custom/{key}/code")
def get_custom_strategy_code_api(key: str):
    """获取自定义策略的源代码。"""
    try:
        code = get_custom_strategy_code(key)
        return {"status": "ok", "data": {"code": code}}
    except ValueError as e:
        raise HTTPException(status_code=404, detail="自定义策略不存在")


@router.post("/custom/save")
def save_custom_strategy_api(req: SaveStrategyRequest):
    """保存自定义策略。"""
    try:
        info = save_custom_strategy(req.key, req.code)
        return {"status": "ok", "data": info}
    except ValueError as e:
        raise HTTPException(status_code=400, detail="策略代码无效，请检查语法和安全性")


@router.delete("/custom/{key}")
def delete_custom_strategy_api(key: str):
    """删除自定义策略。"""
    try:
        delete_custom_strategy(key)
        return {"status": "ok", "message": "策略已删除"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail="策略不存在或无法删除")
