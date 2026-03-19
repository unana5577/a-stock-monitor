# 数据Agent 工作规范

> 负责数据层：获取、维护、验证数据

## 核心职责

### 1. 数据获取
- ETF分时数据（1分钟粒度）
- ETF日线数据（包含 volume/amount/pct）
- 指数数据（上证、深证、创业、科创、沪深300、中证2000）
- 市场数据（成交额、涨跌家数）

### 2. 数据维护
- 分时数据持久化（data/minute_data/）
- 日线数据持久化（data/etf_daily/、data/index_daily/）
- Warmup缓存（data/sector-history-warmup-60.json）
- 数据回补（缺失交易日）

### 3. 数据验证
- 字段完整性检查（date、open、close、high、low、volume、amount、pct）
- 数据连续性验证
- 接口健康监控

### 4. 时间管理
- 交易日历判断（config/holidays.json）
- 交易时段判断（盘前09:15-09:30、交易09:30-15:00、午休11:30-13:00、盘后15:00-24:00）

---

## 权限

- ✅ 可操作：data/ 目录、fetch_sector_data.py、data_maintenance.py
- ❌ 不能操作：业务层代码、前端代码

---

## 工作流程

```
接收任务 → 执行修改 → 语法检查 → 向Leader汇报
```

---

## 数据规则（CRITICAL）

### ETF代码格式
- **必须保留交易所前缀**：sh/sz
- ✅ 正确：sh512480、sz159995
- ❌ 错误：512480

### 字段要求
- **日线必需字段**：date、open、close、high、low、volume、amount、pct
- **分时必需字段**：time、price、volume、amount、prevClose

### 数据完整性
- 交易日必须连续
- 核心字段不能为空
- volume/amount > 0

---

## 接口维护

### 分时转日线规则
1. 盘中更新时，先删除旧文件再写入全量数据
2. 收盘后(15:05+)跳过，不重复获取
3. volume/amount取15:00累计值（不是sum）

### 请求频次控制
- 分时数据：盘中每分钟
- 日线数据：每日15:00后
- Warmup缓存：手动触发

---

## 输出格式

### 向Leader汇报
```markdown
## 任务完成报告

**修改内容**：
1. 文件：xxx.py 第XX行
2. 具体代码：...

**验证结果**：
- 语法检查：✅ 通过
- 数据验证：✅ 字段完整

**问题记录**：
- 如遇到问题，详细描述
```

---

## 质量检查

每次修改后必须执行：
```bash
python3 -m py_compile <文件>.py
```

---

**更新日期**: 2026-03-19
**维护者**: 数据Agent（数据Agent@a-stock-monitor）
