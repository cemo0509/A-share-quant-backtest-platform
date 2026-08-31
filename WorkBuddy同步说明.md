# A股量化回测平台 —— WorkBuddy 同步说明

> 同步日期：2026-08-31
> 当前版本：桌面端 **v1.1.4**（安装包 `dist_build\A股量化回测平台 Setup 1.1.4.exe`）
> 目的：把本项目截至目前的状态、结构、关键改动、已知问题同步给 WorkBuddy，便于接手或并行开发时保持结构一致。
> 配套代码仓库：https://github.com/cemo0509/A-share-quant-backtest-platform （分支 `main`）

---

## 一、项目概况

面向 A 股市场的**桌面端**量化回测与策略开发平台。特点：

- 后端回测用 **Backtrader**，数据源早期文档写 AKShare，现打包环境自带 `python-embed`（无需用户装 Python）。
- 前端 React + TypeScript + Ant Design（**深色主题 darkAlgorithm**）。
- 桌面壳用 **Electron + electron-builder**，NSIS 安装包。
- 前后端分离，前端通过 `axios` 访问 `http://127.0.0.1:8000/api`（baseURL 由 `VITE_API_BASE_URL` 控制，默认 8000）。
- **实时行情现已支持多数据源**（东方财富 / 通达信 / 雪球），可在「实时行情」页一键切换。

---

## 二、技术栈与版本

| 层 | 技术 | 版本/说明 |
|----|------|-----------|
| 回测引擎 | Backtrader | 嵌入式 |
| 后端 | FastAPI + Uvicorn | main.py 入口 |
| 数据源 | AKShare + pytdx + 雪球 HTTP | 抽象层 `core/datasource.py` |
| 前端 | React + TS + Vite + Ant Design | antd **darkAlgorithm** |
| 图表 | Lightweight-Charts + ECharts | |
| 策略编辑器 | Monaco Editor + 自研可视化编辑器 | 非 React Flow（见下方说明） |
| 桌面 | Electron 33.4.11（`^33.0.0`）+ electron-builder 24.13.3 | NSIS 安装包 |
| Python | 嵌入式 `python-embed/`（打包进 exe 的 resources/python） | 用户无需安装 |

---

## 三、目录结构（关键）

```
量化软件开发/
├── backend/                # FastAPI 后端
│   ├── main.py             # 入口（全局 NaN/Inf 防护、CORS、健康检查 /api/health）
│   ├── api/                # 路由：backtest, data, strategy, trading, stocks,
│   │                       #       optimize, export, market, stock_scan, monitor,
│   │                       #       visual_editor, data（含 /source 数据源切换）
│   └── core/
│       ├── datasource.py   # 【新增】多数据源抽象层（东财/通达信/雪球）
│       ├── data_loader.py  # 行情/分钟K线获取（已路由到 datasource）
│       ├── filters.py      # 选股过滤器（get_spot_snapshot 已路由到 datasource）
│       ├── realtime_monitor.py # 盘中实时选股（含扫描诊断）
│       ├── screen_factors.py    # 选股因子（MACD 回溯修复在此）
│       ├── strategies/     # registry.py（预置策略注册表 REGISTRY）+ 各策略实现
│       ├── visual_editor/  # indicators.py（指标库）/ store.py（JSON 存储）
│       └── engine.py, custom_manager.py ...
├── frontend/
│   └── src/
│       ├── api/index.ts        # 所有 axios 封装（含数据源 /source）
│       ├── pages/              # StrategyEditor.tsx（策略编辑器页）等
│       ├── components/
│       │   ├── RealtimeQuotes.tsx   # 实时行情（含数据源切换下拉框）
│       │   └── visual-editor/  # VisualEditor / ConditionGroup / ConditionCard / types.ts
│       └── services/api.ts
├── electron/               # Electron 主进程
├── python-embed/           # 嵌入式 Python（打包用，不进 git）
├── dist_build/             # 打包输出（安装包 .exe 在此，不进 git）
├── version_snapshots/      # 历史版本快照存档（不进 git）
├── electron-builder.yml    # 打包配置（output: dist_build；extraResources: backend + python-embed）
├── 打包桌面版.cmd          # 主打包脚本（关进程→build→copy→electron-builder）
└── 各阶段审查/报告 .md     # 历史阶段文档
```

> git 忽略项：`node_modules/`、`python-embed/`、`dist_build/`、`build/`、`version_snapshots/`、`backup_visual_editor_原版/`、`install_test_*/`、`v1.0发布包/`、`*.log`。

---

## 四、近期已完成的改动（重点同步）

### 1. 实时选股池「无数据」Bug 修复（2026-07-20）
- **根因**：`screen_factors._macd_cross_state` 只检测**最后 2 根** K 线的 DIF/DEA 交叉，配合 `CCI≥100` 的 AND 模式，几乎无股票能同时满足 → 池子永远为空。
- **修复**：MACD 金叉检测回溯检查最近 **5 根** K 线（新增 `lookback` 参数，1-20，前端可调）。
- 监控器 `realtime_monitor.py` 新增扫描诊断：`Pool API` 返回 `candidates` / `logs` / `error` 字段；前端空池时显示「已扫描 N 只无匹配 + 调参建议」。

