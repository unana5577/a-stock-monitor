# 交易助手 5 项问题修复方案（含后续补充）

---

# Part A: 原始 5 项修复（已执行完毕）

## 前期探索结论

ETF 注册后各管道状态：

| 管道 | 是否自动出现 | 备注 |
|------|-------------|------|
| sector-proxy.json | ✅ | POST /api/sector/manage 写入 |
| ETF 页面列表/卡片 | ✅ | GET /api/sector/manage → 完全动态 |
| ETF 页面生命周期卡片 | ✅ | 读 lifecycle.json (自动扫描 daily 目录) |
| ETF 页面归一分析 | ✅ | 读 warmup.json (自动扫描 daily 目录) |
| 概览页 ETF 名称 | ✅ | GET /api/sector/manage |
| 概览页 ETF 分钟线卡片 | ❌ → ✅已修复 | 已改为动态合并 etfSymbolNames keys |
| M1-C 分钟线 n8n | ✅ | 动态 API |
| M1-H stage_runner | ✅ | 读 sector-proxy.json |
| 交易助手 ETF 列表 | ✅ | GET /api/sector/manage |

## 已修复的 6 项

| # | 文件 | 改动 | 说明 |
|---|------|------|------|
| 1 | `pages/overview/ui.js` | fetchMinuteData 动态合并 etfSymbolNames keys | 新 ETF 自动出现在概览归一分析分时图 |
| 2 | `pages/trade/ui.js` | fetchLivePrices 条件改为 `?.minute_price` 可选链 | 新 ETF 不在 stageMap 也拉实时行情 |
| 3 | `pages/trade/ui.js` | syncMapsFromApi fallback `api_name \|\| key` + 行情名写入 symbolNames | 代码再也不裸显 |
| 4 | `server/api/etf.js` | triggerBackfillPipeline 改为 Promise，POST handler 同步 await | 回补弹窗真正等到完成后才显示 ✓ |
| 5a | `波段策略/ocr_positions.py` | parse_positions 每行优先扫描 6 位纯数字代码 | OCR 代码优先匹配 |
| 5b | `pages/trade/index.html` | 截图预览旁加 `✕ 删除截图` 按钮 | 可清除截图 |

---

# Part B: ETF 中文名获取路径（项目说明）

## 名字的唯一来源

整个系统里，ETF 中文名的**唯一外部数据源**是腾讯行情接口 `http://qt.gtimg.cn/q={code}`。不存在"Sina 开盘时用，腾讯收盘后用"的切换——名字和分钟线数据是完全不同的两条线，不要混淆。

## 名字的三条消费路径

| 路径 | 触发时机 | 调外部 API？| 产出 |
|------|---------|-----------|------|
| 后端 `POST /api/sector/manage` | 新增 ETF 注册 | 腾讯（写入 sector-proxy.json 后永久缓存）| `variants.etf["科创半导体设备ETF鹏华"] = "sh589020"` |
| 前端 `/api/trade/quote` | 交易助手代码输入 `onPosEditCodeInput` | 腾讯（每次输入都查一遍）| 实时行情 + 名字 |
| 前端 `GET /api/sector/manage` | ETF 列表/概览/交易助手名称加载 | **无**（读本地 sector-proxy.json）| `symbolNames["sh589020"] = "科创半导体设备ETF鹏华"` |

## 当前存在的问题：重复调腾讯

`POST /api/sector/manage` 和 `/api/trade/quote` 都会调腾讯拿同只 ETF 的名字。这是浪费，因为名字已经写入 sector-proxy.json 永久缓存了。合理的做法是：名字只在 POST 注册这一刻从腾讯获取一次并写入 proxy。之后所有页面（包括 `onPosEditCodeInput`）直接读 `symbolNames`（来自 proxy）即可，不需要再调腾讯。

## 已有的 OCR 漂移修复（待执行）

| # | 文件 | 改动 | 行数 |
|---|------|------|------|
| ocr-A | `波段策略/ocr_positions.py` | row_data["code"] 优先于 NAME_TO_CODE | 1 |
| ocr-B | `波段策略/ocr_positions.py` | normalize_name 返回 None 但已有代码时不丢弃行 | 3 |
| name-A | `pages/trade/index.html` | 名称输入框改为只读展示（loading/已获取/兜底三态）| 3 |
| name-B | `pages/trade/ui.js` | onPosEditCodeInput 加 posEditNameLoading 状态 | 3 |

---

# Part C: 新 ETF 注册后的完整数据链路（项目说明）

## 注册这一刻发生了什么

