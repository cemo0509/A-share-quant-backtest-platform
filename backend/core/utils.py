"""公共工具函数模块。"""

from typing import Any
import numpy as np
import pandas as pd


def safe_convert(obj: Any) -> Any:
    """递归转换不可序列化的类型（numpy 数值等）为 Python 原生类型，并清零 NaN。

    注意 ``bool(np.nan) is True``，所以 ``x or 0`` 无法过滤 NaN，必须显式用
    ``pd.isna`` 判断，否则 NaN 会沿链路泄漏到前端。
    """
    if isinstance(obj, dict):
        return {k: safe_convert(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [safe_convert(v) for v in obj]
    if isinstance(obj, (float, np.floating)):
        f = float(obj)
        if pd.isna(f) or np.isinf(f):
            return 0
        return f
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, np.ndarray):
        return safe_convert(obj.tolist())
    if isinstance(obj, (pd.Timestamp,)):
        return obj.isoformat()
    return obj