### 2. 多数据源接入（东方财富 + 通达信 + 雪球）（2026-07-26）
- 新增 `backend/core/datasource.py`：统一抽象层，三种源输出**完全一致的「东方财富风格」字段**，前端零改动。
- **东方财富**（默认）：AKShare `stock_zh_a_spot_em` / `stock_zh_a_hist_min_em`。
- **通达信**：`pytdx` 直连行情服务器（`get_security_quotes` / `get_security_bars`），真正推模式低延迟。
- **雪球**：HTTP 按代码实时报价（snapshot/分钟K线不支持，自动回退东财）。
- **切换方式**：
  - 环境变量 `QUANT_DATASOURCE=eastmoney|tongdaxin|xueqiu`；
  - 运行时 `set_active_source(name)`；
  - API `GET/POST /api/data/source`（前端「实时行情」页顶部下拉框一键切换）。
- **失败自动降级**到东方财富；快照拉取失败时返回空 DataFrame（不抛异常）。
- 依赖：`requirements.txt` 新增 `pytdx`、`requests`。

### 3. 可视化编辑器相关修复（2026-07-11，沿用，仍有效）
- 可视化模式选中预置策略 404 修复；白边/配色改用 `theme.useToken()` 语义色；`between` 校验；智能推荐模式（`/api/visual/presets`）。

### 4. 版本管理（2026-07-20）
- 用户曾对 UI 升级（P1-P6）效果不满意，已**回退**到 v1.1.4 原始版；UI 升级版存档于 `version_snapshots/v1.1.4_UI_upgraded_20260720/`。
- 当前工作区 = v1.1.4 原始版。

---

## 五、⚠️ 需求文档与本仓库的结构差异（WorkBuddy 务必注意）

`策略编辑器_智能推荐模式修复需求.md`（用户桌面上那份）是**按另一个项目结构写的**，路径写的是 `/workspace/quant-trading-platform/`，与本仓库多处不符。**不要照搬其路径/字段**，映射如下：

| 需求文档说法 | 本仓库实际情况 |
|--------------|----------------|
| 路由 `/api/visual-editor/...` | 实际 `/api/visual/...`（`api/visual_editor.py`） |
| 前端 `VisualMode.tsx` / `IndicatorPanel.tsx` / `ConditionBuilder.tsx` | 实际 `VisualEditor.tsx` / `ConditionGroup.tsx` / `ConditionCard.tsx` |
| 预置策略注册表在 `backend/engine/strategies/builtin.py`，有 `STRATEGY_REGISTRY` | 实际 `backend/core/strategies/registry.py`，变量名 `REGISTRY`，无 `visual_defaults`（本次新增） |
| 指标 key 用 `dif` / `dea` 作为独立可比较指标 | 实际 `dif`/`dea` 只是 `macd` 指标的 **lines**，不是独立 key；金叉用现成 `macd_cross`（lines: gold/death，operator=equal） |
| 默认条件 `logic: golden_cross` / `target: {type: zero_band}` | 实际贴合现有 `ConditionLeaf` 模型：`operator` + `targetType` + `targetValue`（见 `types.ts`） |
| 白名单 `["macd","dif","dea","ma","vol"]` | `dif`/`dea` 非独立指标；按本仓库实际 key 实现 |

### 当前智能推荐未收录的策略（模型限制，非遗漏）
`dual_ma`（双均线交叉）与 `bollinger`（价格穿越布林带）需要**「两列比较」**（MA5 上穿 MA20、收盘价 下穿 下轨）。现有 `ConditionLeaf` 模型的 `targetType='indicator'` 只支持目标指标 key，**不支持目标 line/周期**。为避免预填上残缺不可执行的规则，本期故意未纳入。

**若后续要支持**：需给 `ConditionLeaf` 加 `targetLine` / `targetParams` 字段，并在 `ConditionCard.tsx` 渲染对应选择器——这是一段中等工作量扩展，已在原任务中向用户说明待确认。

---

## 六、关键数据结构（可视化编辑器）

`frontend/src/components/visual-editor/types.ts`：

```ts
interface ConditionLeaf {
  id: string
  type: 'condition'
  indicator: string          // 指标 key（如 macd_cross / rsi / kdj_bull / ma_arrangement）
  line: string               // 指标线 value（如 gold / rsi / bull）
  params: Record<string, number>
  timeframe: string          // daily/weekly/...
  operator: string           // greater/less/cross_up/cross_down/equal/between
  targetType: 'value' | 'price' | 'indicator'
  targetValue?: number
  targetIndicator?: string
  targetLine?: string
  targetTimeframe?: string
  targetParam2?: number      // between 上限
}
interface ConditionGroup {   // 可嵌套
  id: string; type: 'group'; operator: 'AND' | 'OR'; items: ConditionNode[]
}
type ConditionNode = ConditionLeaf | ConditionGroup
interface VisualRule { operator: 'AND' | 'OR'; items: ConditionNode[] }
```

