# 大盘情绪分析 - AI数据喂送文档

## 概述

本文档描述大盘情绪分析系统中，喂给AI的数据来源、获取方式、存储机制。

---

## 数据流程

```
┌─────────────────────────────────────────────────────────────────────┐
│                        数据获取层                                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐        │
│  │  涨跌家数    │    │  大盘指数    │    │  成交额      │        │
│  │  Sina API   │    │  Ashare API  │    │  Tencent API │        │
│  │  (44秒/次)  │    │  (实时)      │    │  (实时)      │        │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘        │
│         │                    │                    │                 │
│         ▼                    ▼                    ▼                 │
│  ┌──────────────────────────────────────────────────────┐          │
│  │              data/breadth-cache.json                │          │
│  │  {up, down, flat, total, ratio, sentiment}          │          │
│  └──────────────────────────────────────────────────────┘          │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        数据持久化层                                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────────────────────────────────────────────┐          │
│  │  收盘后持久化 (11:31, 15:01)                       │          │
│  │  - data/breadth-history.jsonl                      │          │
│  │  - data/archive-YYYYMMDD.jsonl                       │          │
│  └──────────────────────────────────────────────────────┘          │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        AI分析层                                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────────────────────────────────────────────┐          │
│  │  API: /api/ai/debug                                │          │
│  │  1. 读取 breadth-cache.json (实时)                │          │
│  │  2. 读取分时数据 (指数、国债、板块)                │          │
│  │  3. 组装 payload                                   │          │
│  │  4. 调用 LLM 分析                                  │          │
│  └──────────────────────────────────────────────────────┘          │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 1. 涨跌家数接口

### 1.1 数据源优先级

| 优先级 | 数据源 | 接口 | 频率 | 说明 |
|--------|--------|------|------|------|
| 1 | 东财实时 | `fetchEastmoneyBreadth()` | 每30分钟 | 速度快，可能被封 |
| 2 | Sina备用 | `fetchBreadthViaPython()` | 降级使用 | 44秒/次，稳定 |

**东财接口**（优先）：
```javascript
// server.js:507
async function fetchEastmoneyBreadth() {
  const url = 'https://push2.eastmoney.com/api/qt/stock/get?secid=1.000001&fields=f104,f105,f106';
  // f104=上涨, f105=下跌, f106=平盘
  // 返回: {up: xxx, down: xxx, flat: xxx}
}
```

**Sina接口**（备用）：
```python
# scripts/market_breadth_spot.py
df = ak.stock_zh_a_spot()  # 获取5488只股票
up = (df['涨跌幅'] > 0).sum()
down = (df['涨跌幅'] < 0).sum()
```

### 1.2 缓存文件

**文件**: `data/breadth-cache.json`

```json
{
  "ok": true,
  "up": 2231,
  "down": 3124,
  "flat": 134,
  "total": 5489,
  "ratio": 0.71,
  "sentiment": "正常"
}
```

### 1.3 定时任务（Crontab）

```crontab
# 涨跌家数请求 - 开盘后第一次 (9:35)
35 9 * * 1-5 python3 scripts/market_breadth_spot.py

# 涨跌家数请求 - 每30分钟 (10:05, 10:35, 11:05, 13:05...)
5,35 10-14 * * 1-5 python3 scripts/market_breadth_spot.py

# 涨跌家数请求 - 午休收盘 (11:31) + 持久化
31 11 * * 1-5 python3 scripts/market_breadth_spot.py && python3 scripts/save_breadth_history.py

# 涨跌家数请求 - 下午收盘 (15:01) + 持久化
1 15 * * 1-5 python3 scripts/market_breadth_spot.py && python3 scripts/save_breadth_history.py
```

---

## 2. 汇总数据

### 2.1 数据清单

AI分析需要的所有数据：

| 数据项 | 来源 | 接口 | 文件 |
|--------|------|------|------|
| **涨跌家数** | Sina | `stock_zh_a_spot()` | `breadth-cache.json` |
| **上证指数** | Ashare | `fetchAshareMinute('sh000001')` | `data/minute/sse.jsonl` |
| **深证成指** | Ashare | `fetchAshareMinute('sz399001')` | `data/minute/szi.jsonl` |
| **创业板指** | Ashare | `fetchAshareMinute('sz399006')` | `data/minute/gem.jsonl` |
| **科创50** | Ashare | `fetchAshareMinute('sh000680')` | `data/minute/star.jsonl` |
| **沪深300** | Ashare | `fetchAshareMinute('sh000300')` | `data/minute/hs300.jsonl` |
| **中证2000** | 东财 | `fetchEastmoneyDaily('2.932000')` | `data/minute/csi2000.jsonl` |
| **10年国债** | 新浪 | `fetchAshareMinute('sh511260')` | `data/minute/t2603.jsonl` |
| **30年国债** | 新浪 | `fetchAshareMinute('sh511130')` | `data/minute/tl2603.jsonl` |
| **券商板块** | 东财 | `fetchEastmoneyDaily('90.BK0473')` | `data/minute/broker.jsonl` |
| **银行板块** | 东财 | `fetchEastmoneyDaily('90.BK0475')` | `data/minute/bank.jsonl` |
| **保险板块** | 东财 | `fetchEastmoneyDaily('90.BK0474')` | `data/minute/insure.jsonl` |
| **成交额** | Tencent | `fetchTencentDaily()` | `data/market-amount-daily.jsonl` |

### 2.2 ���时数据（缓存）

**文件**: `data/breadth-cache.json`

格式：
```json
{
  "up": 2231,
  "down": 3124,
  "flat": 134,
  "total": 5489,
  "ratio": 0.71,
  "sentiment": "正常"
}
```

### 2.3 历史数据（持久化）

**收盘后写入**：

1. **涨跌家数历史**: `data/breadth-history.jsonl`
   ```jsonl
   [1773802792009, "2026-03-18", 2231, 3124, 134, 5489]
   // [时间戳, 日期, 上涨, 下跌, 平盘, 总数]
   ```

2. **完整归档**: `data/archive-YYYYMMDD.jsonl`
   ```jsonl
   [1773802792009, 4049.91, -0.85, ..., 120326274, 2231, 3124, 4122.68, -1.08]
   // 包含所有指数、板块、国债、成交额、涨跌家数
   ```

---

## 3. AI分析

### 3.1 API接口

```
POST /api/ai/debug
```

### 3.2 数据组装

`server.js` 中的 `buildSnapshotPayload()` 函数：

```javascript
const payload = {
  day: "2026-03-18",
  indices: {
    sse: { price: 4049.91, pct: -0.85, series: [...] },
    szi: { price: 14039.73, pct: -1.87, series: [...] },
    // ...
  },
  bonds: {
    gov: { pct: 0.16 },
    t2603: { pct: -0.43 },
    tl2603: { pct: -0.71 }
  },
  sectors: {
    bank: { pct: 0.46 },
    broker: { pct: -0.14 },
    insure: { pct: -0.18 }
  },
  sentiment: {
    volume: 120326274,
    volumeStr: "12032.6亿",
    upCount: 2231,
    downCount: 3124,
    // ...
  }
};
```

### 3.3 AI分析定时

```crontab
# AI分析 - 数据请求后5分钟
40 9 * * 1-5 curl -X POST http://localhost:8787/api/ai/debug

