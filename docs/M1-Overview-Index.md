# M1 阶段：大盘核心数据全景索引卡

本文档专为你快速定位 M1 阶段的核心数据工作流与文件层级而写。
**任何时候你找不到文件或不知道该点哪个，查这张表就够了。**

***

## 数据落盘终极目录树

为了保证文件分类极其干净、严谨，所有的行情数据严格遵循 `data/<类别>/<周期>/<标的代码>/` 的对称层级结构落盘：

```text
data/
  ├── market/                  # 宏观市场指标 (无具体标的)
  │    ├── market_amount.jsonl     # 全市场成交额与ETF占比 (每5分钟追加)
  │    └── minute/
  │         └── breadth-cache.jsonl# 盘中涨跌家数情绪 (每5分钟追加)
  │
  ├── index/                   # 大盘宽基指数
  │    ├── daily/
  │    │    ├── sh000001/daily.jsonl
  │    │    └── sz399001/daily.jsonl
  │    └── minute/
  │         ├── sh000001/2026-04-17.jsonl
  │         └── sz399001/2026-04-17.jsonl
  │
  └── etf/                     # 行业与主题 ETF
       ├── daily/
       │    ├── sh511130/daily.jsonl
       │    └── sh512480/daily.jsonl
       └── minute/
            ├── sh511130/2026-04-17.jsonl
            └── sh512480/2026-04-17.jsonl

  ├── warmup/                  # 预热与缓存聚合
  │    └── warmup-60.json      # 提取自 index与etf的最近60天日线聚合
  │
  ├── lifecycle/               # 业务分析与计算结果
  │    └── lifecycle.json      # 基于 warmup-60 计算出的各板块生命周期、均线及建议
  │
  └── stage/                   # 波段交易助手 (M1-H)
       └── snapshot.json       # 每5分钟更新的盘中五阶段实时快照
```

***

## 核心目录速查

你只需要记住这三个地方：

1. ⚙️ **要往 n8n 导入工作流？** → 找 `n8n-workflows/` (全都是 `.json`)
2. 💻 **想改底层的 Python 抓取逻辑？** → 找 `treasolo/` (全是核心 `.py` 脚本)
3. 💾 **想查看抓下来的数据结果？** → 找 `data/` (全是 `.jsonl` 记账本)

***

## 5 条核心工作流明细表

### 1. 全市场成交额抓取

- **用途**：每 1 分钟算一次“全市场成交额”和“ETF占比”。(注：开盘时验证)
- **导入 n8n 用的文件**：[n8n-workflows/M1-Market-Amount.json](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/n8n-workflows/M1-Market-Amount.json)
- **底层 Python 脚本**：[treasolo/m1\_market\_amount.py](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/treasolo/m1_market_amount.py)
- **抓下来的数据存在哪**：`data/market/market_amount.jsonl`

### 2. 市场涨跌情绪抓取

- **用途**：每 5 分钟算一次“上涨/下跌/平盘家数”。(注：已按照“麻烦的接口.md”使用新浪全市场接口，需开盘验证)
- **导入 n8n 用的文件**：[n8n-workflows/M1-Breadth-Fetch.json](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/n8n-workflows/M1-Breadth-Fetch.json)
- **底层 Python 脚本**：[treasolo/breadth\_manager.py](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/treasolo/breadth_manager.py)
- **抓下来的数据存在哪**：`data/market/minute/breadth-cache.jsonl`

### 3. 大盘指数：盘中分时抓取

- **用途**：每 1 分钟抓取 6 大指数当前的分钟价，用于画分时线。
- **导入 n8n 用的文件**：[n8n-workflows/M1-A-Index-Minute-Fetch.json](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/n8n-workflows/M1-A-Index-Minute-Fetch.json)
- **底层 Python 脚本**：[treasolo/m1_minute_fetch_indices.py](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/treasolo/m1_minute_fetch_indices.py)
- **抓下来的数据存在哪**：`data/index/minute/<代码>/<日期>.jsonl`

### 4. 金融三板块：盘中分时抓取

