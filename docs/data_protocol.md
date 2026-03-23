# 数据协议文档

> 版本: v1.1
> 更新时间: 2026-03-23
> 说明: 本文档详细记录项目中所有数据类型的接口、存储、流转和定时任务
> **状态**: 分时日线数据已完成自检和实测验证

---

## 一、分时数据

| 数据分类 | 数据类型 | 接口路径 | 接口函数 | 数据来源 | 存储文件 | 保留期限 | 数据流转 | 定时任务 |
|---------|---------|---------|---------|---------|---------|---------|---------|---------|
| **市场数据** | 全市场成交额 | 无独立接口 | buildVolumeFromArchive() | archive提取（第22列） | data/volume-YYYYMMDD.jsonl | 60天 | archive→volume，不转日线 | 无 |
| | 全市场ETF成交额 | 待确认 | 待确认 | 待确认 | 待确认 | 待确认 | 待确认 | 待确认 |
| | 涨跌家数 | 无独立接口 | market_breadth_spot.py | 东财 | market/breadth-history.jsonl | 永久 | 实时拉取 | 盘中实时 |
| **大盘指数** | 上证指数 | /api/minute/sh000001 | loadMinuteSeries() → fetchAshareMinute() | 新浪 | data/minute-YYMMDD-sse.jsonl | 5个交易日 | 实时拉取，15:00转日线 | 11:30、15:00 |
| | 深证成指 | /api/minute/sz399001 | loadMinuteSeries() → fetchAshareMinute() | 新浪 | data/minute-YYMMDD-szi.jsonl | 5个交易日 | 实时拉取，15:00转日线 | 11:30、15:00 |
| | 创业板指 | /api/minute/sz399006 | loadMinuteSeries() → fetchAshareMinute() | 新浪 | data/minute-YYMMDD-gem.jsonl | 5个交易日 | 实时拉取，15:00转日线 | 11:30、15:00 |
| | 科创板指 | /api/minute/sh000688 | loadMinuteSeries() → fetchAshareMinute() | 新浪 | data/minute-YYMMDD-star.jsonl | 5个交易日 | 实时拉取，15:00转日线 | 11:30、15:00 |
| | 沪深300 | /api/minute/sh000300 | loadMinuteSeries() → fetchAshareMinute() | 新浪 | data/minute-YYMMDD-hs300.jsonl | 5个交易日 | 实时拉取，15:00转日线 | 11:30、15:00 |
| **板块** | 银行 | /api/minute/90.BK0475 | loadMinuteSeries() → fetchEastmoneyMinute() | 东财 | data/minute-YYMMDD-bank.jsonl | 5个交易日 | 实时拉取 | 11:30、15:00 |
| | 证券 | /api/minute/90.BK0473 | loadMinuteSeries() → fetchEastmoneyMinute() | 东财 | data/minute-YYMMDD-broker.jsonl | 5个交易日 | 实时拉取 | 11:30、15:00 |
| | 保险 | /api/minute/90.BK0474 | loadMinuteSeries() → fetchEastmoneyMinute() | 东财 | data/minute-YYMMDD-insure.jsonl | 5个交易日 | 实时拉取 | 11:30、15:00 |
| | 中证2000 | /api/minute/2.932000 | loadMinuteSeries() → fetchEastmoneyMinute() | 东财 | data/minute-YYMMDD-csi2000.jsonl | 5个交易日 | 实时拉取 | 11:30、15:00 |
| **关注ETF** | 半导体ETF | /api/minute/sh512480 | fetch_sector_data.py etf-minute | 东财 | **无文件**（实时） | **无文件** | 实时拉取，15:00转日线 | 15:00收盘后 |
| | 云计算ETF | /api/minute/sh516510 | fetch_sector_data.py etf-minute | 东财 | **无文件**（实时） | **无文件** | 实时拉取，15:00转日线 | 15:00收盘后 |
| | 新能源ETF | /api/minute/sh516160 | fetch_sector_data.py etf-minute | 东财 | **无文件**（实时） | **无文件** | 实时拉取，15:00转日线 | 15:00收盘后 |
| | 商业航天ETF | /api/minute/sh563530 | fetch_sector_data.py etf-minute | 东财 | **无文件**（实时） | **无文件** | 实时拉取，15:00转日线 | 15:00收盘后 |
| | 创新药ETF | /api/minute/sh515120 | fetch_sector_data.py etf-minute | 东财 | **无文件**（实时） | **无文件** | 实时拉取，15:00转日线 | 15:00收盘后 |
| | 有色金属ETF | /api/minute/sh512400 | fetch_sector_data.py etf-minute | 东财 | **无文件**（实时） | **无文件** | 实时拉取，15:00转日线 | 15:00收盘后 |
| | 通讯设备ETF | /api/minute/sh515880 | fetch_sector_data.py etf-minute | 东财 | **无文件**（实时） | **无文件** | 实时拉取，15:00转日线 | 15:00收盘后 |
| | 游戏ETF | /api/minute/sh516010 | fetch_sector_data.py etf-minute | 东财 | **无文件**（实时） | **无文件** | 实时拉取，15:00转日线 | 15:00收盘后 |
| | 机器人ETF | /api/minute/sh562500 | fetch_sector_data.py etf-minute | 东财 | **无文件**（实时） | **无文件** | 实时拉取，15:00转日线 | 15:00收盘后 |

