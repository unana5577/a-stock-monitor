# 天时风险预测 — 微任务拆解 + 逐步验证方案

## 核心原则

1. **天时数据只拉一次，落盘缓存** — 干支/月相/农历 对过去日期是确定性的，不需要反复算
2. **每个子任务独立可验证** — 输入源文件明确，输出文件明确，验证命令明确
3. **对账式开发** — 每做完一个子任务，你跑一条命令就能看到结果对不对

---

## 数据的三个层（各自独立落盘）

```
data/astro/                     ← 天时缓存(一次性生成，不改)
  ├── astro_calendar_2025_2026.jsonl   ← 每天一行的干支+月相+农历
  └── astro_calendar_weekly.json       ← 每周汇总

data/index/daily/               ← 指数日线(rsync 从服务器)
data/etf/daily/                 ← ETF日线(rsync 从服务器)

data/astro/                     ← 天时缓存(一次性生成，不改)
  ├── astro_calendar_2025_2026.jsonl   ← 每天一行的干支+月相+农历
  └── astro_calendar_weekly.json       ← 每周汇总

data/astro/backtest/            ← 回测输出(脚本产出的中间结果)
data/astro/risk/                ← 风险引擎输出
data/astro/calibration/         ← 校准报告
data/astro/predict/             ← 预测输出

八字/                           ← 配置 & 取象 & 规则
  ├── prompts.json              ← AI Prompt 模板
  ├── risk_rules.json           ← 风险规则表
  ├── external_events.json      ← 外源事件日历
  ├── etf_wuxing.json           ← ETF五行取象(★新增: 单一真相源)
  └── etf_registry.json         ← ETF注册表(★新增: 脚本自动发现生成)
```

---

## ETF 动态发现 & 取象管理

### 不再硬编码 ETF 列表

当前每个脚本都写死了 `ETF_SYMBOLS = ["sh512480", ...]`。改为：

**新建脚本** `treasolo/m1_etf_discover.py`（每个回测脚本启动时调一次）：

```python
# 扫描 data/etf/daily/ 目录，自动发现所有有日线数据的ETF
# 输出: 八字/etf_registry.json

{
  "discoveredAt": "2026-07-29T18:00:00",
  "etfs": [
    {"sym": "sh512480", "name": "半导体ETF", "dataFrom": "2024-01-02", "dataTo": "2026-07-29", "records": 621},
    {"sym": "sh515880", "name": "通信ETF", ...},
    ...
  ]
}
```

**新建文件** `八字/etf_wuxing.json`（手工维护，取象的单一真相源）：

```json
{
  "sh512480": {"name": "半导体ETF", "wuxing": ["火", "土"], "confirmed": true},
  "sh515880": {"name": "通信ETF", "wuxing": ["水", "火"], "confirmed": true},
  "sh516510": {"name": "云计算ETF", "wuxing": ["水"], "confirmed": true},
  "sh516010": {"name": "游戏ETF", "wuxing": ["水"], "confirmed": true},
  "sh563530": {"name": "商业航天ETF", "wuxing": ["火", "金"], "confirmed": true},
  "sh562500": {"name": "机器人ETF", "wuxing": ["金"], "confirmed": false},
  "sh515120": {"name": "创新药ETF", "wuxing": ["木"], "confirmed": false},
  "sh516160": {"name": "新能源ETF", "wuxing": ["火"], "confirmed": true},
  "sh512400": {"name": "有色金属ETF", "wuxing": ["土"], "confirmed": false}
}
```

### 新增 ETF 后的接入流程

```
1. 服务器上 ETF 日线开始落盘到 data/etf/daily/<新sym>/daily.jsonl
2. rsync 同步到本地
3. 跑 python3 treasolo/m1_etf_discover.py → etf_registry.json 自动更新
4. 在 八字/etf_wuxing.json 手工添加新ETF的五行取象(confirmed: false)
5. 跑回测 → 数据驱动建议取象 → 确认后 confirmed: true
6. 回测脚本重新跑 → 自动 include 新 ETF
```

> **所有回测/信号/风险脚本都从 `etf_registry.json` + `etf_wuxing.json` 读取 ETF 列表和取象，不再硬编码。**

---

## 风险分级体系

