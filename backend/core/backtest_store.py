"""回测结果持久化（P0-9）—— SQLite 存储。

解决的问题：
    回测结果此前只存在前端 zustand，**刷新页面即丢失**，没有回测历史库。
    导致无法回答「上个月我用双均线跑茅台的结果是多少」
    「这两个策略哪个更好」这类最基本的问题，
    每次都要重新配置、重新跑。

    审计定位：复盘、对比、归因功能都建立在持久化之上，
    它是后续所有价值的前置依赖。

选型理由：
    SQLite 是 Python 内置模块，零部署成本，单机桌面应用足够用
    （不需要 Postgres / Redis —— 见「明确不做」清单）。

存储位置：
    打包环境下 backend 目录可能只读，因此优先用户数据目录
    （与 custom_manager / data_loader 的策略保持一致）。
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("backtest_store")


def _get_db_path() -> Path:
    """获取数据库文件路径（优先项目目录，只读则回退用户目录）。"""
    project_dir = Path(__file__).resolve().parent.parent / "data"

    try:
        project_dir.mkdir(parents=True, exist_ok=True)
        test_file = project_dir / ".write_test"
        test_file.write_text("test")
        test_file.unlink()
        return project_dir / "backtest_history.db"
    except (PermissionError, OSError):
        pass

    # 打包环境：使用用户数据目录
    app_data = os.environ.get("APPDATA") or os.path.expanduser("~")
    user_dir = Path(app_data) / "A股量化回测平台" / "data"
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir / "backtest_history.db"


DB_PATH = _get_db_path()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS backtest_runs (
    id              TEXT PRIMARY KEY,
    created_at      TEXT NOT NULL,
    strategy_key    TEXT,
    strategy_name   TEXT,
    symbol          TEXT,
    start_date      TEXT,
    end_date        TEXT,
    period          TEXT,
    adjust          TEXT,
    position_sizing TEXT,
    cash            REAL,
    commission      REAL,
    slippage        REAL,
    data_source     TEXT,
    params_json     TEXT,
    metrics_json    TEXT,
    result_json     TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_created ON backtest_runs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_symbol  ON backtest_runs(symbol);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """初始化数据库（建表 + 索引）。可重复调用。"""
    try:
        with _connect() as conn:
            conn.executescript(_SCHEMA)
    except Exception as e:
        logger.error(f"回测历史数据库初始化失败: {e}")


# 首次导入即建表，避免调用方忘记初始化
init_db()


def save_run(
    result: dict,
    strategy_key: str = "",
    strategy_name: str = "",
    symbol: str = "",
    start_date: str = "",
    end_date: str = "",
    period: str = "daily",
    adjust: str = "qfq",
    position_sizing: str = "allin",
    cash: float = 0,
    commission: float = 0,
    slippage: float = 0,
    params: Optional[dict] = None,
) -> Optional[str]:
    """保存一次回测结果，返回记录 id；失败返回 None。

    持久化失败**绝不能**影响回测本身（返回 None 即可）。
    """
    try:
        run_id = uuid.uuid4().hex[:16]
        metrics = result.get("metrics") or {}

        row = (
            run_id,
            # 毫秒精度：只到秒的话，同一秒内连续跑多次回测会导致
            # 按时间倒序的结果不稳定（历史列表顺序错乱）
            datetime.now().isoformat(timespec="milliseconds"),
            strategy_key,
            strategy_name,
            symbol,
            start_date,
            end_date,
            period,
            adjust,
            position_sizing,
            cash,
            commission,
            slippage,
            result.get("data_source", ""),
            json.dumps(params or {}, ensure_ascii=False),
            json.dumps(metrics, ensure_ascii=False),
            # 完整结果（含资金曲线/交易明细/K线），便于后续复盘
            json.dumps(result, ensure_ascii=False),
        )

        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO backtest_runs (
                    id, created_at, strategy_key, strategy_name, symbol,
                    start_date, end_date, period, adjust, position_sizing,
                    cash, commission, slippage, data_source,
                    params_json, metrics_json, result_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                row,
            )
        return run_id
    except Exception as e:
        logger.warning(f"保存回测历史失败（不影响回测）: {e}")
        return None


def list_runs(limit: int = 100, symbol: str = "") -> list[dict]:
    """列出回测历史（按时间倒序）。

    只返回摘要字段（不含完整 result_json），避免传输大量数据。
    """
    try:
        with _connect() as conn:
            if symbol:
                rows = conn.execute(
                    """
                    SELECT id, created_at, strategy_key, strategy_name, symbol,
                           start_date, end_date, period, adjust, position_sizing,
                           cash, commission, slippage, data_source,
                           params_json, metrics_json
                    FROM backtest_runs
                    WHERE symbol = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (symbol, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, created_at, strategy_key, strategy_name, symbol,
                           start_date, end_date, period, adjust, position_sizing,
                           cash, commission, slippage, data_source,
                           params_json, metrics_json
                    FROM backtest_runs
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()

        out = []
        for r in rows:
            d = dict(r)
            try:
                d["params"] = json.loads(d.pop("params_json") or "{}")
            except Exception:
                d["params"] = {}
            try:
                d["metrics"] = json.loads(d.pop("metrics_json") or "{}")
            except Exception:
                d["metrics"] = {}
            out.append(d)
        return out
    except Exception as e:
        logger.warning(f"读取回测历史失败: {e}")
        return []


def get_run(run_id: str) -> Optional[dict]:
    """读取单条回测（含完整结果，用于复盘/重新载入结果页）。"""
    try:
        with _connect() as conn:
            row = conn.execute(
                "SELECT * FROM backtest_runs WHERE id = ?", (run_id,)
            ).fetchone()
        if row is None:
            return None
        d = dict(row)
        try:
            d["params"] = json.loads(d.pop("params_json") or "{}")
        except Exception:
            d["params"] = {}
        try:
            d["metrics"] = json.loads(d.pop("metrics_json") or "{}")
        except Exception:
            d["metrics"] = {}
        try:
            d["result"] = json.loads(d.pop("result_json") or "{}")
        except Exception:
            d["result"] = {}
        return d
    except Exception as e:
        logger.warning(f"读取回测记录失败: {e}")
        return None


def delete_run(run_id: str) -> bool:
    """删除单条回测记录。"""
    try:
        with _connect() as conn:
            cur = conn.execute(
                "DELETE FROM backtest_runs WHERE id = ?", (run_id,)
            )
        return cur.rowcount > 0
    except Exception as e:
        logger.warning(f"删除回测记录失败: {e}")
        return False


def clear_runs() -> int:
    """清空全部回测历史，返回删除条数。"""
    try:
        with _connect() as conn:
            cur = conn.execute("DELETE FROM backtest_runs")
        return cur.rowcount or 0
    except Exception as e:
        logger.warning(f"清空回测历史失败: {e}")
        return 0
