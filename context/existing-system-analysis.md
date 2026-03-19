# 现有系统分析报告

## 概述
本报告梳理 A 股量化监测系统的现有时间管理、缓存机制和持久化存储方案，为时间管理系统重构提供依据。

---

## 一、时间管理系统

### 1.1 交易日历管理

#### 节假日配置
- **文件位置**: `/Users/una5577/Documents/trae_projects/a-stock-monitor/config/holidays.json`
- **格式**: JSON 数组，包含 2026 年所有节假日
- **示例内容**:
  ```json
  {
    "holidays": [
      "2026-01-01",
      "2026-02-16", "2026-02-17", ...,
      "2026-10-10"
    ]
  }
  ```

#### 备用节假日文件
- **文件位置**: `/Users/una5577/Documents/trae_projects/a-stock-monitor/data/holiday.txt`
- **用途**: 被 `_is_trading_day_session()` 函数读取作为备用
- **状态**: ⚠️ 实际检查时发现代码中引用此文件，但文件可能不存在

### 1.2 交易时间判断函数

#### 函数 1: `_is_trading_day_session()`
- **位置**: `fetch_sector_data.py` 第 55-85 行
- **功能**: 判断是否在交易日内（9:30-15:00，含午休）
- **用途**: 用于午休时仍获取分钟线数据
- **判断逻辑**:
  1. 优先读取环境变量模拟时间（`MOCK_TIME_HOUR`, `MOCK_TIME_MINUTE`）
  2. 支持环境变量模拟日期（`MOCK_TIME_DATE`）
  3. 真实时间判断：
     - 周末（weekday >= 5）→ 非交易日
     - 读取 `data/holiday.txt` → 节假日 → 非交易日
     - 时间范围：570-900 分钟（9:30-15:00）
- **返回值**: `True`（交易日内） / `False`（非交易日内）

#### 函数 2: `_is_market_open()`
- **位置**: `fetch_sector_data.py` 第 87-109 行
- **功能**: 判断当前是否在交易时段（9:30 - 15:00）
- **特点**: ⚠️ **只判断时间，不判断日期**（不检查周末/节假日）
- **判断逻辑**:
  1. 支持环境变量模拟时间（`MOCK_TIME_HOUR`, `MOCK_TIME_MINUTE`）
  2. 真实时间判断：minutes = hour * 60 + minute
  3. 返回 `minutes <= 900`（15:00 前为交易时段）
- **返回值**: `True`（交易时段，15:00 前） / `False`（非交易时段）

### 1.3 时间判断的使用场景

| 函数 | 使用场景 | 是否判断日期 | 是否判断时间 |
|------|---------|------------|------------|
| `_is_trading_day_session()` | 分钟线数据获取、盘中合成当日数据 | ✅ 是（周末/节假日） | ✅ 是（9:30-15:00） |
| `_is_market_open()` | 判断是否在交易时段内 | ❌ 否 | ✅ 是（15:00 前） |

**调用示例**:
```python
# fetch_sector_data.py 第 1934 行
should_fetch_minute = not CACHE_ONLY or _is_trading_day_session()
```

---

## 二、板块→ETF 映射表

### 2.1 SECTOR_MAPPING 定义
- **位置**: `fetch_sector_data.py` 第 16-27 行
- **类型**: 列表，每个元素为字典

```python
SECTOR_MAPPING = [
    {"name": "半导体", "display": "半导体", "code": "BK_半导体"},
    {"name": "云计算", "display": "云计算", "code": "BK_云计算"},
    {"name": "新能源", "display": "新能源", "code": "BK_新能源"},
    {"name": "商业航天", "display": "商业航天", "code": "BK_商业航天"},
    {"name": "创新药", "display": "创新药", "code": "BK_创新药"},
    {"name": "有色金属", "display": "有色金属", "code": "BK_有色金属"},
    {"name": "煤炭行业", "display": "煤炭", "code": "BK_煤炭"},
    {"name": "电力行业", "display": "电力", "code": "BK_电力"},
    {"name": "通信设备", "display": "通讯设备", "code": "BK_通讯设备"},
    {"name": "银行", "display": "银行", "code": "BK_银行"}
]
```

### 2.2 ETF 实际映射表
- **位置**: `scripts/update_etf_simple.py` 第 14-24 行
- **用途**: ETF 数据更新脚本使用