不再是"风险等级 0-5"一个数字，而是**按市场和严重程度双向分级**：

### 维度一：影响范围

| 范围代码 | 含义 | 判断标准 |
|----------|------|----------|
| `ALL` | 全市场风险 | 4指数中至少3个触发 |
| `KC` | 科创板风险 | 仅科创50触发 |
| `CY` | 创业板风险 | 仅创业板触发 |
| `SZ` | 深市风险 | 深证成指触发 |
| `SH` | 沪市风险 | 仅上证触发 |

### 维度二：严重程度

| 等级 | 标签 | 含义 | 判断标准 |
|------|------|------|----------|
| L1 | ⚠️ 注意 | 历史回测该条件下跌概率 >60% | 单因子命中 |
| L2 | 🔶 谨慎 | 历史回测下跌概率 >75% 或平均跌幅>1% | 单因子强信号 |
| L3 | 🔴 危险 | 多因子叠加(≥2条) 或 历史样本中曾出现>3%跌幅 | 2因子叠加 |
| L4 | 💀 高危 | 多因子叠加(≥3条) 且 历史曾出现>5%跌幅 | 3因子叠加 |
| L5 | 🌑 黑天鹅 | 低概率但极端后果的事件窗口 | 特殊标注 |

### 每日风险输出格式

不再是单一数字，而是结构化 JSON：

```json
{
  "day": "2026-04-02",
  "risks": [
    {
      "scope": "ALL",
      "level": "L4",
      "label": "高危",
      "triggeredRules": ["R01", "R02", "R06"],
      "detail": "农历十五 + 丙午日 + 满月窗口叠加 → 2026年历史3/3次全市场下跌, 科创最大跌幅-5.21%",
      "affectedEtfs": ["sh512480", "sh515880", "sh563530"]
    },
    {
      "scope": "KC",
      "level": "L4",
      "label": "高危",
      "triggeredRules": ["R01", "R02"],
      "detail": "科创50在农历十五+丙午日下 历史2/2次下跌, 平均-3.76%"
    }
  ],
  "summary": "全市场高危 + 科创高危, 建议降低科技类ETF仓位"
}
```

### 黑天鹅事件单独处理

`八字/external_events.json` 中新增 `black_swan` 分类：

```json
{
  "black_swan": [
    {"date": "2025-09-04", "label": "盈凸月+丙子日 科创-6.09%", "type": "天体极端"},
    {"date": "2026-03-24", "label": "娥眉月+丁酉日 上证-6.00%", "type": "天体极端"}
  ]
}
```

> 黑天鹅不参与日常规则匹配，但会在日历上标注，用于"这一天历史上发生过极端事件"的提醒。

---

## 微任务清单（12个子任务，7个可独立验证）

### 子任务 A：数据同步 + 天时缓存（一次性）

---

#### A1. 从服务器同步日线数据

| 项 | 内容 |
|----|------|
| **命令** | `rsync -avz stock-server:/opt/.../data/index/daily/ ./data/index/daily/` |
| **验证** | `python3 -c "print(max(open('data/index/daily/sh000001/daily.jsonl').readlines()[-1]))"` → 应显示 2026-07-29 |
| **责任人** | 你跑 rsync，我验证 |

---

#### A2. 生成天时缓存文件

| 项 | 内容 |
|----|------|
| **新建脚本** | `treasolo/m1_astro_cache_gen.py` |
| **输入** | 无（纯计算） |
| **输出** | `data/astro/astro_calendar_2025_2026.jsonl`（每天一行） |
| **格式** | `{"date":"2025-05-01","gzDay":"甲子","tg":"甲","tgWx":"木","dz":"子","dzWx":"水","gzMonth":"辛巳","lunarMonth":"四月","lunarDay":"初四","phaseIdx":4,"phaseName":"满月","waxing":"亏"}` |
| **验证** | `head -3 data/astro/astro_calendar_2025_2026.jsonl` → 肉眼确认 2025-05-01 的干支对不对 |
| **意义** | 之后所有回测/风险/预测脚本**只读这个缓存文件**，不再调 tyme4py。省时间 + 保证一致性 |

---

#### A3. 建 weekly 汇总缓存

