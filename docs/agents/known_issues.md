# 已发现的问题与修复记录

> 记录已发现的问题、根因、修复方案，避免重复踩坑

---

## 2026-03-23：warmup day 字段不准确导致 lifecycle 返回空

### 问题描述
前端"关注ETF"板块显示为空数据

### 根因分析

#### 问题1：warmup day 字段错误
- **位置**：`fetch_sector_data.py:_proxy_history_payload()`
- **原因**：day 字段用今天日期初始化，但实际数据可能只有到 T-1 或更早
- **影响**：warmup 文件的 day="2026-03-23"，但实际数据只到 2026-03-20
- **修复**：day 字段改为从数据中取实际最新日期

#### 问题2：缓存失效机制缺失
- **位置**：`data/` 目录下的各类缓存文件
- **原因**：缓存根据文件名日期生成，但数据更新后缓存没有失效
- **影响**：旧缓存（day=2026-03-20）被 server.js 使用，导致返回空数据
- **修复**：由 Cleanup Agent 负责缓存清理（cleanup_cache.py）

#### 问题3：server.js 日期验证过于严格
- **位置**：`server.js:/api/sector/lifecycle`
- **原因**：当缓存 day !== today 时直接返回空数据，无降级方案
- **影响**：即使有旧数据也无法使用
- **修复**：应返回旧数据并标注 `data_incomplete: true`

### 修复记录
| 日期 | 问题 | 修复方案 | 状态 |
|------|------|----------|------|
| 2026-03-23 | warmup day 字段错误 | 修改 `_proxy_history_payload()` 从数据取日期 | ✅ 已修复 |
| 2026-03-23 | 缓存失效机制 | Cleanup Agent 增加 `cleanup_cache.py` | ✅ 已完成 |
| 2026-03-23 | 日期验证过严 | server.js 允许1-3天容差，返回旧数据+标注 | ✅ 已修复 |

### 预防措施
1. **warmup 生成时**：day 字段必须从实际数据取，不能用今天日期
2. **缓存策略**：数据更新后必须清理旧缓存
3. **接口降级**：接口应优先返回旧数据+标注，而不是直接返回空

### 验证方法
```bash
# 验证 warmup day 字段正确
python3 -c "import json; d=json.load(open('data/sector-history-warmup-60.json')); print(f'day={d[\"day\"]}, 实际最新={max(arr[-1][\"date\"] for n,arr in d[\"history\"].items() if arr)}')"

# 验证接口返回
curl -s "http://127.0.0.1:8787/api/sector/lifecycle?days=60" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'items={len(d[\"items\"])}, day={d[\"day\"]}')"
```

---

## 待修复问题

### 1. server.js 日期验证过严
- **影响**：缓存 day != today 时直接返回空数据
- **建议**：返回旧数据 + `data_incomplete: true`
- **优先级**：高
- **负责人**：Leader

---

**更新日期**: 2026-03-23
