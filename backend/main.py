"""FastAPI 后端入口"""
import asyncio
import logging
from logging.handlers import RotatingFileHandler
import sys
import traceback
from pathlib import Path

# 确保 backend 目录在 sys.path 中，使 api/core 包可被导入
sys.path.insert(0, str(Path(__file__).parent))

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import math as _math
import numpy as _np

from api import backtest, data, strategy, trading, stocks, optimize, export, market, stock_scan
from api import visual_editor, monitor
from core.net_errors import is_network_error as _is_network_error

# 日志配置：控制台 + 文件轮转（单文件最大 5MB，保留 3 个历史文件）
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "backend.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"),
    ],
)
logger = logging.getLogger("quant-backend")

# ===== 全局防线：把非有限浮点（NaN/Inf）转为 None，避免接口返回 500 =====
# 指标计算在窗口不足/模拟数据下会产生 NaN，标准 json.dumps(allow_nan=False) 会抛
# "Out of range float values are not JSON compliant"，导致整个响应失败。
# 这里拦截 starlette 的 JSON 序列化，统一清洗。
import json as _json
_original_json_dumps = _json.dumps


def _clean_nan(obj):
    """递归把 NaN/Inf 清洗成 None，避免 json.dumps(allow_nan=False) 抛 500。

    CPython 标准 json 在序列化 float('nan') 时，不会走 ``default`` 回调，
    而是直接抛 ``ValueError: Out of range float values are not JSON compliant``，
    导致整个响应失败。因此在序列化前先递归把非有限浮点替换成 None。
    """
    if isinstance(obj, dict):
        return {k: _clean_nan(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean_nan(v) for v in obj]
    if isinstance(obj, float) and (_math.isnan(obj) or _math.isinf(obj)):
        return None
    if isinstance(obj, (_np.floating,)):
        f = float(obj)
        return None if (_math.isnan(f) or _math.isinf(f)) else f
    if isinstance(obj, (_np.integer,)):
        return int(obj)
    if isinstance(obj, (_np.ndarray,)):
        return obj.tolist()
    if isinstance(obj, (_np.bool_,)):
        return bool(obj)
    return obj


def _safe_json_dumps(*args, **kwargs):
    kwargs.setdefault("allow_nan", False)

    # 先递归清洗 NaN/Inf，避免标准 json 在 default 回调之前就抛 ValueError
    if args:
        # 注意：此处直接替换 args[0] 为清洗后的对象，保持 (obj,) 的元组结构，
        # 绝不能把整体再包一层 tuple，否则 json.dumps((obj,)) 会把响应序列化成 [obj] 数组。
        cleaned_first = _clean_nan(args[0])
        args = (cleaned_first,) + args[1:]

    def _default(o):
        if isinstance(o, float) and (_math.isnan(o) or _math.isinf(o)):
            return None
        if isinstance(o, (_np.floating,)):
            f = float(o)
            return None if (_math.isnan(f) or _math.isinf(f)) else f
        if isinstance(o, (_np.integer,)):
            return int(o)
        if isinstance(o, (_np.ndarray,)):
            return o.tolist()
        if isinstance(o, (_np.bool_,)):
            return bool(o)
        raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")

    kwargs["default"] = _default
    return _original_json_dumps(*args, **kwargs)


# 让 starlette 的 json 模块使用安全版本
import starlette.responses as _sr

_sr.json.dumps = _safe_json_dumps

# 同时覆盖 fastapi 的 JSONResponse（它内部也引用 starlette.responses.json，
# 但保险起见直接重写 render 方法，确保所有响应走安全序列化）
_OrigJSONResponse = JSONResponse


class SafeJSONResponse(_OrigJSONResponse):
    def render(self, content) -> bytes:
        return _safe_json_dumps(content, ensure_ascii=False, allow_nan=False).encode("utf-8")


JSONResponse = SafeJSONResponse

app = FastAPI(title="A股量化回测平台 API", version="0.1.0")

# CORS：开发 + Electron 生产模式
# 打包检测：PyInstaller 会设置 sys.frozen 属性；打包后资源路径含 "resources"
_is_packaged = getattr(sys, 'frozen', False) or "resources" in str(Path(__file__).resolve()).lower()

_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",  # vite preview
    "http://localhost:5174",  # 备用开发端口
]
# null origin 仅打包模式需要（Electron file:// 协议），开发模式不开放
if _is_packaged:
    _origins.append("null")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_origin_regex=r"^(https?://(localhost|127\.0\.0\.1):(517[3-4]|4173))$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(backtest.router, prefix="/api/backtest", tags=["回测"])
