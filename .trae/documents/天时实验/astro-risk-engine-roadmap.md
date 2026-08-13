# 天时实验：风险预测模块详细实施路线图

## 目录空 — 需先同步数据

`online_debug_data/` 当前为空。需要从服务器拉取截止 7月29日的数据：

```bash
rsync -avz stock-server:/opt/a-stock-monitor/data/index/daily/ ./data/index/daily/
rsync -avz stock-server:/opt/a-stock-monitor/data/etf/daily/ ./data/etf/daily/
```

> 建议做成一个 `treasolo/m1_sync_data.sh` 脚本，一键同步，后续定期跑。

---

## 模块边界划分

```
┌─────────────────────────────────────────────────────────────────┐
│                        天时实验 模块架构                           │
├───────────┬───────────┬───────────┬───────────┬─────────────────┤
│  回测引擎  │  取象验证  │  风险引擎  │  校准闭环  │  展示 & 查询     │
│ (已有基础) │  (已有)   │  (新建)   │  (新建)   │  (增量改造)      │
├───────────┼───────────┼───────────┼───────────┼─────────────────┤
│ 输入:      │ 输入:     │ 输入:     │ 输入:     │ 输入:            │
│ 指数/ETF   │ 日线+干支 │ 规则表+    │ 预测JSON+ │ 风险等级+        │
│ 日线+天时  │ 回测引擎  │ 当日天时+ │ 实际数据   │ 取象数据         │
│ 日历       │ 输出      │ 外源日历   │           │                  │
│            │           │           │           │                  │
│ 输出:      │ 输出:     │ 输出:     │ 输出:     │ 输出:            │
│ stats JSON │ 取象修订   │ 风险等级   │ 权重调整   │ 前端面板         │
│            │ 建议      │ (0~5星)   │ 建议       │                  │
└───────────┴───────────┴───────────┴───────────┴─────────────────┘
```

每个模块的**输入/输出都是文件**，互相解耦，不依赖对方的内存状态。

---

## 阶段一：数据到位 + 大盘回测（本周）

### 1.1 数据同步脚本

**新建** `treasolo/m1_sync_data.sh`

```bash
#!/bin/bash
# 从服务器同步日线数据到本地
rsync -avz stock-server:/opt/a-stock-monitor/data/index/daily/ ./data/index/daily/
rsync -avz stock-server:/opt/a-stock-monitor/data/etf/daily/ ./data/etf/daily/
echo "Synced at $(date)"
```

### 1.2 大盘回测 V4（指数级别）

**修改** `treasolo/m1_astro_full_report.py` → 新增板块：

| 新增内容 | 说 明 |
|----------|------|
| 扩展到 2026-07-29 | 目前到 6/15，同步后覆盖到 7/29 |
| 新增"逐月分指数详细表" | 每个月 4 指数分别的涨跌，附月干支+五行 |
| 新增"指数级别总结" | 区间内"哪个干支日对哪个指数最危险"Top10 |

### 1.3 板块/ETF 回测 V4（ETF 级别）

**修改** `treasolo/m1_astro_signal_synthesizer.py` → 增强：

| 新增内容 | 说 明 |
|----------|------|
| 扩展到 2026-07-29 | 同上 |
| 取象最终确认 | 按用户已修订的取象（通信=水火/半导体=火土/游戏=水） |
| 输出两个维度 | （1）每只 ETF 在各天干下的涨跌 （2）每个板块（科技/资源）的聚合取向 |

---

## 阶段二：风险规则引擎（下周）

### 2.1 单因子规则表

**新建** `八字/risk_rules.json`

这是"已从回测中验证的显著规律"的编码。风控引擎不跑回测，只是读取这张表做当日匹配。

```json
{
  "rules": [
    {
      "id": "R01",
      "name": "农历十五满月日",
      "condition": {"lunarDay": "十五"},
      "action": "risk_up",
      "severity": 3,
      "evidence": "2026年3/3个交易日全跌，科创平均-3.9%",
      "scope": ["sh000688", "sz399006"]
    },
    {
      "id": "R02",
      "name": "丙午日",
      "condition": {"sixtyCycleDay": "丙午"},
      "action": "risk_up",
      "severity": 4,
      "evidence": "2026年2/2个交易日全跌，科创平均-3.76%",
      "scope": ["*"]
    },
    {
      "id": "R03",
      "name": "壬水日新月",
      "condition": {"phaseIndex": 0, "tianGan": "壬"},
      "action": "block_rebound",
      "severity": 3,
      "evidence": "0/3反弹，丁亥月连续三天新全跌",
      "scope": ["*"]
    },
    {
      "id": "R04",
      "name": "乙巳日（年柱日）",
      "condition": {"sixtyCycleDay": "乙巳"},
      "action": "risk_down",
      "severity": -2,
      "evidence": "2026年唯一交易日全涨，科创+3.33%",
      "scope": ["*"]
    },
    {
      "id": "R05",
      "name": "满月+乙木日",
      "condition": {"phaseIndex": 4, "tianGan": "乙"},
      "action": "risk_up",
      "severity": 5,
      "evidence": "满月乙木日后3天100%下跌",
      "scope": ["*"]
    }
  ]
}
```

### 2.2 风险规则引擎

