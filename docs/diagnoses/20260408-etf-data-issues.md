# ETF数据问题诊断与修复方案

## 问题1：分时转日线逻辑缺陷

### 问题描述
`_minute_to_daily_for_etf` 函数会将0值写入日线文件

### 当前代码（fetch_sector_data.py:969-980）
```python
total_volume = volumes[-1] if volumes else 0
total_amount = amounts[-1] if amounts else 0

return {
    "volume": total_volume,   # ← 如果volumes空，写入0
    "amount": total_amount,   # ← 如果amounts空，写入0
    "pct": round(pct, 2),
    "source": "minute"
}
```

### 修复方案
```python
# 1. 验证数据有效性
if not prices or len(prices) == 0:
    return None

# 2. 验证成交额不为0
if not amounts or not volumes or amounts[-1] == 0 or volumes[-1] == 0:
    return None  # 数据无效，不写入

# 3. 返回有效数据
return {
    "volume": total_volume,
    "amount": total_amount,
    "pct": round(pct, 2),
    "source": "minute"
}
```

---

## 问题2：市场成交额数据严重缺失

### 当前状态
```
data/market/etf-amount-daily.jsonl:
- 总行数: 6
- 日期范围: 2026-03-17 ~ 2026-03-20, 2026-04-08
- 缺失: 2026-03-21 ~ 2026-04-07 (18天)
```

### 影响
- 无法计算板块成交额占比
- "资金热度"指标失效
- 无法判断资金进出

### 解决方案
方案A：使用 backfill_market_amount_daily.py 补全历史数据
方案B：修改 API，当缺失市场数据时不计算占比

---

## 问题3：分时数据采集失败

### 当前状态
```python
sector-minute-warmup.json:
{"minute": []}  # 完全空的
```

### 检查项
1. 分时数据采集API是否正常？
2. sector-minute-warmup.json 生成逻辑是否有问题？
3. 是否需要从其他数据源获取分时数据？

### 修复步骤
1. 检查 `_fetch_ashare_minute` 函数
2. 验证分时数据写入逻辑
3. 确保warmup生成时包含有效分时数据

---

## 问题4：数据验证缺失

### 当前问题
- 没有验证 amount=0 的数据
- 没有检查分时数据是否为空
- 没有检查市场数据是否缺失

### 建议添加验证
```python
def validate_etf_data(item):
    """验证ETF数据有效性"""
    if item.get('amount', 0) == 0:
        return False, "成交额为0"
    if item.get('volume', 0) == 0:
        return False, "成交量为0"
    if item.get('source') == 'minute' and item.get('amount', 0) == 0:
        return False, "分时数据成交额为0"
    return True, "OK"
```

---

## 优先级

| 问题 | 优先级 | 影响范围 |
|-----|--------|---------|
| **分时转日线0值** | 🔴 P0 | 导致所有历史数据错误 |
| **市场成交额缺失** | 🔴 P0 | 导致热度指标失效 |
| **分时数据为空** | 🟡 P1 | 影响fallback质量 |
| **数据验证缺失** | 🟡 P1 | 影响数据质量 |

---

## 行动项

- [ ] 修复 `_minute_to_daily_for_etf` 验证逻辑
- [ ] 补全市场成交额历史数据（3/21-4/7）
- [ ] 检查分时数据采集问题
- [ ] 添加数据质量验证
- [ ] 定期检查数据完整性（cron job）
