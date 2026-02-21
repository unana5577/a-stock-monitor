# 板块生命周期判断系统实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为A股量化软件实现板块生命周期判断系统，通过位置+阶段两层结构识别板块状态。

**Architecture:** 
- 数据层：Python 模块计算 Alpha、成交额占比、位置、阶段
- API 层：Node.js 服务端暴露接口
- 展示层：前端表格展示结果

**Tech Stack:** Python (pandas, akshare), Node.js, Express

**项目路径:** `/Users/una5577/Documents/trae_projects/a-stock-monitor`

---

## Task 1: 定义数据接口格式

**Files:**
- Create: `docs/api-schema.json`

**Step 1: 创建 API 响应格式定义**

```json
{
  "sector_lifecycle_response": {
    "板块名称": "string",
    "位置区域": "string (异常区/低位区/中位区/高位区)",
    "位置名称": "string (过热期/强势期/...)",
    "阶段信号": "string (衰退期/背离期A/背离期B/加速期/震荡期/启动期/潜伏期)",
    "显示名称": "string",
    "含义": "string",
    "操作建议": "string",
    "指标数据": {
      "alpha_5": "number",
      "alpha_20": "number",
      "amount_share": "number",
      "amount_share_ma5": "number",
      "ma20": "number",
      "ma60": "number",
      "bias_20": "number",
      "close": "number",
      "pct": "number"
    }
  }
}
```

**Step 2: 保存文件**

保存到 `docs/api-schema.json`

**Step 3: Commit**

```bash
git add docs/api-schema.json
git commit -m "docs: define sector lifecycle API schema"
```

---

## Task 2: 实现 Alpha 计算模块

**Files:**
- Create: `sector_lifecycle.py`
- Create: `tests/test_sector_lifecycle.py`

**Step 1: 写测试 - Alpha 计算**

```python
import pytest
from sector_lifecycle import calculate_alpha

def test_calculate_alpha_positive():
    """板块涨幅10%，大盘涨幅5%，Alpha应为正"""
    sector_return = 0.10
    market_return = 0.05
    result = calculate_alpha(sector_return, market_return)
    assert abs(result - 0.05) < 0.001

def test_calculate_alpha_negative():
    """板块涨幅2%，大盘涨幅5%，Alpha应为负"""
    sector_return = 0.02
    market_return = 0.05
    result = calculate_alpha(sector_return, market_return)
    assert abs(result - (-0.03)) < 0.001

def test_calculate_alpha_zero_market():
    """大盘涨幅为0时的边界情况"""
    sector_return = 0.05
    market_return = 0.0
    result = calculate_alpha(sector_return, market_return)
    assert result == 0.05  # 直接返回板块涨幅
```

**Step 2: 运行测试，确认失败**

```bash
cd /Users/una5577/Documents/trae_projects/a-stock-monitor
python -m pytest tests/test_sector_lifecycle.py -v
```
Expected: FAIL (module not found)

**Step 3: 实现 Alpha 计算函数**

```python
# sector_lifecycle.py

def calculate_alpha(sector_return: float, market_return: float) -> float:
    """
    计算板块相对大盘的超额收益 (Alpha)
    
    Args:
        sector_return: 板块涨幅 (如 0.10 表示 10%)
        market_return: 大盘涨幅 (如 0.05 表示 5%)
    
    Returns:
        Alpha 值 (如 0.05 表示超额收益 5%)
    """
    if market_return == 0:
        return sector_return
    return sector_return - market_return


def calculate_alpha_n_days(sector_data: list, market_data: list, days: int) -> float:
    """
    计算N日Alpha
    
    Args:
        sector_data: 板块收盘价列表 [(date, close), ...]
        market_data: 大盘收盘价列表 [(date, close), ...]
        days: 天数 (如 5, 20)
    
    Returns:
        N日Alpha值
    """
    if len(sector_data) < days + 1 or len(market_data) < days + 1:
        return None
    
    # 取最近 days+1 个数据点
    sector_recent = sector_data[-(days+1):]
    market_recent = market_data[-(days+1):]
    
    # 计算涨幅
    sector_return = (sector_recent[-1][1] - sector_recent[0][1]) / sector_recent[0][1]
    market_return = (market_recent[-1][1] - market_recent[0][1]) / market_recent[0][1]
    
    return calculate_alpha(sector_return, market_return)
```

