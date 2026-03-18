# sector_lifecycle 模块架构文档

> 版本：v2.0
> 日期：2026-03-18
> 状态：✅ 已完成并测试通过

---

## 一、模块概述

`sector_lifecycle` 是板块生命周期分析的核心模块，提供ETF操作建议的完整分析流程。

### 核心功能

1. **数据加载** - ETF、指数、全市场成交额数据
2. **动态基准选择** - 基于60天相关系数自动选择最优基准
3. **指标计算** - Alpha、趋势、量能、乖离率
4. **操作建议生成** - 基于完整映射表（17种场景）

---

## 二、模块结构

```
sector_lifecycle/
├── __init__.py              # 模块导出
├── data_loader.py           # 数据加载器
├── benchmark.py             # 动态基准选择
├── indicators.py            # 技术指标计算
└── advice.py                # 操作建议生成
```

---

## 三、模块说明

### 3.1 data_loader.py - 数据加载器

**类**：`DataLoader`

**方法**：
- `load_etf_data(filename)` - 加载ETF日线数据
- `load_index_data(filename)` - 加载指数日线数据
- `load_etf_amount_data()` - 加载全市场ETF成交额数据

**使用示例**：
```python
from sector_lifecycle import DataLoader

loader = DataLoader(data_dir="data")
etf_df = loader.load_etf_data("etf_515880.jsonl")
market_amount = loader.load_etf_amount_data()
```

---

### 3.2 benchmark.py - 动态基准选择

**类**：`BenchmarkSelector`

**方法**：
- `select_benchmark(etf_df)` - 选择最相关基准指数
- `load_benchmark_data(code)` - 加载基准数据

**基准候选**：
- 上证指数（sh000001）
- 深证成指（sz399001）
- 创业板指（sz399006）
- 科创50（sh000680）

**选择逻辑**：
- 基于60天滚动相关系数
- 自动选择相关性最高的指数
- 返回基准名称、代码、相关系数

**使用示例**：
```python
from sector_lifecycle import DataLoader, BenchmarkSelector

loader = DataLoader()
selector = BenchmarkSelector(loader)

benchmark_info = selector.select_benchmark(etf_df)
# 返回: {"benchmark": "上证指数", "code": "sh000001", "correlation": 0.85}

bench_df = selector.load_benchmark_data(benchmark_info['code'])
```

---

### 3.3 indicators.py - 技术指标计算

**类**：`Indicators`（静态方法类）

**方法**：

1. **Alpha超额收益**
   - `calculate_alpha(etf_df, bench_df, period)` - 计算Alpha
   - `get_alpha_strength(alpha)` - 获取强弱描述

2. **趋势指标**
   - `calculate_ma_slope(df, window)` - 计算MA斜率
   - 支持MA5（短期）和MA20（中期）

3. **乖离率风险**
   - `calculate_risk_level(df)` - 计算7级风险等级
   - 基于60天滚动分位数

4. **资金热度**
   - `calculate_fund_heat(etf_df, market_amount_data)` - 计算资金热度
   - 优先使用真实成交额，备选使用量比

**风险等级**：
- 极度风险、高风险、中高位风险、中位风险、中低位风险、低风险、极度超跌

**使用示例**：
```python
from sector_lifecycle import Indicators

# Alpha
alpha_5 = Indicators.calculate_alpha(etf_df, bench_df, 5)
alpha_20 = Indicators.calculate_alpha(etf_df, bench_df, 20)
strength = Indicators.get_alpha_strength(alpha_5)

# 趋势
ma5_slope = Indicators.calculate_ma_slope(etf_df, 5)
ma20_slope = Indicators.calculate_ma_slope(etf_df, 20)

# 风险等级
risk_level, bias_5 = Indicators.calculate_risk_level(etf_df)

# 资金热度
fund_status, fund_heat, fund_change, display = Indicators.calculate_fund_heat(
    etf_df, market_amount_data
)
```

---

### 3.4 advice.py - 操作建议生成

**类**：`AdviceGenerator`

**方法**：
- `generate_advice(risk_level, fund_status, ma5_slope)` - 生成操作建议

**完整映射表**（17种场景）：
- 极度风险/高风险 → 减仓/离场
- 极度超跌 + 放量 → 关注企稳/抄底
- 低风险 + 放量 + 向上 → 关注企稳/试水
- 其他风险等级根据资金热度和趋势组合判断

**使用示例**：
```python
from sector_lifecycle import AdviceGenerator

generator = AdviceGenerator()
advice, reason = generator.generate_advice(
    risk_level="中低位风险",
    fund_status="放量",
    ma5_slope=-0.06
)
# 返回: ("关注", "关注企稳机会")
```

---

## 四、完整使用流程

### 4.1 基本使用