### 说明

- **数据来源**:
  - 新浪分时: loadMinuteSeries() → fetchAshareMinute() (Ashare.py)
  - 东财分时: loadMinuteSeries() → fetchEastmoneyMinute() (push2.eastmoney.com)
  - 东财ETF: fetch_sector_data.py etf-minute (fund_etf_hist_min_em)
  - archive提取: buildVolumeFromArchive() (第22列)
  - 涨跌家数: market_breadth_spot.py (ak.stock_zh_a_spot)

- **存储位置**:
  - 大盘指数分时: `data/minute-YYMMDD-*.jsonl`（前端读取）
  - 板块分时: `data/minute-YYMMDD-*.jsonl`（前端读取）
  - ETF分时: `data/minute_data/minute_*_YYYY-MM-DD.jsonl`（转日线用）
  - 成交额分时: `data/volume-YYYYMMDD.jsonl`

- **保留期限**:
  - 大盘指数分时: 5个交易日
  - 板块分时: 5个交易日
  - ETF分时: 无文件（实时拉取）
  - 成交额分时: 60天（跟随archive）
  - 涨跌家数: 永久

- **数据流转**:
  - 大盘指数: 实时拉取，15:00转日线
  - 板块: 实时拉取
  - ETF: 实时拉取，15:00转日线
  - 成交额: archive→volume，不转日线
  - 涨跌家数: 实时拉取

- **接口验证状态**:
  - ✅ 大盘指数分时（6个）: 已验证
  - ✅ 板块分时（4个）: 已验证
  - ✅ 涨跌家数: 已验证
  - ⚠️ 全市场ETF成交额分时: 待确认

---

## 二、日线数据