**Step 4: 运行测试，确认通过**

```bash
python -m pytest tests/test_sector_lifecycle.py::test_calculate_alpha -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add sector_lifecycle.py tests/test_sector_lifecycle.py
git commit -m "feat: add alpha calculation module with tests"
```

---

## Task 3: 实现成交额占比计算

**Files:**
- Modify: `sector_lifecycle.py`
- Modify: `tests/test_sector_lifecycle.py`

**Step 1: 写测试 - 成交额占比计算**

```python
def test_calculate_amount_share():
    """成交额占比计算"""
    from sector_lifecycle import calculate_amount_share
    sector_amount = 1000
    total_amount = 5000
    result = calculate_amount_share(sector_amount, total_amount)
    assert abs(result - 0.2) < 0.001

def test_calculate_amount_share_ma5():
    """5日均值计算"""
    from sector_lifecycle import calculate_amount_share_ma5
    history = [0.1, 0.15, 0.2, 0.18, 0.2]
    result = calculate_amount_share_ma5(history)
    assert abs(result - 0.166) < 0.01
```

**Step 2: 运行测试，确认失败**

```bash
python -m pytest tests/test_sector_lifecycle.py::test_calculate_amount_share -v
```
Expected: FAIL

**Step 3: 实现成交额占比计算**

```python
# 添加到 sector_lifecycle.py

def calculate_amount_share(sector_amount: float, total_amount: float) -> float:
    """
    计算成交额占比
    
    Args:
        sector_amount: 板块成交额
        total_amount: 全市场成交额
    
    Returns:
        成交额占比 (0-1之间)
    """
    if total_amount == 0:
        return 0
    return sector_amount / total_amount


def calculate_amount_share_ma5(history: list) -> float:
    """
    计算5日平均成交额占比
    
    Args:
        history: 历史成交额占比列表 [0.1, 0.15, ...]
    
    Returns:
        5日均值
    """
    if len(history) < 5:
        return sum(history) / len(history) if history else 0
    return sum(history[-5:]) / 5
```

**Step 4: 运行测试，确认通过**

```bash
python -m pytest tests/test_sector_lifecycle.py::test_calculate_amount -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add sector_lifecycle.py tests/test_sector_lifecycle.py
git commit -m "feat: add amount share calculation with tests"
```

---

## Task 4: 实现位置判断逻辑

**Files:**
- Modify: `sector_lifecycle.py`
- Modify: `tests/test_sector_lifecycle.py`

**Step 1: 写测试 - 位置判断**

```python
def test_determine_position_overheated():
    """过热期判断"""
    from sector_lifecycle import determine_position
    result = determine_position(alpha_20=0.10, amount_share_ma5=0.6)
    assert result['区域'] == '高位区'
    assert result['位置'] == '过热期'

def test_determine_position_strong():
    """强势期判断"""
    from sector_lifecycle import determine_position
    result = determine_position(alpha_20=0.10, amount_share_ma5=0.4)
    assert result['区域'] == '高位区'
    assert result['位置'] == '强势期'

def test_determine_position_active():
    """活跃期判断"""
    from sector_lifecycle import determine_position
    result = determine_position(alpha_20=0.05, amount_share_ma5=0.4)
    assert result['区域'] == '中位区'
    assert result['位置'] == '活跃期'

def test_determine_position_neutral():
    """中性期判断"""
    from sector_lifecycle import determine_position
    result = determine_position(alpha_20=0.0, amount_share_ma5=0.4)
    assert result['区域'] == '中位区'
    assert result['位置'] == '中性期'

def test_determine_position_frozen():
    """冰点期判断"""
    from sector_lifecycle import determine_position
    result = determine_position(alpha_20=-0.05, amount_share_ma5=0.2)
    assert result['区域'] == '低位区'
    assert result['位置'] == '冰点期'
```

