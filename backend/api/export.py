"""数据导出 API 路由。"""
from __future__ import annotations

import json
import csv
import io
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from models.schemas import ExportRequest

router = APIRouter()
logger = logging.getLogger("export")


@router.post("/json")
def export_json(req: ExportRequest):
    """导出为 JSON 格式。"""
    try:
        # 将数据转换为 JSON 字符串
        json_str = json.dumps(req.data, ensure_ascii=False, indent=2)
        
        # 创建流式响应
        response = StreamingResponse(
            iter([json_str]),
            media_type="application/json"
        )
        response.headers["Content-Disposition"] = f"attachment; filename={req.filename}.json"
        
        return response
        
    except Exception as e:
        logger.error(f"JSON导出异常: {e}")
        raise HTTPException(status_code=500, detail="JSON导出失败，请稍后重试")


@router.post("/csv")
def export_csv(req: ExportRequest):
    """导出为 CSV 格式（适用于交易明细）。"""
    try:
        data = req.data
        
        # 检查数据格式
        if not isinstance(data, list) or len(data) == 0:
            raise ValueError("数据必须是非空列表")
        
        # 创建 CSV 字符串
        output = io.StringIO()
        
        # 获取所有可能的字段名
        fieldnames = set()
        for item in data:
            fieldnames.update(item.keys())
        fieldnames = sorted(fieldnames)
        
        # 写入 CSV
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for item in data:
            writer.writerow(item)
        
        # 创建流式响应
        response = StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv"
        )
        response.headers["Content-Disposition"] = f"attachment; filename={req.filename}.csv"
        
        return response
        
    except Exception as e:
        logger.error(f"CSV导出异常: {e}")
        raise HTTPException(status_code=500, detail="CSV导出失败，请稍后重试")


@router.get("/backtest/{backtest_id}")
def export_backtest_result(backtest_id: str, format: str = "json"):
    """导出回测结果（示例，实际需要先保存回测结果到数据库）。"""
    # 这里只是一个示例，实际实现需要：
    # 1. 从数据库加载回测结果
    # 2. 根据 format 参数返回相应格式
    
    raise HTTPException(status_code=501, detail="此功能尚未实现，请使用前端直接导出")
