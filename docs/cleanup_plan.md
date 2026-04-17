# 仓库清理与重构计划 (Cleanup & Restructure Plan)

> **状态**: 待确认 (Draft)
> **原则**: 先建后拆，只删明确无用的产物/脚本，重构代码需保证 M0/M1 链路不中断。

---

## 1. 核心目录确立与重构 (traesolo 专区)

**决定**: 沿用拼写错误但寓意很好的 `treasolo/` (Treasure Solo，搞钱机器) 作为核心代码专区。
**重构动作**: 将当前散落在外的功能按“领域驱动”收拢到 `treasolo/` 内部。

**目标结构**:
```text
treasolo/
├── runner.py              # 唯一主入口 (n8n -> server.js -> runner.py)
├── analysis/              # 分析层：基于已有数据的计算 (信号、策略、复盘)
├── datasets/              # 数据集层：定义业务数据结构
│   ├── providers/         # 内部包：数据源对接 (akshare, sina, tencent 等)
│   └── qa/                # 内部包：强校验逻辑 (数据质量、空值、异常波动)
└── storage/               # 存储层：落盘与读取 (data/m1/, data/runs/ 等的读写)
```

**说明**: 数据源对接 (`providers`) 和 强校验 (`qa`) 确实应该属于 `datasets` 模块的下层实现，因为它们都是为了保证“吐出合格的数据集”而存在的。

---

## 2. 待清理清单 (可直接删除)

这些文件已被确认是测试产物、垃圾日志或废弃工作流，**清理后不会影响任何运行中的业务**。

### A. 废弃的日志与一次性分析产物
*路径: `logs/`*
- [ ] `logs/*.csv` (例如 `operation_advice_*.csv`, `operation_simple_*.csv`)
- [ ] `logs/*.json` (例如 `four_factor_*.json`, `kline_patterns_*.json`, `method_comparison_*.json`)
*(注：只删 csv/json，保留 `logs/*.log` 作为真实日志)*

### B. 废弃的 n8n 工作流
*路径: `n8n-workflows/`*
- [ ] `data-monitoring-workflow.json` (被 v2 替代)
- [ ] `data-monitoring-workflow-v2.json` (M0之前的老版本监控)
- [ ] `data-monitoring-workflow-detailed.json`
- [ ] `market-breadth-5m.json` (将被纳入 M1 或 treasolo 体系)

### C. 废弃的根目录测试脚本
*路径: 项目根目录*
- [ ] `test_*.py` / `test_*.js` (例如 `test_minute_pct.py`, `test_target.js`, `test_gtimg.py` 等)
- [ ] `check_*.py` (例如 `check_etf_data.py`, `check_etf_eastmoney.py`)
- [ ] `verify_*.py` (例如 `verify_pct_step1.py`)

---

## 3. 待确认清单 (需讨论或迁移)

这些文件可能还有参考价值，或者目前仍有部分功能依赖它们。

### A. 散落的业务脚本
*路径: `scripts/` 和 根目录*
- `scripts/market_snapshot_sina.py` (目前还有人在用它看实时快照吗？M1 会接管)
- `fetch_sector_data.py`, `sector_lifecycle.py` (旧版核心逻辑，是否移入 `_archive` 还是等 `treasolo/analysis` 重写后再删？)

### B. M0/M1 脚本归位
- 我们刚才写的 `scripts/m1_minute_to_daily.py` 和 `m1_backfill_index.py`，目前是通过 `server.js` 的 `/api/m1/run` 调用的。
- **确认点**: 是让它们继续待在 `scripts/` 里，还是借着这次重构，把它们改造成 `treasolo/runner.py` 的一个 Step (比如 `--steps m1-backfill`)？

---

## 4. 数据与版本控制规范

1. **`data/` 目录规范**:
   - `data/` 整体维持在 `.gitignore` 中，绝对不入 Git。
   - `data/runs/` (Run Journal) 的保留策略将写入代码：只保留最近 30 天。
2. **`logs/` 目录规范**:
   - 将 `logs/` 整体加入 `.gitignore`。
3. **工作流登记卡**:
   - 在 `docs/workflows/` 下为 M1-B、M1-Backfill 等建立 Markdown 说明卡片。