**Step 2: 运行测试，确认失败**

```bash
python -m pytest tests/test_sector_lifecycle.py::test_determine_position -v
```
Expected: FAIL

**Step 3: 实现位置判断逻辑**

```python
# 添加到 sector_lifecycle.py

def determine_position(alpha_20: float, amount_share_ma5: float) -> dict:
    """
    判断板块位置
    
    Args:
        alpha_20: 20日Alpha值 (如 0.10 表示 10%)
        amount_share_ma5: 5日平均成交额占比 (如 0.6 表示 60%)
    
    Returns:
        {'区域': '高位区', '位置': '过热期'}
    """
    # 阈值定义 (需要回测调优)
    alpha_high = 0.08   # 8%
    alpha_mid = 0.03    # 3%
    alpha_low = -0.03   # -3%
    
    amount_high = 0.5   # 50%
    amount_low = 0.3    # 30%
    
    # 位置矩阵判断
    if alpha_20 > alpha_high:
        # 高Alpha区域
        if amount_share_ma5 > amount_high:
            return {'区域': '高位区', '位置': '过热期'}
        elif amount_share_ma5 > amount_low:
            return {'区域': '高位区', '位置': '强势期'}
        else:
            return {'区域': '高位区', '位置': '背离期'}
    
    elif alpha_20 > alpha_mid:
        # 中高Alpha区域
        if amount_share_ma5 > amount_high:
            return {'区域': '中位区', '位置': '热门期'}
        elif amount_share_ma5 > amount_low:
            return {'区域': '中位区', '位置': '活跃期'}
        else:
            return {'区域': '高位区', '位置': '背离期'}
    
    elif alpha_20 > alpha_low:
        # 中性区域
        if amount_share_ma5 > amount_high:
            return {'区域': '低位区', '位置': '补涨期'}
        elif amount_share_ma5 > amount_low:
            return {'区域': '中位区', '位置': '中性期'}
        else:
            return {'区域': '中位区', '位置': '磨底期'}
    
    else:
        # 低Alpha区域
        if amount_share_ma5 > amount_high:
            return {'区域': '异常区', '位置': '异常期'}
        elif amount_share_ma5 > amount_low:
            return {'区域': '低位区', '位置': '弱势期'}
        else:
            return {'区域': '低位区', '位置': '冰点期'}
```

**Step 4: 运行测试，确认通过**

```bash
python -m pytest tests/test_sector_lifecycle.py::test_determine_position -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add sector_lifecycle.py tests/test_sector_lifecycle.py
git commit -m "feat: add position determination logic with tests"
```

---

## Task 5: 实现阶段判断逻辑

**Files:**
- Modify: `sector_lifecycle.py`
- Modify: `tests/test_sector_lifecycle.py`

**Step 1: 写测试 - 阶段判断**

```python
def test_determine_stage_recession():
    """衰退期判断"""
    from sector_lifecycle import determine_stage
    result = determine_stage(
        close=3000,
        ma20=3100,
        ma60=3200,
        bias_20=-3.2,
        pct=-2.5,
        amount_share=0.4,
        rs_change_20=0.1
    )
    assert result == '衰退期'

def test_determine_stage_launch():
    """启动期判断"""
    from sector_lifecycle import determine_stage
    result = determine_stage(
        close=3300,
        ma20=3200,
        ma60=3100,
        ma60_slope=0.01,
        bias_20=3.5,
        pct=2.5,
        amount_share=0.65,
        rs_change_20=0.2
    )
    assert result == '启动期'

def test_determine_stage_acceleration():
    """加速期判断"""
    from sector_lifecycle import determine_stage
    result = determine_stage(
        close=3400,
        ma20=3200,
        ma60=3100,
        ma20_slope=0.02,
        bias_20=8.5,
        pct=3.0,
        amount_share=0.5,
        rs_change_20=0.3
    )
    assert result == '加速期'

def test_determine_stage_oscillation():
    """震荡期判断"""
    from sector_lifecycle import determine_stage
    result = determine_stage(
        close=3250,
        ma20=3200,
        ma60=3100,
        ma20_slope=0.1,
        bias_20=3.5,
        pct=0.5,
        amount_share=0.4,
        rs_change_20=0.1
    )
    assert result == '震荡期'

def test_determine_stage_dormant():
    """潜伏期判断"""
    from sector_lifecycle import determine_stage
    result = determine_stage(
        close=3000,
        ma20=3100,
        ma60=3200,
        bias_20=-3.2,
        pct=-0.5,
        amount_share=0.2,
        rs_change_20=-0.1
    )
    assert result == '潜伏期'
```