| 数据分类 | 数据类型 | 接口路径 | 接口函数 | 数据来源 | 存储文件 | 保留期限 | 数据流转 | 定时任务 |
|---------|---------|---------|---------|---------|---------|---------|---------|---------|
| **市场数据** | 市场成交额 | /api/market/amount_daily | get_market_breadth() | 东财 | market/market-amount-daily.jsonl | 永久 | 实时拉取 | 15:00收盘后 |
| | ETF成交额 | /api/market/etf_amount_total | etf_amount_daily_sina.py | 新浪 | market/etf-amount-total.jsonl | 永久 | 实时拉取 | 15:00收盘后 |
| **大盘指数** | 上证指数 | /api/index/sh000001 | get_index_history() | 东财 | index_daily/index_000001.jsonl | 永久 | 追加写入 | 15:00收盘后 |
| | 深证成指 | /api/index/sz399001 | get_index_history() | 东财 | index_daily/index_399001.jsonl | 永久 | 追加写入 | 15:00收盘后 |
| | 创业板指 | /api/index/sz399006 | get_index_history() | 东财 | index_daily/index_399006.jsonl | 永久 | 追加写入 | 15:00收盘后 |
| | 科创板指 | /api/index/sh000688 | get_index_history() | 东财 | index_daily/index_000688.jsonl | 永久 | 追加写入 | 15:00收盘后 |
| **关注ETF** | 半导体ETF | 无 | _fetch_akshare_sina_etf() | 新浪 | etf_daily/etf_512480.jsonl | 永久 | 追加写入 | 15:00收盘后 |
| | 云计算ETF | 无 | _fetch_akshare_sina_etf() | 新浪 | etf_daily/etf_516510.jsonl | 永久 | 追加写入 | 15:00收盘后 |
| | 新能源ETF | 无 | _fetch_akshare_sina_etf() | 新浪 | etf_daily/etf_516160.jsonl | 永久 | 追加写入 | 15:00收盘后 |
| | 商业航天ETF | 无 | _fetch_akshare_sina_etf() | 新浪 | etf_daily/etf_563530.jsonl | 永久 | 追加写入 | 15:00收盘后 |
| | 创新药ETF | 无 | _fetch_akshare_sina_etf() | 新浪 | etf_daily/etf_515120.jsonl | 永久 | 追加写入 | 15:00收盘后 |
| | 有色金属ETF | 无 | _fetch_akshare_sina_etf() | 新浪 | etf_daily/etf_512400.jsonl | 永久 | 追加写入 | 15:00收盘后 |
| | 通讯设备ETF | 无 | _fetch_akshare_sina_etf() | 新浪 | etf_daily/etf_515880.jsonl | 永久 | 追加写入 | 15:00收盘后 |
| | 游戏ETF | 无 | _fetch_akshare_sina_etf() | 新浪 | etf_daily/etf_516010.jsonl | 永久 | 追加写入 | 15:00收盘后 |
| | 机器人ETF | 无 | _fetch_akshare_sina_etf() | 新浪 | etf_daily/etf_562500.jsonl | 永久 | 追加写入 | 15:00收盘后 |
| **国债期货** | 10年国债期货 | 无 | get_futures_daily() | 新浪 | futures_daily/futures_T.jsonl | 永久 | 追加写入 | 15:00收盘后 |
| | 30年国债期货 | 无 | get_futures_daily() | 新浪 | futures_daily/futures_TL.jsonl | 永久 | 追加写入 | 15:00收盘后 |
| **大盘综合** | 大盘快照归档 | 无 | fetchAshareSnapshot() | 新浪/腾讯 | archive-YYYYMMDD.jsonl | 60天 | 每日生成 | 15:00收盘后 |

**说明**:
- 涨跌家数: 数据来源为东财（ak.stock_zh_a_spot），当前接口被封，需寻找替代方案
- 市场成交额: **Task #10** 待修复，数据源待确认
- ETF成交额: 新浪接口（fund_etf_category_sina），数据正常
- archive归档: 数据来源为新浪/腾讯快照接口，存储位置为 `data/`，文件命名 `archive-YYYYMMDD.jsonl`，保留期限60天（用于warmup），**Task #12**: 当前24个文件（2026-02-10至2026-03-23），36天缺失

### 日线数据实测验证

