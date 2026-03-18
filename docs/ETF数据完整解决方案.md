# ETF数据完整解决方案

> **版本**: v2.0 | **日期**: 2026-03-12

---

## 零、数据持久化架构（v2.0新增）

### 0.1 三层架构设计

```
┌─────────────────────────────────────────────────────────────────┐
│  前端API (/api/sector/history_proxy)                            │
│  ↓ 请求                                                         │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Layer 1: Warmup缓存 (固定文件名)                         │   │
│  │ data/sector-history-warmup-60.json                      │   │
│  │ - 包含所有ETF的60天日线数据                              │   │
│  │ - 启动时自动检查更新                                    │   │
│  │ - 优先返回，不做日期裁剪                                │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ↓ 无Warmup时                                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Layer 2: ETF日线持久化文件                              │   │
│  │ data/etf_daily/etf_XXXXXX.jsonl                        │   │
│  │ - 完整历史数据（2022年至今）                            │   │
│  │ - 每请求自动去重合并                                    │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ↓ 无本地文件时                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Layer 3: 网络请求 (AkShare Sina)                       │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 0.2 核心改进

| 问题 | v1.0 | v2.0 |
|------|------|------|
| Warmup文件名 | `sector-history-warmup-{date}-60.json` | `sector-history-warmup-60.json`（固定） |
| 启动更新 | 手动 | 自动检测过期并更新 |
| 数据读取 | 查找最新缓存文件 | 固定文件名直读 |
| 日期裁剪 | 使用latestTradingDay裁剪 | 不裁剪，直接返回warmup原始数据 |

### 0.3 可用于回测的持久化数据

**ETF日线数据**（完整历史）：
```
data/etf_daily/
├── etf_512480.jsonl   # 半导体 (2022-01-20 ~ 2026-03-12)
├── etf_516510.jsonl   # 云计算
├── etf_516160.jsonl   # 新能源
├── etf_512400.jsonl   # 有色金属
├── etf_515120.jsonl   # 创新药
├── etf_515880.jsonl   # 通讯设备
├── etf_516010.jsonl   # 游戏
├── etf_562500.jsonl   # 机器人
└── etf_563530.jsonl   # 商业航天
```

**大盘指数数据**（完整历史）：
```
data/index_daily/
├── index_000001.jsonl   # 上证指数 (2017-12-08 ~ 2026-03-12)
├── index_399001.jsonl   # 深证成指
├── index_399006.jsonl   # 创业板指
└── index_000688.jsonl   # 科创板指
```

**数据格式**（JSONL，每行一条）：
```json
{"date": "2026-03-12", "open": 1.571, "high": 1.592, "low": 1.542, "close": 1.551, "volume": 5939418.0, "amount": 929203113.0, "pct": -1.65}
```

### 0.4 启动时数据更新流程

```javascript
// server.js: 启动后3秒执行
setTimeout(async () => {
  // 1. 补全历史缺失数据
  await backfillMissingDataOnStartup();
  // 2. 更新warmup（如果过期）
  await updateWarmupIfNeeded();
}, 3000);

// updateWarmupIfNeeded() 检查逻辑
const warmupFile = 'data/sector-history-warmup-60.json';
const warmupDay = warmupData.day;  // 例如 2026-03-12
const gap = daysBetween(today, warmupDay);
if (gap > 1) {
  // 重新生成warmup（从本地ETF文件读取）
  await regenerateWarmup(60);
}
```

### 0.5 相关代码位置

| 文件 | 功能 |
|------|------|
| `fetch_sector_data.py:_save_etf_to_disk()` | ETF数据持久化到jsonl |
| `fetch_sector_data.py:_load_etf_from_disk()` | 从本地读取ETF数据 |
| `fetch_sector_data.py:warmup_proxy_files()` | 生成固定文件名warmup |
| `server.js:fetchTencentDaily()` | ETF/指数从本地文件读取 |
| `server.js:updateWarmupIfNeeded()` | 启动时检查更新warmup |

**读取优先级**：
1. ETF → warmup文件 → etf_daily/*.jsonl → 网络请求
2. 指数 → index_daily/*.jsonl → 腾讯API
3. 板块 → 腾讯API

---

## 一、数据源配置

### 1.1 ETF专用数据源（优先级）

```
ETF数据获取策略（自动检测）：
1. AkShare Sina（ETF专用）→ fund_etf_hist_sina()
   - 检测规则：6位数字且以5(上交所)或1(深交所)开头
   - 数据范围：完整历史，满足2025-05-19起始要求
   - 自动应用：所有符合格式的ETF代码