**Step 2: 运行测试，确认失败**

```bash
python -m pytest tests/test_sector_lifecycle.py::test_determine_stage -v
```
Expected: FAIL

**Step 3: 实现阶段判断逻辑**

```python
# 添加到 sector_lifecycle.py

def determine_stage(
    close: float,
    ma20: float,
    ma60: float,
    bias_20: float,
    pct: float,
    amount_share: float,
    rs_change_20: float,
    ma20_slope: float = 0,
    ma60_slope: float = 0,
    high_20: float = None,
    rs_max_20: float = None,
    amount_share_high_20: float = None
) -> str:
    """
    判断板块阶段
    
    按优先级判断：衰退期 > 背离期 > 加速期 > 启动期 > 震荡期 > 潜伏期 > 兜底
    """
    # 1. 衰退期
    if close < ma20 and ma20 < ma60:
        return '衰退期'
    
    # 2. 背离期(A): 价格创新高但RS走弱
    if high_20 and close >= high_20 * 0.995:
        if rs_max_20 and rs_change_20 < rs_max_20 * 0.7:
            return '背离期A'
    
    # 3. 背离期(B): 成交额占比回落
    if amount_share_high_20 and amount_share_high_20 > 0:
        decline = (amount_share_high_20 - amount_share) / amount_share_high_20
        if decline >= 0.20:
            return '背离期B'
    
    # 4. 加速期
    if bias_20 >= 8 and ma20_slope > 0:
        return '加速期'
    
    # 5. 启动期
    if (close > ma60 and ma60_slope > 0 and pct >= 2 and amount_share >= 0.6):
        return '启动期'
    
    # 6. 震荡期
    if 2 <= bias_20 <= 5 and abs(ma20_slope) <= 0.2:
        return '震荡期'
    
    # 7. 潜伏期
    if close < ma60 and rs_change_20 >= -0.2 and amount_share <= 0.3:
        return '潜伏期'
    
    # 8. 兜底规则
    if close >= ma60:
        return '震荡期'
    else:
        return '潜伏期'
```

**Step 4: 运行测试，确认通过**

```bash
python -m pytest tests/test_sector_lifecycle.py::test_determine_stage -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add sector_lifecycle.py tests/test_sector_lifecycle.py
git commit -m "feat: add stage determination logic with tests"
```

---

## Task 6: 实现组合命名逻辑

**Files:**
- Modify: `sector_lifecycle.py`
- Create: `sector_lifecycle_config.py`
- Modify: `tests/test_sector_lifecycle.py`

**Step 1: 创建配置文件 - 组合命名表**

