"""自定义策略管理器：负责保存、加载、列出用户编写的自定义策略。

自定义策略以Python文件形式保存在 strategies/custom/ 目录下，
文件名即为策略key，便于动态加载。
"""
from __future__ import annotations

import ast
import importlib.util
import inspect
import logging
import os
import re
import sys
from pathlib import Path
from typing import Optional

import backtrader as bt

_cm_logger = logging.getLogger("custom_manager")

# 策略代码安全校验常量
MAX_CODE_LENGTH = 500_000  # 500KB 上限
FORBIDDEN_IMPORTS = {
    'os', 'subprocess', 'sys', 'shutil', 'socket', 'ctypes', 'importlib',
    'builtins', 'eval', 'exec', 'compile', '__import__', 'open', 'input',
    'pathlib', 'glob', 'fnmatch', 'io', 'code', 'codeop', 'linecache',
    'tokenize', 'traceback', 'gc', 'signal', 'mmap', 'fcntl', 'pty',
    'resource', 'multiprocessing', 'threading', 'concurrent', 'asyncio',
}
FORBIDDEN_PATTERNS = [
    r'__import__\s*\(',
    r'eval\s*\(',
    r'exec\s*\(',
    r'compile\s*\(',
    r'getattr\s*\([^)]*,\s*[\'"]__',
    r'setattr\s*\(',
    r'delattr\s*\(',
    r'globals\s*\(\s*\)',
    r'locals\s*\(\s*\)',
    r'__builtins__',
    r'__builtin__',
    r'builtins',
    r'ctypes',
    r'os\s*\.\s*system',
    r'os\s*\.\s*popen',
    r'os\s*\.\s*remove',
    r'os\s*\.\s*rmdir',
    r'os\s*\.\s*unlink',
    r'os\s*\.\s*chmod',
    r'os\s*\.\s*chown',
    r'os\s*\.\s*exec',
    r'os\s*\.\s*spawn',
    r'os\s*\.\s*kill',
    r'subprocess',
    r'socket',
    r'shutil',
    r'pickle',
    r'marshal',
    r'__class__\s*\.\s*__',
    r'__subclasses__',
    r'__bases__',
    r'__mro__',
    r'__globals__',
    r'__code__',
    r'__closure__',
    r'__func__',
    r'__self__',
    r'__dict__\s*\.',
    r'_compile',
    r'_parse',
    r'base64',
    r'codecs\s*\.\s*decode',
    r'codecs\s*\.\s*encode',
    r'\\x[0-9a-fA-F]{2}',
    r'chr\s*\(\s*0',
    r'ord\s*\(\s*',
]


# 允许策略代码导入的模块白名单（纯计算/数据处理，无系统副作用）
_ALLOWED_IMPORT_MODULES = {
    'backtrader', 'bt', 'math', 'cmath', 'numpy', 'np',
    'pandas', 'pd', 'datetime', 'time', 'typing',
    'collections', 'itertools', 'functools', 'operator',
    'numbers', 'decimal', 'fractions', 'statistics', 'dataclasses',
    'abc', 'enum', 'copy', 'json', 're', 'string',
    '__future__',  # from __future__ import annotations 是标准写法
}

# 保存原始 __import__，供受限版本调用
_ORIG_IMPORT = __builtins__['__import__'] if isinstance(__builtins__, dict) else getattr(
    __builtins__, '__import__'
)


def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    """受限的 __import__：只允许导入白名单模块。

    此前沙箱完全移除了 __import__，导致任何带 import 语句的策略代码
    （包括 ``import backtrader as bt``）在加载阶段就抛
    ``ImportError: __import__ not found``。这里改为白名单放行。
    """
    root = (name or "").split(".")[0]
    if root not in _ALLOWED_IMPORT_MODULES:
        raise ImportError(f"策略代码不允许导入模块: {root}")
    return _ORIG_IMPORT(name, globals, locals, fromlist, level)