| 项 | 内容 |
|----|------|
| **新建脚本** | `treasolo/m1_astro_cache_weekly.py`（或合并在 A2 里） |
| **输出** | `data/astro/astro_calendar_weekly.json` |
| **内容** | 每周一 ~ 周日 的日期范围 + 该周的月相变化 + 月干支 |
| **验证** | `python3 -c "import json; print(json.load(open('data/astro/astro_calendar_weekly.json'))[0])"` → 第一周的汇总 |

---

### 子任务 B：大盘回测（指数级别）

---

#### B1. 单日：给定日期 → 4指数涨跌

| 项 | 内容 |
|----|------|
| **新建脚本** | `八字/查指定日.py` |
| **输入** | 日期参数 `--day 2026-07-29` |
| **输出** | 该日 4指数涨跌 + 干支 + 月相 + 农历 |
| **验证** | `python3 八字/查指定日.py --day 2026-04-02` → 应输出 上证-0.74% 深证-1.60% 创业-2.31% 科创-2.77%（之前验证过） |

> **这个脚本就是之前我们手写的临时的正式版，以后不再手写一次性脚本。**

---

#### B2. 月相节点 × 4指数统计

| 项 | 内容 |
|----|------|
| **修改脚本** | `treasolo/m1_astro_full_report.py` 的 Section 1-2 — 改成读 A2 缓存文件而非实时计算 |
| **输入** | `data/astro/astro_calendar_2025_2026.jsonl` + `data/index/daily/*/daily.jsonl` |
| **输出** | stdout 文本 + `data/astro/backtest/phase_index.json` |
| **验证** | 看 Section 1 的"新月窗口汇总" → 反弹比例是否和上一次一致 |

---

#### B3. 干支 × 4指数统计

| 项 | 内容 |
|----|------|
| **修改脚本** | `treasolo/m1_astro_full_report.py` 中 日干×指数 的统计部分 — 同样读缓存 |
| **输出** | stdout + `data/astro/backtest/ganzhi_index.json` |
| **验证** | 看"丙午日对应上证/深证/创业/科创的涨跌"是否和我们手动查的一致 |

---

### 子任务 C：板块/ETF 回测（ETF 级别）

---

#### C1. 天干 × 每只ETF 响应矩阵

| 项 | 内容 |
|----|------|
| **修改脚本** | `treasolo/m1_astro_signal_synthesizer.py` 的 Section 1 — 读缓存 |
| **输入** | `data/astro/astro_calendar_2025_2026.jsonl` + `data/etf/daily/*/daily.jsonl` |
| **输出** | `data/astro/backtest/etf_stem_response.json` |
| **格式** | `{"sh512480": {"甲": {"avgPct": 0.19, "winRate": 0.50, "n": 24}, ...}, ...}` |
| **验证** | `python3 -c "import json; d=json.load(open('data/astro/backtest/etf_stem_response.json')); print(d['sh515880']['癸'])"` → 应输出通信ETF在癸水日的 avgPct≈+1.16%（之前验证过） |

**对账点**: 这个 JSON 你拿去看，每只 ETF 在每个天干下表现如何，一目了然。不对就能定位到具体数据。

---

#### C2. 月干×日干 交互响应矩阵

| 项 | 内容 |
|----|------|
| **输出** | `data/astro/backtest/etf_month_stem_interaction.json` |
| **格式** | `{"sh512480": {"甲甲": {"avgPct": ..., "n": ...}, "甲乙": ..., ...}}` |
| **验证** | 查"月癸×日丁(半导体)" → 应 ≈ +6.88%（之前信号合成器的显著交互） |

**对账点**: 如果某个交互得分不对，说明那组数据的原始日线或干支对应有问题。

---

### 子任务 D：风险规则引擎

---

#### D1. 风险规则表

| 项 | 内容 |
|----|------|
| **新建文件** | `八字/risk_rules.json` |
| **每条规则格式** | `{"id":"R01","condition":{...},"severity":4,"evidence":"...","backtest":{"hitRate":"3/3","samples":3}}` |
| **验证** | 打开这个 JSON，检查每条规则的 evidence 是否和我们手动验证的一致 |

---

#### D2. 规则引擎