```python
# sector_lifecycle_config.py

POSITION_STAGE_COMBOS = {
    # 高位区
    ('过热期', '加速期'): {
        '显示名称': '过热·加速赶顶',
        '含义': '情绪极度亢奋，随时见顶',
        '操作建议': '分批止盈'
    },
    ('过热期', '背离期A'): {
        '显示名称': '过热·量价背离',
        '含义': '价格新高但RS走弱，危险',
        '操作建议': '减仓观望'
    },
    ('过热期', '衰退期'): {
        '显示名称': '过热·高位崩塌',
        '含义': '放量大跌，主力出货',
        '操作建议': '果断清仓'
    },
    ('过热期', '震荡期'): {
        '显示名称': '过热·高位震荡',
        '含义': '高位换手，方向不明',
        '操作建议': '轻仓观望'
    },
    ('强势期', '加速期'): {
        '显示名称': '强势·主升加速',
        '含义': '强势上涨，趋势健康',
        '操作建议': '持股待涨'
    },
    ('强势期', '震荡期'): {
        '显示名称': '强势·中继整理',
        '含义': '上涨中继，洗盘换手',
        '操作建议': '持有/低吸'
    },
    ('背离期', '震荡期'): {
        '显示名称': '背离·高位滞涨',
        '含义': '价格高位但资金撤退',
        '操作建议': '逐步减仓'
    },
    ('背离期', '衰退期'): {
        '显示名称': '背离·趋势反转',
        '含义': '资金撤退+价格下跌',
        '操作建议': '清仓离场'
    },
    # 中位区
    ('热门期', '启动期'): {
        '显示名称': '热门·强势启动',
        '含义': '资金关注+启动信号',
        '操作建议': '追涨介入'
    },
    ('活跃期', '启动期'): {
        '显示名称': '活跃·平稳启动',
        '含义': '健康启动，值得参与',
        '操作建议': '建仓布局'
    },
    ('活跃期', '震荡期'): {
        '显示名称': '活跃·箱体震荡',
        '含义': '区间震荡，等待方向',
        '操作建议': '高抛低吸'
    },
    ('中性期', '启动期'): {
        '显示名称': '中性·底部启动',
        '含义': '低位启动，机会较大',
        '操作建议': '积极建仓'
    },
    ('中性期', '潜伏期'): {
        '显示名称': '中性·蓄势待发',
        '含义': '资金潜伏，等待催化',
        '操作建议': '小仓埋伏'
    },
    ('磨底期', '震荡期'): {
        '显示名称': '磨底·筑底阶段',
        '含义': '底部震荡，逐步企稳',
        '操作建议': '分批建仓'
    },
    # 低位区
    ('补涨期', '启动期'): {
        '显示名称': '补涨·滞后启动',
        '含义': '轮动补涨，短线机会',
        '操作建议': '快进快出'
    },
    ('冰点期', '潜伏期'): {
        '显示名称': '冰点·左侧布局',
        '含义': '极度冷门，长线布局',
        '操作建议': '小仓试探'
    },
    # 异常区
    ('异常期', '衰退期'): {
        '显示名称': '异常·爆量下跌',
        '含义': '放量暴跌，恐慌出逃',
        '操作建议': '观望等待'
    },
}

# 默认兜底
DEFAULT_COMBO = {
    '显示名称': '待观察',
    '含义': '信号不明确，需持续监控',
    '操作建议': '观望'
}
```

**Step 2: 写测试 - 组合命名**

```python
def test_get_display_name():
    """组合命名测试"""
    from sector_lifecycle import get_combo_info
    result = get_combo_info('过热期', '加速期')
    assert result['显示名称'] == '过热·加速赶顶'
    assert result['操作建议'] == '分批止盈'

def test_get_display_name_default():
    """未定义组合返回默认值"""
    from sector_lifecycle import get_combo_info
    result = get_combo_info('未知', '未知')
    assert result['显示名称'] == '待观察'
```

**Step 3: 实现组合命名逻辑**

```python
# 添加到 sector_lifecycle.py
from sector_lifecycle_config import POSITION_STAGE_COMBOS, DEFAULT_COMBO

def get_combo_info(position: str, stage: str) -> dict:
    """
    获取位置+阶段组合的展示信息
    
    Args:
        position: 位置名称 (如 '过热期')
        stage: 阶段名称 (如 '加速期')
    
    Returns:
        {'显示名称': '...', '含义': '...', '操作建议': '...'}
    """
    key = (position, stage)
    return POSITION_STAGE_COMBOS.get(key, DEFAULT_COMBO)
```

**Step 4: 运行测试**