```
用户输入代码 → 点确认
  → registerEtfViaApi(sh589020)
    → POST /api/sector/manage {code, category, sub_category}
      → 后端做 5 件事：
        1. 校验代码格式 sh/sz + 6位数字
        2. 调腾讯拿名字 → "科创半导体设备ETF鹏华"
        3. 写入 sector-proxy.json（名字永久缓存）
        4. 启动回补流水线（4步串行，已改为同步等待）
        5. 返回 {ok:true, etfs: {sh589020: {api_name:"科创半导体设备ETF鹏华", ...}}}
```

## 回补流水线 4 步

```
步骤1: m1_backfill.py    调 Sina → 拉历史日线    → data/etf/daily/sh589020/daily.jsonl   耗时~30s
步骤2: m1_minute_fetch.py 调 Sina → 当前快照      → data/etf/minute/sh589020/{day}.jsonl 耗时~5s
步骤3: m1_warmup.py       无外部API → 60天聚合    → data/warmup/warmup-60.json            耗时~10s
步骤4: m1_lifecycle.py    无外部API → 生命周期分析 → data/lifecycle/lifecycle.json          耗时~15s
```

总耗时约 60-90 秒（已改为 POST 同步等待，前端弹窗"数据接入中..."覆盖全过程）。

## 4 步的依赖关系

```
daily.jsonl（步骤1产出）
    ├──→ warmup 消费（步骤3）→ warmup-60.json
    │                           └──→ lifecycle 消费（步骤4）→ lifecycle.json
    ├──→ lifecycle 直接消费（步骤4）
    └──→ stage_runner 消费（n8n M1-H 每5分钟）→ stage/snapshot.json

分钟 JSONL（步骤2产出）
    └──→ stage_runner --use-minute 模式消费（盘中阶段判定）
```

## 各页面如何感知新 ETF

| 页面 | 感知方式 | 需要哪些数据已就绪 |
|------|---------|-------------------|
| 交易助手 | GET /api/sector/manage + /api/trade/stage_snapshot | proxy.json + snapshot.json |
| ETF 行情页 | GET /api/sector/manage + lifecycle.json | proxy.json + lifecycle.json |
| 盘中概览 | GET /api/sector/manage + /api/m1/data/overview | proxy.json + warmup.json + lifecycle.json |

三个页面都归根到底依赖于步骤 1 的 daily.jsonl。如果步骤 1 失败 → 步骤 3/4 对这只 ETF 不产出数据 → ETF 行情页和概览页看不到分析。但交易助手仍能看到（只需要 proxy.json）。

---

# Part D: 当日分钟线问题诊断与方案

## 现状

`m1_minute_fetch_etf.py`（步骤 2）注册时拉取的只是**当前时刻的一个快照**（1 个点），不是全天 240 点的完整分时线。完整分时线要靠 **n8n M1-C** 工作流盘中每分钟从 Sina 拉一次累积起来。

| 场景 | 行为 | 结果 |
|------|------|------|
| 盘中注册 | n8n 每分钟补点一次 | 当天收盘有 240 点 ✅ |
| 盘后注册 | 只拉到 1 个点 + n8n 不跑（非交易时段）| 归一分析图横线 ❌ |

当前没有"历史分钟线回补"功能。

## 三种方案

### 方案 A：接受现状，不做改动

**逻辑**：新增 ETF 当天（或盘后新增的下一个交易日）n8n 盘中自然累积出完整分钟线。这和"一只刚上市的 ETF 第一天没有历史数据"是同一个道理——数据需要时间积累。

**改什么**：无。

**代价**：用户注册后的当天看不到完整的归一分析分时曲线（只有 1 个点），体验不好。

### 方案 B：回补管线中把分钟线也回补（多次调新浪）

**逻辑**：在步骤 2（m1_minute_fetch_etf.py）中增加"历史分钟线回补"模式。注册时如果已是下午 15:00 后，用 `ak.fund_etf_hist_sina` 拉当天分钟线（Sina 支持传 period="1" 获取当天 1 分钟线），一次性写入 240 个点。

**改什么**：
- `treasolo/m1_minute_fetch_etf.py`：增加 `--backfill` 参数，用 Sina 历史分钟线接口替代当前单次快照逻辑
- 约 15-20 行改动

**代价**：Sina 1min 历史线数据可能不全（只返最近几个交易日），且 AkShare 的 `fund_etf_hist_sina` 参数需要验证是否支持 period="1"。中等风险。

### 方案 C：注册后用腾讯分钟线替代，一次性回补当天全部点

**逻辑**：不通过 Sina 回补，而是用腾讯的分钟线 API（类似 `qt.gtimg.cn` 的 kline 接口）拉取当天已产生的全部分钟线，一次性写入。