```python
from sector_lifecycle import (
    DataLoader,
    BenchmarkSelector,
    Indicators,
    AdviceGenerator
)

# 1. 初始化
loader = DataLoader()
benchmark_selector = BenchmarkSelector(loader)
indicators = Indicators()
advice_generator = AdviceGenerator()

# 2. 加载数据
etf_df = loader.load_etf_data("etf_515880.jsonl")
market_amount_data = loader.load_etf_amount_data()

# 3. 动态基准选择
benchmark_info = benchmark_selector.select_benchmark(etf_df)
bench_df = benchmark_selector.load_benchmark_data(benchmark_info['code'])

# 4. 计算指标
alpha_5 = indicators.calculate_alpha(etf_df, bench_df, 5)
risk_level, bias_5 = indicators.calculate_risk_level(etf_df)
ma5_slope = indicators.calculate_ma_slope(etf_df, 5)
fund_status, fund_heat, fund_change, _ = indicators.calculate_fund_heat(
    etf_df, market_amount_data
)

# 5. 生成建议
advice, reason = advice_generator.generate_advice(
    risk_level, fund_status, ma5_slope
)
```

### 4.2 脚本使用

```bash
# 运行模块化版本脚本
python3 scripts/operation_advice.py

# 输出文件
# - logs/operation_advice_YYYYMMDD.json
# - logs/operation_advice_YYYYMMDD.csv
```

---

## 五、技术特点

### 5.1 模块化设计
- **独立模块**：每个功能独立文件，易于维护
- **清晰接口**：标准化的输入输出
- **可复用**：可在其他脚本中独立使用

### 5.2 数据处理
- **Pandas支持**：使用DataFrame进行数据处理
- **日期处理**：自动转换日期格式
- **数据验证**：检查数据完整性

### 5.3 计算优化
- **滚动窗口**：60天滚动计算
- **相关系数**：NumPy优化计算
- **分位数**：高效的风险等级判断

### 5.4 容错机制
- **数据不足**：返回"数据不足"状态
- **双重模式**：资金热度支持真实成交额和量比两种模式
- **基准兜底**：无法选择时默认上证指数

---

## 六、输出字段说明

### 6.1 基本信息
- `etf_name`: ETF名称
- `etf_code`: ETF代码
- `close`: 收盘价
- `pct`: 涨跌幅
- `benchmark`: 基准指数

### 6.2 展示指标
- `alpha_5`: 5日Alpha
- `alpha_20`: 20日Alpha
- Alpha强弱：显著强势✅、小幅强势、小幅弱势、显著弱势❌

### 6.3 判断指标
- `risk_level`: 风险等级（7级）
- `bias_5`: 乖离率
- `ma5_slope`: MA5斜率（短期趋势）
- `ma20_slope`: MA20斜率（中期趋势）
- `short_trend`: 短期趋势（向上/向下）
- `medium_trend`: 中期趋势（向上/向下）
- `fund_status`: 资金热度（放量/缩量/持平）
- `fund_heat`: 热度占比（%）
- `fund_heat_change`: 热度变化比例

### 6.4 操作建议
- `advice`: 操作建议（如"小仓位试水"、"观望"等）
- `reason`: 原因说明

---

## 七、版本对比

### 单脚本版本 vs 模块化版本

| 特性 | 单脚本版本 | 模块化版本 |
|------|-----------|-----------|
| 文件结构 | 1个文件（415行） | 5个模块文件 |
| 可维护性 | ⭐⭐ | ⭐⭐⭐⭐⭐ |
| 可复用性 | ❌ | ✅ |
| 测试性 | 困难 | 简单 |
| 扩展性 | 困难 | 简单 |
| 适用场景 | 快速原型 | 生产环境 |

### 迁移路径

1. **保持兼容** - 单脚本版本继续可用
2. **逐步迁移** - 新功能使用模块化版本
3. **API集成** - 模块化版本更易于集成到API

---

## 八、后续优化

### 8.1 性能优化
- [ ] 添加缓存机制（避免重复计算）
- [ ] 并行处理多个ETF
- [ ] 增量更新（只更新最新数据）

### 8.2 功能扩展
- [ ] 支持更多ETF
- [ ] 增加自定义基准
- [ ] 添加回测功能
- [ ] 历史建议记录

### 8.3 API集成
- [ ] RESTful API接口
- [ ] WebSocket实时推送
- [ ] 前端数据展示

---

## 九、测试验证

### 9.1 单元测试
```bash
# TODO: 添加单元测试
python3 -m pytest tests/test_sector_lifecycle.py
```

### 9.2 集成测试
```bash
# 运行完整脚本
python3 scripts/operation_advice.py

# 验证输出
cat logs/operation_advice_20260318.csv
```

### 9.3 测试结果
✅ 所有9个ETF数据正常
✅ 动态基准选择功能正常
✅ 所有指标计算正确
✅ 操作建议映射完整
✅ JSON/CSV输出正确

---

## 十、常见问题

### Q1: 如何添加新的ETF？
**A**: 在 `ETF_LIST` 配置中添加即可：
```python
{"name": "新ETF", "code": "5XXXXX", "file": "etf_5XXXXX.jsonl"}
```

### Q2: 如何修改基准指数？
**A**: 在 `benchmark.py` 的 `BENCHMARKS` 列表中修改或添加。

### Q3: 资金热度为什么有的是0？
**A**: 当缺少全市场成交额数据时，系统使用量比模式，热度占比显示为0。

### Q4: 如何调整风险等级阈值？
**A**: 修改 `indicators.py` 中 `calculate_risk_level()` 的分位数设置。

---

**文档维护**：Claude
**最后更新**：2026-03-18
