"""参数化策略变体管理：把「预置策略 + 一组参数」固化成一条独立策略。

与 custom_manager（存 Python 源码）的区别：
- custom_manager 存**代码**，需要 AST 校验 + 受限沙箱动态加载，重且面大；
- 变体只存**「基础策略 key + 参数字典」**，不存任何代码：
  · 加载时直接复用 REGISTRY 里已验证过的策略类，没有代码注入风险；
  · 回测时把固化参数注入即可（engine 已有「按策略类声明过滤参数」的保护）；
  · 原预置策略完全不受影响——变体只是只读引用它，不修改它。

存储：``variants/<key>.json``，一个变体一个文件，便于备份 / 删除 / 列举。
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Optional

_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")

_VARIANT_DIR = Path(__file__).parent / "variants"

logger = logging.getLogger("variant_manager")


def _ensure_dir() -> None:
    _VARIANT_DIR.mkdir(parents=True, exist_ok=True)


def _path(key: str) -> Path:
    return _VARIANT_DIR / f"{key}.json"


def _validate_key(key: str) -> None:
    """key 会作为文件名，必须严格限制字符集，避免路径穿越。"""
    if not _KEY_RE.match(key or ""):
        raise ValueError(
            "策略 key 只能包含字母、数字、下划线和连字符，且以字母开头（最长 64 字符）"
        )


def _read(key: str) -> Optional[dict]:
    p = _path(key)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:  # 文件损坏不应拖垮整个策略列表
        logger.error("变体文件损坏 %s: %s", p, e)
        return None


def get_variant(key: str) -> Optional[dict]:
    """读取单个变体；不存在或损坏返回 None。"""
    return _read(key)


def list_variants() -> list[dict]:
    """列出全部变体（按 key 排序）。损坏文件跳过，不抛异常。"""
    if not _VARIANT_DIR.exists():
        return []
    out: list[dict] = []
    for p in sorted(_VARIANT_DIR.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error("跳过损坏的变体文件 %s: %s", p, e)
            continue
        if isinstance(data, dict) and data.get("key"):
            out.append(data)
    return out


def save_variant(
    key: str,
    name: str,
    base_key: str,
    params: dict,
    description: str = "",
) -> dict:
    """保存一个参数化变体。

    校验链（任一项不满足即抛 ValueError，由 API 层转成 400）：
    1. key 字符集合法；
    2. base_key 必须是**预置策略**（不允许基于自定义/变体，避免多层嵌套难以追踪）；
    3. params 的键必须都在基础策略声明的参数内（挡住未知参数注入）；
    4. key 不得与预置策略、已有变体、已有自定义策略冲突 —— 「另存为」语义要求
       原策略保持不变，撞名覆盖会破坏这个保证。
    """
    _validate_key(key)

    # 延迟导入：registry 会在模块级导入本模块，避免循环依赖
    from .registry import REGISTRY

    if base_key not in REGISTRY:
        raise ValueError(f"基础策略不存在或不是预置策略: {base_key}")

    base_params = REGISTRY[base_key].params or []
    declared = {p.get("name") for p in base_params}
    unknown = sorted(set(params or {}) - declared)
    if unknown:
        raise ValueError(f"未知参数（不属于 {base_key}）: {unknown}")

    if key in REGISTRY:
        raise ValueError(f"「{key}」是预置策略，不能覆盖，请换一个名字")

    if _path(key).exists():
        raise ValueError(f"已存在同名策略「{key}」，请换一个名字")

    try:
        from .custom_manager import list_custom_strategies

        if any(s.get("key") == key for s in list_custom_strategies()):
            raise ValueError(f"已存在同名自定义策略「{key}」，请换一个名字")
    except ValueError:
        raise
    except Exception:
        # 自定义策略列举失败不应阻断变体保存
        pass

    data = {
        "key": key,
        "name": name or key,
        "description": description or "",
        "base_key": base_key,
        "params": dict(params or {}),
        "type": "variant",
    }

    _ensure_dir()
    p = _path(key)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("保存参数化变体: %s (base=%s)", key, base_key)
    return data


def delete_variant(key: str) -> None:
    """删除变体；不存在则抛 ValueError。"""
    p = _path(key)
    if not p.exists():
        raise ValueError(f"变体不存在: {key}")
    p.unlink()
    logger.info("删除参数化变体: %s", key)


def build_params_with_defaults(base_key: str, overrides: dict) -> list[dict]:
    """把基础策略的参数定义复制一份，并用变体的固化值替换 default。

    这样前端拿到的是「已经填好固化值」的参数定义，既能渲染输入框，
    也能让用户在此基础上继续微调——需求里「选中新策略并继续调参」即由此实现。
    注意：只替换 default，不动 params 的既有结构（label/min/max/type 原样保留）。
    """
    from .registry import REGISTRY

    base = REGISTRY.get(base_key)
    if not base:
        return []
    out: list[dict] = []
    for p in base.params or []:
        item = dict(p)
        name = p.get("name")
        if name in (overrides or {}):
            item["default"] = overrides[name]
        out.append(item)
    return out
