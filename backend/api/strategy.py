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
from models.schemas import SaveStrategyRequest

router = APIRouter()


@router.get("/list")
def get_strategies():
    """返回所有策略（预置 + 自定义）及其可配置参数。"""
    return {"status": "ok", "data": list_strategies()}


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