```python
ETF_CONFIG = {
    "sh512480": "半导体",
    "sh516160": "新能源",
    "sh512400": "有色金属",
    "sh515880": "通讯设备",
    "sh515120": "创新药",
    "sh516010": "游戏",
    "sh516510": "云计算",
    "sh562500": "机器人",
    "sh563530": "商业航天",
}
```

### 2.3 映射完整性分析

| 板块名称 | BK代码 | ETF代码 | ETF名称 | 状态 |
|---------|-------|---------|---------|------|
| 半导体 | BK_半导体 | sh512480 | 半导体设备 | ✅ 完整 |
| 云计算 | BK_云计算 | sh516510 | 云计算ETF | ✅ 完整 |
| 新能源 | BK_新能源 | sh516160 | 新能源ETF | ✅ 完整 |
| 商业航天 | BK_商业航天 | sh563530 | 商业航天ETF | ✅ 完整 |
| 创新药 | BK_创新药 | sh515120 | 创新药ETF | ✅ 完整 |
| 有色金属 | BK_有色金属 | sh512400 | 有色金属ETF | ✅ 完整 |
| 煤炭行业 | BK_煤炭 | ❌ 缺失 | - | ⚠️ 缺失 ETF |
| 电力行业 | BK_电力 | ❌ 缺失 | - | ⚠️ 缺失 ETF |
| 通信设备 | BK_通讯设备 | sh515880 | 通信设备ETF | ✅ 完整 |
| 银行 | BK_银行 | ❌ 缺失 | - | ⚠️ 缺失 ETF |
| 游戏 | ❌ 未定义 | sh516010 | 游戏ETF | ⚠️ 未在 SECTOR_MAPPING 定义 |
| 机器人 | ❌ 未定义 | sh562500 | 机器人ETF | ⚠️ 未在 SECTOR_MAPPING 定义 |

**发现的问题**:
1. `SECTOR_MAPPING` 定义了 10 个板块，但实际 ETF 只有 9 个
2. "游戏" 和 "机器人" 有 ETF 但未在 `SECTOR_MAPPING` 中定义
3. "煤炭"、"电力"、"银行" 有板块定义但缺少 ETF

---

## 三、缓存机制梳理

### 3.1 Warmup 缓存（启动预热）

#### 文件清单
| 文件名 | 大小 | 用途 | 更新频率 |
|-------|------|------|---------|
| `sector-history-warmup-60.json` | 324K | 60天历史数据缓存（9个板块） | 手动/定时任务 |
| `sector-minute-warmup.json` | 206K | 分时数据缓存（9个板块） | 手动/定时任务 |
| `sector-history-warmup-2026-03-09-365.json` | 872K | 365天历史数据缓存 | 历史版本 |

#### 生成函数
- **函数**: `warmup_proxy_files(sectors, days=60, variant=None)`
- **位置**: `fetch_sector_data.py` 第 983-1000 行
- **触发方式**: 命令行 `python fetch_sector_data.py warmup`
- **特点**:
  - 使用固定文件名（不包含日期），方便启动时自动更新
  - 包含 `history`（日线）、`minute`（分时）、`day`（日期）、`watch`（板块列表）

#### Warmup 文件结构
```json
{
  "day": "2026-03-19",
  "history": {
    "半导体": [{date, open, close, high, low, volume, amount, pct}, ...],
    "云计算": [...],
    ...
  },
  "minute": {
    "半导体": [{time, price, volume, amount}, ...],
    ...
  },
  "watch": ["半导体", "云计算", ...],
  "variant": "etf"
}
```

#### 使用优先级
1. **优先级 1**: 读取 warmup 缓存（第 2045-2103 行）
2. **优先级 2**: warmup 不可用时，使用 `sector-cache.csv` 备选方案

### 3.2 Sector Cache（板块缓存）

#### 文件信息
- **文件名**: `sector-cache.csv`
- **位置**: `/Users/una5577/Documents/trae_projects/a-stock-monitor/data/sector-cache.csv`
- **大小**: 103K
- **行数**: 953 行
- **日期范围**: 2025-08-27 ~ 2026-03-19
- **板块数**: 8 个（云计算、创新药、半导体、商业航天、新能源、有色金属、机器人、通讯设备）

#### 字段结构
| 字段名 | 类型 | 说明 |
|-------|------|------|
| date | string | 日期（YYYY-MM-DD） |
| sector | string | 板块名称 |
| code | string | 板块代码（如 BK_半导体） |
| type | string | 类型 |
| pct | float | 涨跌幅 |
| amount | float | 成交额 |
| volume | float | 成交量 |
| turnover | float | 换手率 |
| open, high, low, close | float | OHLC 价格 |

