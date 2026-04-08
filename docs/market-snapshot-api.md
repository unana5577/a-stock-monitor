# 全市场快照 API（合并版）

## 功能
合并了两个接口的数据采集：
1. **A股涨跌家数**（stock_zh_a_spot）
2. **全市场ETF成交额**（fund_etf_category_sina）

## 脚本位置
`scripts/market_snapshot_sina.py`

## 定时任务
```bash
# 全市场快照数据采集（只在开盘时间）
# 上午：9:30-11:30
30-59/5 9 * * 1-5 /opt/homebrew/opt/python@3.14/bin/python3 scripts/market_snapshot_sina.py >> server.log 2>&1
*/5 10-11 * * 1-5 /opt/homebrew/opt/python@3.14/bin/python3 scripts/market_snapshot_sina.py >> server.log 2>&1
# 下午：13:00-15:00
*/5 13 * * 1-5 /opt/homebrew/opt/python@3.14/bin/python3 scripts/market_snapshot_sina.py >> server.log 2>&1
*/5 14 * * 1-5 /opt/homebrew/opt/python@3.14/bin/python3 scripts/market_snapshot_sina.py >> server.log 2>&1
0-55/5 15 * * 1-5 /opt/homebrew/opt/python@3.14/bin/python3 scripts/market_snapshot_sina.py >> server.log 2>&1
```

**执行时间**：周一到周五，**开盘时间每5分钟**（9:30-11:30, 13:00-15:00）

**非交易时间**：返回缓存数据（不请求接口）

## 输出文件

### 1. 涨跌家数缓存（实时）
`data/market/breadth-cache.json`

```json
{
  "up": 5084,
  "down": 382,
  "flat": 32,
  "total": 5498,
  "ratio": 13.31,
  "sentiment": "亢奋"
}
```

### 2. ETF成交额历史（每日）
`data/market/etf-amount-daily.jsonl`

```json
{"date": "2026-04-08", "amount": 429826469294.0, "amount_yi": 4298.26, "count": 1475, "timestamp": "2026-04-08T13:27:29.590297"}
```

## 接口详情

### 涨跌家数接口
- **接口名称**：`stock_zh_a_spot()`
- **请求耗时**：约10秒
- **数据来源**：新浪财经
- **覆盖范围**：沪深北全市场（约5498只股票）
- **返回字段**：代码、名称、最新价、涨跌幅、成交量、成交额

### ETF成交额接口
- **接口名称**：`fund_etf_category_sina(symbol="ETF基金")`
- **请求耗时**：<1秒
- **数据来源**：新浪财经
- **覆盖范围**：全市场ETF（约1475只）
- **返回字段**：代码、名称、最新价、涨跌幅、成交量、成交额

## 交易时间判断

脚本会自动判断当前是否是交易时间：

- **交易时间**（9:30-11:30, 13:00-15:00）
  - 请求接口获取实时数据
  - 更新缓存文件
  - 返回最新数据

- **非交易时间**（午休、收盘后、周末）
  - 不请求接口（节省资源）
  - 直接返回缓存数据
  - 如果缓存不存在，返回 `null`

## 数据更新逻辑

### 涨跌家数（breadth-cache.json）
- 直接覆盖，保留最新快照
- 用于前端实时显示市场情绪

### ETF成交额（etf-amount-daily.jsonl）
- 追加模式，保留历史记录
- 每天更新当天的记录（如果存在则替换，否则追加）
- 用于历史分析和成交额占比计算

## 优势

1. ✅ **减少请求次数**：一次调用获取两个数据
2. ✅ **统一数据源**：都是新浪财经，时间一致
3. ✅ **减少维护成本**：一个脚本代替两个
4. ✅ **自动更新**：交易时间每5分钟自动执行
5. ✅ **数据持久化**：实时快照+历史记录

## 测试

### 手动执行（交易时间）
```bash
python3 scripts/market_snapshot_sina.py
```

**输出**：
```
============================================================
全市场快照数据采集
============================================================
[13:47:56] 开始获取全市场快照数据...
  1. 获取A股涨跌家数...
     ✅ 涨跌家数: 上涨5101 / 下跌365 / 平盘32，情绪: 亢奋
  2. 获取ETF成交额...
     ✅ ETF成交额: 4594.59亿，ETF数量: 1475
  💾 涨跌家数已缓存到: data/market/breadth-cache.json
  💾 ETF成交额已保存到: data/market/etf-amount-daily.jsonl
============================================================
✅ 快照数据采集完成
============================================================
```

### 手动执行（非交易时间）
```bash
python3 scripts/market_snapshot_sina.py
```

**输出**：
```
============================================================
全市场快照数据采集
============================================================
[12:30:00] 非交易时间，返回缓存数据
  ✅ 使用缓存数据
```

### 查看定时任务
```bash
crontab -l | grep market_snapshot
```

## 已废弃的脚本

以下脚本已被 `market_snapshot_sina.py` 替代：
- `scripts/market_breadth_spot.py`（涨跌家数）
- `scripts/etf_amount_total_sina.py`（ETF成交额）