**新建** `treasolo/m1_risk_engine.py`

```python
# 输入: 日期
# 输出: 风险等级(0~5) + 命中规则列表 + 影响范围

def assess_risk(day: str) -> dict:
    # 1. 查询当日天时（干支/月相/农历）
    # 2. 逐一匹配 risk_rules.json 中的条件
    # 3. 汇总命中规则的 severity 取最大值
    # 4. 输出: {"level": 4, "rules": ["R02","R01"], "detail": "..."}
```

### 2.3 多因子叠加模型

```
当日风险 = max(R01, R02, R03...) + bonus(多因子同时命中加1级)

加上外源日历叠加:
  - 股指期货交割日: +1
  - 美联储议息日: +1 (需要手动维护一个 fomc_dates.json)
  - A股财报密集期(每年4月/8月/10月底): +1
  - 美股VIX>30的日子: +1
```

**新建** `八字/external_events.json`

```json
{
  "fomc_2026": ["2026-01-29", "2026-03-19", "2026-05-07", "2026-06-18", "2026-07-30"],
  "futures_delivery_2026": ["2026-01-16", "2026-02-20", ...],
  "earnings_season": ["2026-04", "2026-08", "2026-10"]
}
```

### 2.4 输出到前端

**新建 API 路由** `GET /api/m1/data/astro/risk?day=2026-07-29`（在 `server/api/astro.js`）

返回：
```json
{
  "day": "2026-07-29",
  "riskLevel": 4,
  "riskLabel": "高风险",
  "triggeredRules": [
    {"id": "R02", "name": "丙午日", "severity": 4}
  ],
  "stackedFactors": [
    {"factor": "股指期货交割日", "bonus": 1}
  ],
  "affectedScope": ["科创50", "创业板指"]
}
```

---

## 阶段三：信号合成器→预测管线

### 3.1 补 astro_predict API

**修改** `server/api/astro.js` → 新增路由：

```
GET /api/m1/data/astro_predict?day=2026-07-29
```

内部调用 `m1_astro_signal_synthesizer.py --day 2026-07-29 --mode predict`

返回每个 ETF 的合成信号（>0看多, <0看空）+ 星级。

### 3.2 补 astro_review API

```
GET /api/m1/data/astro_review?day=2026-07-28
```

对比昨天的预测 vs 实际，记录命中/失误。

---

## 阶段四：校准闭环

### 4.1 每日盘后校准脚本

**新建** `treasolo/m1_daily_calibrate.py`

流程：
```
1. 读昨天的 astro_predict 预测
2. 读昨天实际的指数/ETF 涨跌
3. 对比：预测对了多少、错了多少
4. 调用 AI (/api/ai/chat) 用 八字/prompts.json 的 calibration 模板做分析
5. 如果某条规则连续错 N 天 → 降权或停用
```

### 4.2 规则权重自动优化

在 `risk_rules.json` 里每条规则加 `weight` 字段：
- 初始权重 = severity
- 每次校准：命中且方向正确 → weight +0.1；方向错误 → weight -0.5
- weight < 1 的规则自动暂停（不触发）

---

## 阶段五：前端展示

### 5.1 特殊日查询工具

在 `pages/astro/index.html` 底部新增一个「干支日查询」面板：
- 输入牛日干支（如"丙午"）或农历日（如"十五"）
- 显示该日历史上所有出现的日期 + 4指数涨跌
- 替换现在每次手写临时脚本的方式

### 5.2 风险仪表盘

在页面顶部新增「今日风险」横条：
- 显示 `GET /api/m1/data/astro/risk` 返回的风险等级（绿/黄/红）
- 列出命中的规则（"今日农历十五 + 丙午日 → 高风险"）
- 标注被影响的 ETF

---

## 文件改动汇总

| 文件 | 动作 | 阶段 |
|------|------|------|
| `treasolo/m1_sync_data.sh` | **新建** | 1 |
| `treasolo/m1_astro_full_report.py` | 修改（扩到7/29） | 1 |
| `treasolo/m1_astro_signal_synthesizer.py` | 修改（扩到7/29） | 1 |
| `八字/risk_rules.json` | **新建** | 2 |
| `八字/external_events.json` | **新建** | 2 |
| `treasolo/m1_risk_engine.py` | **新建** | 2 |
| `server/api/astro.js` | 修改（+risk +predict +review路由） | 2,3 |
| `treasolo/m1_daily_calibrate.py` | **新建** | 4 |
| `pages/astro/index.html` | 修改（+风险仪表盘 +干支查询） | 5 |
| `pages/astro/ui.js` | 修改（+面板逻辑） | 5 |
| 已有6个回测脚本 | **不改** | — |

---

## 验证步骤

1. `bash treasolo/m1_sync_data.sh` → 确认数据到 7/29
2. `python3 treasolo/m1_astro_full_report.py` → 确认扩展到 7/29
3. `python3 treasolo/m1_risk_engine.py --day 2026-07-29` → 输出风险等级
4. `curl http://localhost:8787/api/m1/data/astro/risk?day=2026-07-29` → 200
5. `curl http://localhost:8787/api/m1/data/astro_predict?day=2026-07-29` → 200
6. 8784 前端 → 风险仪表盘可见 + 干支查询工具可用
