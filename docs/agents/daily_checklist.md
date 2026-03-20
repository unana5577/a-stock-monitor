# 每日数据检查清单

> **更新日期**: 2026-03-20
> **执行时机**: 每日开盘前（09:15前）

---

## 一、时间判断

| 当前时间 | 交易状态 | 数据预期 |
|---------|---------|---------|
| 00:00-09:15 | 非交易时间 | 分时数据为空，日线截止到昨日 |
| 09:15-09:30 | 盘前集合竞价 | 无分时数据 |
| 09:30-11:30 | 早盘交易 | 分时数据实时更新 |
| 11:30-13:00 | 午间休市 | 分时数据停止 |
| 13:00-15:00 | 午盘交易 | 分时数据实时更新 |
| 15:00-24:00 | 盘后 | 分时数据完整，日线可用 |

**关键规则**：
- ❌ **未开盘时（09:30前）不要请求分时接口** - 会报错或返回空数据
- ✅ **未开盘时检查昨日日线数据** - 应该截止到昨天
- ✅ **开盘后检查今日分时数据** - 从09:30开始有数据

---

## 二、数据清单

### 2.1 日线数据（每日收盘后更新）

| 数据类型 | 代码 | 文件路径 | 接口 | 检查内容 |
|---------|------|---------|------|---------|
| **ETF日线** | sh512480 | data/etf_daily/etf_512480.jsonl | `_fetch_akshare_sina_etf()` | 最新日期应为昨天，volume/amount非0 |
| **ETF日线** | sh516510 | data/etf_daily/etf_516510.jsonl | `_fetch_akshare_sina_etf()` | 最新日期应为昨天，volume/amount非0 |
| **ETF日线** | sh516160 | data/etf_daily/etf_516160.jsonl | `_fetch_akshare_sina_etf()` | 最新日期应为昨天，volume/amount非0 |
| **ETF日线** | sh563530 | data/etf_daily/etf_563530.jsonl | `_fetch_akshare_sina_etf()` | 最新日期应为昨天，volume/amount非0 |
| **ETF日线** | sh515120 | data/etf_daily/etf_515120.jsonl | `_fetch_akshare_sina_etf()` | 最新日期应为昨天，volume/amount非0 |
| **ETF日线** | sh512400 | data/etf_daily/etf_512400.jsonl | `_fetch_akshare_sina_etf()` | 最新日期应为昨天，volume/amount非0 |
| **ETF日线** | sh515880 | data/etf_daily/etf_515880.jsonl | `_fetch_akshare_sina_etf()` | 最新日期应为昨天，volume/amount非0 |
| **ETF日线** | sh516010 | data/etf_daily/etf_516010.jsonl | `_fetch_akshare_sina_etf()` | 最新日期应为昨天，volume/amount非0 |
| **ETF日线** | sh562500 | data/etf_daily/etf_562500.jsonl | `_fetch_akshare_sina_etf()` | 最新日期应为昨天，volume/amount非0 |
| **指数日线** | sh000001 | data/index_daily/index_000001.jsonl | `get_index_history()` | 最新日期应为昨天，**amount非0** |
| **指数日线** | sz399001 | data/index_daily/index_399001.jsonl | `get_index_history()` | 最新日期应为昨天，**amount非0** |
| **指数日线** | sz399006 | data/index_daily/index_399006.jsonl | `get_index_history()` | 最新日期应为昨天，**amount非0** |
| **指数日线** | sh000688 | data/index_daily/index_000688.jsonl | `get_index_history()` | 最新日期应为昨天，**amount非0** |

### 2.2 分时数据（交易时段实时更新）

| 数据类型 | 文件路径 | 接口 | 检查时机 | 检查内容 |
|---------|---------|------|---------|---------|
| **ETF分时** | data/minute-YYYYMMDD.jsonl | `get_etf_minute_data()` | 09:30后 | 今日分时数据 |
| **指数分时** | data/minute-YYYYMMDD.jsonl | `get_etf_minute_data()` | 09:30后 | 今日分时数据 |

**注意**：
- 分时文件名按日期命名：`minute-20260320.jsonl`
- 未开盘时分时文件不存在或为空
- 09:30后分时文件开始有数据

---

## 三、每日检查流程

### 3.1 早盘检查（09:15前）