#### 缓存刷新逻辑
- **函数**: `_need_cache_refresh(df)`
- **位置**: `fetch_sector_data.py` 第 1213-1219 行
- **判断条件**:
  ```python
  if CACHE_ONLY:  # 环境变量控制
      return False
  latest = _latest_cache_date(df)
  if not latest:
      return True
  return latest < _today_str()  # 最新日期 < 今天 → 需要刷新
  ```

#### 缓存更新流程
1. **函数**: `get_sector_payload(sector_items, indicator_days=20)`
2. **位置**: `fetch_sector_data.py` 第 1920-1941 行
3. **逻辑**:
   ```python
   df = _load_cache()
   if (df is None or df.empty or _need_cache_refresh(df)) and not CACHE_ONLY:
       df = _update_sector_cache(sectors, ensure_days=indicator_days)
   ```

### 3.3 环境变量控制

| 环境变量 | 值 | 作用 | 默认值 |
|---------|---|------|--------|
| `CACHE_ONLY` | `"1"` / `"0"` | 强制只使用缓存，不请求网络 | `"0"` |
| `FORCE_SECTOR_ETF` | `"1"` / `"0"` | 强制使用 ETF 数据源 | `"0"` |
| `MOCK_TIME_HOUR` | 小时数 | 模拟小时（用于测试） | - |
| `MOCK_TIME_MINUTE` | 分钟数 | 模拟分钟（用于测试） | - |
| `MOCK_TIME_DATE` | 日期字符串 | 模拟日期（用于测试） | - |

---

## 四、持久化存储梳理

### 4.1 文件分类总览

#### 按用途分类

| 类别 | 目录/文件 | 数量 | 总大小 | 用途 |
|-----|----------|------|-------|------|
| **ETF 日线** | `data/etf_daily/` | 9 文件 | 1.7M | ETF 历史日线数据 |
| **指数日线** | `data/index_daily/` | 4 文件 | 1.1M | 指数历史日线数据 |
| **分时数据** | `data/minute_data/` | 15 文件 | ~300K | 当日分时数据 |
| **Warmup缓存** | `data/*warmup*.json` | 6 文件 | ~2M | 启动预热缓存 |
| **板块缓存** | `data/sector-cache.csv` | 1 文件 | 103K | 板块日线缓存 |
| **配置文件** | `config/holidays.json` | 1 文件 | <1K | 节假日配置 |
| **分析报告** | `data/*.json` | 50+ 文件 | 50M+ | 历史分析报告 |

### 4.2 ETF 日线数据

#### 目录结构
```
data/etf_daily/
├── etf_512400.jsonl  (有色金属)
├── etf_512480.jsonl  (半导体)
├── etf_515120.jsonl  (创新药)
├── etf_515880.jsonl  (通讯设备)
├── etf_516010.jsonl  (游戏)
├── etf_516160.jsonl  (新能源)
├── etf_516510.jsonl  (云计算)
├── etf_562500.jsonl  (机器人)
├── etf_563530.jsonl  (商业航天)
├── etf_backfill_2026-03-09.json
└── etf_backfill_2026-03-16.json
```

#### 字段结构（JSONL 格式）
```json
{"date": "2026-03-19", "open": 1.234, "close": 1.256, "high": 1.260, "low": 1.230, "volume": 1234567, "amount": 1234567.89, "pct": 1.23}
```

#### 维护机制
- **增量更新**: `maintain_etf_data(etf_code)` 自动补全缺失交易日
- **全量请求**: 本地无数据时请求 1000 条
- **回补逻辑**: 计算缺失交易日，批量补全
- **文件函数**:
  - `_save_etf_to_disk(etf_code, data_list)`: 保存
  - `_load_etf_from_disk(etf_code, days=None)`: 读取
  - `_get_latest_etf_date(etf_code)`: 获取最新日期

### 4.3 指数日线数据

#### 目录结构
```
data/index_daily/
├── index_000001.jsonl  (上证指数)
├── index_000688.jsonl  (科创板)
├── index_399001.jsonl  (深证成指)
└── index_399006.jsonl  (创业板)
```

#### 数据来源
- **函数**: `_fetch_tencent_daily(code, limit=180)`
- **接口**: 腾讯行情接口（`https://web.ifzq.gtimg.cn/appstock/app/fqkline/get`）

### 4.4 分时数据

