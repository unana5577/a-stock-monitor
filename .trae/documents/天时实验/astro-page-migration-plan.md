# 天时实验页迁移计划

## 目标

把八字/天时功能从旧的 `public/index_m1.html` + `public/ui_m1.js` 中独立出来，迁移到新架构的 `pages/astro/` + `server/api/astro.js`，符合 project_rules 第 7、8 节的隔离规范。

## 当前状态

| 文件 | 状态 |
|------|------|
| `server/api/astro.js` | ✅ 已有 4 条路由（别的 agent 已迁移），但路径有 bug |
| `pages/astro/server.js` | ✅ 已建好，端口 8784，自动代理 API 到 8787 |
| `pages/astro/index.html` | ❌ 不存在，需新建 |
| `pages/astro/ui.js` | ❌ 不存在，需新建 |
| `public/index_m1.html` | ⚠️ 仍有八字/天时 HTML 代码（旧架构，不再改） |
| `public/ui_m1.js` | ⚠️ 仍有八字/天时 JS 代码（旧架构，不再改） |
| `treasolo/m1_bazi.py` | ✅ 已含大运计算 |
| `八字/prompts.json` | ✅ 已含模板配置 |

## 需要做的事（4 步）

### 1. 修复 `server/api/astro.js` 的路径 bug

当前路径是相对于 `server/api/` 的，但脚本在项目根目录：

```javascript
// 错误（当前）
path.join(__dirname, 'treasolo', 'm1_bazi.py')   // → server/api/treasolo/...
path.join(__dirname, '八字', 'prompts.json')       // → server/api/八字/...

// 正确（修复后）
path.join(__dirname, '..', '..', 'treasolo', 'm1_bazi.py')
path.join(__dirname, '..', '..', '八字', 'prompts.json')
```

`execFile` 的 `cwd` 也要从 `__dirname` 改为项目根目录。

### 2. 新建 `pages/astro/index.html`

参照 `pages/etf/index.html` 的模式，只包含天时/八字板块的功能：
- 八字录入表单（性别、出生日期、出生地）
- 八字展示 + 大运显示
- 八字财务分析（AI 生成）
- 当日操作风险提示
- 月相日历
- 天时预测矩阵
- AI 聊天（带八字上下文）
- 月相图标 SVG

样式完全复用 `pages/etf/index.html` 的 Tailwind 配置 + CSS 变量。

### 3. 新建 `pages/astro/ui.js`

从 `public/ui_m1.js` 中**只提取**八字/天时相关的代码：
- `baziProfile`、`baziPrompts`、`loadBaziPrompts`、`replaceTemplate`
- `userGender`、`userBirth`、`userPlace`、`baziReady`、`submitBazi`、`fetchBaziProfile`
- `ensureFinanceAuto`、`ensureDailyRiskAuto`、`financeAuto`、`dailyRiskAuto`
- `astroPredict`、`astroSelectedDay`、`selectAstroDay`、`fetchAstroPredict`
- `astroMonthDays`、`astroWeekDays`、`astroMonthGanzhi`
- `astroSelectedGanzhiDay`、`astroSelectedLunarDay`、`astroSelectedPhase`
- `chatMessages`、`sendChat`（含八字/大运上下文注入）
- `astroPhaseSvg`、`astroPhaseRiskText`、月相相关 computed
- `renderAstroHistoryChart`
- 所有工具函数：`callChat`、`fetchWithRetry`、`getBeijingToday`、`formatAmount` 等
- `onMounted` 中的初始化逻辑

不碰的代码（别的 agent 的）：ETF 行情、交易助手、概览页等。

### 4. 清理旧文件（确认后执行）

从 `public/index_m1.html` 和 `public/ui_m1.js` 中删除八字/天时相关代码，保证旧页面不会报错（比如移除引用了已删除 computed 的 HTML 模板）。

## 验证步骤

1. 启动 8787 服务：`PORT=8787 node server/server.js`
2. 启动天时页：`PORT=8784 node pages/astro/server.js`
3. 访问 `http://localhost:8784` → 确认天时页面正常渲染
4. 提交八字 → 确认大运显示 "当前大运: 乙酉（41-50岁）· 起运 1 岁"
5. 切换月相日历 → 确认日历正常
6. 进入 AI 对话 → 确认上下文包含八字+大运

## 风险点

- `server/api/astro.js` 的路径 bug 会导致八字 API 调用失败，需要验证修复后正常
- 从 `ui_m1.js` 提取代码时需保持变量名一致，避免遗漏 computed/watch 依赖
- `index_m1.html` 和 `ui_m1.js` 清理时需确认没有其他板块引用八字/天时的 computed