def _get_safe_builtins() -> dict:
    """返回受限的 builtins 环境，防止沙箱逃逸。

    只暴露回测策略所需的安全内置函数和类型，
    移除所有危险的函数如 eval/exec/open 等。
    保留白名单受限的 __import__，保证策略能正常使用 backtrader。
    """
    import builtins
    safe = {
        # 基础类型
        'int': int, 'float': float, 'str': str, 'bool': bool,
        'list': list, 'dict': dict, 'tuple': tuple, 'set': set,
        'bytes': bytes, 'bytearray': bytearray, 'complex': complex,
        'frozenset': frozenset, 'object': object, 'type': type,
        # 数学运算
        'abs': abs, 'min': min, 'max': max, 'sum': sum, 'round': round,
        'pow': pow, 'divmod': divmod,
        # 序列/迭代
        'len': len, 'range': range, 'enumerate': enumerate,
        'zip': zip, 'map': map, 'filter': filter, 'sorted': sorted,
        'reversed': reversed, 'iter': iter, 'next': next,
        'slice': slice, 'all': all, 'any': any,
        # 类型判断
        'isinstance': isinstance, 'issubclass': issubclass,
        'hasattr': hasattr, 'getattr': getattr,
        'callable': callable,
        # 输出（仅 print）
        'print': print,
        # 字符串
        'repr': repr, 'format': format, 'ascii': ascii,
        'chr': chr, 'ord': ord, 'bin': bin, 'hex': hex, 'oct': oct,
        # 属性
        'property': property, 'staticmethod': staticmethod,
        'classmethod': classmethod,
        # 异常
        'Exception': Exception, 'ValueError': ValueError,
        'TypeError': TypeError, 'RuntimeError': RuntimeError,
        'IndexError': IndexError, 'KeyError': KeyError,
        'AttributeError': AttributeError, 'ZeroDivisionError': ZeroDivisionError,
        'OverflowError': OverflowError, 'StopIteration': StopIteration,
        # 实用
        'hash': hash, 'id': id, 'dir': dir, 'vars': vars,
        # super（策略类继承需要）
        'super': super,
        # 受限 import（仅白名单模块，保证 import backtrader 可用）
        '__import__': _safe_import,
        # 定义类必需（策略类声明），否则 class 语句抛 NameError
        '__build_class__': builtins.__build_class__,
        # 真值常量
        'True': True, 'False': False, 'None': None,
        # 错误信息
        'NotImplemented': NotImplemented,
        'Ellipsis': Ellipsis,
    }
    return safe


def _get_custom_dir() -> Path:
    """获取自定义策略目录。

    打包环境下 backend 目录可能只读，使用用户目录存储。
    """
    project_dir = Path(__file__).resolve().parent / "custom"

    # 尝试使用项目目录
    try:
        project_dir.mkdir(parents=True, exist_ok=True)
        test_file = project_dir / ".write_test"
        test_file.write_text("test")
        test_file.unlink()
        return project_dir
    except (PermissionError, OSError):
        pass

    # 项目目录不可写（打包环境），使用用户数据目录
    app_data = os.environ.get('APPDATA') or os.path.expanduser('~')
    custom_dir = Path(app_data) / 'A股量化回测平台' / 'custom_strategies'
    custom_dir.mkdir(parents=True, exist_ok=True)
    return custom_dir


CUSTOM_DIR = _get_custom_dir()


def _strategy_key_from_filename(filename: str) -> str:
    """从文件名生成策略key（去掉.py后缀）。"""
    return filename[:-3] if filename.endswith(".py") else filename


def _validate_key(key: str) -> bool:
    """校验策略 key 合法性，防止路径遍历和注入攻击。"""
    if not key or len(key) > 128:
        return False
    # 仅允许字母、数字、下划线、短横线
    return bool(re.match(r'^[a-zA-Z0-9_\-]+$', key))


def _filename_from_key(key: str) -> str:
    """从策略key生成文件名（已校验合法性）。"""
    return f"{key}.py"


def _validate_code_security(code: str) -> None:
    """对策略代码进行安全审计，阻止危险操作。

    Raises:
        ValueError: 如果代码包含禁止的操作。
    """
    if len(code) > MAX_CODE_LENGTH:
        raise ValueError(f"策略代码过长（{len(code)} 字节），上限 {MAX_CODE_LENGTH} 字节")

    # 检查危险导入
    import_pattern = re.compile(r'import\s+(\S+)')
    from_pattern = re.compile(r'from\s+(\S+)\s+import')
    for pattern in [import_pattern, from_pattern]:
        for match in pattern.finditer(code):
            module = match.group(1).split('.')[0]
            if module in FORBIDDEN_IMPORTS:
                raise ValueError(f"策略代码不允许导入模块: {module}")

    # 检查危险模式
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, code):
            raise ValueError(f"策略代码包含禁止的操作模式: {pattern}")


def list_custom_strategies() -> list[dict]:
    """列出所有自定义策略。"""
    result = []
    for py_file in sorted(CUSTOM_DIR.glob("*.py")):
        key = _strategy_key_from_filename(py_file.name)
        try:
            code = py_file.read_text(encoding="utf-8")
            info = _extract_strategy_info(code)
            result.append({
                "key": key,
                "name": info.get("name", key),
                "description": info.get("description", ""),
                "type": "custom",
            })
        except Exception:
            result.append({
                "key": key,
                "name": key,
                "description": "（无法解析策略信息）",
                "type": "custom",
            })
    return result


def get_custom_strategy_code(key: str) -> str:
    """获取自定义策略的源代码。"""
    if not _validate_key(key):
        raise ValueError(f"无效的策略 key: {key}")
    filepath = CUSTOM_DIR / _filename_from_key(key)
    if not filepath.exists():
        raise ValueError(f"自定义策略不存在: {key}")
    return filepath.read_text(encoding="utf-8")