2. Ashare（备）      → 可靠，���回溯更久
```

**ETF代码格式要求**：
- ✅ 必须包含sh/sz前缀：`sh512480`(上交所)、`sz159995`(深交所)
- ✅ 5开头=上交所ETF，1开头=深交所ETF
- ⚠️ **禁止随意删除sh/sz前缀或更换为其他ETF代码**

**实现位置**：`fetch_sector_data.py:122-130`
```python
def _fetch_tencent_daily(code, limit=365):
    # 检测是否为ETF代码(6位数字,5开头或1开头)
    clean_code = code.replace("sh", "").replace("sz", "")
    is_etf = len(clean_code) == 6 and clean_code.isdigit() and clean_code[0] in ['5', '1']

    # 如果是ETF代码,优先使用AkShare Sina接口
    if is_etf:
        return _fetch_akshare_sina_etf(code, limit)
```

**状态**：✅ 2026-03-09验证通过，所有7个ETF满足数据要求

---

## 二、ETF分时数据支持

### 2.1 分时数据接口

**AkShare接口**：`fund_etf_hist_min_em(symbol=纯数字, period='1')`
- 参数：`symbol='159995'`（纯数字，无需sh/sz前缀）
- 返回字段：`['时间', '开盘', '收盘', '最高', '最低', '成交量', '成交额', '均价']`
- 数据粒度：1分钟

**实现位置**：
- `fetch_sector_data.py:get_etf_minute_data()` - Python数据获取
- `server.js:/api/minute/{code}` 路由 - ETF代码识别与API

### 2.2 ETF分时路由

**代码识别规则**：6位数字，5开头(上交所)或1开头(深交所)
```javascript
// server.js: /api/minute/{code} 路由
const isETF = /^\d{6}$/.test(code) && ['5', '1'].includes(code[0]);
if (isETF) {
    const etfCode = code[0] === '5' ? `sh${code}` : `sz${code}`;
    // 调用 fetch_sector_data.py etf-minute ${etfCode}
}
```

**前端调用示例**：
```javascript
// 获取芯片ETF分时数据
fetch('/api/minute/159995')
    .then(res => res.json())
    .then(data => {
        console.log(data); // { day: "2026-03-10", data: [...], prevClose: 1.843 }
    });
```

### 2.3 数据格式

```json
{
    "date": "2026-03-10",
    "data": [
        {
            "time": "2026-03-10 09:30",
            "price": 1.843,
            "volume": 27187,
            "amount": 5010564.0
        },
        // ... 更多分钟数据
    ],
    "prevClose": 1.843
}
```

**状态**：✅ 2026-03-10已实现并测试通过

---

## 三、板块行情与关联分析（ETF分时曲线）

### 3.1 【当日】分时曲线显示

**实现位置**：`public/ui.js:renderSectorHistory()`

**功能说明**：
- 当用户点击"当日"按钮时，图表显示ETF分时曲线（分钟级）
- 时间轴格式：HH:MM（09:30-15:00）
- 数据归一化：以prevClose为基准计算累计涨跌幅
- 支持多ETF对比：可同时查看多个板块的分时走势

**关键代码**：
```javascript
// 当 days === 1 时使用分时数据
if (days === 1 && data.minute) {
  Object.keys(data.minute).forEach(name => {
    const seriesData = item?.series || [];
    const prevClose = item?.prevClose ?? null;
    // 计算归一化数据
    const base = prevClose || seriesData[0]?.price;
    const lineData = seriesData.map(p =>
      ((p.price - base) / base * 100).toFixed(2)
    );
  });
}
```

### 3.2 API接口支持

**接口**：`/api/sector/history_proxy?sectors=半导体,新能源&days=1`

**返回格式**：
```json
{
  "day": "2026-03-10",
  "history": {
    "半导体": [{ "date": "2026-03-10", "close": 1.234, ... }],
    "新能源": [{ "date": "2026-03-10", "close": 0.987, ... }]
  },
  "minute": {
    "半导体": {
      "series": [
        { "time": "2026-03-10 09:30", "price": 1.230 },
        { "time": "2026-03-10 09:31", "price": 1.232 },
        // ... 241条分时数据
      ],
      "prevClose": 1.234
    },
    "新能源": { "series": [...], "prevClose": 0.987 }
  }
}
```

**实现位置**：`server.js:/api/sector/history_proxy` 路由（已修复ETF分时数据获取）

### 3.3 批量数据获取

**命令**：
```bash
# 批量获取所有ETF今日分时数据
python3 << 'EOF'
import json, subprocess
with open('data/sector-proxy.json', 'r', encoding='utf-8') as f:
    etf_map = json.load(f)['variants']['etf']

for name, code in etf_map.items():
    result = subprocess.run(
        ['python3', 'fetch_sector_data.py', 'etf-minute', code],
        capture_output=True, text=True, timeout=30
    )
    data = json.loads(result.stdout)
    print(f"{name}: {len(data['data'])}条分时数据")
