"""获取全市场股票代码+名称，保存为 JSON 文件。"""
import akshare as ak
import json
import os

print("正在从 AKShare 获取全市场股票代码和名称...")
df = ak.stock_zh_a_spot_em()
result = dict(zip(df['代码'].astype(str), df['名称'].astype(str)))
print(f"获取到 {len(result)} 只股票")

cache_dir = os.path.join(os.path.dirname(__file__), 'cache')
os.makedirs(cache_dir, exist_ok=True)
cache_file = os.path.join(cache_dir, 'stock_name_map.json')

with open(cache_file, 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print(f"已保存到 {cache_file}")
