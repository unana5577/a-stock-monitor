# M1 数据与文件规范约定

为避免历史遗留问题（如 `data/index_daily` 混乱、文件含义不清）在 M1 阶段重演，所有由 M1 新产生的数据文件和脚本必须严格遵循以下目录结构和命名规范。

---

## 1. 业务产物目录 (`data/m1/`)

为了与过去的代码彻底隔离，M1 阶段的所有增量业务数据均落盘于 `data/m1/` 下，按**数据类型**划分。

```text
data/m1/
├── market/                 # 全市场级别宏观数据
│   ├── market_amount.jsonl     # 全市场真实总成交额（含上证+深证+ETF）
│   ├── market_breadth.jsonl    # 全市场涨跌家数与情绪快照
│
├── index/                  # 各大宽基指数的日线/分时数据
│   ├── sh000001/
│   │   ├── daily.jsonl         # 完美日线（含真实 OHLC 与真实 Amount）
│   │   ├── minute.jsonl        # 盘中分时流（当天结束后归档或滚动）
│   ├── sz399001/
│   │   ├── daily.jsonl
│   │   └── ...
│   └── ...
│
└── etf/                    # 具体 ETF 的日线/分时数据
    ├── 510300/
    │   ├── daily.jsonl         # 包含 amount 的个股级日线
    │   └── ...
    └── ...
```

**文件规范约定：**
1. **统一扩展名**：流式追加数据必须为 `.jsonl`。
2. **强制元数据**：任何 `xxx.jsonl` 旁必须生成同名 `.meta.json`，说明其更新时间 (`asOf`)、数据源 (`providerId`) 等。
3. **数据冗余处理**：禁止在一个文件里既存分时又存日线，**时间颗粒度必须物理隔离**（目录或文件名区分）。

---

## 2. 脚本与工作流隔离

为避免旧脚本（如 `scripts/market_snapshot_sina.py`）里各种历史补丁的干扰，M1 的新代码采取完全独立的文件。

```text
# 1. 核心运行逻辑（纯 Python）
treasolo/
├── m1_market.py        # 专门负责 M1 阶段的全市场数据抓取与合并
├── m1_index.py         # 专门负责 4大指数/沪深300 的分时转日线及 Amount 拼接
└── m1_etf.py           # 专门负责 ETF 级别的数据抓取与校验

# 2. n8n 工作流定义（JSON）
n8n-workflows/
├── M1-A-Market-Amount.json       # 替换/升级原 M0-A
├── M1-B-Index-Daily-Merge.json   # 批量处理 4 大指数的日线合并
└── M1-C-ETF-Daily.json           # 专门处理 ETF 级别的数据
```

---

## 3. 旧文件清理准则（TODO 列表）

在 M1 业务完全跑通并能在前端展示前，旧文件**只读不删**。
一旦 M1 对应模块上线，我们将按以下路径清理：

1. **废弃池**：新建 `data/_deprecated_m0_before/`，将旧文件移入。
   - 例：`mv data/index_daily/index_000001.jsonl data/_deprecated_m0_before/`
2. **平滑过渡**：前端 API 或查询接口切换为读取 `data/m1/` 下的新路径。
3. **历史清洗**：如果 M1 需要补齐历史日线（比如 4-16 的空缺），必须通过专门的 `scripts/m1_backfill.py` 脚本，从可信接口（新浪/腾讯）重拉数据写入 `data/m1/`，**绝对不从旧文件中提取残缺数据**。