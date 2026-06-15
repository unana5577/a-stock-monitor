# 天时页面差异修复计划

## 发现的问题

对比 `pages/astro/ui.js` + `pages/astro/index.html` 与原 `public/ui_m1.js` + `public/index_m1.html` 的天时部分，存在以下差距：

---

## JS 差异（`pages/astro/ui.js` 需修复 6 处）

### 1. `astroPhaseSvg` — 月相 SVG 完全不对（**这就是月相不渲染的根因**）

**现状**：用了简化版的灰色圆+白色 path，SVG 路径完全不同于原版，没有渐变、没有环形山。月相卡片里的 SVG 渲染出来是灰白一团。

**需改为**：原版的完整实现：
- `radialGradient` 明亮黄渐变（#FFF9C4 → #FDD835 → #FBC02D）
- 8 个月相 path（从 `ui_m1.js:L1930-L1938` 复制）
- `filter="softTerminator"` + `clipPath="moonCircle"` 
- 5 个 crater 环形山（深色系，multiply 混合模式）
- `viewBox="0 0 28 28"`、50% 透明黑底圆

### 2. `runAstroPredict` — 缺失

**现状**：`pages/astro/ui.js` 中没有这个函数，但 HTML 中「更新预测」按钮 `@click="runAstroPredict(astroSelectedDay)"` 会报错。

**需补**：POST `/api/m1/data/astro_predict/run` → 触发预测 → 重新拉取数据并刷新图表。

### 3. `scrollAstroPhaseToDay` — 实现不同

**现状**：`parentNode.scrollLeft = ...` 手动计算偏移

**需改为**：原版 `scrollIntoView({ block: 'nearest', inline: 'center', behavior: 'auto' })`，更可靠。

### 4. `astroProbTagClass` — CSS class 细微差异

**现状**：`border-red-300 bg-red-50` vs 原版 `border-red-200 bg-red-50`

**需统一**到原版样式。

### 5. `selectAstroDay` — 缺少 journal 联动

**原版有** `if (!journalDay.value) journalDay.value = day;`，选了日期自动填充到复盘表单。新版缺失。

### 6. 缺失 journal 全套 + `submitJournal`

需补：`journalDay`、`journalMood`、`journalNote`、`journalSubmitting`、`journalStatus`、`submitJournal`。

---

## HTML 差异（`pages/astro/index.html` 缺失 4 个板块）

### 7. 本周交易表 — 缺失

原版 `index_m1.html:L1216-L1251`：横向滚动表格，表头 周一~周五（日期+干支），行=大盘+每个 ETF，每格显示 `astroWeekCellTag(date, sym)`。

### 8. 明日预测网格 — 缺失

原版 `index_m1.html:L1253-L1304`：
- 「更新预测」按钮
- 次日大盘上涨文字
- 品种 × 时间窗口表格（+1/+5/+15/+30），每格 `astroProbTag` + `astroProbTagClass`

### 9. 昨日预测复盘 — 缺失

原版 `index_m1.html:L1324-L1351`：品种/预测(+1)/实际/命中 四列表格。

### 10. 手工复盘录入 — 缺失

原版 `index_m1.html:L1354-L1384`：日期输入、情绪 1-5、备注 textarea、提交按钮。

---

## 执行计划（共 10 个修复）

| # | 修复内容 | 文件 | 行范围 |
|---|---------|------|--------|
| 1 | 替换 `astroPhaseSvg` 为原版完整实现 | `pages/astro/ui.js` | L720-L744 → 全替换 |
| 2 | 补 `runAstroPredict` 函数 | `pages/astro/ui.js` | 在 `selectAstroDay` 后插入 |
| 3 | 修复 `scrollAstroPhaseToDay` | `pages/astro/ui.js` | L415-L421 → 全替换 |
| 4 | 修复 `astroProbTagClass` CSS class | `pages/astro/ui.js` | L492-L500 → 微调 |
| 5 | `selectAstroDay` 补 journalDay 联动 | `pages/astro/ui.js` | L453 → 加一行 |
| 6 | 补 journal 全套变量 + `submitJournal` | `pages/astro/ui.js` | 在 variables 区 + 函数区 |
| 7 | 补「本周交易表」HTML | `pages/astro/index.html` | 在月相轴后面插入 |
| 8 | 补「明日预测网格」HTML | `pages/astro/index.html` | 在 7 后面插入 |
| 9 | 补「昨日预测复盘」HTML | `pages/astro/index.html` | 在 ETF 走势对比后面 |
| 10 | 补「手工复盘录入」HTML | `pages/astro/index.html` | 在 9 后面 |

---

## 不会碰的文件
- `server/api/astro.js` — 不改
- `pages/astro/server.js` — 不改
- 其他板块文件 — 不改