**改什么**：
- 新增一个小脚本或复用 `server.js` 中已有的分钟线拉取逻辑（`fetchMinuteKlineForCode`）
- 在回补管线步骤 2 调用这个脚本
- 约 10 行改动

**代价**：腾讯分钟线接口目前只在 `server.js` 里指数（上证/深证/创业板/科创/沪深 300）用过，ETF 分钟线支持不确定。需要验证接口返回格式。

### 推荐方案 B

**风险最低**：只是把注册时的单次 Sina 快照改成 Sina 分钟线抓取，接口是同一个（`ak.fund_etf_category_sina` 换成 `ak.fund_etf_hist_sina`），不用引入新依赖。

---

# Part E: 盘中概览卡片新增 ETF 自动加入分析

## 当前状态

盘中概览页（`pages/overview/ui.js`）的数据来自 `/api/m1/data/overview`，该路由读取：

| 数据块 | 文件源 | 是否自动含新 ETF？|
|--------|--------|-------------------|
| warmup（60日量能）| data/warmup/warmup-60.json | ✅ 自动扫描 daily 目录 |
| lifecycle（板块分析）| data/lifecycle/lifecycle.json | ✅ 自动扫描 daily 目录 |
| market_amount（成交额）| data/market/daily/amount/daily.jsonl | ✅ ETF 无关，大盘数据 |
| intraday_snapshot（分时）| data/stage/snapshot.json（含 minute_price）| ✅ stage_runner 读 proxy |
| policy（政策面）| 本地配置 | ✅ ETF 无关 |

**结论**：盘中概览的 warmup/lifecycle 数据已经自动包含新增 ETF。因为 `m1_warmup.py` 和 `m1_lifecycle.py` 都是**扫描 data/etf/daily/ 目录**，只要 daily.jsonl 存在（回补步骤 1 成功），新 ETF 的数据就在下一轮 lifecycle 生成时被自动包含。

## 唯一需要确认的点

概览页 `fetchOverview()` 每 60 秒刷新一次。回补管线同步完成（已改为 await）时，POST 返回后 `lifecycle.json` 已是包含新 ETF 的最新版。概览页下次刷新（≤ 60 秒内）就能看到。

**无需额外改动。**

---

# Part F: 全部改动汇总

| # | 文件 | 改动 | 行数 | 状态 |
|---|------|------|------|------|
| 1 | pages/overview/ui.js | 概览 ETF 分钟线动态合并 | ~5 | ✅ 已执行 |
| 2 | pages/trade/ui.js | fetchLivePrices 可选链 | 1 | ✅ 已执行 |
| 3 | pages/trade/ui.js | api_name 兜底 + 行情名写入 | 3 | ✅ 已执行 |
| 4 | server/api/etf.js | 回补同步等待 | ~5 | ✅ 已执行 |
| 5a | 波段策略/ocr_positions.py | 6 位代码优先识别 | ~8 | ✅ 已执行 |
| 5b | pages/trade/index.html | 截图删除按钮 | 1 | ✅ 已执行 |
| ocr-A | 波段策略/ocr_positions.py | row_data["code"] 优先于 NAME_TO_CODE | 1 | 🔲 待执行 |
| ocr-B | 波段策略/ocr_positions.py | 有代码时不再丢弃行 | 3 | 🔲 待执行 |
| name-A | pages/trade/index.html | 名称输入框改为只读展示 | 3 | 🔲 待执行 |
| name-B | pages/trade/ui.js | onPosEditCodeInput 加 loading | 3 | 🔲 待执行 |
| min-A | treasolo/m1_minute_fetch_etf.py | 注册时回补当天完整分钟线（方案B）| ~18 | 🔲 待决策 |
| min-B | server/api/etf.js | 回补管线步骤 2 参数调整 | 1 | 🔲 待决策 |

**已执行**：6 项，~23 行。
**待执行（OCR+名称修复）**：4 项，~10 行。
**待决策（分钟线回补方案 B）**：2 项，~19 行。

---

# Part G: 验证步骤

1. OCR 截图 6 只 ETF → 结果含 6 只全部代码 → 一键导入成功
2. 新增 ETF 代码输入 → 名称自动展示为只读 "名称：科创半导体设备ETF鹏华（来自行情接口）"，无输入框
3. 新增 ETF → 回补弹窗 "数据接入中..." → 60-90 秒后 "✓ 数据回补完成"
4. 持仓列表中文名显示正常（非代码）
5. ETF 行情页生命周期卡片含新增 ETF
6. 概览页归一分析分时图含新增 ETF 曲线
7. 截图预览旁有删除按钮
