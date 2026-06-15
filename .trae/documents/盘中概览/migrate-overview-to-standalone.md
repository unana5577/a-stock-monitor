# 盘中概览页迁移计划

## 目标

将 `public/index_m1.html` + `public/ui_m1.js` 单体内仅存的 TAB 1（盘中概览）拆到 `pages/overview/`，上线后旧的 `index_m1.html` 弃用。**纯搬运，不改功能、不修 bug。**

## 关键结论：迁移完可以弃用旧单体

- ETF 行情（TAB 2）已在 `pages/etf/` 独立运行（端口 8782）
- 交易助手（TAB 3）已在 `pages/trade/` 独立运行（端口 8783）
- 天时实验（TAB 4）框架已就位 `pages/astro/`（Agent D 后续搬入）
- 旧 `index_m1.html` 仅剩 TAB 1 盘中概览 → 本次搬完后，`index_m1.html` + `ui_m1.js` 即可弃用

## 当前状态

| 文件 | 状态 |
|------|------|
| `pages/overview/server.js` | ✅ 已就位，端口 8781，API 已代理到 8787 |
| `pages/overview/index.html` | ❌ 不存在，需要新建 |
| `pages/overview/ui.js` | ❌ 不存在，需要新建 |
| `server/api/overview.js` | ✅ 已有 13 条概览专属路由，直接用 |
| `public/index_m1.html` | 仅剩 TAB 1（179-316 行）+ Tab 导航栏（90-135 行），搬完可删除 |
| `public/ui_m1.js` | 2775 行，TAB 2/3/4 的代码已复制到各自页面，本次提取 TAB 1 代码 |

## 搬到 overview 页面的内容

### 1. pages/overview/index.html

复制 `pages/etf/index.html` 的骨架结构（head 完全一致），替换 body 内容为 TAB 1 的三个区块：

| 区块 | 说明 |
|------|------|
| AI 宏观解读与仓位建议 | 左侧进度条 + 右侧 AI 文本 |
| 市场情绪与成交额对比 | 左涨跌平 + 右 ECharts 量能曲线 |
| 核心资产分时矩阵 | 多个 1 分钟分时卡片 |

所有 Vue 绑定变量名保持不变（`overviewAiPositionPct`、`breadthData`、`volumeStats` 等）。

### 2. pages/overview/ui.js

从 `ui_m1.js` 提取 overview 独占的代码：

**Data refs（9 个）**
- `marketAmount` — 成交额快照
- `breadthData` — 涨跌家数
- `volumeHistory` — 历史成交额序列
- `intradayVolume` — 今日分钟成交额
- `intradayYdayVolume` — 昨日分钟成交额
- `volumeStats` — 量能对比结论
- `overviewAiText` — AI 文本
- `overviewAiUpdatedAt` — AI 更新时间
- `overviewAiLoading` — AI 加载状态

**Computed（2 个）**
- `overviewAiSections` — AI 分段解析
- `overviewAiPositionPct` — 仓位百分比提取

**Methods（5 个）**
- `fetchOverview()` — 调 `/api/m1/data/overview`
- `fetchBreadth()` — 调 `/api/market/breadth`
- `fetchVolumeHistory()` — 调 `/api/m1/data/volume_history`
- `refreshOverviewAi()` — 调 `/api/ai/report`
- `renderVolumeChart()` — 渲染量能 ECharts

**共享工具函数（复制副本，不进 shared）**
- `formatAmount()`、`getPriceColor()`、`parseAiSections()` — 各页面各自维护副本（和 ETF 页面的处理方式一致）

**共享数据（从 fetchOverview 返回中取 overview 用到的字段）**
- `indexSymbols`、`symbolNames`、`currentPrices`、`chartsLoaded`、`lastUpdate`
- 以及分时矩阵渲染相关：`fetchMinuteData()`、`renderMinuteChart()`

### 3. 轮询

`onMounted` 里起 60s 定时器，刷新 `fetchOverview()` + `fetchBreadth()` + `fetchMinuteData()`。

## 不需要搬的

- **Tab 导航栏**：每个页面独立，不需要 sidebar 切换
- **TAB 2/3/4 的 HTML 和 Vue 逻辑**：已在各自页面或等待 Agent 搬
- **旧 monolith 的 `activeTab` 切换逻辑**：独立页面不需要
- **旧 monolith 里的 `watch(activeTab)` 图表 resize**：独立页面不需要

## 文件变更

| 操作 | 文件 |
|------|------|
| 新建 | `pages/overview/index.html` |
| 新建 | `pages/overview/ui.js` |
| 不改动 | `pages/overview/server.js`（已就位） |
| 不改动 | `public/index_m1.html`、`public/ui_m1.js`（迁移完成后择机删除） |

## 验证

```bash
# 启动 overview 页面
node pages/overview/server.js
# 浏览器打开 http://localhost:8781

# 验证 checklist
curl http://127.0.0.1:8781/                  → 200
curl http://127.0.0.1:8781/api/m1/data/overview  → 200 with ok:true
```

预期现象：
- 页面显示三个区块，没有报错
- 成交额曲线正常渲染（ECharts）
- 核心资产分时图每 60s 刷新
- AI 复盘文本正常显示
