# 前端 UI 说明（现状版）

## 1. 前端形态与入口
- 形态：单页应用（无前端路由），通过 Tab 切换视图
- 入口页面：[public/index.html](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/public/index.html)
- 入口脚本与交互逻辑：[public/ui.js](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/public/ui.js)
- UI 依赖（本地静态库）：
  - Vue（浏览器全局）：[public/libs/vue.js](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/public/libs/vue.js)
  - ECharts：[public/libs/echarts.min.js](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/public/libs/echarts.min.js)
  - Tailwind CSS：[public/libs/tailwind.min.css](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/public/libs/tailwind.min.css)
- 托管方式：由 Node 服务静态托管 `public/`，并提供 `/api/*` 接口（见 [server.js](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/server.js)）

## 2. 顶部通用区
- 标题：快捷看盘 + AI 分析
- 更新时间：展示“本页面最近一次成功拿到数据的时间”（`dataTs`，按浏览器本地时区格式化为 `MM-DD HH:MM:SS`）
  - 来源优先级：`/api/snapshot/latest` 返回的 `ts`；盘中分钟线有更新时，会用分钟线最新时间刷新 `dataTs`
  - 含义边界：这是“页面数据刷新时间”，不等同于交易所时间；若节假日/非交易时段触发回退数据，时间可能对应“最近一次可用交易日数据的生成/更新时间”
- 刷新按钮：触发全量刷新（概览/行情/新闻相关数据）

## 3. Tab：概览（overview）
定位：快速浏览“情绪 + 指数/债 + 量能 + AI解读”。

### 3.1 AI 今日解读
- 展示分段：走势判断 / 支撑依据 / 情绪结论 / 资金风格 / 仓位建议 / 提示
- 支持单独刷新（右上角 ⟳）
- 位置参考：[index.html: 概览Tab](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/public/index.html#L30-L57)

### 3.2 Prompt 调试（stock-daily）
- 可编辑 Prompt，点击“生成解读”输出模型结果（用于调试）
- 显示加载中/错误信息
- 位置参考：[index.html: Prompt调试](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/public/index.html#L47-L57)

### 3.3 大盘情绪（量能=沪深主板成交额）
- 涨跌家数：进度条+数量（仅在拉到数据后显示该模块）
- 成交额卡片（核心量能）
  - 主值：当日成交额（`sentiment.volumeStr`，直接展示为文本，如 `xxxx.x亿`）
  - 右上角对比：对比昨日同一时刻的增量/缩量（`sentiment.volumeCmp`）
    - 展示格式：`增量/缩量 {pct}% / {delta}亿（对比MM-DD）`
    - 缺失策略：`pct` 或 `delta` 不可用时显示“昨日缺失”
    - 颜色：按 `pct` 正负红/绿
  - ETF 行：展示 ETF 成交额与占比（`sentiment.etfAmountStr / sentiment.etfSharePct`），并附带 `asof` 时间（若有）
  - Sparkline：成交额火花线（ECharts 容器 `#spark-volume`）
    - 两条线：今日（红/绿，随最新分时数据变化决定）+ 昨日（蓝色虚线水平线，为上一个交易日分时均线）
    - 横轴：交易分钟轴（09:30-11:30，13:00-15:00）
    - 纵轴：相对当日首个有效分钟的变化百分比（用于观察“量能抬升/回落”的斜率）
    - Tooltip：显示该分钟的成交额原始值（单位：亿），支持同时对比今日/昨日
    - 显示连续性：在首个与最后一个有效点之间，缺失分钟会用“最后一次有效值”补齐（仅用于图形连续显示）

### 3.4 国债与指数（火花线）
- 30年国债ETF 511130、10年国债ETF 511260、沪深300、中证2000（均带 sparkline）

### 3.5 金融指数（火花线）
- 银行 BK0475、证券 BK0473、保险 BK0474

### 3.6 大盘走势（腾讯源，火花线）
- 上证、深证、创业板、科创综指 000680、平均股价

## 4. Tab：行情（market）
定位：盘中/盘后“风险门控 + 自选对比 + 主线轮动 + 板块分析”。

### 4.1 左侧：控制与摘要
#### 4.1.1 API 服务
- 当前 `apiBase` 显示 + 输入框可切换到指定服务地址
- 留空恢复同源
- `apiBase` 来源优先级：URL 参数 `?api=` → localStorage `api_base` → 同源/localhost（见 [ui.js: apiBase](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/public/ui.js#L76-L88)）

#### 4.1.2 风险门控（盘中/盘后）
- 恐慌状态（is_panic）、下跌占比、涨跌家数
- 风险标签（tags）与仓位上限（cap）

#### 4.1.3 自选池（盘中对比 / 昨日对照）
- 展示：昨涨跌幅、今涨跌幅、趋势标签（如转强/转弱/修复转强）、动能/资金行为、热度Δ
- Top 标记：主线 Top1-3 会同步到自选池的 Top 标识（见 [index.html: 自选池与Top标记](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/public/index.html#L201-L293)）

#### 4.1.4 主线&轮动（盘后）
- 口径固定为 ETF 代理（UI 选择框 disabled）
- 盘中结构监控：大类/细分切换；细分模式左右两栏涨跌幅分布图（ECharts）
- 支持：强制刷新、导出 JSON、复制 Markdown

#### 4.1.5 文本类输出
- 板块跷跷板/同涨同跌（marketAi.seesaw）
- 涨跌幅榜趋势判断（marketAi.streak）
- 板块 Prompt 调试（sector）

### 4.2 右侧：板块分析主体
#### 4.2.1 板块行情与关联分析
- 时间窗：当日 / 5日 / 30日 / 60日
- 关注板块输入：逗号分隔；支持“管理”弹窗
- 趋势图：`#sector-trend-chart`（ECharts）
- 上涨周期矩阵：支持近 2/3/6/12 个月跨度切换；按“主线/题材”属性标注
- 属性口径提示：近20交易日上涨天数/累计涨幅/连涨等规则（见 [index.html: 上涨周期矩阵](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/public/index.html#L347-L403)）

#### 4.2.2 板块生命周期监测
- 卡片展示：阶段信号、含义、动能/资金/建议、归因说明、Alpha/Bias/热度变化等指标（见 [index.html: 生命周期](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/public/index.html#L408-L444)）

## 5. Tab：新闻（news）
定位：按分类阅读新闻，并提供热度图（ECharts 容器）。

- 顶部：刷新按钮（加载中提示）
- 分类列表：宏观等（折叠详情、摘要、原文链接、标签、影响等级/重要性星级）
- 右侧：板块热度图区域（ECharts 容器）

## 6. 数据与接口对接（前端视角）
- 前端统一使用 `fetch(apiBase + '/api/...')` 拉取数据
- 更完整的接口口径与字段说明参考：[docs/trae-frontend-apis.md](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/docs/trae-frontend-apis.md)

## 7. 本地状态（LocalStorage）
- `api_base`：API 服务地址（可由 `?api=` 写入）
- `sector_input`：关注板块输入默认值
- `rotation_month_span`：上涨周期矩阵月份跨度（2/3/6/12）

## 8. 现状约束
- 页面结构集中在 [public/index.html](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/public/index.html)
- 状态/计算属性/请求/图表绘制集中在 [public/ui.js](file:///Users/una5577/Documents/trae_projects/a-stock-monitor/public/ui.js)
- 无打包构建流程；修改后刷新页面即可验证