#### 目录结构
```
data/minute_data/
├── minute_sh512400_2026-03-19.jsonl
├── minute_sh512480_2026-03-19.jsonl
├── minute_sh515120_2026-03-19.jsonl
├── ...
└── minute_sz159995_2026-03-18.jsonl
```

#### 文件命名规则
```
minute_{ETF代码}_{日期}.jsonl
```

#### 数据特点
- **时效性**: 仅存储当日分时数据
- **更新频率**: 每分钟更新（盘中）
- **数据源**: AkShare 分时接口
- **总行数**: 353 行（15 个文件）

### 4.5 配置文件

#### 节假日配置
- **文件**: `config/holidays.json`
- **格式**: JSON 数组
- **内容**: 2026 年所有节假日
- **维护方式**: 手动更新

#### 备用节假日文件
- **文件**: `data/holiday.txt`
- **状态**: ⚠️ 代码中引用但文件可能不存在
- **用途**: 被 `_is_trading_day_session()` 读取

---

## 五、数据更新频率

### 5.1 实时数据
- **分时数据**: 每分钟更新（盘中 9:30-15:00）
- **文件**: `data/minute_data/minute_*_2026-03-19.jsonl`

### 5.2 日线数据
- **ETF 日线**: 每日 15:00 后更新
  - 增量更新：仅补全缺失交易日
  - 维护函数：`maintain_etf_data(etf_code)`
- **指数日线**: 每日 15:00 后更新
- **板块缓存**: 每日刷新（`_update_sector_cache()`）

### 5.3 Warmup 缓存
- **更新频率**: 手动触发 / 定时任务
- **命令**: `python fetch_sector_data.py warmup [板块列表] [天数]`
- **默认天数**: 60 天

### 5.4 历史报告
- **分析报告**: 按需生成（不自动更新）
- **文件示例**:
  - `sector-rank-20260318.json`
  - `intraday-rotation-summary-20260313.json`

---

## 六、缺失功能清单

### 6.1 时间管理缺失

| 功能 | 当前状态 | 缺失描述 |
|------|---------|---------|
| 统一交易日历 | ⚠️ 分散 | 节假日在 `config/holidays.json`，代码中引用 `data/holiday.txt` |
| 交易时间判断 | ⚠️ 不统一 | `_is_trading_day_session()` 判断日期+时间，`_is_market_open()` 只判断时间 |
| 交易日计算 | ❌ 缺失 | 无法计算两个日期之间的交易日列表 |
| 盘前/盘后时段判断 | ❌ 缺失 | 无法区分 9:15-9:30、11:30-13:00、15:00-15:30 |
| 节假日自动更新 | ❌ 缺失 | 需手动更新 `holidays.json` |

### 6.2 板块映射缺失

| 功能 | 当前状态 | 缺失描述 |
|------|---------|---------|
| 统一映射表 | ⚠️ 分散 | `SECTOR_MAPPING` 和 `ETF_CONFIG` 分离 |
| 煤炭/电力/银行 ETF | ❌ 缺失 | 有板块定义但缺少 ETF 对应 |
| 映射关系验证 | ❌ 缺失 | 无法验证板块代码和 ETF 代码的完整性 |

### 6.3 缓存管理缺失

| 功能 | 当前状态 | 缺失描述 |
|------|---------|---------|
| 缓存过期策略 | ⚠️ 简单 | 仅判断最新日期是否 < 今天 |
| 缓存版本管理 | ❌ 缺失 | 无法识别缓存格式变更 |
| 缓存预热调度 | ❌ 缺失 | 无自动定时更新 warmup 缓存 |
| 缓存降级策略 | ✅ 完整 | warmup → sector-cache.csv → 网络请求 |

### 6.4 持久化缺失

| 功能 | 当前状态 | 缺失描述 |
|------|---------|---------|
| 分时数据持久化策略 | ⚠️ 简单 | 仅存储当日，无历史归档 |
| 数据文件清理 | ❌ 缺失 | 无自动清理过期文件机制 |
| 数据文件索引 | ❌ 缺失 | 无元数据记录各文件的数据范围 |
| 数据完整性校验 | ❌ 缺失 | 无校验机制检测数据缺失/损坏 |

---

## 七、技术债务识别

### 7.1 代码层面

1. **重复代码**: ETF 代码规范化逻辑重复出现（`_normalize_etf_code()`）
2. **错误处理不足**: 多处 `try-except pass` 吞掉异常，难以排查问题
3. **魔法数字**: 硬编码时间阈值（570、900、1000 等）
4. **环境变量依赖**: 时间判断依赖环境变量，容易导致测试环境不一致