# AI分析 - 每30分钟
10,40 10-14 * * 1-5 curl -X POST http://localhost:8787/api/ai/debug

# AI分析 - 午休后 (11:36)
36 11 * * 1-5 curl -X POST http://localhost:8787/api/ai/debug

# AI分析 - 下午收盘后 (15:06)
6 15 * * 1-5 curl -X POST http://localhost:8787/api/ai/debug
```

---

## 4. 验证实时数据

### 4.1 检查涨跌家数缓存

```bash
curl -s http://localhost:8787/api/market/breadth | jq .
```

预期输出：
```json
{
  "ok": true,
  "data": {
    "up": 2231,
    "down": 3124,
    "flat": 134,
    "total": 5489,
    "ratio": 0.71,
    "sentiment": "正常"
  }
}
```

### 4.2 检查AI收到的数据

```bash
# 方法1：查看日志
tail -f server.log | grep "AI Debug"

# 方法2：直接调用API
curl -s -X POST http://localhost:8787/api/ai/debug \
  -H "Content-Type: application/json" -d '{}' | jq '.text'
```

### 4.3 验证AI输出的涨跌家数

AI输出应该包含：
- 上涨家数：与 breadth-cache.json 中的 up 值一致
- 下跌家数：与 breadth-cache.json 中的 down 值一致

---

## 5. 删除错误缓存

### 5.1 需要删除的文件

| 文件 | 问题 |
|------|------|
| `data/market_breadth.json` | 旧数据（1540/3829） |
| `data/market-breadth-*.json` | 日期缓存，已过时 |
| `data/archive-2026031*.jsonl` | 包含错误涨跌家数的归档 |

### 5.2 删除命令

```bash
rm -f data/market_breadth.json
rm -f data/market-breadth-*.json
rm -f data/archive-2026031{2,3,6,7,8}.jsonl
```

---

## 6. 相关文件清单

### 6.1 核心文件

| 文件 | 说明 |
|------|------|
| `server.js` | 数据获取、组装、归档主逻辑 |
| `scripts/market_breadth_spot.py` | 涨跌家数获取脚本 |
| `scripts/save_breadth_history.py` | 涨跌家数持久化脚本 |
| `prompts/stock-daily.txt` | AI分析prompt定义 |

### 6.2 数据文件

| 文件 | 说明 |
|------|------|
| `data/breadth-cache.json` | 涨跌家数实时缓存 |
| `data/breadth-history.jsonl` | 涨跌家数历史记录 |
| `data/archive-YYYYMMDD.jsonl` | 完整数据归档 |

### 6.3 Crontab配置

| 任务 | 频率 | 说明 |
|------|------|------|
| 涨跌家数请求 | 9:35 + 每30分钟 | 刷新缓存 |
| 涨跌家数持久化 | 11:31, 15:01 | 收盘后写入历史 |
| AI分析 | 数据请求后5分钟 | 生成分析结果 |

---

## 7. 常见问题

### Q1: AI引用的涨跌家数是旧数据

**原因**: 归档中写入的是旧缓存数据

**解决**:
1. 删除 `data/market_breadth.json`
2. 删除 `data/market-breadth-*.json`
3. 重启服务器

### Q2: 东财API返回0/0/100

**原因**: 非交易时间调用东财API

**解决**:
1. 代码中已增加检测：`(up === 0 && down === 0) return null`
2. 会降级使用Sina接口

### Q3: 分时数据为空

**原因**: 未在交易时间内获取分时数据

**解决**:
1. 确认当前是交易时间
2. 检查分时文件是否存在

---

## 8. 数据口径对照表

| 字段 | 来源 | 单位 | 示例 |
|------|------|------|------|
| up | Sina/AKShare | 家 | 2231 |
| down | Sina/AKShare | 家 | 3124 |
| flat | Sina/AKShare | 家 | 134 |
| volume | Tencent | 元 | 120326274000 |
| volumeStr | 计算 | 亿 | "12032.6亿" |
| sse.price | Ashare | 点 | 4049.91 |
| sse.pct | Ashare | % | -0.85 |
| gov.pct | 东财 | % | 0.16 |
| broker.pct | 东财 | % | -0.14 |