```bash
python -m pytest tests/test_sector_lifecycle.py::test_get_display -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add sector_lifecycle.py sector_lifecycle_config.py tests/test_sector_lifecycle.py
git commit -m "feat: add position-stage combo naming logic"
```

---

## Task 7: 整合主分析函数

**Files:**
- Modify: `sector_lifecycle.py`
- Modify: `tests/test_sector_lifecycle.py`

**Step 1: 写测试 - 完整分析**

```python
def test_analyze_sector_full():
    """完整板块分析测试"""
    from sector_lifecycle import analyze_sector
    import pandas as pd
    
    # 模拟数据
    sector_data = pd.DataFrame({
        'date': pd.date_range('2026-01-01', periods=60, freq='D'),
        'close': [3000 + i*5 for i in range(60)],
        'amount': [1000 + i*10 for i in range(60)]
    })
    
    market_data = pd.DataFrame({
        'date': pd.date_range('2026-01-01', periods=60, freq='D'),
        'close': [3000 + i*3 for i in range(60)]
    })
    
    result = analyze_sector(sector_data, market_data, '半导体')
    
    assert '板块名称' in result
    assert '位置区域' in result
    assert '阶段信号' in result
    assert '显示名称' in result
    assert '操作建议' in result
```

**Step 2: 实现主分析函数**

```python
# 添加到 sector_lifecycle.py
import pandas as pd

def analyze_sector(sector_df: pd.DataFrame, market_df: pd.DataFrame, sector_name: str) -> dict:
    """
    完整板块生命周期分析
    
    Args:
        sector_df: 板块数据 DataFrame (columns: date, close, amount)
        market_df: 大盘数据 DataFrame (columns: date, close)
        sector_name: 板块名称
    
    Returns:
        完整分析结果字典
    """
    # 1. 计算 Alpha
    alpha_5 = calculate_alpha_n_days(
        list(zip(sector_df['date'], sector_df['close'])),
        list(zip(market_df['date'], market_df['close'])),
        days=5
    )
    alpha_20 = calculate_alpha_n_days(
        list(zip(sector_df['date'], sector_df['close'])),
        list(zip(market_df['date'], market_df['close'])),
        days=20
    )
    
    # 2. 计算成交额占比 (这里简化，实际需要全市场数据)
    amount_share = sector_df['amount'].iloc[-1] / 10000  # 假设全市场10000
    amount_share_history = (sector_df['amount'] / 10000).tolist()
    amount_share_ma5 = calculate_amount_share_ma5(amount_share_history)
    
    # 3. 计算 MA
    ma20 = sector_df['close'].rolling(20).mean().iloc[-1]
    ma60 = sector_df['close'].rolling(60).mean().iloc[-1]
    
    # 4. 计算 Bias
    close = sector_df['close'].iloc[-1]
    bias_20 = (close - ma20) / ma20 * 100 if ma20 else 0
    
    # 5. 计算 MA 斜率
    ma20_series = sector_df['close'].rolling(20).mean()
    ma20_slope = (ma20_series.iloc[-1] - ma20_series.iloc[-5]) / 5 if len(ma20_series) >= 5 else 0
    
    ma60_series = sector_df['close'].rolling(60).mean()
    ma60_slope = (ma60_series.iloc[-1] - ma60_series.iloc[-5]) / 5 if len(ma60_series) >= 5 else 0
    
    # 6. 判断位置
    position_info = determine_position(alpha_20 or 0, amount_share_ma5)
    
    # 7. 判断阶段
    stage = determine_stage(
        close=close,
        ma20=ma20,
        ma60=ma60,
        bias_20=bias_20,
        pct=sector_df['close'].pct_change().iloc[-1] * 100 if len(sector_df) > 1 else 0,
        amount_share=amount_share,
        rs_change_20=alpha_20 or 0,  # 简化处理
        ma20_slope=ma20_slope,
        ma60_slope=ma60_slope,
        high_20=sector_df['close'].rolling(20).max().iloc[-1],
        rs_max_20=max(alpha_20 or 0, 0.1),  # 简化处理
        amount_share_high_20=max(amount_share_history[-20:]) if amount_share_history else amount_share
    )
    
    # 8. 获取组合信息
    combo_info = get_combo_info(position_info['位置'], stage)
    
    # 9. 返回完整结果
    return {
        '板块名称': sector_name,
        '位置区域': position_info['区域'],
        '位置名称': position_info['位置'],
        '阶段信号': stage,
        '显示名称': combo_info['显示名称'],
        '含义': combo_info['含义'],
        '操作建议': combo_info['操作建议'],
        '指标数据': {
            'alpha_5': round(alpha_5 * 100, 2) if alpha_5 else None,
            'alpha_20': round(alpha_20 * 100, 2) if alpha_20 else None,
            'amount_share': round(amount_share * 100, 2),
            'amount_share_ma5': round(amount_share_ma5 * 100, 2),
            'ma20': round(ma20, 2),
            'ma60': round(ma60, 2),
            'bias_20': round(bias_20, 2),
            'close': round(close, 2),
            'pct': round(sector_df['close'].pct_change().iloc[-1] * 100, 2) if len(sector_df) > 1 else 0
        }
    }
```