### 7.2 数据层面

1. **文件格式不一致**: 部分使用 JSONL，部分使用 JSON，部分使用 CSV
2. **命名不统一**: `sector-cache.csv` vs `etf_512400.jsonl` vs `minute_sh512480_2026-03-19.jsonl`
3. **数据冗余**: warmup 缓存和 sector-cache.csv 存储重复数据
4. **版本管理缺失**: 无数据格式版本号，难以兼容性升级

### 7.3 运维层面

1. **手动维护**: 节假日配置需手动更新
2. **无监控**: 无缓存命中率、数据完整性等监控指标
3. **无告警**: 数据获取失败无告警机制
4. **无备份**: 无数据文件备份策略

---

## 八、优化建议

### 8.1 时间管理系统重构

1. **统一交易日历管理**:
   - 合并 `config/holidays.json` 和 `data/holiday.txt`
   - 自动从交易日历 API 更新节假日
   - 支持交易日计算（`get_trading_days(start, end)`）

2. **统一交易时间判断**:
   - 合并 `_is_trading_day_session()` 和 `_is_market_open()`
   - 新增函数：`is_pre_market()`, `is_after_market()`, `is_lunch_break()`
   - 使用枚举代替魔法数字（`TRADING_START = 570`, `TRADING_END = 900`）

### 8.2 板块映射统一

1. **合并映射表**: 将 `SECTOR_MAPPING` 和 `ETF_CONFIG` 合并为一个配置文件
2. **完整性验证**: 启动时检查映射表完整性（板块↔ETF 一一对应）
3. **支持别名**: 板块显示名称（"通讯设备"）和板块代码（"BK_通讯设备"）分离

### 8.3 缓存策略优化

1. **缓存元数据**: 记录缓存生成时间、数据范围、版本号
2. **智能刷新**: 根据数据时效性自动选择刷新策略
3. **缓存预热**: 定时任务自动更新 warmup 缓存（每日 16:00）
4. **缓存降级**: 完善现有降级逻辑，增加缓存不可用时的告警

### 8.4 持久化优化

1. **统一文件命名**: `{类型}_{代码}_{开始日期}_{结束日期}.jsonl`
2. **文件索引**: 维护元数据文件，记录各文件的数据范围
3. **自动清理**: 定期清理过期分时数据文件（保留最近 7 天）
4. **数据校验**: 启动时校验数据完整性（日期连续性、字段完整性）

---

## 九、关键数据指标

| 指标 | 数值 | 说明 |
|------|------|------|
| ETF 数量 | 9 | 实际有 ETF 数据的板块 |
| 板块数量 | 10 | SECTOR_MAPPING 定义的板块 |
| 指数数量 | 4 | 上证、深证、创业板、科创板 |
| sector-cache.csv 行数 | 953 | 8 个板块的历史数据 |
| ETF 日线总行数 | 8380 | 9 个 ETF 的历史数据 |
| 分时数据文件数 | 15 | 最近 3 天的分时数据 |
| Warmup 缓存大小 | 324K | 60 天历史数据 |
| 总数据文件数 | 112 | JSONL + CSV + JSON |

---

## 十、相关文件路径

### 核心代码
- `/Users/una5577/Documents/trae_projects/a-stock-monitor/fetch_sector_data.py` - 数据获取主模块
- `/Users/una5577/Documents/trae_projects/a-stock-monitor/scripts/update_etf_simple.py` - ETF 更新脚本

### 配置文件
- `/Users/una5577/Documents/trae_projects/a-stock-monitor/config/holidays.json` - 节假日配置

### 数据目录
- `/Users/una5577/Documents/trae_projects/a-stock-monitor/data/etf_daily/` - ETF 日线数据
- `/Users/una5577/Documents/trae_projects/a-stock-monitor/data/index_daily/` - 指数日线数据
- `/Users/una5577/Documents/trae_projects/a-stock-monitor/data/minute_data/` - 分时数据
- `/Users/una5577/Documents/trae_projects/a-stock-monitor/data/sector-cache.csv` - 板块缓存
- `/Users/una5577/Documents/trae_projects/a-stock-monitor/data/sector-history-warmup-60.json` - Warmup 缓存

---

**报告生成时间**: 2026-03-19
**分析范围**: 时间管理、缓存机制、持久化存储
**下一步**: 基于此分析设计统一的时间管理系统和缓存策略
