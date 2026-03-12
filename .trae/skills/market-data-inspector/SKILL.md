---
name: "market-data-inspector"
description: "Audits quote/sector data sources and freshness. Invoke when prices/pct/volume look wrong, stale, or inconsistent across UI blocks."
---

# Market Data Inspector

## Purpose

快速定位“行情/板块/自选池/量能”相关问题的根因：数据源是哪一个、是否过期、口径是否一致、是哪一段链路把口径算错了。

## What to Check First (60 seconds)

1. **源与新鲜度**
   - 找到对应接口返回里的 `asof` / `asof_ts` / `source` / `market_open` 字段
   - 判断数据是否来自缓存、是否跨日、是否在交易时段却不刷新

2. **口径**
   - `pct` 是否按 “昨收→现价/收盘” 计算（而不是 “今开→现价/收盘”）
   - 分时（minute）与日线（daily）是否混用、是否用错了 `prevClose`

3. **一致性对账**
   - 选一个标的/ETF：对比
     - 日线最后两天 `pct`
     - 分时最后价与 `prevClose` 推导的实时 `pct`
   - UI 不一致通常是“源不同”或“pct 口径不同”

## Repository Hotspots (where to look)

- **Server 聚合与缓存**
  - `server.js`：分钟线、快照、板块代理、asof/source 注入、volume compare
- **Frontend 计算与展示**
  - `public/ui.js`：自选池“昨/今”、分时渲染、成交额曲线、文案口径
  - `public/index.html`：各卡片字段的标题与 tooltip 口径
- **Python 数据构造**
  - `fetch_sector_data.py`：板块/指数/市场成交额的日线构造、补数命令

## Debug Playbooks

### A) “自选池昨/今/实时对不上行情软件”

Checklist:
- 是否走了 ETF 代理口径（proxy+etf）
- `history[-2].pct` 是否对应“上一交易日”
- `history[-1].pct` 是否对应“昨收→今收”
- `minute.prevClose` 是否为昨收、并且分时 `series` 是当日

### B) “成交额对比/昨日缺失/收盘不全”

Checklist:
- 分时序列时间轴是否用北京时间（避免 `00:xx` 这种非交易时间）
- 昨日是否有收盘数据点（15:00）
- 若缺失：是否触发了“补齐昨日/收盘成交额”的请求回填逻辑

### C) “热度Δ/量能Δ特别大”

Checklist:
- UI 文案是否表达的是 **占比变化** 还是 **成交量变化**
- 指标字段来源：`Amount_Share_Change`（占比相对变化） vs `volChange`（近5日/近20日成交量变化）

## Output Format (what to report back)

- **Symptom**：哪里不对（UI 区域 + 标的/板块名）
- **Source**：数据来自哪里（API/缓存/文件/第三方）
- **Freshness**：asof 与是否跨日
- **Mismatch**：哪个字段/口径导致不一致
- **Fix**：建议改动点（前端/后端/数据源）