**Step 3: 运行测试**

```bash
python -m pytest tests/test_sector_lifecycle.py::test_analyze_sector -v
```
Expected: PASS

**Step 4: Commit**

```bash
git add sector_lifecycle.py tests/test_sector_lifecycle.py
git commit -m "feat: add main analyze_sector function"
```

---

## Task 8: 集成到现有服务

**Files:**
- Modify: `server.js`
- Modify: `fetch_sector_data.py`

**Step 1: 在 fetch_sector_data.py 添加导出函数**

```python
# 在 fetch_sector_data.py 末尾添加

def export_lifecycle_analysis():
    """导出所有板块的生命周期分析"""
    from sector_lifecycle import analyze_sector
    import pandas as pd
    
    # 获取所有板块数据
    sectors = ['bank', 'broker', 'insure', 'gem', 'star', 'hs300', 'csi2000']
    results = []
    
    for sector in sectors:
        # 读取板块数据
        sector_df = load_sector_data(sector)  # 需要实现
        market_df = load_market_data()  # 需要实现
        
        result = analyze_sector(sector_df, market_df, sector)
        results.append(result)
    
    return results
```

**Step 2: 在 server.js 添加 API 端点**

```javascript
// 在 server.js 添加

app.get('/api/sector-lifecycle', async (req, res) => {
  try {
    const result = await runPythonFile('fetch_sector_data.py', ['export_lifecycle_analysis']);
    res.json(JSON.parse(result));
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});
```

**Step 3: 测试 API**

```bash
curl http://localhost:8787/api/sector-lifecycle
```
Expected: JSON 数组，包含所有板块分析结果

**Step 4: Commit**

```bash
git add server.js fetch_sector_data.py
git commit -m "feat: integrate lifecycle analysis into API"
```

---

## Task 9: 前端展示组件

**Files:**
- Modify: `public/index.html`

**Step 1: 添加板块生命周期表格**

```html
<!-- 在 public/index.html 添加 -->
<div id="sector-lifecycle" class="section">
  <h2>板块生命周期</h2>
  <table id="lifecycle-table">
    <thead>
      <tr>
        <th>板块</th>
        <th>位置</th>
        <th>阶段</th>
        <th>状态</th>
        <th>含义</th>
        <th>操作建议</th>
      </tr>
    </thead>
    <tbody id="lifecycle-body">
      <!-- 动态填充 -->
    </tbody>
  </table>
</div>

<script>
async function loadLifecycle() {
  const res = await fetch('/api/sector-lifecycle');
  const data = await res.json();
  
  const tbody = document.getElementById('lifecycle-body');
  tbody.innerHTML = data.map(s => `
    <tr class="position-${s.位置区域}">
      <td>${s.板块名称}</td>
      <td>${s.位置区域} · ${s.位置名称}</td>
      <td>${s.阶段信号}</td>
      <td><strong>${s.显示名称}</strong></td>
      <td>${s.含义}</td>
      <td>${s.操作建议}</td>
    </tr>
  `).join('');
}

// 页面加载时执行
loadLifecycle();
setInterval(loadLifecycle, 60000); // 每分钟刷新
</script>
```