EOF
```

**执行结果**（2026-03-10）：
```
✅ 成功获取 9/9 个ETF分时数据
半导体(sh512480): 241条
云计算(sh516510): 241条
新能源(sh516160): 241条
商业航天(sh563530): 241条
创新药(sh512690): 241条
有色金属(sh512400): 241条
通讯设备(sh515880): 241条
游戏(sh516010): 241条
机器人(sh562500): 241条
```

**状态**：✅ 2026-03-10已实现并验证

---

## 四、交易日数据逻辑

---

## 三、交易日数据逻辑

### 2.1 时段定义

| 时段 | 分时数据 | 日线数据 | 保存策略 |
|------|---------|---------|---------|
| **交易时段** | ✅ 当日分时 | 昨日日线 | runtime/minute/ |
| **收盘后** | ❌ 无 | ✅ 当日日线 | data/minute-${date}.jsonl |
| **非交易日** | ❌ 无 | 最近交易日 | 不保存 |

### 3.2 代码位置

```javascript
// server.js: 判断交易时段
const morning = minutes >= 570 && minutes <= 690;   // 9:30-11:30
const afternoon = minutes >= 780 && minutes <= 900; // 13:00-15:00

// 分时数据保存
writeMinuteFile(runtimeFile, data);  // 交易时段
```

---

## 五、数据回补方案

### 4.1 回补范围

- **起始日期**：2025-05-19
- **结束日期**：当前日期
- **用途**：回测、MA60计算、动态基准选择

### 4.2 执行命令

```bash
# 运行回补脚本
python3 scripts/backfill_etf_daily.py 2025-05-19 2026-03-09

# 或使用默认参数
python3 scripts/backfill_etf_daily.py
```

---

## 六、盘中操作提示

### 5.1 分时数据监控

```javascript
// 每2秒刷新分时
setInterval(() => {
    if (isMarketOpenNow()) {
        fetch(`/api/minute/${etf_code}`)
            .then(data => {
                updateChart(data);
                const signal = analyzeIntraday(data);
                showTip(signal);
            });
    }
}, 2000);
```

### 5.2 买卖点判断

```python
# 突破早盘高点 → 买入
# 乖离过大回落 → 卖出
# 其他 → 观望
```

---

## 七、数据完整性验证

### 6.1 验证标准

| 检查项 | 标准 |
|--------|------|
| 起始日期 | ≤ 2025-05-19 |
| 交易日覆盖率 | ≥ 90% |
| 字段完整性 | date/open/close/high/low/volume/amount |
| 数据连续性 | 除节假日外连续 |

### 6.2 验证命令

```bash
python3 -c "
import sys
sys.path.insert(0, '.')
from scripts.backfill_etf_daily import backfill_etf_data
result = backfill_etf_data()
print(f'✅ 回补完成，共处理 {len(result)} 个ETF')
"
```

---

## 八、实施步骤

### 阶段1：数据回补（立即执行）
- [x] 运行回补脚本
- [ ] 验证数据完整性
- [ ] 修复缺失数据

### 阶段2：分时数据优化
- [x] 实现ETF分时数据获取
- [x] 修复/api/sector/history_proxy接口ETF分时支持
- [x] 前端【当日】模式分时曲线显示
- [x] 批量获取ETF分时数据（9个ETF各241条）
- [ ] 优化分时数据保存
- [ ] 实现盘中操作提示
- [ ] 添加买卖点判断

### 阶段3：验证与测试
- [x] 后端API验证（9个ETF分时数据获取成功）
- [ ] 前端展示验证（需盘中测试）
- [ ] 回测验证
- [ ] 盘中提示测试

---

## 九、相关文件

| 文件 | 说明 |
|------|------|
| `fetch_sector_data.py` | ETF分时数据获取（get_etf_minute_data） |
| `server.js` | /api/minute/{code} 路由ETF识别 |
| `scripts/backfill_etf_daily.py` | 回补脚本 |
| `data/sector-proxy.json` | ETF配置 |
| `data/etf_daily/` | ETF日线存储 |
| `data/minute-*.jsonl` | ETF分时缓存 |
| `runtime/minute/` | 运行时分时数据 |

---

**更新记录**:
- 2026-03-12: v2.1 - 建立大盘指数持久化存储（index_daily），清理archive等旧文件
- 2026-03-12: v2.0 - 实施三层持久化架构：固定文件名warmup + ETF日线文件 + 自动启动更新；修复历史日期显示问题（2026-03-09→2026-03-12）
- 2026-03-10: 添加ETF分时数据支持，实现/api/minute/{code}路由；修复/api/sector/history_proxy接口ETF分���获取；前端【当日】模式支持分时曲线显示；批量获取9个ETF分时数据（各241条）
- 2026-03-09: 初始版本，执行数据回补
