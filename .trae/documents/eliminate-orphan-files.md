# 消除落盘孤儿文件计划

## 目标

1. 所有落盘文件必须被消费（没有孤儿文件）
2. n8n 采集链是唯一的分钟线文件生产者（Node.js 侧不再写落盘文件）
3. 旧 server.js（8787）和新骨架（8788）同时满足上述要求

---

## 完整审计结果

### 每个文件的落盘与消费分析

| 文件 | 落盘者 | 消费者 | 结论 |
|------|--------|--------|------|
| `data/minute-*.jsonl` | LunchSave 午休持久化（Node.js 非 n8n） | `/api/minute/<code>` 路由 → **此路由无前端/n8n 调用** | **孤儿文件，删除写入链** |
| `data/archive-*.jsonl` | `archiveSnapshot()` → `/api/snapshot` 等路由触发 | 5 条路由（snapshot / panic / breadth / volumeCmp / AI aggregator） | **保留，有消费者** |
| `data/overview-history-*.json` | `/api/overview/history` 路由 | 只有 `/api/overview/history` 自己 | **保留，有消费者** |
| `data/backtest_*.json/csv` | 手动回测脚本 | `/api/signals` 消费 backtest_false_kill.json，但文件不存在 → 永久空数组 | **删除根目录残留文件，保留代码中的读逻辑不动** |
| `data/Ashare.py` | rsync 遗留 | 无 | **删除** |
| `data/etf_benchmarks.json` | 不存在 | 代码零引用 | 无操作 |
| `data/northbound_flow.json` | 不存在 | 代码零引用 | 无操作 |
| `data/market_context.json` | 不存在 | 代码零引用 | 无操作 |
| `data/breadth-cache.json` | `buildSnapshotPayload` + `breadth_manager.py` | `/api/market/breadth` + AI 聚合 | **保留** |
| `data/calendar.json` | `readCalendarEvents()` 自动创建空模板 | `/api/calendar` | **保留** |

---

## 要删除的（旧 server.js 和 context.js 两个文件都要改）

### 1. 删除午休持久化 setInterval

**文件**：`server.js`（根目录那个旧文件，~L6227-L6256）

**内容**：每分钟检查一次，11:30 时把 `runtime/minute/minute-{day}-{code}.jsonl` copy 到 `data/minute-{day}-{code}.jsonl`

**删除理由**：这是唯一的非 n8n 落盘入口，产物无人消费。`runtime/minute/` 里的文件只在内存态有用，不需要固化到 data/。

### 2. 删除 `/api/minute/<code>` 整个路由

**文件**：`server/api/shared.js`（L164-L440 左右）

**内容**：`if (url.pathname.startsWith('/api/minute/'))` 开头的路由大块（约 280 行），根据 code 前缀分 ETF/指数/板块分支，内部读取 `data/minute-*` 与 `runtime/minute-*` 合并后返回

**删除理由**：0 个前端页面、0 个 n8n 工作流调用此路由

### 3. 修改 `loadMinuteSeries()` 停止读扁平文件

**文件**：`server.js` 和 `server/context.js` 中的 `loadMinuteSeries()` 函数

**现状**：第一数据源尝试 `data/minute-YYYYMMDD-{code}.jsonl`，然后与 `runtime/minute/` 合并

**改为**：第一数据源改为读取结构化目录：
- 指数类（sse/szi/gem/star/hs300）：`data/index/minute/{code}/{date}.jsonl`
- 板块类（bank/broker/insure）：`data/sector/minute/{code}/{date}.jsonl`
- 国债类（gov/t/tl）：`data/sector/minute/{code}/{date}.jsonl`
- 加权合成类（avg/csi2000）：运行时从成分股实时计算（当前逻辑不变）

**fallback 链保持**：结构化文件 → runtime 合并 → 网络 fetch → runtime 兜底

### 4. 删除三个孤儿函数

**文件**：`server.js` 和 `server/context.js`

| 函数 | 理由 |
|------|------|
| `minuteFilePath()` | 只生成 `data/minute-*` 路径，唯一调用方是 `/api/minute/<code>` 路由和 `loadMinuteSeries()`，两者都已删除/迁移 |
| `findLatestMinuteFile()` | 同上，是 `/api/minute/<code>` 的兜底函数 |
| `prevCloseFromMinuteFile()` | 同上，只被已删除路由调用 |

### 5. 更新 context.js 的 exports

删除 `minuteFilePath`, `findLatestMinuteFile` 等的模块导出（从 install 注入列表移除）。

---

## 不动的

| 内容 | 理由 |
|------|------|
| `archiveSnapshot()` 及相关 archive 读写 | 5 条路由消费 |
| `/api/overview/history` 及其缓存 | overview 板块消费 |
| `backtest_false_kill.json` 的**读取逻辑**（`buildSignalsFromBacktest()`） | 代码保留，`/api/signals` 功能不变（仍返回空数组）。生成脚本是外部回测工具，不属于本次范围 |
| `breadth-cache.json` / `calendar.json` 读写 | 均有合法消费者 |
| `cleanup_minute_files.py` 中的 `cleanup_flat_minute_files()` | 保留此函数，处理历史遗留（直到所有旧文件被自然清理完） |
| n8n 工作流、treasolo Python 脚本 | 零改动 |

---

## 改动范围

| 文件 | 操作 |
|------|------|
| `server.js`（旧 8787） | 删除 LunchSave setInterval（~30行）、删除 `loadMinuteSeries` 内读扁平文件逻辑、删除三个函数定义 |
| `server/context.js` | 修改 `loadMinuteSeries()` 读结构化目录、删除 `minuteFilePath`/`findLatestMinuteFile`/`prevCloseFromMinuteFile` |
| `server/api/shared.js` | 删除 `/api/minute/<code>` 路由块（~280行） |
| `data/backtest_*.json`、`data/backtest_*.csv`、`data/Ashare.py` | 删除残留文件 |
| `treasolo/cleanup_minute_files.py` | 保留不动（已有 flat 清理块） |

---

## 验证清单

```bash
# 1. 启动旧 8787 → 不崩溃
node server.js &
curl http://127.0.0.1:8787/health

# 2. 核心路由全部返回 200（不受影响）
curl http://127.0.0.1:8787/api/snapshot
curl http://127.0.0.1:8787/api/panic
curl http://127.0.0.1:8787/api/market/status
curl http://127.0.0.1:8787/api/m1/data/overview
curl http://127.0.0.1:8787/api/m1/data/minute?symbol=sh000001

# 3. 确认午休不再写新文件
# 模拟 11:30 或等到实际 11:30，检查 data/ 下无新的 minute-*.jsonl

# 4. 确认 cleanup 脚本对旧文件的清理逻辑仍正常
python3 treasolo/cleanup_minute_files.py --keep-days 3 --apply
```
