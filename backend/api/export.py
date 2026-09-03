"""数据导出 API 路由。"""
from __future__ import annotations

import json
import csv
import io
import logging
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from models.schemas import ExportRequest, ExportCsvDataRequest

router = APIRouter()
logger = logging.getLogger("export")


def _content_disposition(filename: str) -> str:
    """生成 Content-Disposition 头，支持中文文件名。

    HTTP 头只能按 latin-1 编码，把中文直接拼进 header 会让响应写出时抛
    ``UnicodeEncodeError: 'latin-1' codec can't encode characters``，
    表现为每次导出都 500——而用户只看到「请稍后重试」，重试多少次都没用。

    按 RFC 5987 处理：
    - ``filename`` 提供 ASCII 回退名（非 ASCII 字符替换为下划线），兼容老客户端；
    - ``filename*=UTF-8''<percent-encoded>`` 给出现代浏览器采用的真实文件名。
    """
    ascii_name = "".join(c if ord(c) < 128 else "_" for c in filename)
    # 回退名不得含引号 / 换行，否则会破坏 header 结构
    ascii_name = ascii_name.replace('"', "").replace("\r", "").replace("\n", "")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


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
        response.headers["Content-Disposition"] = _content_disposition(f"{req.filename}.json")

        return response

    except Exception as e:
        logger.error(f"JSON导出异常: {e}")
        # 给出真实原因：「请稍后重试」会让人以为重试有用，而实际会一直失败
        raise HTTPException(status_code=500, detail=f"JSON导出失败：{e}")


@router.post("/csv")
def export_csv(req: ExportCsvDataRequest):
    """导出为 CSV 格式（适用于交易明细）。"""
    try:
        data = req.data

        # schema 已保证 data 是 list[dict]，这里只需防空
        if not data:
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
        response.headers["Content-Disposition"] = _content_disposition(f"{req.filename}.csv")

        return response

    except ValueError as e:
        # 数据本身的问题属调用方可修正，用 400 明确告知，而不是笼统 500
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"CSV导出异常: {e}")
        raise HTTPException(status_code=500, detail=f"CSV导出失败：{e}")


@router.get("/backtest/{backtest_id}")
def export_backtest_result(backtest_id: str, format: str = "json"):
    """导出回测结果（示例，实际需要先保存回测结果到数据库）。"""
    # 这里只是一个示例，实际实现需要：
    # 1. 从数据库加载回测结果
    # 2. 根据 format 参数返回相应格式
    
    raise HTTPException(status_code=501, detail="此功能尚未实现，请使用前端直接导出")