def save_custom_strategy(key: str, code: str) -> dict:
    """保存自定义策略。
    
    Args:
        key: 策略key（也是文件名）
        code: Python策略代码
        
    Returns:
        策略元信息
    """
    # 校验 key 合法性
    if not _validate_key(key):
        raise ValueError(f"无效的策略 key: {key}，仅允许字母、数字、下划线和短横线")
    
    # 基本语法检查
    try:
        ast.parse(code)
    except SyntaxError as e:
        raise ValueError(f"Python语法错误: {e}")
    
    # 安全检查
    _validate_code_security(code)
    
    # 检查是否包含Backtrader策略类
    if "bt.Strategy" not in code and "backtrader" not in code:
        raise ValueError("策略代码必须包含Backtrader策略类（继承 bt.Strategy）")
    
    filepath = CUSTOM_DIR / _filename_from_key(key)
    filepath.write_text(code, encoding="utf-8")
    
    info = _extract_strategy_info(code)
    return {
        "key": key,
        "name": info.get("name", key),
        "description": info.get("description", ""),
    }


def delete_custom_strategy(key: str) -> bool:
    """删除自定义策略。"""
    if not _validate_key(key):
        raise ValueError(f"无效的策略 key: {key}")
    filepath = CUSTOM_DIR / _filename_from_key(key)
    if not filepath.exists():
        raise ValueError(f"自定义策略不存在: {key}")
    filepath.unlink()
    return True


def load_custom_strategy_class(key: str) -> type[bt.Strategy]:
    """动态加载自定义策略类。
    
    在Backtrader中，需要通过策略类名来引用。
    这里我们约定：自定义策略文件中必须有一个继承bt.Strategy的类，
    我们取第一个这样的类作为策略类。
    """
    if not _validate_key(key):
        raise ValueError(f"无效的策略 key: {key}")
    filepath = CUSTOM_DIR / _filename_from_key(key)
    if not filepath.exists():
        raise ValueError(f"自定义策略不存在: {key}")
    
    # 加载前对文件内容进行安全检查
    code = filepath.read_text(encoding="utf-8")
    _validate_code_security(code)
    
    module_name = f"custom_strategy_{key}"
    
    # 动态加载模块
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    if spec is None or spec.loader is None:
        raise ValueError(f"无法加载策略模块: {key}")
    
    module = importlib.util.module_from_spec(spec)
    # 注入受限的 __builtins__，防止沙箱逃逸
    _safe_builtins = _get_safe_builtins()
    module.__builtins__ = _safe_builtins
    sys.modules[module_name] = module

    # 注意：加载后不能从 sys.modules 移除模块——
    # backtrader 的 metabase.donew() 实例化策略时会执行
    # ``sys.modules[cls.__module__]``，若移除，
    # 后续 cerebro 实例化该策略将抛 KeyError。
    # 策略模块体积极小，常驻内存可接受。
    spec.loader.exec_module(module)

    # 查找策略类
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if (isinstance(attr, type) and
                issubclass(attr, bt.Strategy) and
                attr is not bt.Strategy):
            return attr

    raise ValueError(f"策略文件中未找到有效的Backtrader策略类: {key}")


def _extract_strategy_info(code: str) -> dict:
    """从策略代码中提取元信息（名称、描述等）。
    
    约定：在策略文件开头使用注释格式：
    # Name: 策略名称
    # Description: 策略描述
    """
    info = {}
    for line in code.splitlines():
        line = line.strip()
        if line.startswith("# Name:"):
            info["name"] = line[7:].strip()
        elif line.startswith("# Description:"):
            info["description"] = line[14:].strip()
    return info


def load_strategy_from_code(code: str) -> type[bt.Strategy]:
    """从代码字符串直接动态加载策略类（不保存文件）。

    用于前端提交自定义策略代码并立即回测的场景。
    """
    import tempfile
    import os

    # 基本语法检查
    try:
        ast.parse(code)
    except SyntaxError as e:
        raise ValueError(f"Python语法错误: {e}")

    # 安全检查
    _validate_code_security(code)

    # 检查是否包含 Backtrader 策略类
    if "bt.Strategy" not in code and "backtrader" not in code:
        raise ValueError("策略代码必须包含 Backtrader 策略类（继承 bt.Strategy）")

    # 创建临时文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
        f.write(code)
        temp_file = f.name

    try:
        # 动态加载模块
        module_name = f"_temp_strategy_{id(code)}"
        spec = importlib.util.spec_from_file_location(module_name, temp_file)
        if spec is None or spec.loader is None:
            raise ValueError("无法加载策略代码")

        module = importlib.util.module_from_spec(spec)
        # 注入受限的 __builtins__，防止沙箱逃逸
        _safe_builtins = _get_safe_builtins()
        module.__builtins__ = _safe_builtins
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        # 查找策略类
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, bt.Strategy)
                and attr is not bt.Strategy
            ):
                return attr

        raise ValueError("策略代码中未找到有效的 Backtrader 策略类（需继承 bt.Strategy）")
    finally:
        # 只清理临时文件。
        # 不能 sys.modules.pop(module_name)：backtrader 实例化策略时会用
        # sys.modules[cls.__module__]，提前移除会导致 run_backtest 抛 KeyError。
        try:
            os.unlink(temp_file)
        except OSError:
            pass
