"""网络/数据源异常识别与降级工具。

背景：
    本项目所有行情数据都依赖外部接口（AKShare→东方财富、通达信、雪球）。
    在弱网、代理、非交易时段、数据源限流等场景下，这些请求经常抛出
    ``requests`` 系异常（RemoteDisconnected / ProxyError / Timeout 等）。

    这类异常属于「外部依赖不可用」，并非服务端代码缺陷。若一律映射为
    500「服务器内部错误」，会让前端刷红、用户误以为程序坏了，也会污染
    错误日志、掩盖真正的 bug。

方案：
    - ``is_network_error()`` 判定异常是否属于外部数据源不可用。
    - ``degraded_payload()`` 生成统一降级响应体（200 + degraded 标记），
      让前端拿到结构完整但为空的数据，自行友好提示。
"""
from __future__ import annotations

import logging

logger = logging.getLogger("net_errors")

# 异常类型判定使用的类名字符串（避免强制 import requests/pytdx）
_NETWORK_EXC_NAMES = (
    "ConnectionError",
    "ConnectTimeout",
    "ReadTimeout",
    "Timeout",
    "TooManyRedirects",
    "ProxyError",
    "SSLError",
    "RemoteDisconnected",
    "IncompleteRead",
    "ProtocolError",
    "ChunkedEncodingError",
    "ContentDecodingError",
    "TdxConnectionError",
)

# 异常消息关键字（兜底，覆盖被二次包装成 RuntimeError 的情况）
_NETWORK_MSG_MARKERS = (
    "connection aborted",
    "connection reset",
    "connection refused",
    "connection closed",
    "remote end closed",
    "remote host",
    "max retries exceeded",
    "unable to connect to proxy",
    "proxyerror",
    "failed to establish a new connection",
    "temporary failure in name resolution",
    "name or service not known",
    "network is unreachable",
    "network is down",
    "timed out",
    "timeout",
    "read operation timed out",
    "no route to host",
    "errno 10054",
    "errno 10060",
    "errno 10061",
    "errno 11001",
    "无法连接",
    "连接超时",
    "网络",
)

# 内置的网络类异常（不依赖第三方库即可判定）
_BUILTIN_NETWORK_EXC = (ConnectionError, TimeoutError)


def is_network_error(exc: BaseException) -> bool:
    """判定异常是否属于「外部数据源/网络不可用」。

    采用「类型优先 + 消息关键字兜底」双重判定：
    requests/urllib3/pytdx 的异常大多继承自 OSError 或被二次包装，
    仅靠 isinstance 容易漏判，因此补充类名与消息文本匹配。
    """
    if exc is None:
        return False

    # 1) 内置网络异常
    if isinstance(exc, _BUILTIN_NETWORK_EXC):
        return True

    # 2) 按类名匹配（覆盖 requests / urllib3 / pytdx 等未直接 import 的类型）
    for cls in type(exc).__mro__:
        if cls.__name__ in _NETWORK_EXC_NAMES:
            return True

    # 3) 消息关键字兜底（覆盖被包装成 RuntimeError/Exception 的情况）
    msg = str(exc).lower()
    return any(marker in msg for marker in _NETWORK_MSG_MARKERS)


def degraded_payload(what: str, exc: BaseException, empty: object = None) -> dict:
    """生成降级响应体：结构完整、数据为空，并携带 degraded 标记。

    前端可据此显示「数据暂不可用」而不是红色错误提示。
    同时以 WARNING 级别记录（而不是 ERROR），避免污染真正的错误日志。
    """
    reason = f"{what}暂不可用（网络或数据源问题）"
    logger.warning(f"{reason}: {exc}")
    return {
        "status": "ok",
        "data": [] if empty is None else empty,
        "degraded": True,
        "reason": reason,
    }