| 数据类型 | 日期范围 | 记录数 | 状态 |
|---------|---------|-------|------|
| 上证指数 | 2017-12-08 至 2026-03-20 | - | ✅ 正常 |
| 深证成指 | 2017-12-11 至 2026-03-20 | - | ✅ 正常 |
| 创业板指 | 2017-12-11 至 2026-03-20 | - | ✅ 正常 |
| 科创板指 | 2019-12-31 至 2026-03-20 | - | ✅ 正常 |
| 半导体ETF | 2022-01-20 至 2026-03-20 | 1006条 | ✅ 正常 |
| 云计算ETF | 2022-01-20 至 2026-03-20 | 1006条 | ✅ 正常 |
| 新能源ETF | 2022-01-20 至 2026-03-20 | 1006条 | ✅ 正常 |
| 商业航天ETF | 2025-11-14 至 2026-03-20 | 83条 | ✅ 正常 |
| 创新药ETF | 2021-01-04 至 2026-03-20 | 1261条 | ✅ 正常 |
| 有色金属ETF | 2022-01-20 至 2026-03-20 | 1006条 | ✅ 正常 |
| 通讯设备ETF | 2022-01-20 至 2026-03-20 | 1007条 | ✅ 正常 |
| 游戏ETF | 2022-01-20 至 2026-03-20 | 1007条 | ✅ 正常 |
| 机器人ETF | 2022-01-20 至 2026-03-20 | 1007条 | ✅ 正常 |
| 市场成交额 | 2017-12-08 至 2026-03-20 | 2007条 | ⚠️ 待修复(#10) |
| ETF成交额 | 2026-03-17 至 2026-03-20 | 5条 | ✅ 正常 |
| archive归档 | 2026-02-10 至 2026-03-23 | 24个文件 | ⚠️ 36天缺失(#12) |

---

## 三、warmup + AI数据

### 3.1 warmup数据

| 数据分类 | 数据类型 | 接口路径 | 接口函数 | 数据来源 | 存储文件 | 保留期限 | 数据流转 | 定时任务 |
|---------|---------|---------|---------|---------|---------|---------|---------|---------|
| **warmup** | 板块历史数据 | 无 | warmup_proxy_files() | 日线数据（ETF/指数） | sector-history-warmup-60.json | 60天 | 每日生成 | 15:00收盘后 |
| | 分时预热数据 | 无 | warmup_proxy_files() | 分时数据（ETF） | sector-minute-warmup.json | 1天 | 实时更新 | 盘中实时 |
| | 关注ETF历史 | 无 | warmup_proxy_files() | ETF日线 | sector-history-warmup-60.json | 60天 | 每日生成 | 15:00收盘后 |

**说明**:
- warmup目的: 系统启动时预加载关键数据，提升响应速度
- 数据范围: 最近60个交易日
- 触发时机: 系统启动时

### 3.2 AI实时接口（/api/snapshot）

| 数据分类 | 数据类型 | 接口路径 | 接口函数 | 数据来源 | 存储文件 | 保留期限 | 数据流转 | 定时任务 |
|---------|---------|---------|---------|---------|---------|---------|---------|---------|
| **AI实时接口** | 大盘指数快照(5个) | /api/snapshot | buildSnapshotPayload() | 主：新浪fetchAshareMinute<br>备：腾讯fetchSnapshot | **无文件**（实时） | **无文件** | 实时拉取 | 盘中实时 |
| | 板块快照(4个) | /api/snapshot | buildSnapshotPayload() | 主：东财fetchEastmoneySnapshot<br>备：东财loadMinuteSeries | **无文件**（实时） | **无文件** | 实时拉取 | 盘中实时 |
| | 国债期货快照(2个) | /api/snapshot | buildSnapshotPayload() | 主：东财ETF分时<br>备：腾讯fetchSnapshot | **无文件**（实时） | **无文件** | 实时拉取 | 盘中实时 |
| | 成交额数据 | /api/snapshot | buildSnapshotPayload() | 腾讯fetchSnapshot(上证+深证amount) | **无文件**（实时） | **无文件** | 实时拉取 | 盘中实时 |
| | 涨跌家数 | /api/snapshot | buildSnapshotPayload() | 主：东财fetchBreadthRealtime<br>备：历史存档 | **无文件**（实时） | **无文件** | 实时拉取 | 盘中实时 |
| | AI分析文本 | /api/snapshot?ai=1 | ensureAiText() | 百炼/| **无文件**（实时） | **无文件** | 实时生成 | 盘中实时 |

**说明**:
- **主备关系**: 大盘指数、板块、国债等数据都有主数据源和备用数据源，优先使用主数据源，失败时使用备用
- **涨跌家数**: 主数据源为东财（ak.stock_zh_a_spot），当前被封，使用历史存档备用
- **Task #11**: AI实时接口数据溯源分析，⚠️ 午市收盘无法实测，待下一交易日验证

### AI实时接口数据来源对照

| 数据项 | 主数据源 | 备数据源 | 对应分时数据 | 状态 |
|-------|---------|---------|------------|------|
| 上证/深证/创业板/科创/沪深300 | 新浪fetchAshareMinute | 腾讯fetchSnapshot | ✅ 大盘指数分时 | ⚠️ 待确认 |
| 中证2000 | 东财loadMinuteSeries | 无 | ✅ 板块分时 | ⚠️ 待确认 |
| 银行/证券/保险 | 东财fetchEastmoneySnapshot | 东财loadMinuteSeries | ✅ 板块分时 | ⚠️ 待确认 |
| 10年国债期货(T) | 东财ETF分时 | 腾讯fetchSnapshot | ✅ ETF分时 | ⚠️ 待确认 |
| 30年国债期货(TL) | 东财ETF分时 | 腾讯fetchSnapshot | ✅ ETF分时 | ⚠️ 待确认 |
| 成交额 | 腾讯fetchSnapshot | archive历史数据 | ✅ 分时数据 | ⚠️ 待确认 |
| 涨跌家数 | 东财被封 | 历史存档 | ✅ 历史数据 | ⚠️ 待确认 |

### 实测数据验证

| 数据类型 | 日期范围 | 状态 |
|---------|---------|------|
| warmup文件 | 2026-03-20（60天） | ✅ 正常 |
| sector-history-warmup-60.json | 9个ETF历史数据 | ✅ 正常 |
| sector-minute-warmup.json | 9个ETF分时数据 | ✅ 正常 |
| /api/snapshot | 实时构建 | ⚠️ 午市收盘，待验证 |

---

## 四、定时任务

| 数据分类 | 任务名称 | 执行时间 | 涉及数据 | 执行脚本/函数 | 状态 |
|---------|---------|---------|---------|-------------|------|
| **盘中任务** | 涨跌家数实时更新 | 09:00-14:00 (每分钟) | breadth-cache.json | market_breadth_spot.py | ⚠️ 接口被封 |
| | AI分析文本生成 | 09:40,10:10/40,11:10/40,12:10/40,13:10/40,14:10/40,15:06 | **无文件**（实时） | curl /api/ai/debug | ✅ 正常 |
| **收盘后任务** | 大盘/板块分时保存 | 11:30、15:00 | data/minute-YYMMDD-*.jsonl | data_maintenance.py update_minute_data() | ✅ 正常 |
| | 涨跌家数持久化 | 15:00 | market/breadth-history.jsonl | save_breadth_history.py | ✅ 正常 |
| | ETF日线更新 | 15:30 | etf_daily/etf_*.jsonl | data_maintenance.py update_all_etf_data() | ✅ 正常 |
| | 大盘指数日线更新 | 15:30 | index_daily/index_*.jsonl | data_maintenance.py update_all_index_data() | ✅ 正常 |
| **数据维护** | 分时数据清理 | 每周手动 | data/minute/ | clean_data.py | ✅ 正常 |
| | archive数据回补 | 待一次性执行 | archive-YYYYMMDD.jsonl | 待实现 | ⏳ 待实现(#12) |
| | warmup更新 | 15:30 | sector-history-warmup-60.json | data_maintenance.py | ✅ 正常 |
| | ETF成交额统计 | 15:30 | market/etf-amount-total.jsonl | etf_amount_daily_sina.py | ✅ 正常 |

### 说明

- **盘中任务**:
  - 分时数据保存：11:30（早盘收盘，120个点）、15:00（全天收盘，240个点）
  - 涨跌家数每分钟请求一次，但脚本内会判断交易时段
  - AI分析在关键时间点触发（开盘后、午间、收盘前）

- **收盘后任务**:
  - 11:30: 大盘/板块分时保存（早盘数据）
  - 15:00: 大盘/板块分时保存（全天数据）、涨跌家数持久化
  - 15:30: ETF日线、大盘指数日线、warmup更新、ETF成交额统计

- **数据维护**:
  - 分时数据清理: 手动执行，保留5个交易日
  - archive数据回补: 待实现，需回补至60天

- **crontab配置**:
  ```bash
  # 分时数据保存（早盘收盘、全天收盘）
  30 11 * * 1-5 /usr/bin/python3 data_maintenance.py >> /Users/una5577/Documents/trae_projects/a-stock-monitor/logs/data_minute.log 2>&1
  0 15 * * 1-5 /usr/bin/python3 data_maintenance.py >> /Users/una5577/Documents/trae_projects/a-stock-monitor/logs/data_minute.log 2>&1

  # 涨跌家数（每分钟）
  * 9-14 * * 1-5 /opt/homebrew/opt/python@3.14/bin/python3 scripts/market_breadth_spot.py

  # 涨跌家数持久化（15:00收盘）
  0 15 * * 1-5 /opt/homebrew/opt/python@3.14/bin/python3 scripts/save_breadth_history.py

  # 日线更新（收盘后）
  30 15 * * 1-5 /usr/bin/python3 data_maintenance.py >> /Users/una5577/Documents/trae_projects/a-stock-monitor/logs/data_daily.log 2>&1

  # AI分析（关键时间点）
  40 9 * * 1-5 curl -s -X POST http://localhost:8787/api/ai/debug
  10,40 10-14 * * 1-5 curl -s -X POST http://localhost:8787/api/ai/debug
  36 11 * * 1-5 curl -s -X POST http://localhost:8787/api/ai/debug
  6 15 * * 1-5 curl -s -X POST http://localhost:8787/api/ai/debug
  ```
| 15:00-15:05 | 大盘指数日线更新 | index_daily/index_*.jsonl | get_index_history() | ✅ 正常 |
| 15:00-15:05 | ETF日线更新（优先新浪） | etf_daily/etf_*.jsonl | _fetch_akshare_sina_etf() | ✅ 正常 |
| 15:00-15:05 | ETF分时转日线（兜底） | etf_daily/etf_*.jsonl | minute_to_daily_for_etf() | ✅ 正常 |
| 15:00-15:05 | 大盘快照归档 | archive-YYYYMMDD.jsonl | fetchAshareSnapshot() | ✅ 正常 |
| 15:00-15:05 | 成交额提取 | volume-YYYYMMDD.jsonl | buildVolumeFromArchive() | ✅ 正常 |
| 15:00-15:05 | ETF成交额统计 | market/etf-amount-total.jsonl | etf_amount_daily_sina.py | ✅ 正常 |

### 4.3 盘后任务

| 时间 | 任务 | 涉及数据 | 执行脚本 | 状态 |
|-----|------|---------|---------|------|
| 18:00-21:00 | 新浪日线对账验证 | etf_daily/etf_*.jsonl | **Task #8** 待实现 | ⏳ 待实现 |
| 18:00-21:00 | 数据差异修正 | etf_daily/etf_*.jsonl | **Task #8** 待实现 | ⏳ 待实现 |

### 4.4 数据维护任务

| 任务 | 涉及数据 | 执行脚本 | 频率 | 状态 |
|-----|---------|---------|------|------|
| 分时数据清理 | minute-YYMMDD-*.jsonl | clean_data.py | 每周 | ✅ 正常 |
| 数据完整性验证 | 全部数据 | verify_data.py | 每周 | ✅ 正常 |
| archive数据回补 | archive-YYYYMMDD.jsonl | **Task #12** 待实现 | 一次性 | ⏳ 待实现 |

---

## 五、待处理任务

### Task #10: 市场成交额数据修复
- **问题**: market-amount-daily.jsonl 数据不正确
  - 早期数据: sh有值，sz为0
  - 近期数据: sz有值，sh为0
- **目标**: 确认正确数据源，重新生成

### Task #11: AI实时接口数据溯源分析
- **问题**: /api/snapshot 数据来源未完全确认
- **目标**: 确认各数据项来源，验证数据正确性

### Task #12: 大盘综合 archive 数据回补
- **问题**: 当前仅5天数据（20260316-20260320）
- **目标**: 回补至60天，满足warmup需求

### Task #13: 清理根目录旧版分时文件
- **问题**: data/minute-YYYYMMDD-*.jsonl 旧版文件未清理
- **目标**: 清理14个旧版文件，保留 data/minute/ 下的分时数据

### Task #14: 拆分verify_data.py
- **问题**: 当前 verify_data.py 逻辑混乱
- **目标**: 拆分为 verify_daily_data.py 和 verify_minute_data.py

---

**维护者**: Leader
**文档版本**: v1.0
**最后更新**: 2026-03-23
