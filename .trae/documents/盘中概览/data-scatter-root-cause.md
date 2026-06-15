# data/ 散落文件根因分析

## 问题现状

`data/` 根目录散落 400+ 个文件，分 7 类：

| 类型 | 数量 | 示例 |
|------|------|------|
| 板块分钟线 `minute-YYYYMMDD-code.jsonl` | 336 | `minute-20260423-bank.jsonl` |
| 快照归档 `archive-YYYYMMDD.jsonl` | 51 | `archive-20260324.jsonl` |
| 概览历史 `overview-history-YYYYMMDD.json` | 15 | |
| 回测产物 `backtest_*.json/csv` | 6 | |
| 市场宽度缓存 | 3 | `breadth-cache.json`, `market-breadth-*.json` |
| 杂项数据 | 5 | `calendar.json`, `etf_benchmarks.json`, `northbound_flow.json` 等 |
| Python 脚本 | 1 | `Ashare.py`（不应在 data/ 中） |

---

## 根因 1：板块分钟线双轨制

存在两套不互通的落盘体系：

```
treasolo Python 脚本（n8n 调用）            server.js/context.js（Node API 服务）
    ↓                                              ↓
data/index/minute/sse/2026-06-15.jsonl       data/minute-20260615-sse.jsonl
data/sector/minute/bank/2026-06-15.jsonl     data/minute-20260615-bank.jsonl
data/etf/minute/sh512480/2026-06-15.jsonl    （ETF 无扁平路径，靠 Python 侧）
```

- **Python 采集链**（M1-A/B/C 工作流 → treasolo/m1_minute_fetch_*.py）写的是子目录规范路径，**符合 project_rules 规划**
- **Node API 服务链**（`server.js` 中的 `minuteFilePath()` 函数）仍然在写旧的扁平路径 `data/minute-{date}-{code}.jsonl`
- 午休持久化逻辑（`server.js` L6241-L6255）也从 `runtime/minute/` 往扁平路径拷贝
- 根目录 `minute-*` 文件从 4 月 23 日积压至今，约 34 个交易日

**为什么没清理**：`cleanup_minute_files.py` 只扫描 `data/index/minute/`、`data/etf/minute/`、`data/sector/minute/` 三级路径，不扫描 `data/` 根目录的 `minute-*` 文件。**是清理盲区。**

---

## 根因 2：archive 清理未实际生效

- `M1-F-Cleanup-Minute.json` 工作流配置了 `keepDays: 3, apply: true`
- 但 `archive-*.jsonl` 从 3 月 24 日积压到今天（近 3 个月），完整保留
- **说明 n8n 工作流在服务器上未实际调度，或 `/api/m1/run` 路由根本没有收这个请求**

排查方向：
- 服务器 `8787` 的旧 `server.js` 是否正常运行
- n8n 工作流在服务器上是否被启用、cron 触发是否正常
- `cleanup_minute_files.py` 的参数传递链路：`n8n → /api/m1/run → execFile` 是否正确调到了脚本

> 对应的好数据（`data/index/minute/`、`data/etf/minute/`、`data/sector/minute/`）已由 cleanup 脚本正常清理，说明脚本本身可运行，但 archive 清理块可能存在环境差异（如 n8n 工作流近期才加 archive 清理、或旧版 cleanup 没有这个块）。

---

## 根因 3：杂项文件归属缺失

| 文件 | 问题 | 应归入 |
|------|------|--------|
| `Ashare.py` | Python 脚本不应在 data/ | `treasolo/` 或项目根 |
| `backtest_*.json/csv` | 回测产物散落 | `data/astro/backtest/` |
| `breadth-cache.json` | 根目录单文件 | `data/market/minute/` |
| `market-breadth-*.json` | 根目录单文件 | `data/market/minute/` |
| `overview-history-*.json` | 根目录单文件 | `data/overview/history/` |
| `calendar.json` | 实际路径是 `config/holidays.json` | 可能同名混淆 |
| `etf_benchmarks.json` | 散落 | 可保留或移入 `data/etf/` |
| `northbound_flow.json` | 散落 | 可归入 `data/market/` |
| `market_context.json` | 散落 | 可归入 `data/market/` |
| `intraday-rotation-summary-*.json` | 散落 | 可归入 `data/market/minute/` |

---

## 根因 4：`server.js` 和 `server/api/*.js` 里仍保留了旧版数据读取路径

`server/api/shared.js` 里某些路由通过 `minuteFilePath()` 读的仍然是 `data/` 根部扁平文件，这些路由如果被调用到，也反过来在写扁平文件（比如 index/bank/broker/insure 板块数据有两份副本：一份在 `data/sector/minute/`，一份在 `data/` 根部）。

---

## 清理优先级建议

| 优先级 | 动作 | 影响 |
|--------|------|------|
| **P0** | 排查 n8n `M1-F-Cleanup-Minute` 在服务器上是否被调度 | 所有清理都不生效 |
| **P0** | 手动执行一次 `python3 treasolo/cleanup_minute_files.py --keep-days 3 --apply` 清理 archive + 散落 minute 文件 | 立即回收磁盘空间 |
| P1 | `cleanup_minute_files.py` 增加对 `data/minute-*.jsonl` 的清理块 | 防止再次堆积 |
| P1 | 统一 `minuteFilePath()` 落盘路径到 Python 脚本的 `data/{domain}/minute/{code}/{date}.jsonl` 结构 | 消除双轨制 |
| P2 | 归位散落 JSON 文件（回测→astro/backtest/、宽度→market/minute/ 等） | 目录整洁 |
| P2 | 删除 `Ashare.py`（data/ 下那一个） | 数据目录不应有脚本 |
