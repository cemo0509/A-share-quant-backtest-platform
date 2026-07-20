# A股量化回测平台 —— WorkBuddy 同步说明

> 同步日期：2026-07-11
> 当前版本：桌面端 v1.1.2（安装包 `dist_build\A股量化回测平台 Setup 1.1.2.exe`）
> 目的：把本项目截至目前的状态、结构、关键改动、已知问题同步给 WorkBuddy，便于接手或并行开发时保持结构一致。

---

## 一、项目概况

面向 A 股市场的**桌面端**量化回测与策略开发平台。特点：

- 后端回测用 **Backtrader**，数据源早期文档写 AKShare，现打包环境自带 `python-embed`（无需用户装 Python）。
- 前端 React + TypeScript + Ant Design（**深色主题 darkAlgorithm**）。
- 桌面壳用 **Electron + electron-builder**，NSIS 安装包。
- 前后端分离，前端通过 `axios` 访问 `http://127.0.0.1:8000/api`（baseURL 由 `VITE_API_BASE_URL` 控制，默认 8000）。

---

## 二、技术栈与版本

| 层 | 技术 | 版本/说明 |
|----|------|-----------|
| 回测引擎 | Backtrader | 嵌入式 |
| 后端 | FastAPI + Uvicorn | main.py 入口 |
| 前端 | React + TS + Vite + Ant Design | antd **darkAlgorithm** |
| 图表 | Lightweight-Charts + ECharts | |
| 策略编辑器 | Monaco Editor + 自研可视化编辑器 | 非 React Flow（见下方说明） |
| 桌面 | Electron 33 + electron-builder 24 | NSIS 安装包 |
| Python | 嵌入式 `python-embed/`（打包进 exe 的 resources/python） | 用户无需安装 |

---

## 三、目录结构（关键）

```
量化软件开发/
├── backend/                # FastAPI 后端
│   ├── main.py             # 入口（全局 NaN/Inf 防护、CORS、健康检查 /api/health）
│   ├── api/                # 路由：backtest, data, strategy, trading, stocks,
│   │                       #       optimize, export, market, stock_scan, monitor,
│   │                       #       visual_editor
│   └── core/
│       ├── strategies/     # registry.py（预置策略注册表 REGISTRY）+ 各策略实现
│       ├── visual_editor/  # indicators.py（指标库）/ store.py（JSON 存储）/ __init__.py
│       └── engine.py, custom_manager.py ...
├── frontend/
│   └── src/
│       ├── api/index.ts        # 所有 axios 封装（含可视化接口）
│       ├── pages/              # StrategyEditor.tsx（策略编辑器页）等
│       ├── components/visual-editor/  # VisualEditor / ConditionGroup / ConditionCard / types.ts
│       └── services/api.ts
├── electron/               # Electron 主进程
├── python-embed/           # 嵌入式 Python（打包用）
├── dist_build/             # 打包输出（安装包 .exe 在此）
├── electron-builder.yml    # 打包配置（output: dist_build；extraResources: backend + python-embed）
├── 打包桌面版.cmd          # 主打包脚本（关进程→build→copy→electron-builder）
└── 各阶段审查/报告 .md     # 历史阶段文档
```

---

## 四、近期已完成的改动（重点同步）

### 1. 可视化编辑器 404 修复
- **根因**：处于可视化模式时选中预置策略（如 `dual_ma`，非可视化规则）会触发 `GET /api/visual/load/dual_ma`，后端查不到返回 404。
- **修复**：`frontend/src/pages/StrategyEditor.tsx` 选中 `category!=='visual'` 的策略时强制切回 `code` 模式，`VisualEditor` 仅在 `category==='visual'` 渲染。

### 2. 可视化编辑器白边框/配色修复
- **根因**：全局 antd 深色主题下，编辑器写成大量浅色硬编码（`#fff` / `#fafafa` / `#f0f7ff` / `#f5f5f5` / `#888`），形成刺眼白块。
- **修复**：全部改用 `theme.useToken()` 语义色（`colorBgContainer` / `colorBgElevated` / `colorBorderSecondary` / `colorTextSecondary` 等）。涉及 `VisualEditor.tsx`、`ConditionGroup.tsx`、`ConditionCard.tsx`、`StrategyEditor.tsx`（列表选中高亮 `#1890ff20` → `token.controlItemBgActive`）。

### 3. `between` 校验
- `VisualEditor.tsx` 新增 `findBetweenMissing` 递归校验，保存前拦截区间上下限缺值。

### 4. 智能推荐模式（最新）
- **后端**：
  - `backend/core/strategies/registry.py`：`StrategyInfo` 加 `visual_defaults` 字段；定义 4 个可精确表达的推荐规则（macd 金叉 / rsi<30 / kdj 金叉 / 均线多头排列）。
  - `backend/api/visual_editor.py`：新增 `GET /api/visual/presets`，返回 `{presets:{key:rule}, names:{key:name}}`。
- **前端**：
  - `frontend/src/api/index.ts`：封装 `getVisualPresets()`。
  - `frontend/src/components/visual-editor/types.ts`：新增 `applyPreset()`（深拷贝 + 重生成节点 id）。
  - `frontend/src/components/visual-editor/VisualEditor.tsx`：工具条加「智能推荐 💡」下拉，选中后预填；编辑区有内容时弹确认框。

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

## 七、构建与打包流程

1. **前端构建**：`cd frontend && npm run build`（tsc -b && vite build，输出 frontend/dist）。
2. **复制到 electron**：`xcopy /y /e frontend\dist\* electron\dist\`。
3. **桌面打包**：`npm run dist`（electron-builder，配置见 `electron-builder.yml`，输出 `dist_build\`）。
4. **一键脚本**：`打包桌面版.cmd`（已含关进程→构建→复制→打包全流程）。
5. 安装包：`dist_build\A股量化回测平台 Setup 1.1.2.exe`。

开发期启动后端：`cd backend && python -m uvicorn main:app --host 127.0.0.1 --port 8000`。
前端 dev：`cd frontend && npm run dev`（默认 5173，CORS 已在后端白名单）。

---

## 八、已知问题 / 待办

- [ ] **可视化编辑器两列比较**：`dual_ma` / `bollinger` 智能推荐未纳入（见第五节），需扩展 `ConditionLeaf` 模型。
- [ ] 前端构建有 chunk > 500KB 警告（不影响功能，可后续做 code-splitting）。
- [ ] `StrategyEditor.tsx` 中 `ruleName` 时序偶发滞后（实测无碍，观察项）。
- [ ] 阶段历史文档（阶段2~9 审查报告）记录了更多历史修复，按需查阅根目录对应 `.md`。

---

## 九、给 WorkBuddy 的接手建议

1. **改可视化相关功能**：只动 `frontend/src/components/visual-editor/*` 与 `backend/api/visual_editor.py` + `backend/core/visual_editor/*`，并同步更新 `frontend/src/api/index.ts` 封装。
2. **改预置策略/智能推荐默认规则**：动 `backend/core/strategies/registry.py` 的 `REGISTRY` 与 `visual_defaults`。
3. **配色一律用 `theme.useToken()` 语义色**，不要再写死浅色（否则深色主题下会再次出现白块）。
4. 任何新增的「预置策略推荐」必须保证其 `visual_defaults` 能精确映射到现有 `ConditionLeaf` 模型，否则不要加入（参考未收录的 dual_ma/bollinger 原因）。
5. 打包前先跑 `tsc -b` 与 `vite build` 确认无误，再用 `打包桌面版.cmd`。

---

*本文档由 CodeBuddy 于 2026-07-11 生成，反映当时项目真实状态。后续改动请以代码为准。*