| 项 | 内容 |
|----|------|
| **新建脚本** | `treasolo/m1_risk_engine.py` |
| **输入** | `--day 2026-07-29` + 读 A2缓存 + 读 D1规则表 + 读 外源事件表 |
| **输出** | stdout + `data/astro/risk/risk_2026-07-29.json` |
| **验证** | `python3 treasolo/m1_risk_engine.py --day 2026-04-02` → 应命中 R01(农历十五) + R02(丙午) 两条规则，风险等级 ≥ 4 |

**对账点**: 选一个我们知道答案的日期（如4/2 = 农历十五 + 丙午），看引擎输出了我们预期的规则。

---

#### D3. 外源事件表

| 项 | 内容 |
|----|------|
| **新建文件** | `八字/external_events.json` |
| **内容** | 2025-2026年 股指期货交割日 / 美联储FOMC日期 |
| **验证** | 挑一个已知的FOMC日期（2026-01-29），确认在表里 |

---

### 子任务 E：预测 + 校准管线

---

#### E1. 补 astro_predict API

| 项 | 内容 |
|----|------|
| **修改文件** | `server/api/astro.js` → 加 `GET /api/m1/data/astro_predict?day=` |
| **内部调用** | `m1_astro_signal_synthesizer.py --day X --mode single` |
| **输出格式** | `[{sym, name, signal, stars, bias}]` |
| **验证** | `curl http://localhost:8787/api/m1/data/astro_predict?day=2026-06-12` → 应返回 新能源★★★、有色★★ 等（之前信号合成器输出过） |

---

#### E2. 补 astro_review API

| 项 | 内容 |
|----|------|
| **修改文件** | `server/api/astro.js` → 加 `GET /api/m1/data/astro_review?day=` |
| **输出** | 该日预测信号 vs 实际涨跌 对比 |
| **验证** | `curl http://localhost:8787/api/m1/data/astro_review?day=2026-06-12` → 每一项都标 ✓/✗ |

---

#### E3. 每日校准脚本

| 项 | 内容 |
|----|------|
| **新建脚本** | `treasolo/m1_daily_calibrate.py` |
| **输入** | 昨天的 predict JSON + 昨天的实际涨跌 |
| **输出** | `data/astro/calibration/calibrate_2026-07-29.json` |
| **动作** | 对比 → 更新 risk_rules.json 中每条规则的 live 字段 → 降权/升权 |
| **验证** | 跑一次看校准报告: `python3 treasolo/m1_daily_calibrate.py --day 2026-06-12` |

---

### 子任务 F：前端展示

---

#### F1. 风险仪表盘

| 项 | 内容 |
|----|------|
| **修改文件** | `pages/astro/index.html` → 顶部加横条 |
| **数据源** | `GET /api/m1/data/astro/risk` |
| **展示** | 风险等级（绿/黄/红）+ 命中规则列表 |

---

#### F2. 干支日查询工具

| 项 | 内容 |
|----|------|
| **修改文件** | `pages/astro/index.html` → 底部加面板 |
| **功能** | 输入干支（如"丙午"）→ 列出历史上每次该日的情况 |
| **对等替换** | 之前手写 `查丙午日.py` 的逻辑，做成前端表单 |

---

## 验证对账总表（你每步可以跑的命令）

| 子任务 | 验证命令 | 预期结果 |
|--------|----------|----------|
| A1 | `tail -1 data/index/daily/sh000001/daily.jsonl` | 日期=2026-07-29 |
| A2 | `head -3 data/astro/astro_calendar_2025_2026.jsonl` | 干支+月相 肉眼对 |
| B1 | `python3 八字/查指定日.py --day 2026-04-02` | 上证-0.74% 深证-1.60% 创业-2.31% 科创-2.77% |
| B2 | `python3 treasolo/m1_astro_full_report.py` | 新月窗口反弹比例≈63% |
| C1 | 读 `data/astro/backtest/etf_stem_response.json` | 通信/癸水=+1.16% |
| D2 | `python3 treasolo/m1_risk_engine.py --day 2026-04-02` | 风险≥4,命中R01+R02 |
| E1 | `curl localhost:8787/api/m1/data/astro_predict?day=2026-06-12` | 返回9个ETF信号 |
