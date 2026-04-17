# M1 阶段：大盘核心数据全景索引卡

本文档专为你快速定位 M1 阶段的 5 条核心数据工作流而写。
**任何时候你找不到文件或不知道该点哪个，查这张表就够了。**

---

## 核心目录速查
你只需要记住这三个地方：
1. ⚙️ **要往 n8n 导入工作流？** → 找 `n8n-workflows/` (全都是 `.json`)
2. 💻 **想改底层的 Python 抓取逻辑？** → 找 `treasolo/` (全是核心 `.py` 脚本)
3. 💾 **想查看抓下来的数据结果？** → 找 `data/` (全是 `.jsonl` 记账本)

---

## 5 条核心工作流明细表

### 1. 全市场成交额抓取
- **用途**：每 5 分钟算一次“全市场成交额”和“ETF占比”。(注：开盘时验证)
- **导入 n8n 用的文件**：[n8n-workflows/M1-Market-Amount.json](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/n8n-workflows/M1-Market-Amount.json)
- **底层 Python 脚本**：[treasolo/m1_market_amount.py](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/treasolo/m1_market_amount.py)
- **抓下来的数据存在哪**：`data/m1/market/market_amount.jsonl`

### 2. 市场涨跌情绪抓取
- **用途**：每 5 分钟算一次“上涨/下跌/平盘家数”。(注：已按照“麻烦的接口.md”使用新浪全市场接口，需开盘验证)
- **导入 n8n 用的文件**：[n8n-workflows/M1-Breadth-Fetch.json](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/n8n-workflows/M1-Breadth-Fetch.json)
- **底层 Python 脚本**：[treasolo/breadth_manager.py](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/treasolo/breadth_manager.py)
- **抓下来的数据存在哪**：`data/minute/breadth-cache.jsonl`

### 3. 大盘指数：盘中分时抓取
- **用途**：每 30 分钟抓取 7 大指数当前的分钟价，用于画分时线。
- **导入 n8n 用的文件**：[n8n-workflows/M1-A-Index-Minute-Fetch.json](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/n8n-workflows/M1-A-Index-Minute-Fetch.json)
- **底层 Python 脚本**：[treasolo/m1_minute_fetch_indices.py](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/treasolo/m1_minute_fetch_indices.py)
- **抓下来的数据存在哪**：`data/market/minute/<代码>/<日期>.jsonl`

### 4. 大盘指数：收盘抢发日线
- **用途**：每天 15:01，用最后一次分时价，拼出今天的日线收盘价。
- **导入 n8n 用的文件**：[n8n-workflows/M1-B-Minute2Daily.json](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/n8n-workflows/M1-B-Minute2Daily.json)
- **底层 Python 脚本**：[treasolo/m1_minute_to_daily.py](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/treasolo/m1_minute_to_daily.py)
- **抓下来的数据存在哪**：`data/m1/index/<代码>/daily.jsonl`

### 5. 大盘指数与 ETF：晚间权威对账与回补 (共用)
- **用途**：每天 18:00，去官方接口要最终结算日线，强制覆盖我们 15:01 抢发的数据，保证 100% 准确。支持对所有大盘指数与 ETF 的日线进行漏缺天数补齐。
- **导入 n8n 用的文件**：[n8n-workflows/M1-E-Backfill-Universal.json](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/n8n-workflows/M1-E-Backfill-Universal.json)
- **底层 Python 脚本**：[treasolo/m1_backfill.py](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/treasolo/m1_backfill.py)
- **抓下来的数据存在哪**：与各自的日线是同一个文件 `data/m1/index/<代码>/daily.jsonl` 或 `data/m1/etf/<代码>/daily.jsonl`，直接覆盖更新。

---

## ETF 专属工作流 (含分时与日线)

### 6. ETF：盘中分时抓取 (全字段)
- **用途**：每 30 分钟抓取核心 ETF 分时数据，包含 `price`, `pct`, `amount`, `vol`, `open`, `high`, `low` 等完整字段。
- **导入 n8n 用的文件**：[n8n-workflows/M1-C-ETF-Minute-Fetch.json](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/n8n-workflows/M1-C-ETF-Minute-Fetch.json)
- **底层 Python 脚本**：[treasolo/m1_minute_fetch_etf.py](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/treasolo/m1_minute_fetch_etf.py)
- **抓下来的数据存在哪**：`data/market/minute/<代码>/<日期>.jsonl`

### 7. ETF：收盘抢发日线
- **用途**：每天 15:01，用 ETF 的最后一次分时数据，生成当天的收盘日线。
- **导入 n8n 用的文件**：[n8n-workflows/M1-D-ETF-Minute2Daily.json](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/n8n-workflows/M1-D-ETF-Minute2Daily.json)
- **底层 Python 脚本**：[treasolo/m1_minute_to_daily_etf.py](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/treasolo/m1_minute_to_daily_etf.py)
- **抓下来的数据存在哪**：`data/m1/etf/<代码>/daily.jsonl`

---

## 附录：当前监控的 6 大核心指数对照表

这是上述工作流中 `<代码>` 所对应的具体指数，**如果找不到文件，请核对这 6 个代码目录**：

| 指数代码 | 指数名称 | 说明 |
| :--- | :--- | :--- |
| `sh000001` | 上证指数 | 核心大盘 |
| `sz399001` | 深证成指 | 核心大盘 |
| `sz399006` | 创业板指 | 核心大盘 |
| `sh000688` | 科创50 | 核心大盘 |
| `sh000300` | 沪深300 | 核心大盘 |
| `sh000852` | 中证1000 | 核心大盘 |