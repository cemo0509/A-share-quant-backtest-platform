# 升级报告：因子选股器同花顺式改造 + 审计整改汇总

> 生成日期：2026-09-14
> 目的：供 WorkBuddy 复核本轮全部改动
> ✅ **推送状态**：`origin/main` 已更新至 `f3881f0`（`36cd9a4..f3881f0`）。
> 本轮升级核心的 3 个 commit（`917c067` 同花顺式编辑器、`4b35b31` 因子选股器、`f3881f0` 日志）
> **已全部推送到 GitHub**。WorkBuddy 直接 `git pull` 最新 `main`（目标 HEAD = `f3881f0`）即可完整复核。

---

## 1. 升级目标

将原本"复杂但不好用"的策略编辑/选股重做成**同花顺式因子标签块**交互：

- **因子选股器**：自由组合已知因子（条件）→ 筛出符合的股票
- **统一界面**：选股器与可视化策略编辑器共用同一套"条件标签块"交互（扁平 AND）
- **刷新模式**：首次下载数据慢，之后改条件在本地秒级重筛（数据/计算/筛选三层分离）

---

## 2. 改动总览（按 commit，均在 `main` 分支）

### 阶段一：同花顺式编辑器 + 因子选股器（**本次核心，已推送**）

#### `917c067` — 同花顺式因子标签块编辑器
- **新增** `frontend/src/components/factor-editor/FactorEditor.tsx`（331 行）
  - 顶部横排条件标签块（点击编辑 / × 删除 / 复制）
  - 左侧因子分类 + 右侧指标库（点指标弹条件类型选择，复用 `buildConditionOptions`）
  - 只支持**扁平 AND**（同花顺风格）
  - 选股器与策略编辑器共用
- **重写** `frontend/src/components/visual-editor/VisualEditor.tsx`
  - 原「指标树 / 参数面板 / 条件预览」三栏 → `FactorEditor`
  - 保留：保存 / 生成代码 / 立即回测 / 智能推荐 / 全局设置 / JSON 预览
  - 加载旧规则（含嵌套 group）经 `collectLeaves` 压平为扁平 AND
- 类型检查通过（`tsc -b --force`）

#### `4b35b31` — 自定义因子选股（后端筛选引擎 + 前端因子选股页）
- **新增** `backend/core/screener.py`（341 行）
  - 直接对本地 K 线 `DataFrame` **计算指标并布尔判断，不跑 backtrader 回测**（秒级基础）
  - 指标（pandas 向量化）：MA / EMA / MACD / KDJ / BOLL / RSI / CCI / WR / BIAS / OBV /
    成交量 / 均量 / 量比 / 成交额 / 换手 / 价格 / 振幅 / 涨跌幅 / 新高新低 / 均线排列
  - **关键防护**：`mock` 数据（`is_mock`）一律跳过；无法计算的指标/运算符 → 该股不满足
    （宁缺毋滥，不输出噪声，同 A-01 原则）
- **新增** `backend/api/screener.py`：`POST /api/screener/run`
  - 提取条件叶子（递归拍平嵌套）→ 解析日期/股票范围（复用 `_get_scan_symbols`）→
    可选 `prefetch_klines` 预热 → `screen_symbols` 向量化筛选
- `backend/models/schemas.py` 加 `ScreenerRequest`；`backend/main.py` 注册路由
- **新增** `frontend/src/pages/FactorScreener.tsx`（148 行）
  - FactorEditor + 范围（沪深300/中证500/全市场）+ 日期区间 + 开始筛选 + 结果表格
  - `App.tsx` 接入 `/screener` 路由与「选股与行情」菜单；`api/index.ts` 加 `runScreener`
- **冒烟验证（端到端，非仅语法）**：
  - 恒真条件 `price>0` → 返回 3/3（贵州茅台/平安银行/美的集团，**真实数据非 mock**）
  - `MA5>0`=3 且 `MA5<MA10`=3（与 `MA5>MA10`=0 完美互补）→ **指标计算正确**
  - `pytest` 30 passed

### WorkBuddy 审计整改（已推送，`origin/main` 可见）

#### `c4a6c25` — F-01 / E-02 / F-02 / F-04
- **F-01**：`OptimizeResultItem` 加 `data_source` 字段并透传 `run_backtest` 结果（此前 optimize 接口
  完全漏传，mock 静默）；`Optimize`/`Compare` 表格加「数据源」列（绿=真实/橙=模拟）+ mock 红色告警
- **E-02**：`main.py` 503 分支加 `exc_info=True`（保留堆栈，防误判吞掉真实 bug）
- **F-02**：`stores/index.ts` 回测结果持久化到 `sessionStorage`（F5 不丢）
- **F-04**：`Optimize.tsx` 参数网格改 Tabs（可视化 最小值/最大值/个数 + 保留 JSON）
- `.gitignore` 忽略 `*.tsbuildinfo`、`backend/data/scan_results/`

#### `d8426cc` — S-01 / S-02 / S-03 / F-02c
- **S-03**：`Results.tsx` `data_source` 缺省不再宣称"真实行情"，改黄色"数据来源未知"警告
- **S-01**：`setResult` 写入失败 `console.warn`（不再静默吞配额错误）
- **S-02**：持久化带 schema 版本号，结构变更旧缓存自动作废
- **F-02c**：表单参数记忆（提交时存、mount 时回填，含 dayjs 反序列化）+ "重置为默认"按钮
- `requirements.txt` 补 `pytest>=8.0.0,<9.0.0`

