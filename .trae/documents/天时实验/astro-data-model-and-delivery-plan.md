# 天时日历 — 数据模式、动态变量与盘后校准方案

## 一、核心结论

1. **数据分四层**：静态历法（永久缓存）、动态变量（每日校准调优）、动态行情（每日同步）、衍生结果（可重算）。
2. **日柱不写死**：每个指数保留「主日柱 + 备选日柱」候选集，每天盘后并行验证，表现更好者切为主。
3. **股指期货交割日 = 纯计算**：每月第三个周五 + 节假日顺延，不网上搜索。
4. **盘后校准闭环**：收盘后「实际盘面描述 → 自动验证 → 修正算法变量」，不是改结论，是调参数。

---

## 二、动态变量全清单（已落盘 `八字/astro_dynamic_vars.json`）

这是校准闭环要"自动修正"的全部变量。文件里分 `static`（不变）与 `tunable`（可调）两部分。

### static（算法结构，永不调优）

| 项 | 内容 |
|----|------|
| tiangan_wuxing | 十天干五行（甲乙木…） |
| dizhi_wuxing | 十二地支五行（子水…） |
| sheng / ke | 五行相生/相克关系 |

### tunable（动态变量，每日盘后可修正）

| 变量 | 当前值 | 含义 |
|------|--------|------|
| `indices[].pillar` | 戊申/丁巳/庚午/丙寅 | 主日柱（可切换） |
| `indices[].candidates` | 每指数3个候选 | 备选日柱池 |
| `energy_weights` | 年50%/月30%/日20% | 三层能量权重 |
| `score_map` | 同气+2/被生+1/被克-2/泄-1 | 生克打分分值（年/月/日三层各一套） |
| `verdict_thresholds` | 强+1.5 / 弱-1.5 | 偏强/偏弱判定线 |
| `switch_rule` | 窗口20/样本10/优势0.15 | 切换日柱的触发规则 |

---

## 三、四层数据模式

| 层 | 文件/目录 | 性质 |
|----|-----------|------|
| L1 静态历法 | `data/astro/astro_calendar.jsonl` | 一次生成永久缓存，不联网不重算 |
| L2 动态变量 | `八字/astro_dynamic_vars.json` + `risk_rules.json` | 算法参数，盘后校准可调 |
| L3 动态行情 | `data/index/daily/`、`data/etf/daily/` | 每日 rsync 同步 |
| L4 衍生结果 | `data/astro/risk/`、`predict/`、`calibration/` | 可重算，落盘可追溯 |

---

## 四、交割日（纯计算）

**规则**：股指期货交割日 = 合约月份的第三个周五；遇法定节假日顺延到下一交易日。

**前置缺口**：`config/holidays.json` 目前只有 2026 年，需补全 2024/2025 年节假日，历史回测才准确。

---

## 五、盘后校准闭环（核心新增）

每天收盘后（约 15:30）运行，流程：

```
1. 取数   读当天 4 指数实际涨跌幅（data/index/daily/）
2. 读预测 读当天早上生成的预测（data/astro/predict/YYYY-MM-DD.json）
3. 验证   每个指数「预测方向 vs 实际方向」→ 命中率
4. 归因   每个预测错误的指数，回溯是日柱错 / 权重偏 / 风险规则误报
5. 修算法 修正 tunable 动态变量（不直接改预测结论）
6. 落盘   写 data/astro/calibration/YYYY-MM-DD.json，记录改了哪些变量、为什么
7. 更新   astro_dynamic_vars.json / risk_rules.json 的 tunable 值
```

### 修正算法（不是改结论）的具体动作

| 现象 | 修正动作 |
|------|----------|
| 主日柱连续 N 天预测错，备选日柱同期命中率高 | 切换 `pillar` 到表现更好的候选 |
| 能量权重导致系统性偏差 | 微调 `energy_weights`（如年 0.50→0.48） |
| 生克打分方向持续错 | 微调 `score_map` 分值 |
| 某风险规则持续误报 | 降 `weight`，低于阈值停用 |

---

## 六、实施步骤

| Step | 动作 | 产出 |
|------|------|------|
| 1 | ✅ 建 `八字/astro_dynamic_vars.json` | 动态变量配置 |
| 2 | ✅ 更新本方案文档 | — |
| 3 | `server/api/astro.js` 实现 JS 计算中枢（读动态变量） | calcEnergyScore/calcDeliveryDays/checkRiskFactors |
| 4 | 实现 `astro_calendar_month` + `astro_daily_detail` API | 返回主+备选双结果 |
| 5 | 前端转正 + 接入 Fetch | 日历可视化 |
| 6 | 建 `m1_daily_calibrate.py` | 盘后校准闭环 |
| 7 | 补全 `config/holidays.json` 2024/2025 | 交割日历史回测 |

---

## 七、验证

1. `astro_dynamic_vars.json` 里 4 个指数都有主+备选日柱，候选 ≥ 2。
2. JS 计算中枢对同一日期，能同时输出主日柱和备选日柱的得分。
3. 交割日 `calcDeliveryDays(2026)` 输出 12 天，核对 2026-07-17。
4. 校准脚本跑一次，能生成 calibration 报告并回写 tunable 变量。

*文档更新时间: 2026-08-13*
