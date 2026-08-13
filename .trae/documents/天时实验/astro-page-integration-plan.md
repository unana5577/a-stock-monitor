# 天时日历 (Astro Calendar) 接入页面规划

## 1. 目标与背景

经过前期的数据回测和业务逻辑梳理，我们已确立了天时实验的四个核心维度：
1. **日柱锚定**：上证(戊申)、深证(丁巳)、创业(庚午)、科创(丙寅)。
2. **能量生克**：流年(50%) + 流月(30%) + 流日(20%) 的五行能量叠加计算。
3. **风险共振**：满月/新月、股指交割日、双土日/极性日、年月日三层克伐。
4. **命主结合**：结合个人的八字日柱推算进财/防守建议。

本规划旨在**彻底重构现有的天时实验页 (8784)**，放弃原有的横向滚动结构，采用**高密度网格日历 (Glassmorphism 视觉)** 为核心载体，实现“宏观天象 -> 市场情绪 -> 板块映射 -> 个人操作”的可视化闭环。

---

## 2. 架构决策：Node.js 原生驱动

**核心原则：后端直接使用 Node.js 读取 JSONL，彻底脱离 Python `execFile` 依赖。**

*   **数据底座**：
    *   `data/astro/astro_calendar.jsonl`：包含每一天的阳历、农历、干支、五行、月相。
    *   `data/index/daily/*.jsonl`：包含四大指数的历史行情（用于复盘对账）。
*   **计算中枢**：
    *   所有“天干地支映射、生克得分计算、风险规则判定”均用 JS 在 `server/api/astro.js` 内存中完成。
    *   请求速度提升到毫秒级，便于前端日历快速切换月份。

---

## 3. 后端 API 接口设计 (`server/api/astro.js`)

将原有的零散 API 整合为两个强大的数据接口，直接服务于日历组件。

### API 1: 月度日历聚合接口 (Monthly Calendar API)
**Endpoint**: `GET /api/m1/data/astro_calendar_month?month=2026-07&user_pillar=癸亥`

**功能**：一次性返回指定月份（包含前后补齐天数，凑齐日历网格）的所有交易日核心数据。

**返回结构** (示例)：
```json
{
  "ok": true,
  "month": "2026-07",
  "macro": {
    "yearGz": "丙午", "monthGz": "乙未",
    "summary": "火土焦织，能量极端",
    "indexTrend": ["偏多", "偏多", "偏空", "高危"] // 上/深/创/科
  },
  "days": [
    {
      "date": "2026-07-17",
      "dayNum": 17,
      "disabled": false,
      "lunar": "初四",
      "ganzhi": "癸未",
      "phase": null,
      "isDelivery": true,        // 股指交割日
      "riskLevel": 2,            // 风险等级 (0-3)
      "personal": "danger",      // 结合 user_pillar: money(进财), danger(克伐), null(平稳)
      "preds": [0.8, 0.5, -0.2, -1.5] // 四指数生克得分 (正多负空)
    }
    // ... 其他日期
  ]
}
```

### API 2: 单日深度推演接口 (Daily Detail API)
**Endpoint**: `GET /api/m1/data/astro_daily_detail?date=2026-07-17&user_pillar=癸亥`

**功能**：当用户在前端点击某一天时，获取该日的深度解析文案。

**返回结构** (示例)：
```json
{
  "ok": true,
  "date": "2026-07-17",
  "riskAlerts": [
    "股指期货交割日，历史上叠加下跌趋势极易发生大波动。",
    "当日干支(癸未)为极性日，双土/火极重，流动性易枯竭。"
  ],
  "indexAnalysis": [
    {"name": "上证", "pillar": "戊申", "score": 1.2, "desc": "流日相生，支撑较强"},
    {"name": "科创", "pillar": "丙寅", "score": -2.8, "desc": "年月日三层克伐，破位高危"}
  ],
  "personalAdvice": {
    "type": "danger",
    "title": "今日七杀克身，宜空仓",
    "desc": "结合今日大盘风险，科创板风险极高，建议保留现金，耐心等待下一个水木相生的日子。"
  }
}
```

---

## 4. 前端重构任务 (`pages/astro/`)

### 4.1 废弃与替换
*   完全丢弃原有的横向月相轴 (`#astro-phase-scroll`)。
*   丢弃原有的“明日(Tomorrow)”表格，将其融合到日历点击后的“单日深度推演”面板中。
*   旧的 `index.html` 改名为 `index_old.html` 备份。将我刚写好的原型 `calendar_demo.html` 更名为新的 `index.html`。

### 4.2 UI 组件拆解与数据绑定
基于刚确认的**带有毛玻璃特效、M1标准配色**的 HTML 原型，进行 Vue 数据绑定：

1.  **全局状态 (State)**：
    *   `currentMonth` (YYYY-MM)
    *   `userPillar` (命主日柱参数)
    *   `calendarDays` (日历网格数据数组)
    *   `selectedDay` (当前点击选中的日期)
    *   `dayDetail` (选定日期的深度解析数据)

2.  **月度基调面板 (Month Energy Bar)**：
    *   绑定 `macro.yearGz`, `macro.monthGz`。
    *   绑定宏观预判文案和四盘指示标签。

3.  **日历网格 (Calendar Grid)**：
    *   使用 `v-for="day in calendarDays"` 渲染格子。
    *   根据 `day.phase`、`day.isDelivery`、`day.riskLevel` 动态渲染 Badge 图标。
    *   底部四盘指示灯根据 `day.preds` 数组动态绑定 `.led-up` (红) 或 `.led-down` (绿)。

4.  **右侧单日面板 (Daily Detail Panel)**：
    *   监听日历格子的 `@click` 事件，触发请求 `API 2`。
    *   动态渲染 `riskAlerts` (风险因子共振警报)。
    *   动态渲染 `indexAnalysis` (四盘量化推演)。
    *   动态渲染 `personalAdvice` (命主操作建议)。

---

## 5. 执行步骤 (Action Plan)

1.  **Step 1: 核心常量抽取**。在 `server/api/astro.js` 顶部建立常量表（天干地支五行对照表、四大指数日柱配置表）。
2.  **Step 2: 编写工具函数**。在 `astro.js` 中实现纯 JS 版本的：
    *   `calcEnergyScore(year, month, day, targetPillar)`：计算生克得分。
    *   `checkRiskFactors(date, lunar, ganzhi)`：校验满月、交割日、极性日。
3.  **Step 3: 实现 API**。完成 `astro_calendar_month` 和 `astro_daily_detail` 两个路由。
4.  **Step 4: 前端骨架替换**。将 `calendar_demo.html` 替换为 `index.html`。
5.  **Step 5: 前端 Vue 逻辑重写**。在 `ui.js` 中接入 Fetch 逻辑，绑定真实数据渲染。
6.  **Step 6: 本地联调验证**。选择 `2026-07` 和 `2026-08` 进行点击测试，核对风险标签和预测分数是否正确。

---
*文档更新时间: 2026-08-13*