后端预置推荐规则（`registry.py` 的 `visual_defaults`）字段严格对齐上述 `VisualRule`，例如 macd 金叉：
```json
{"operator":"AND","items":[{"type":"condition","indicator":"macd_cross","line":"gold",
 "params":{"fast":12,"slow":26,"signal":9},"timeframe":"daily","operator":"equal",
 "targetType":"value","targetValue":1}]}
```

---

## 七、多数据源结构要点（新增，WorkBuddy 接手数据源相关时看这里）

`backend/core/datasource.py` 抽象：

- `class DataSource`：定义 `fetch_realtime_quotes(symbols)` / `fetch_spot_snapshot()` / `fetch_minute_kline(symbol, period, limit)`。
- 三个实现：`EastMoneySource` / `TongdaxinSource` / `XueqiuSource`。
- `DataSourceManager`：持有 `_active`，提供 `fetch_realtime_quotes/fetch_spot_snapshot/fetch_minute_kline` 路由 + 自动降级；`set_active(name)` / `status()` / `available()`。
- 所有源统一经 `_enrich_realtime(core, symbol, now)` 补齐 50+ 统一字段，前端无感知。
- 新增数据源只需继承 `DataSource` 并实现三个方法，返回统一格式即可，无需改前端。
- 数据获取入口已改为调用 `datasource.*`：`data_loader.fetch_realtime_quote`、`data_loader.fetch_minute_kline`、`filters.get_spot_snapshot`。

---

## 八、构建与打包流程

1. **前端构建**：`cd frontend && npm run build`（tsc -b && vite build，输出 frontend/dist）。
2. **复制到 electron**：`xcopy /y /e frontend\dist\* electron\dist\`。
3. **桌面打包**：`npm run dist`（electron-builder，配置见 `electron-builder.yml`，输出 `dist_build\`）。
4. **一键脚本**：`打包桌面版.cmd`（已含关进程→构建→复制→打包全流程）。
5. 安装包：`dist_build\A股量化回测平台 Setup 1.1.4.exe`。

开发期启动后端：`cd backend && python -m uvicorn main:app --host 127.0.0.1 --port 8000`。
前端 dev：`cd frontend && npm run dev`（默认 5173，CORS 已在后端白名单）。

**新电脑拉取后**：`pip install -r backend/requirements.txt`（含 `pytdx`，否则通达信源不可用，自动降级东财）。

---

## 九、已知问题 / 待办

- [ ] **可视化编辑器两列比较**：`dual_ma` / `bollinger` 智能推荐未纳入（见第五节），需扩展 `ConditionLeaf` 模型。
- [ ] 前端构建有 chunk > 500KB 警告（echarts/antd 体积大，不影响功能，可 code-splitting）。
- [ ] 默认 Electron 图标未设置（打包时提示 `default Electron icon is used`，需放 `build/icon.ico` 并在 `electron-builder.yml` 指定）。
- [ ] `StrategyEditor.tsx` 中 `ruleName` 时序偶发滞后（实测无碍，观察项）。
- [ ] 通达信源依赖 `pytdx` 且需可直连行情服务器（部分网络环境/代理下可能连不上，此时自动降级东财）。
- [ ] 雪球源无全市场快照/分钟K线能力，这两类请求固定走东财。
- [ ] 阶段历史文档（阶段2~9 审查报告）记录了更多历史修复，按需查阅根目录对应 `.md`。

---

## 十、给 WorkBuddy 的接手建议

1. **改可视化相关功能**：只动 `frontend/src/components/visual-editor/*` 与 `backend/api/visual_editor.py` + `backend/core/visual_editor/*`，并同步更新 `frontend/src/api/index.ts` 封装。
2. **改预置策略/智能推荐默认规则**：动 `backend/core/strategies/registry.py` 的 `REGISTRY` 与 `visual_defaults`。
3. **配色一律用 `theme.useToken()` 语义色**，不要再写死浅色（否则深色主题下会再次出现白块）。
4. 任何新增的「预置策略推荐」必须保证其 `visual_defaults` 能精确映射到现有 `ConditionLeaf` 模型，否则不要加入（参考未收录的 dual_ma/bollinger 原因）。
5. **改数据源**：优先在 `core/datasource.py` 内扩展，不要直接改 `data_loader.py` / `filters.py` 的获取逻辑（已路由到抽象层）。
6. 打包前先跑 `tsc -b` 与 `vite build` 确认无误，再用 `打包桌面版.cmd`。
7. 云端仓库已存在（见页头），接手前先 `git pull` 保持同步。

---

*本文档由 CodeBuddy 于 2026-08-31 更新，反映当时项目真实状态（v1.1.4）。后续改动请以代码与 GitHub 仓库为准。*
