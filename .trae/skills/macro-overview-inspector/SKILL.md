---
name: "macro-overview-inspector"
description: "Inspects market overview (indices breadth, total turnover, volume series) and backfill completeness. Invoke when overview cards show wrong totals, missing yday, or flat/odd curves."
---

# Macro Overview Inspector

## Purpose

专门针对“大盘概况”区域（指数、上涨/下跌家数、全市场成交额、分时曲线、昨对比）做快速排查与对账，重点解决：
- 昨日/收盘数据不全
- 时间轴错位（时区/交易分钟过滤）
- 全市场口径 vs 局部口径混用

## Quick Checklist

1. **Total Turnover (全市场成交额)**
   - 今日总额：来自实时快照汇总（通常是沪+深金额）
   - 昨日总额：必须能从“日线/权威源”取到并回填（不能靠不完整的本地 archive）

2. **Intraday Series (分时曲线)**
   - 时间必须是北京时间 `09:30-11:30 + 13:00-15:00`
   - 分时数据若是累计口径：分时（每分钟）需要差分；累计曲线需要单调

3. **Freshness**
   - `asof` / `asof_ts` 是否更新
   - `market_open` 为 true 时是否按节奏刷新

4. **Cross-check**
   - 用两个来源对账：
     - 快照当日总额（实时）
     - 日线昨日总额（收盘后）

## Common Root Causes

- **时区错误**：用 `new Date(ts)` 的本地时区直接取 `HH:MM`，会把交易时间映射到 `00:xx` 等错误区间
- **昨日不全**：服务没在收盘后抓取一次最终值，导致昨日只到上午/中午
- **口径不一致**：把“主板”当成“全市场”或反之

## What to Inspect in Code

- `server.js`
  - 归档：是否每个交易日收盘后保证写入最终一条
  - 分时成交额：时间轴生成与过滤（交易分钟）
  - 昨日对比：昨日总额的回填来源与优先级

- `public/ui.js`
  - spark 图：画的是累计曲线还是分时曲线、昨日线的含义
  - 文案：避免用“增量/热度”造成口径误解

## Recommended Debug Output

- 今日：总额、asof、分时点数、最后一个时间点
- 昨日：总额来源（回填/本地/归档）、是否有 15:00 点
- UI：当前展示的是累计还是分时，昨日线表示什么