- **用途**：每 1 分钟抓取银行、证券、保险三大行业指数（使用新浪源 `sz399986`, `sz399975`, `sz399809` 替代常被墙的东方财富 BK 板块）的分钟数据。
- **导入 n8n 用的文件**：[n8n-workflows/M1-B-Sector-Minute-Fetch.json](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/n8n-workflows/M1-B-Sector-Minute-Fetch.json)
- **底层 Python 脚本**：[treasolo/m1_minute_fetch_sector.py](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/treasolo/m1_minute_fetch_sector.py)
- **抓下来的数据存在哪**：`data/sector/minute/<bank/broker/insure>/<日期>.jsonl`

### 5. 大盘指数：收盘抢发日线

- **用途**：每天 15:01，用最后一次分时价，拼出今天的日线收盘价。
- **导入 n8n 用的文件**：[n8n-workflows/M1-B-Minute2Daily.json](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/n8n-workflows/M1-B-Minute2Daily.json)
- **底层 Python 脚本**：[treasolo/m1\_minute\_to\_daily.py](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/treasolo/m1_minute_to_daily.py)
- **抓下来的数据存在哪**：`data/index/daily/<代码>/daily.jsonl`

### 6. 大盘指数与 ETF：晚间权威对账与回补 (共用)

- **用途**：每天 18:00，去官方接口要最终结算日线，强制覆盖我们 15:01 抢发的数据，保证 100% 准确。支持对所有大盘指数与 ETF 的日线进行漏缺天数补齐。在此工作流最后，会自动再次触发 Warmup 与 Lifecycle 刷新业务指标。
- **导入 n8n 用的文件**：[n8n-workflows/M1-E-Backfill-Universal.json](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/n8n-workflows/M1-E-Backfill-Universal.json)
- **底层 Python 脚本**：[treasolo/m1_backfill.py](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/treasolo/m1_backfill.py)
- **抓下来的数据存在哪**：与各自的日线是同一个文件 `data/index/daily/<代码>/daily.jsonl` 或 `data/etf/daily/<代码>/daily.jsonl`，直接覆盖更新。

***

## ETF 专属工作流 (含分时与日线)

### 7. ETF：盘中分时抓取 (全字段)

- **用途**：每 1 分钟抓取核心 ETF 分时数据，包含 `price`, `pct`, `amount`, `vol`, `open`, `high`, `low` 等完整字段。
- **导入 n8n 用的文件**：[n8n-workflows/M1-C-ETF-Minute-Fetch.json](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/n8n-workflows/M1-C-ETF-Minute-Fetch.json)
- **底层 Python 脚本**：[treasolo/m1_minute_fetch_etf.py](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/treasolo/m1_minute_fetch_etf.py)
- **抓下来的数据存在哪**：`data/etf/minute/<代码>/<日期>.jsonl`

### 8. ETF：收盘抢发日线

- **用途**：每天 15:01，用 ETF 的最后一次分时数据，生成当天的收盘日线。**注：本脚本包含严格的分时完整性校验。如果盘中分时断流或缺失 15:00 数据，将自动触发官方接口回补，补齐 240 分钟后再精确推导 OHLC 与成交量，确保日线无误。**
- **导入 n8n 用的文件**：[n8n-workflows/M1-D-ETF-Minute2Daily.json](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/n8n-workflows/M1-D-ETF-Minute2Daily.json)
- **底层 Python 脚本**：[treasolo/m1_minute_to_daily_etf.py](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/treasolo/m1_minute_to_daily_etf.py)
- **抓下来的数据存在哪**：`data/etf/daily/<代码>/daily.jsonl`

***

## 预热与生命周期分析

### 9. 核心缓存预热与业务指标 (Warmup & Lifecycle)

- **用途**：盘后（或日线回填后）触发。从历史文件中提取并聚合最近 60 天的数据，计算 MA5/10/20 均线以及所处生命周期阶段（吸筹、主升、主跌等），为前端极速渲染提供统一缓存。
- **导入 n8n 用的文件**：[n8n-workflows/M1-G-Warmup-Lifecycle.json](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/n8n-workflows/M1-G-Warmup-Lifecycle.json)
- **底层 Python 脚本**：相关聚合逻辑内置于各管理脚本中，输出为静态 JSON。
- **抓下来的数据存在哪**：`data/warmup/warmup-60.json` 和 `data/lifecycle/lifecycle.json`