```bash
# 1. 检查服务器状态
curl -s http://localhost:8787/api/market/date

# 2. 检查ETF日线数据最新日期
python3 << 'EOF'
import os, json
etf_dir = 'data/etf_daily'
files = [f for f in os.listdir(etf_dir) if f.endswith('.jsonl')]
for f in sorted(files):
    with open(os.path.join(etf_dir, f)) as fp:
        lines = fp.readlines()
        if lines:
            last = json.loads(lines[-1])
            print(f'{f}: {last["date"]}')
EOF

# 3. 检查指数日线数据最新日期
python3 << 'EOF'
import os, json
idx_dir = 'data/index_daily'
files = [f for f in os.listdir(idx_dir) if f.endswith('.jsonl')]
for f in sorted(files):
    with open(os.path.join(idx_dir, f)) as fp:
        lines = fp.readlines()
        if lines:
            last = json.loads(lines[-1])
            print(f'{f}: {last["date"]}')
EOF
```

**预期结果**：
- 所有ETF和指数日线最新日期 = 昨天日期（如2026-03-19）
- 无2026-03-20的日线数据（因为今天还没收盘）

### 3.2 盘中检查（09:30-15:00）

```bash
# 1. 检查分时数据文件是否存在
ls -lh data/minute-$(date +%Y%m%d).jsonl

# 2. 检查分时数据量
python3 << 'EOF'
import json
today = "2026-03-20"
minute_file = f"data/minute-{today.replace('-', '')}.jsonl"
try:
    with open(minute_file) as f:
        lines = f.readlines()
    print(f'分时数据条数: {len(lines)}')
    if lines:
        first = json.loads(lines[0])
        last = json.loads(lines[-1])
        print(f'第一条: {first.get("time", "N/A")}')
        print(f'最后一条: {last.get("time", "N/A")}')
except FileNotFoundError:
    print('分时文件不存在（未到交易时间）')
EOF
```

**预期结果**：
- 09:30前：分时文件不存在
- 09:30后：分时文件存在，数据从09:30开始
- 15:00后：分时数据完整，241条（09:30-15:00，每分钟一条）

### 3.3 收盘后检查（15:00后）

```bash
# 1. 检查分时转日线是否完成
python3 -c "
import sys
sys.path.insert(0, '.')
from data_maintenance import convert_minute_to_daily
convert_minute_to_daily()
"

# 2. 检查今日日线数据是否生成
# (同早盘检查流程，最新日期应为今天)
```

---

## 四、接口对应关系

### 4.1 日线接口

| 接口函数 | 数据源 | 调用时机 | 用途 | 状态 |
|---------|--------|---------|------|------|
| `_fetch_akshare_sina_etf()` | 新浪ETF日线 | 收盘后 | 获取ETF日线数据 | ✅ 正常 |
| `get_index_history()` | `stock_zh_index_daily_em` | 收盘后 | 获取指数日线（含成交额） | ✅ 正常 |
| `_fetch_etf_date_range()` | 新浪ETF日线 | 缺失时 | 增量回补数据 | ✅ 正常 |

### 4.2 分时接口

| 接口函数 | 数据源 | 调用时机 | 用途 | 状态 |
|---------|--------|---------|------|------|
| `get_etf_minute_data()` | 东财分时 | 交易时段 | 获取ETF分时数据 | ✅ 正常 |

### 4.3 涨跌家数接口

| 接口函数 | 数据源 | 调用时机 | 用途 | 状态 |
|---------|--------|---------|------|------|
| `get_market_breadth()` | 东财全市场 | 交易时段 | 获取涨跌家数 | ⚠️ 东财被封 |
| 腾讯快照接口 | `qt.gtimg.cn` | 交易时段 | 获取指数快照 | ✅ 备用 |

**重要**：
- ❌ **不要在非交易时间调用分时接口** - 会报错
- ✅ **只在09:30-15:00调用分时接口**
- ⚠️ **东财接口被封，涨跌家数暂时无法获取**

---

## 五、每日数据更新任务

### 5.1 开盘前（09:15前）

```bash
# 1. 更新指数日线（包含成交额）
python3 << 'EOF'
import sys
sys.path.insert(0, '.')
from data_maintenance import update_index_data

indices = [
    ('000001', '上证指数'),
    ('399001', '深证成指'),
    ('399006', '创业板指'),
    ('000688', '科创板指'),
]
for code, name in indices:
    update_index_data(code, name)
EOF
```

