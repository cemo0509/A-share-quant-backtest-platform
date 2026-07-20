"""可视化策略编辑器 —— 规则存储。

可视化规则以 JSON 形式保存到自定义策略目录，与 Python 自定义策略共用同一目录，
但文件名加 .json 后缀（Python 策略是 .py）。这样在打包环境下也能写到 AppData。
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

logger = logging.getLogger("visual_editor_store")

# 复用 custom_manager 的目录解析逻辑（打包环境 -> AppData）
try:
    from core.strategies.custom_manager import CUSTOM_DIR
except Exception:  # 兜底
    CUSTOM_DIR = Path(__file__).resolve().parent.parent / "strategies" / "custom"


def _rule_dir() -> Path:
    CUSTOM_DIR.mkdir(parents=True, exist_ok=True)
    return CUSTOM_DIR


def _validate_key(key: str) -> bool:
    if not key or len(key) > 128:
        return False
    return bool(re.match(r'^[a-zA-Z0-9_\-]+$', key))


def _filename_from_key(key: str) -> str:
    return f"{key}.json"


def save_visual_rule(key: str, name: str, description: str, rule: dict) -> dict:
    """保存可视化规则。

    rule 为前端构建的条件树（含 operator / items）。
    返回规则元信息。
    """
    if not _validate_key(key):
        raise ValueError(f"无效的策略 key: {key}，仅允许字母、数字、下划线和短横线")
    if not name or not name.strip():
        raise ValueError("策略名称不能为空")

    path = _rule_dir() / _filename_from_key(key)
    payload = {
        "key": key,
        "name": name.strip(),
        "description": (description or "").strip(),
        "category": "visual",
        "rule": rule,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "key": key,
        "name": payload["name"],
        "description": payload["description"],
    }


def load_visual_rule(key: str) -> dict:
    """加载可视化规则，返回完整 payload（含 rule 树）。"""
    if not _validate_key(key):
        raise ValueError(f"无效的策略 key: {key}")
    path = _rule_dir() / _filename_from_key(key)
    if not path.exists():
        raise ValueError(f"可视化策略不存在: {key}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise ValueError(f"可视化策略文件损坏: {key}")
    if data.get("category") != "visual":
        raise ValueError(f"该 key 不是可视化策略: {key}")
    return data


def list_visual_rules() -> list[dict]:
    """列出所有可视化规则元信息。"""
    result = []
    rule_dir = _rule_dir()
    for f in sorted(rule_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if data.get("category") != "visual":
            continue
        result.append({
            "key": data.get("key", f.stem),
            "name": data.get("name", f.stem),
            "description": data.get("description", ""),
            "type": "custom",
        })
    return result


def delete_visual_rule(key: str) -> bool:
    if not _validate_key(key):
        raise ValueError(f"无效的策略 key: {key}")
    path = _rule_dir() / _filename_from_key(key)
    if not path.exists():
        raise ValueError(f"可视化策略不存在: {key}")
    path.unlink()
    return True