**Step 2: 添加样式**

```css
/* 添加到 public/style.css */
.position-高位区 { background-color: #ffe0e0; }
.position-中位区 { background-color: #e0ffe0; }
.position-低位区 { background-color: #e0e0ff; }
.position-异常区 { background-color: #ffffe0; }
```

**Step 3: 测试页面**

打开浏览器访问 http://localhost:8787，确认表格正常显示

**Step 4: Commit**

```bash
git add public/index.html public/style.css
git commit -m "feat: add sector lifecycle display component"
```

---

## Task 10: 阈值调优脚本

**Files:**
- Create: `scripts/tune_thresholds.py`

**Step 1: 创建调优脚本**

```python
# scripts/tune_thresholds.py

import pandas as pd
import json
from sector_lifecycle import analyze_sector

def backtest_thresholds(data_path, alpha_thresholds, amount_thresholds):
    """
    回测不同阈值组合的预测准确率
    
    Args:
        data_path: 历史数据路径
        alpha_thresholds: Alpha阈值列表 [(0.05, 0.03), (0.08, 0.05), ...]
        amount_thresholds: 成交额阈值列表 [(0.4, 0.2), (0.5, 0.3), ...]
    
    Returns:
        各阈值组合的准确率
    """
    results = []
    
    for alpha_high, alpha_mid in alpha_thresholds:
        for amount_high, amount_low in amount_thresholds:
            # 运行回测
            accuracy = run_backtest(data_path, alpha_high, alpha_mid, amount_high, amount_low)
            results.append({
                'alpha_high': alpha_high,
                'alpha_mid': alpha_mid,
                'amount_high': amount_high,
                'amount_low': amount_low,
                'accuracy': accuracy
            })
    
    # 按准确率排序
    results.sort(key=lambda x: x['accuracy'], reverse=True)
    return results

def run_backtest(data_path, alpha_high, alpha_mid, amount_high, amount_low):
    """
    执行单次回测
    
    返回预测准确率
    """
    # TODO: 实现回测逻辑
    # 1. 遍历历史数据
    # 2. 对每个时间点判断位置和阶段
    # 3. 统计后续5日涨跌情况
    # 4. 计算准确率
    return 0.75  # 示例值

if __name__ == '__main__':
    # 测试不同阈值组合
    alpha_thresholds = [(0.06, 0.02), (0.08, 0.03), (0.10, 0.05)]
    amount_thresholds = [(0.4, 0.2), (0.5, 0.3), (0.6, 0.4)]
    
    results = backtest_thresholds('data/', alpha_thresholds, amount_thresholds)
    print(json.dumps(results, indent=2, ensure_ascii=False))
```

**Step 2: Commit**

```bash
git add scripts/tune_thresholds.py
git commit -m "feat: add threshold tuning script"
```

---

## 验收标准汇总

| 任务 | 验收标准 |
|------|----------|
| T1 | API schema 文档创建完成 |
| T2 | Alpha 计算测试通过 |
| T3 | 成交额占比计算测试通过 |
| T4 | 9个位置判断测试通过 |
| T5 | 8个阶段判断测试通过 |
| T6 | 组合命名测试通过 |
| T7 | 完整分析函数测试通过 |
| T8 | API 端点返回正确 JSON |
| T9 | 前端页面正常展示表格 |
| T10 | 调优脚本可运行 |

---

## 执行说明

**本计划应使用 superpowers:executing-plans 或 superpowers:subagent-driven-development 执行。**

**推荐执行方式：**
- 在 Trae IDE 中打开项目 `/Users/una5577/Documents/trae_projects/a-stock-monitor`
- 按 Task 顺序逐个执行
- 每个 Task 完成后运行测试确认
- 频繁 commit

**预计工作量：** 约 2-3 小时（取决于数据准备情况）
