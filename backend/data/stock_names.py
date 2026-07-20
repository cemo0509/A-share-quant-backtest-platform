"""股票名称缓存模块：解决 akshare 部分股票名称缺失的问题。

提供全市场股票名称和行业映射，支持：
- 从 akshare 获取全市场股票基本信息并缓存
- 按代码查询名称和行业
- 获取全市场代码列表（用于选股池扫描）
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stock_names")


def _get_data_dir() -> Path:
    """获取数据目录（打包环境下使用用户数据目录）。"""
    project_data = Path(__file__).resolve().parent

    # 尝试使用项目目录
    try:
        project_data.mkdir(parents=True, exist_ok=True)
        test_file = project_data / ".write_test"
        test_file.write_text("test")
        test_file.unlink()
        return project_data
    except (PermissionError, OSError):
        pass

    # 打包环境使用用户数据目录
    app_data = os.environ.get('APPDATA') or os.path.expanduser('~')
    data_dir = Path(app_data) / 'A股量化回测平台' / 'data'
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


class StockNameCache:
    """股票名称缓存，单例模式。

    三级数据源优先级：
    1. 内存缓存（names dict）
    2. 本地 parquet/JSON 缓存文件
    3. akshare 在线获取
    """

    _instance: Optional["StockNameCache"] = None

    def __new__(cls) -> "StockNameCache":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self.data_dir = _get_data_dir()
        self.cache_file = self.data_dir / "stock_names.parquet"
        self.json_cache_file = self.data_dir / "stock_name_map.json"

        # 内存缓存: {code: {name, sector, market}}
        self.names: dict[str, dict] = {}
        self._loaded = False
        self._loading = False
        self._load_lock = threading.Lock()

        # 内置硬编码映射（保底）
        self._hardcoded = {
            '600103': ('青山纸业', '造纸'), '600000': ('浦发银行', '银行'),
            '600036': ('招商银行', '银行'), '600519': ('贵州茅台', '白酒'),
            '601318': ('中国平安', '保险'), '600276': ('恒瑞医药', '医药'),
            '600887': ('伊利股份', '食品饮料'), '601166': ('兴业银行', '银行'),
            '600030': ('中信证券', '证券'), '000001': ('平安银行', '银行'),
            '000002': ('万科A', '房地产'), '000858': ('五粮液', '白酒'),
            '000333': ('美的集团', '家电'), '000651': ('格力电器', '家电'),
            '002594': ('比亚迪', '汽车'), '300750': ('宁德时代', '新能源'),
            '688981': ('中芯国际', '半导体'), '601012': ('隆基绿能', '光伏'),
            '600309': ('万华化学', '化工'), '601888': ('中国中免', '免税'),
            '002415': ('海康威视', '安防'), '000725': ('京东方A', '面板'),
            '002475': ('立讯精密', '消费电子'), '300059': ('东方财富', '互联网金融'),
            '600016': ('民生银行', '银行'), '601328': ('交通银行', '银行'),
            '601398': ('工商银行', '银行'), '601288': ('农业银行', '银行'),
            '601988': ('中国银行', '银行'), '600048': ('保利发展', '房地产'),
            '001979': ('招商蛇口', '房地产'), '000069': ('华侨城A', '房地产'),
            '002304': ('洋河股份', '白酒'), '603288': ('海天味业', '调味品'),
            '600809': ('山西汾酒', '白酒'), '000568': ('泸州老窖', '白酒'),
            '600741': ('华域汽车', '汽车零部件'), '601238': ('广汽集团', '汽车'),
            '002230': ('科大讯飞', '人工智能'), '300124': ('汇川技术', '工业自动化'),
            '688111': ('金山办公', '软件'), '300496': ('中科创达', '软件'),
            '002410': ('广联达', '软件'), '300454': ('深信服', '网络安全'),
        }

    def _load_cache(self):
        """从本地缓存加载股票名称映射。

        优先级：本地 JSON 缓存 > 硬编码兜底 > 后台异步刷新
        """
        if self._loaded:
            return
        with self._load_lock:
            if self._loaded or self._loading:
                return
            self._loading = True

        # 1. 先加载硬编码映射（保底数据，始终可用）
        for code, (name, sector) in self._hardcoded.items():
            self.names[code] = {'name': name, 'sector': sector, 'market': self._guess_market(code)}

        # 2. 从 JSON 缓存文件加载（比硬编码更全）
        json_loaded = 0
        if self.json_cache_file.exists():
            try:
                with open(self.json_cache_file, 'r', encoding='utf-8') as f:
                    cached = json.load(f)
                for code, name in cached.items():
                    if code not in self.names:
                        self.names[code] = {
                            'name': name,
                            'sector': '未知',
                            'market': self._guess_market(code),
                        }
                json_loaded = len(cached)
                logger.info(f"从 JSON 缓存加载股票名称: {json_loaded} 只")
            except Exception as e:
                logger.warning(f"加载 JSON 缓存失败: {e}")

        self._loaded = True
        self._loading = False

        # 3. 如果本地缓存不足全市场（全 A 股应有 5000+ 只），后台异步尝试从 AKShare 刷新
        #    注意：阈值不能定太低（如 200），否则 696 这类"部分缓存"会误判为已足够而永不补全。
        total_loaded = len(self.names)
        if total_loaded < 4000:
            logger.info(f"本地缓存仅 {total_loaded} 只股票（全市场应 5000+），将在后台尝试从 AKShare 刷新...")
            import threading
            t = threading.Thread(target=self.refresh_from_akshare, daemon=True)
            t.start()

    def _guess_market(self, code: str) -> str:
        """根据代码判断市场。"""
        if code.startswith(('60', '68', '9')):
            return 'sh'
        return 'sz'

    def refresh_from_akshare(self, force: bool = False) -> bool:
        """从 akshare 获取全市场股票信息并更新缓存。

        Args:
            force: 是否强制刷新（忽略已有缓存）

        Returns:
            是否成功
        """
        # 如果已有大量缓存且非强制刷新，跳过（防止频繁请求）
        if not force and len(self.names) > 2000:
            logger.info(f"缓存已有 {len(self.names)} 只股票，跳过刷新")
            return True

        for attempt in range(3):
            try:
                import akshare as ak
                logger.info(f"正在从 AKShare 获取全市场股票信息（尝试 {attempt + 1}/3）...")

                # 获取全市场股票代码和名称
                df = ak.stock_info_a_code_name()
                count = 0
                for _, row in df.iterrows():
                    code = str(row['code'])
                    name = str(row['name'])
                    industry = str(row.get('industry', '未知')) if 'industry' in row else '未知'
                    self.names[code] = {
                        'name': name,
                        'sector': industry,
                        'market': self._guess_market(code),
                    }
                    count += 1

                # 保存到 JSON 缓存
                name_map = {code: info['name'] for code, info in self.names.items()}
                self.json_cache_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self.json_cache_file, 'w', encoding='utf-8') as f:
                    json.dump(name_map, f, ensure_ascii=False)

                self._loaded = True
                logger.info(f"从 AKShare 加载股票信息: {count} 只")
                return True

            except Exception as e:
                logger.warning(f"AKShare 加载失败（尝试 {attempt + 1}/3）: {e}")
                if attempt < 2:
                    time.sleep(2)

        self._loaded = True  # 即使失败也标记已加载，使用已有缓存
        return False

    def get_name(self, symbol: str) -> str:
        """根据代码获取股票名称。

        Args:
            symbol: 股票代码（如 "000001"、"sh600519" 或 "sz002558"）

        Returns:
            股票名称，找不到时返回 "股票{code}"
        """
        self._load_cache()
        code = symbol.replace('sh', '').replace('sz', '').replace('SH', '').replace('SZ', '')
        if code in self.names:
            return self.names[code]['name']
        return f"股票{code}"

    def get_sector(self, symbol: str) -> str:
        """根据代码获取所属行业。

        Args:
            symbol: 股票代码

        Returns:
            行业名称，找不到时返回 "未知"
        """
        self._load_cache()
        code = symbol.replace('sh', '').replace('sz', '').replace('SH', '').replace('SZ', '')
        if code in self.names:
            return self.names[code].get('sector', '未知')
        return "未知"

    def get_market(self, symbol: str) -> str:
        """根据代码获取市场（sh/sz）。"""
        self._load_cache()
        code = symbol.replace('sh', '').replace('sz', '').replace('SH', '').replace('SZ', '')
        if code in self.names:
            return self.names[code].get('market', self._guess_market(code))
        return self._guess_market(code)

    def get_info(self, symbol: str) -> dict:
        """获取股票完整信息（名称、行业、市场）。"""
        self._load_cache()
        code = symbol.replace('sh', '').replace('sz', '').replace('SH', '').replace('SZ', '')
        if code in self.names:
            return dict(self.names[code])
        return {'name': f"股票{code}", 'sector': '未知', 'market': self._guess_market(code)}

    def get_all_codes(self) -> list[str]:
        """获取所有已缓存的 A 股代码列表。"""
        self._load_cache()
        return list(self.names.keys())

    def get_all_symbols(self) -> list[str]:
        """获取所有带市场前缀的 A 股代码列表（如 sh600519, sz002558）。

        用于选股池扫描等场景。
        """
        self._load_cache()
        result = []
        for code, info in self.names.items():
            market = info.get('market', self._guess_market(code))
            result.append(f"{market}{code}")
        return result

    def search(self, keyword: str, limit: int = 20) -> list[dict]:
        """模糊搜索股票（按代码或名称）。

        Args:
            keyword: 搜索关键词
            limit: 返回数量上限

        Returns:
            [{symbol, code, name, sector}, ...]
        """
        self._load_cache()
        results = []
        keyword_lower = keyword.lower()
        for code, info in self.names.items():
            name = info.get('name', '')
            if keyword_lower in code.lower() or keyword_lower in name.lower():
                market = info.get('market', self._guess_market(code))
                results.append({
                    'symbol': f"{market}{code}",
                    'code': code,
                    'name': name,
                    'sector': info.get('sector', '未知'),
                })
            if len(results) >= limit:
                break
        return results


# 全局单例
_stock_name_cache = StockNameCache()


def get_stock_name(symbol: str) -> str:
    """快捷函数：根据代码获取名称。"""
    return _stock_name_cache.get_name(symbol)


def get_stock_sector(symbol: str) -> str:
    """快捷函数：根据代码获取行业。"""
    return _stock_name_cache.get_sector(symbol)


def get_all_stock_symbols() -> list[str]:
    """快捷函数：获取所有带市场前缀的代码列表。"""
    return _stock_name_cache.get_all_symbols()


def get_all_codes() -> list[str]:
    """快捷函数：获取所有纯数字代码列表。"""
    return _stock_name_cache.get_all_codes()


def search_stocks(keyword: str, limit: int = 20) -> list[dict]:
    """快捷函数：模糊搜索股票。"""
    return _stock_name_cache.search(keyword, limit)


def refresh_stock_names() -> bool:
    """快捷函数：刷新股票名称缓存。"""
    return _stock_name_cache.refresh_from_akshare(force=True)