app.include_router(data.router, prefix="/api/data", tags=["数据"])
app.include_router(strategy.router, prefix="/api/strategy", tags=["策略"])
app.include_router(trading.router, prefix="/api/trading", tags=["交易"])
app.include_router(stocks.router, prefix="/api/stocks", tags=["股票"])
app.include_router(optimize.router, prefix="/api/optimize", tags=["参数优化"])
app.include_router(export.router, prefix="/api/export", tags=["导出"])
app.include_router(market.router, prefix="/api/market", tags=["市场状态"])
app.include_router(stock_scan.router, prefix="/api", tags=["选股池"])
app.include_router(visual_editor.router, prefix="/api/visual", tags=["可视化策略"])
app.include_router(monitor.router, prefix="/api", tags=["实时监控"])


# ==================== 全局异常处理 ====================
# 不应被全局处理器静默捕获的异常类型
_PASSTHROUGH_EXCEPTIONS = (
    asyncio.CancelledError,
    KeyboardInterrupt,
    SystemExit,
    ConnectionResetError,
    GeneratorExit,
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """捕获所有未处理异常，返回统一格式错误，避免泄露 traceback。

    注意：asyncio.CancelledError / KeyboardInterrupt / SystemExit 等
    不应被静默处理，会重新抛出以便上层正确关闭。
    """
    # 透传关键系统异常，不吞掉
    if isinstance(exc, _PASSTHROUGH_EXCEPTIONS):
        raise exc

    # 外部数据源不可用（弱网/代理/限流）不是服务端缺陷：返回 503 并以 WARNING
    # 记录，避免与真正的代码 bug 混在一起，前端也能给出准确的「网络」提示。
    if _is_network_error(exc):
        logger.warning(
            f"外部数据源不可用: {request.method} {request.url.path}\n{exc}"
        )
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "detail": "行情数据源暂时不可用，请检查网络后重试",
            },
        )

    logger.error(f"未捕获异常: {request.method} {request.url.path}\n{traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={"status": "error", "detail": "服务器内部错误，请稍后重试"},
    )


# ==================== 根路由 & 健康检查 ====================
@app.get("/")
def root():
    return {"status": "ok", "service": "quant-a-stock-backend", "version": "0.1.0"}


@app.get("/api/health")
def health_check():
    """健康检查端点，Electron 启动时轮询此接口等待后端就绪。"""
    return {"status": "ok"}


if __name__ == "__main__":
    import time as _time

    reload_mode = not _is_packaged
    # 打包环境下：TIME_WAIT 最长可能 120s，给予充足重试窗口
    max_retries = 30 if _is_packaged else 1
    retry_delay = 4  # seconds (30 × 4 = 120s coverage)

    for attempt in range(max_retries):
        try:
            config = uvicorn.Config(
                "main:app",
                host="127.0.0.1",
                port=8000,
                reload=reload_mode,
                log_level="info",
            )
            server = uvicorn.Server(config)
            server.run()
            break  # server stopped normally
        except SystemExit as e:
            code = getattr(e, "code", 1)
            if attempt < max_retries - 1:
                logger.warning(
                    f"后端退出 (code={code})，{retry_delay}s 后重试 ({attempt + 1}/{max_retries})..."
                )
                _time.sleep(retry_delay)
                continue
            logger.error(f"后端多次启动失败 (SystemExit code={code})")
            raise
        except Exception as e:
            msg = str(e)
            if "10013" in msg or "10048" in msg or "address already in use" in msg.lower():
                if attempt < max_retries - 1:
                    logger.warning(
                        f"端口 8000 被占用，{retry_delay}s 后重试 ({attempt + 1}/{max_retries})..."
                    )
                    _time.sleep(retry_delay)
                    continue
            logger.error(f"后端启动失败: {e}")
            raise
