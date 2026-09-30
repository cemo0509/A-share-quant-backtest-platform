"""父进程看门狗：桌面版防孤儿后端进程。

Electron 主进程启动后端时，把自己的 PID 通过环境变量 QUANT_PARENT_PID
传进来。本模块启动一个守护线程定期检查该进程是否仍然存活——若主进程
已退出（正常关闭的清理逻辑失效、崩溃、被任务管理器强杀等任何原因），
后端立即自行退出，避免在用户桌面上残留无人管理的 python.exe。

背景：Windows 上子进程不会随父进程退出而终止，而 Electron 的
window-all-closed / before-quit 清理在主进程被强杀时根本不会执行。
看门狗是覆盖该场景的最后一道防线。

仅使用标准库（ctypes），兼容嵌入式 Python（无 psutil 依赖）。
"""
import logging
import os
import threading
import time

logger = logging.getLogger("quant-backend.watchdog")

_INTERVAL = 3.0  # 检查间隔（秒）


def _pid_alive_win(pid: int) -> bool:
    """Windows: 用 OpenProcess + GetExitCodeProcess 检查进程是否存活。

    PROCESS_QUERY_LIMITED_INFORMATION 只要求最小权限，不会被普通权限
    差异挡住。注意退出码恰好等于 259 (STILL_ACTIVE) 的进程会被误判为
    存活——概率极低，可接受（宁可漏杀不可误杀）。
    """
    import ctypes
    from ctypes import wintypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259

    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        # 打不开：进程不存在（已退出并已被系统回收）
        return False
    try:
        exit_code = wintypes.DWORD()
        if kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return exit_code.value == STILL_ACTIVE
        return True  # 查询失败时保守认为仍存活
    finally:
        kernel32.CloseHandle(handle)


def _pid_alive_posix(parent_pid: int) -> bool:
    """POSIX: 父进程死后，孤儿进程的 ppid 会变为 1（init/launchd）。"""
    try:
        return os.getppid() == int(parent_pid)
    except Exception:
        return True  # 判断失败时不误杀


def start_parent_watchdog(parent_pid=None, interval: float = _INTERVAL) -> bool:
    """启动看门狗。返回 True 表示已启用。

    parent_pid 缺省时读环境变量 QUANT_PARENT_PID（由 Electron 注入）。
    手动 `python main.py` 运行时没有该变量，看门狗不启用，行为不变。
    """
    if parent_pid is None:
        parent_pid = os.environ.get("QUANT_PARENT_PID")
    if not parent_pid:
        return False
    try:
        parent_pid = int(parent_pid)
    except (TypeError, ValueError):
        logger.warning(f"QUANT_PARENT_PID 无效: {parent_pid!r}，看门狗未启用")
        return False

    if parent_pid == os.getpid():
        return False  # 自己监控自己没有意义

    if os.name == "nt":
        alive_fn = lambda: _pid_alive_win(parent_pid)  # noqa: E731
    else:
        alive_fn = lambda: _pid_alive_posix(parent_pid)  # noqa: E731

    def _watch():
        logger.info(f"父进程看门狗已启动（监控 PID {parent_pid}，间隔 {interval}s）")
        while alive_fn():
            time.sleep(interval)
        logger.error(f"父进程 (PID {parent_pid}) 已退出，后端自动结束以防残留")
        # os._exit 立即终止，不走 atexit/finally/uvicorn 优雅关闭——
        # 此刻任何清理都已无意义，快速退出才是目的（防止关闭流程卡住）
        os._exit(0)

    thread = threading.Thread(target=_watch, name="parent-watchdog", daemon=True)
    thread.start()
    return True