#### `84e7f35` — S-04 / S-05
- **S-04**：`Results.tsx` 无交易提示孪生分支改三分支（unknown 不宣称真实，否则与上方 S-03 黄警自相矛盾）
- **S-05**：`Backtest.tsx` 参数保存从 `runBacktest` 之后挪到 `validateFields` 之后、请求之前
  （失败会跳 catch，旧位置永远执行不到；失败恰恰最需要保留参数）

#### `36cd9a4` — A-01 / B-01 / B-02
- **A-01**：`codegen.py` 记录所有退化条件于 `ctx.degraded`，入口统一拦截报错。
  原只检查整体 `"False"` 才能抓，导致：
  - 双条件其一失效 → 生成 `(x>0) and False` 漏抓
  - `MA5 > 未知指标` → 目标退化 `0.0` → 生成 `MA5 > 0.0` **恒真** → 策略变"有钱就买"漏抓
  现任一退化即拒绝生成，提示含"若取 0 会使条件恒真"
- **B-01**：导出 `Content-Disposition` 用 RFC 5987（ASCII 回退 + `filename*=UTF-8''...`），
  中文文件名不再 500；错误详情带真因（不再"请稍后重试"）
- **B-02**：CSV schema 拆 `ExportCsvDataRequest`（`data: list[dict]`），
  原 `ExportRequest.data: dict` 与实现要求 `list` 死结，CSV 永远不可用

---

## 3. 验证记录

| 项 | 结果 |
|---|---|
| 前端 `tsc -b --force` | 917c067 / 4b35b31 通过 |
| 后端 `py_compile` | 所有改动文件语法 OK |
| 后端 `pytest tests -q` | **30 passed**（36cd9a4 后） |
| **A-01 对照实验**（4 场景） | 合法生成 / 单失效拦截 / 双失效其一拦截 / MA5>未知拦截 — 全部符合预期 |
| **B-01/B-02 对照** | 中文文件名 200、CSV list 200、空 400 |
| **因子选股冒烟** | 真实数据返回、指标计算正确（MA 互补验证） |

---

## 4. WorkBuddy 复核历史中的误判更正（复核前必读）

这几点在此前报告中基于旧快照判断，最新代码已纠正，请于最新 `main` 重新确认：

1. **E-01「回归测试 0 条」— 误判**
   `backend/tests/` 已有 6 个测试文件（`test_analysis` / `test_costs` / `test_data_reliability` /
   `test_strategies_smoke` / `test_trading_rules` / `test_main`），对应提交 `d4cab30`，已在 `origin/main`。
   验证：`git ls-tree origin/main backend/tests/` 直接列出 6 文件；
   `git merge-base --is-ancestor d4cab30 origin/main` = YES。

2. **E-02「`_is_network_error` 仍用 27 个子串」— 误判**
   `core/net_errors.py` 早已收敛为 **21 个传输层特有短语**，注释明写排除 `TimeoutError`
   （避免把回测超时误报为网络问题）。

3. **CDN 缓存导致"改动没生效"假象 — 关键坑**
   `raw.githubusercontent.com` 对刚推送内容有约 5 分钟 `max-age` 缓存。
   此前第一次拉到旧副本，险些误判"一条都没改"。
   **所有 raw URL 必须带 cache-buster**：`.../stores/index.ts?cb=20260914120000`

---

## 5. 给 WorkBuddy 的复核指引

1. **先 `git pull` 最新 `main`**（目标 HEAD = `f3881f0`，核心 commit 已全部推送，直接拉取即可）
2. 核验远端代码**务必带 cache-buster** 拉 raw，否则命中旧缓存
3. 本地跑回归：`cd backend && python -m pytest tests -q`
   （`pytest` 已在 `requirements.txt` 声明，需先 `pip install -r requirements.txt`）
4. 重点复核项：
   - **因子选股器**：`POST /api/screener/run` 的真实筛选行为（mock 跳过、指标计算、结果正确性）
   - **A-01**：构造"双条件其一失效""`MA > 未知指标`"确认报错而非生成恒真策略
   - **F-01**：`optimize` / `compare` / `results` 三页数据源标注链路
   - **同花顺式 FactorEditor**：在策略编辑器的集成与旧规则压平

---

## 6. 待办 / 未做（明确告知，非遗漏）

- **P-01**（Results 页回显请求参数）：跑多次迭代后分不清哪个结果对应哪组参数。
  需后端加 `request_params`（~5 行）+ 前端顶部摘要（~15 行），为 v1.4 复盘/历史列表打底。
  WorkBuddy 建议"单独排一次"，**尚未实施**。
- **RealtimePool 的 F-01 状态条**：经核实该页不调回测、`akshare` 失败显式报错，
  F-01「基于 mock 回测的噪声决策」风险不成立，**可缓**。
- **安全事项**（与代码无关）：早期会话中一个 fine-grained PAT 明文进入过对话记录，
  建议持有者轮换。

---

## 7. 附：推送受阻与解决记录

核心 3 个 commit 起初推送 403，远端返回
`Permission to cemo0509/... denied to cemo0509`——**不是 remote URL 问题**（早已是干净 URL、
认证交给 GCM），而是本机 GCM 缓存的登录账号 `cemo0509` 对该仓库**没有写权限**。

解决过程（在用户终端）：

```powershell
cmdkey /delete:git:https://github.com   # 删掉失效的 GitHub 凭据
git push origin main                     # 重新弹 GitHub 登录，用有写权限的账号授权
```

推送成功：`36cd9a4..f3881f0  main -> main`。

推送后 `origin/main` = `f3881f0`，WorkBuddy 即可完整复核本轮升级。