***

## AI 盘面解析工作流

### 10. 大盘综合智能复盘 (DeepSeek)

- **用途**：交易日内每半小时（10:00, 10:30, 11:00, 13:30, 14:00, 14:30）自动执行。提取当前的大盘、国债、情绪、量能特征，喂给大模型输出三段式实战点评。
- **导入 n8n 用的文件**：[n8n-workflows/M1-AI-Intraday-Report.json](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/n8n-workflows/M1-AI-Intraday-Report.json)
- **底层 Python 脚本**：[treasolo/m1_ai_aggregator.py](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/treasolo/m1_ai_aggregator.py) & [treasolo/m1_ai_reporter.py](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/treasolo/m1_ai_reporter.py)
- **使用的 Prompt**：[prompts/stock-daily-v2.txt](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/prompts/stock-daily-v2.txt)
- **抓下来的数据存在哪**：`data/market/ai/snapshot.jsonl`（特征底表）和 `data/market/ai/report.jsonl`（大模型推理结果）

### 11. ETF 板块轮动 AI 解析

- **用途**：交易日内配合大盘解析执行，基于 11 大行业 ETF 的资金偏好、涨跌异动与量价背离，生成“科技/资源阵营跷跷板”等资金流向推演。
- **导入 n8n 用的文件**：[n8n-workflows/M1-AI-ETF-Intraday-Report.json](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/n8n-workflows/M1-AI-ETF-Intraday-Report.json)
- **底层 Python 脚本**：[treasolo/m1_etf_ai_reporter.py](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/treasolo/m1_etf_ai_reporter.py)
- **抓下来的数据存在哪**：`data/market/ai/etf_report.jsonl`

***

## 运维、清理与可观测性

### 12. 分时数据过期清理 (保留 T-3)

- **用途**：每天 09:15 自动扫描 `index/minute/`、`etf/minute/` 和 `sector/minute/` 等目录，按文件倒序严格保留每个标的最近 3 个交易日的分时数据，删除冗余文件。同时清空 `breadth-cache.jsonl` 情绪缓存，并在原位按行截断保留 AI 日志文件的最近 3 天记录，防止单文件无限膨胀。
- **导入 n8n 用的文件**：[n8n-workflows/M1-F-Cleanup-Minute.json](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/n8n-workflows/M1-F-Cleanup-Minute.json)
- **底层 Python 脚本**：[treasolo/cleanup_minute_files.py](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/treasolo/cleanup_minute_files.py)

### 13. N8N 工作流可观测性监控 (Observability)

- **用途**：探针级工作流，负责监控系统内其他业务工作流的运行状态（如执行耗时、成功率、节点报错抛出），为后续运维排障提供日志支撑。
- **导入 n8n 用的文件**：`runner-observability.json` / `runner-observability-intraday.json` / `runner-observability-manual.json`

***

## 波段交易助手专属工作流

### 14. 五阶段实时快照（日线 + 分时混合）

- **用途**：每 5 分钟（盘中）通过 HTTP POST 调用服务端 `POST /api/trade/run-stage-snapshot`，触发 `波段策略/stage_runner.py --use-minute --output-snapshot`。读取每只 ETF 日线 + 当日分钟线，将最新分钟价拼入日线末尾后用实时价判断五阶段（主升/启动/震荡/下跌/防守）及 MA20 挂单价，写入 `data/stage/snapshot.json` 供前端毫秒级读取。
- **导入 n8n 用的文件**：[n8n-workflows/M1-H-Stage-Snapshot.json](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/n8n-workflows/M1-H-Stage-Snapshot.json)
- **底层 Python 脚本**：[波段策略/stage_runner.py](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/波段策略/stage_runner.py) (参数: `--use-minute --output-snapshot`)
- **抓下来的数据存在哪**：`data/stage/snapshot.json`
- **下游消费者**：`GET /api/trade/stage_snapshot` → 交易助手页（8783 端口）→ 表格阶段列 + 持仓实时收益 + 多档挂单价
- **备用方案**：若未导入 n8n，`pages/trade/server.js` 已内置 `setInterval` 5 分钟定时器。