### 5.2 交易时段（09:30-15:00）

```bash
# 1. 检查分时数据
ls -lh data/minute-$(date +%Y%m%d).jsonl

# 2. 检查涨跌家数（每分钟）
python3 -c "
import sys
sys.path.insert(0, '.')
from fetch_sector_data import get_market_breadth
result = get_market_breadth()
if result:
    print(f'涨:{result[\"up\"]} 跌:{result[\"down\"]} 平:{result[\"flat\"]}')
"
```

### 5.3 收盘后（15:00后）

```bash
# 1. 分时转日线
python3 -c "
import sys
sys.path.insert(0, '.')
from data_maintenance import convert_minute_to_daily
convert_minute_to_daily()
"

# 2. 更新ETF日线
python3 -c "
import sys
sys.path.insert(0, '.')
from data_maintenance import update_all_etf_data
update_all_etf_data()
"
```

---

## 五、常见问题

### 5.1 日线数据缺失

**症状**：ETF日线最新日期 < 昨天日期

**原因**：
- 昨日数据未更新
- 接口调用失败

**解决**：
```bash
python3 << 'EOF'
import sys
sys.path.insert(0, '.')
from data_maintenance import update_etf_data

# 更新缺失的ETF
update_etf_data('sh512480', '半导体')
EOF
```

### 5.2 分时数据为空

**症状**：交易时间分时文件为空

**原因**：
- 未到09:30
- 分时接口调用失败

**解决**：
- 检查当前时间是否 >= 09:30
- 查看data_maintenance.py日志

### 5.3 指数数据失败

**症状**：指数日线无法获取

**原因**：
- 东财接口被封
- 网络问题

**解决**：
- 使用腾讯接口兜底
- 检查网络连接

---

## 六、检查脚本

```python
#!/usr/bin/env python3
# 每日数据检查脚本
import os
import json
from datetime import datetime, timedelta

def check_etf_daily():
    """检查ETF日线数据"""
    etf_dir = 'data/etf_daily'
    files = [f for f in os.listdir(etf_dir) if f.endswith('.jsonl')]

    print('=== ETF日线数据检查 ===')
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

    for f in sorted(files):
        with open(os.path.join(etf_dir, f)) as fp:
            lines = fp.readlines()
            if lines:
                last = json.loads(lines[-1])
                date = last['date']
                status = '✅' if date == yesterday else '⚠️'
                print(f'{status} {f}: {date}')

def check_index_daily():
    """检查指数日线数据"""
    idx_dir = 'data/index_daily'
    files = [f for f in os.listdir(idx_dir) if f.endswith('.jsonl')]

    print('\\n=== 指数日线数据检查 ===')
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

    for f in sorted(files):
        with open(os.path.join(idx_dir, f)) as fp:
            lines = fp.readlines()
            if lines:
                last = json.loads(lines[-1])
                date = last['date']
                status = '✅' if date == yesterday else '⚠️'
                print(f'{status} {f}: {date}')

def check_minute_data():
    """检查分时数据"""
    today = datetime.now().strftime('%Y%m%d')
    minute_file = f'data/minute-{today}.jsonl'

    print(f'\\n=== 分时数据检查 ({datetime.now().strftime("%H:%M")}) ===')

    try:
        with open(minute_file) as f:
            lines = f.readlines()

        print(f'分时数据条数: {len(lines)}')

        if lines:
            first = json.loads(lines[0])
            last = json.loads(lines[-1])
            print(f'第一条: {first.get("time", "N/A")}')
            print(f'最后一条: {last.get("time", "N/A")}')

            # 检查数据完整性
            current_hour = datetime.now().hour
            if current_hour >= 9 and current_hour < 15:
                expected_min = (current_hour - 9) * 60 + 30
                if current_hour > 12:
                    expected_min -= 90  # 减去午休时间
                print(f'预期数据条数: {expected_min}')
                print(f'{'✅' if len(lines) >= expected_min else '⚠️'} 数据完整性检查')

    except FileNotFoundError:
        print('分时文件不存在（未到交易时间或未生成）')

if __name__ == '__main__':
    check_etf_daily()
    check_index_daily()
    check_minute_data()
```

---

**维护者**：数据Agent
**更新频率**：每日开盘前更新检查清单
