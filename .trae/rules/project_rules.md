## 项目规则

### 一、多 Agent 协作公约（防代码漂移）
> 目标：多个 Agent 同时改同一网站的不同板块时，防止公共层被各写一套、命名/结构不一致、CSS 互相覆盖。

#### 1. 文件所有权边界（Agent 只能改自己板块的专属文件，严禁越界）
- **前端页面/板块**：每个 Agent 只允许修改自己负责板块的 HTML 区块和对应的 Vue setup 函数块；`index_m1.html` 和 `ui_m1.js` 目前是全量单文件结构，改之前必须先 grep 搜索确认你的改动不会波及别的板块的 DOM id 或 Vue computed/method/watch。
- **后端路由**：`server.js` 里的路由用 `if (url.pathname === "/api/...")` 裸写；新增路由时：
  - 查阅已有路由命名规律（如 `/api/m1/data/xxx`、`/api/m1/run`），新路由必须遵循同类前缀，不得随意起名
  - **不得删除或改动别人的路由匹配条件**（即使你以为它没用到）
- **treasolo/Python 脚本**：脚本之间已按功能域分层（数据采集/转日线/AI/天时/运维），新脚本放到对应域，复用 `runner.py` 的公共工具（交易日推算、JSONL 读写），不要内联重写同类函数。

#### 2. 公共层保护（只能调用，不能重写）
- **前端公共依赖**：ECharts（`echarts.init`）、Tailwind CSS（class 工具类）、Vue 3（`createApp/setup`）只能通过已有方式引用，不得自行引入其他版本的 CDN 或新图表库。
- **后端公共桥接**：`server.js` 里的 `execFile` 调用 Python 脚本是唯一的前后端数据通道，**不得在 server.js 里内联写数据处理逻辑**（比如自己拼 SQL、自己直接调 AkShare），数据处理必须走 treasolo 脚本。
- **Python 公共工具**：`runner.py` 提供的 `resolve_effective_day`、`read_holiday_set`、JSONL 读写函数是项目统一基础设施，每个脚本都要用它们处理交易日/日期，**不得自己重新实现一套日期推算或文件读写函数**。
- **数据存储路径**：所有数据统一落盘 `data/<类别>/<子路径>/`。新增数据类型时先参考已有目录结构，保持同级命名一致（如 `data/etf/minute/{sym}/{date}.jsonl`），不要自创目录名。

#### 3. 样式公约（CSS/主题只在一个地方定义）
- 全局主题色、背景色、滚动条样式全部在 `index_m1.html` 的 `<style>` 标签中定义。
- 各板块内部只允许用 **Tailwind 语义类名**（如 `bg-green-100 text-green-700`）或**引用已有 CSS 变量/class**，不得硬编码 `#ff0000` 等裸颜色值，也不得在板块区块内重新定义 `::-webkit-scrollbar` 等全局样式。

#### 4. 命名与数据口径公约
- **API 路由**：一律 `/api/<domain>/<resource>` 两级以上，不得用 `/api/xxx` 单级命名。
- **JSON 字段名**：前后端传输的字段名保持 snake_case（如 `market_amount`、`etf_amount`），不用 camelCase（如 `marketAmount`），和现有快照/日线/生命周期字段一致。
- **成交额单位**：落盘 `amount` 字段统一为**元**，不得混用万元/千元；如有外部接口返回万元，必须在数据源层转换完再落盘。
- **日期格式**：落盘 `date` 字段统一 `YYYY-MM-DD`；分钟时间戳统一 `HH:MM` 或 `YYYY-MM-DD HH:MM:SS`（北京时间）。

#### 5. 修改前"影响面检查"强制流程
每次动手改代码前，Agent 必须先做两件事：
- **grep 搜索**：用被修改的函数名/变量名/路由/字段名搜索全仓库，列出所有引用点，汇报给用户确认。
- **对账确认**：如果修改涉及数据口径（`amount`/`pct`/`vol`/日期），必须读取一份样本数据文件，对比修改前后的数值变化，确保不会产生数量级偏差。

#### 6. 部署安全
- **不碰 `.env`**：任何 Agent 不得读取、上传、覆盖服务器上的 `.env` 文件；同步代码时 `.env` 必须在排除列表里。
- **同步排除项铁律**：rsync/scp 同步代码到服务器时，必须排除 `.git/`、`data/`、`.env`、`node_modules/`、`__pycache__/`、`*.pyc`。
- **部署后验证**：代码同步到服务器后，Agent 必须给出明确的"预期现象"和"如何确认生效"（如 curl 某个 API、n8n 手动执行某条工作流看 stdout），不能只说"应该好了"。
- **n8n 工作流里的 URL**：一律使用 `http://app:8787/api/m1/run`（容器内 Docker 网络），不得写 `localhost` 或 `host.docker.internal` 或 IP 地址。

#### 7. 端口与页面隔离（每个 Agent 一个端口，互不干涉）

> 总原则：**1 个共享数据 API 端口 + 4 个页面端口**。数据层所有 Agent 只读不改，页面层各自独占一个端口和目录。

**端口分配（固定，不得随意占用）**

| 端口 | 用途 | Agent |
|------|------|-------|
| `8780` | 统一入口页（壳子，iframe 聚合四个页面） | 公共 |
| `8787` | 共享数据 API（不改，所有页面共用） | 所有人只读 |
| `8781` | 盘中概览页 | Agent A |
| `8782` | ETF 行情页 | Agent B |
| `8783` | 交易助手页 | Agent C |
| `8784` | 天时实验页 | Agent D |

**文件目录隔离（每个 Agent 只能改自己目录）**

```
pages/
  shell/            → 公共（端口 8780）
    index.html
    server.js

  overview/         → Agent A（端口 8781）
    index.html
    ui.js
    server.js
  etf/              → Agent B（端口 8782）
    index.html
    ui.js
    server.js
  trade/            → Agent C（端口 8783）
    index.html
    ui.js
    server.js
  astro/            → Agent D（端口 8784）
    index.html
    ui.js
    server.js
server.js           → 8787，共享数据 API（所有 Agent 只读不改）
```

**每个页面 server.js 的强制规则**
- 只监听自己端口的 `PORT`（不得占别人端口）。
- 所有 `/api/*` 请求**必须转发到** `http://127.0.0.1:8787`（共享数据层），不得自己写裸请求、调 AkShare、读文件。
- 静态文件只能返回自己目录下的 HTML/JS/CSS，不得读别的页面目录的文件。
- Agent 启动 server.js 时用独立进程（PM2 或直接 `node pages/<板块>/server.js &`），不能几个人共用同一个 8787 进程。

**跨板块共享原则**
- 共享数据 API（8787）只允许在 `server.js`（或 `pages/api/` 路由）中新增**只读**查询路由；不得新增可修改数据的写路由（除非用户明确允许）。
- 如果两个页面需要同一种新数据，在 8787 加一条 API 路由，两个页面的 Agent 各自通过 `fetch('/api/...')` 调用，不得各自复制一份数据处理逻辑。


**统一入口页（Shell）说明**
- 统一入口在 `pages/shell/`，端口 **8780**，用于聚合四个独立页面。
- Shell 用 **iframe** 嵌入各页面（`http://127.0.0.1:8781~8784`），tab 栏切换时懒加载 iframe。
- 各 Agent **不需要**在 Shell 里写任何代码；自己的页面在自己的端口跑，Shell 自动聚合。
- 各 Agent **不要在页面里写导航栏、Tab 切换、侧边栏**——这些由 Shell 统一提供。页面只需做好自己的内容区即可。

**页面 UI 公约（在 iframe 内正确显示的强制规则）**
| 规则 | 说明 |
|------|------|
| **不要设 `overflow: hidden` 在 body** | iframe 内页面用 `overflow-y: auto` 保持自身滚动，否则内容被裁切 |
| **页面标题用 `<title>` 标签** | Shell tab 切换不需要页面自带 header，自己页的 header 保留 `页面名称 + 更新时间` |
| **背景色统一 `#F4F4F5`（q-bg）** | 和 Shell 的背景无缝融合，不要用其他颜色 |
| **不使用 `target="_parent"` 或 `window.parent`** | iframe 是各 Agent 的沙盒，不要试图操作外层 DOM |
| **页面的 API 请求走自己端口的代理** | 已经在 server.js 里配好了 `/api/*` 转 8787 的转发，Agent 不需要额外处理 |
| **`<head>` 里的 Tailwind/Vue/ECharts CDN 照抄** | 每个 iframe 是独立文档，必须各自引入依赖（已在 skeletons 中配好） |
| **字体统一** | `font-family: Inter, -apple-system, BlinkMacSystemFont, "PingFang SC", sans-serif` |

#### 8. 后端切块隔离（每个 Agent 只能改自己的路由文件）

> 现状问题：`server.js` 是单文件，55+ 条路由全挤在一起，多个 Agent 共改一个文件必然冲突。

**切块后目录结构**

```
server/
  api/
    overview.js    → Agent A（盘中概览相关路由）
    etf.js         → Agent B（ETF 行情相关路由）
    trade.js       → Agent C（交易助手相关路由）
    astro.js       → Agent D（天时实验相关路由）
    shared.js      → 公共路由（成交额/快照/日历/health 等，所有人只读）
  server.js        → 主入口，只做 require + 路由分发 + listen，不写业务逻辑
```

**每个 api/*.js 的强制规则**
- 一个文件只包含自己板块的路由处理函数，用 `if (url.pathname === '/api/...')` 匹配。
- 每个文件暴露一个数组或函数，供主入口统一注册。
- **Agent 只能修改自己板块的 `server/api/<板块>.js`**，不得改主入口 `server/server.js`、公共路由 `server/api/shared.js`、别人的板块路由。
- 新增数据查询直接调用 `treasolo/` 下已有的 Python 脚本，通过 `execFile` 执行；不得在路由文件里自建数据处理函数。

**主入口 server/server.js 的约束**
- 只做：`require` 各路由模块 → 按 url.pathname 匹配分发 → 没命中返回 404 → `listen(PORT)`。
- 不写任何业务判断逻辑，不断增减任何路由条件。
- 需要新增路由时，Agent 在自己板块文件里加，然后在主入口加一行 `require` + 一行分发调用。

**共享路由 server/api/shared.js 的约束**
- 只能新增"所有页面都用得到"的只读查询路由。
- 涉及修改数据/触发回补/写文件的路由，必须由用户明确确认后由指定的 Agent 添加。
- 不能删除、修改已有路由的匹配条件。

### 二、业务规则（数据口径 & 时间基准）

- 全部"日期/交易时段/分钟对齐"统一按北京时间（Asia/Shanghai），不得使用 ISO(UTC) 日期推导交易日
- 概览页"成交额/量能"展示口径固定：快照成交额为沪深主板累计成交额；历史成交额为按日汇总序列
- 交易日选择固定：非交易时段一律以"最近交易日"作为 day；T-1/T-2 以交易日序列递推，不得简单 day-1
- 量能对比与昨日曲线必须同口径同来源：若严格 T-1 量能数据不完整，允许回退到最近可用交易日，并在数据里提供 asOf 标识供前端展示
- 缓存必须落盘可追溯：快照归档、分钟线、量能点、概览日线与历史成交额均应在 data/ 下可定位；缺失时后端需自检并自动补齐，不得只在 UI 提示缺失

### 三、排障操作规范

- **优先直接在服务器上查文件内容**：出现数据不一致、曲线不显示、指标异常等 Bug，第一步应该是 ssh 到服务器、tail/cat/grep 相应 `data/` 下的落盘文件，确认数据源是否正常落盘、字段值是否异常。
- **诊断 -> 方案 -> 用户确认 -> 修改**：查出问题后，先给用户清晰的根因说明和修改方案（改哪个文件、哪几行、预期效果），用户确认后再动手。严禁跳过确认直接改服务器代码。
- **服务器文件目录速查**（固定路径，不要每次查）：
  - 项目根目录：`/opt/a-stock-monitor`
  - ETF 分钟线：`data/etf/minute/{symbol}/{YYYY-MM-DD}.jsonl`
  - ETF 日线：`data/etf/daily/{symbol}/daily.jsonl`
  - 大盘分钟线：`data/index/minute/{symbol}/{YYYY-MM-DD}.jsonl`
  - 大盘日线：`data/index/daily/{symbol}/daily.jsonl`
  - 市场成交额：`data/market/daily/amount/daily.jsonl`
  - 板块生命周期：`data/lifecycle/lifecycle-{YYYY-MM-DD}.json`
  - Warmup 缓存：`data/warmup/warmup-{YYYY-MM-DD}-60.json`
  - AI 输出：`data/market/ai/report.jsonl`、`data/market/ai/etf_report.jsonl`
  - 快照/热点：`data/market/ai/snapshot.jsonl`
  - n8n 工作流备份：`n8n-workflows/`
  - Python 脚本：`treasolo/`


#### 9. 部署红线（任何人不得违反）

> **以下规则源于线上事故复盘。任何 Agent 违反其中一条，必须在下次对话开始时报告给用户。**

| # | 规则 | 说明 |
|---|------|------|
| **1** | **永远不改线上的 8787 `server.js`** | 它是共享数据 API，project_rules 明确写"所有 Agent 只读不改"。修改必须经过：本地新骨架 8788 验证 → 本地 8787 vs 8788 全量 JSON 对比 → 备份线上 server.js → 才能推 |
| **2** | **修改必须分三阶段验证** | 阶段一：改新骨架 8788 本地验证 → 阶段二：本地 8787+8788 全量 JSON 对比（至少 10 条核心路由）→ 阶段三：服务器备份→部署→Docker 重建 |
| **3** | **不在任何阶段直接改线上** | 在线服务器上的文件先 cp 备份（带日期戳），确认备份成功后才允许覆盖 |
| **4** | **所有页面端口只能代理 8787** | 页面 server.js 里的 API 代理必须指向 `http://127.0.0.1:8787`。8788 是测试骨架，不在线上运行，任何 Agent 不得把页面代理到 8788 |
| **5** | **数据文件只删孤儿、不删 n8n 产出** | 确认文件被消费才能删；否则先问用户。archive/overview-history/breadth-cache 是核心依赖，绝不可删 |
| **6** | **改 `loadMinuteSeries` 前先跑全量映射验证** | 它是 snapshot/warmup/overview 构建链的数据源，13 种 code 映射路径必须逐条验证，不能一把改 |

#### 10. 文档管理规范

**位置**：所有文档放在 `.trae/documents/` 下，按板块分文件夹：

```
.trae/documents/
  盘中概览/          → 概览页相关方案、复盘
  波段交易助手/       → 交易助手/波段策略相关
  ETF行情/           → ETF 页面相关
  天时实验/          → 天时/Astro 相关
```

**命名规则**：`{日期YYYYMMDD}_{简短描述}.md`

示例：`20260615_清理孤儿文件方案.md`

**禁止**：文档散落在 `.trae/documents/` 根目录；旧的不合规文档应在 git commit 后移到对应板块文件夹。

### 四、数据管理规范（本地开发与线上隔离）

> 目标：本地 `data/` 和线上 `data/` 命名完全一致，代码无需改路径；数据单向从服务器拉取，绝不从本地推到线上。

#### 1. 本地数据同步（唯一命令，任何人照此执行）
```bash
rsync -avz --exclude='runtime/' stock-server:/opt/a-stock-monitor/data/ ./data/
```
- 本地 `data/` 就是线上 `data/` 的完整镜像
- 本地代码读写 `data/` 路径和线上完全相同，无需任何环境变量或路径判断

#### 2. 部署时排除 data/（强制）
- 部署脚本（rsync 到服务器、Docker build）必须包含 `--exclude 'data/'`
- 本地 `data/` 永远不覆盖线上 `data/`
- 线上 `data/` 的唯一写入者是 n8n 工作流（`treasolo/` Python 脚本）

#### 3. Agent 新增文件落盘规范

**所有 Agent 产生的新数据文件，必须遵循线上目录结构，路径从项目根开始：**

| 数据类型 | 路径 | 命名规则 |
|----------|------|----------|
| 大盘分钟线 | `data/index/minute/{symbol}/{YYYY-MM-DD}.jsonl` | symbol 用 sh/sz 前缀全码 |
| 大盘日线 | `data/index/daily/{symbol}/daily.jsonl` | 同上 |
| ETF 分钟线 | `data/etf/minute/{symbol}/{YYYY-MM-DD}.jsonl` | symbol 用 sh/sz 前缀全码 |
| ETF 日线 | `data/etf/daily/{symbol}/daily.jsonl` | 同上 |
| 板块分钟线 | `data/sector/minute/{sector}/{YYYY-MM-DD}.jsonl` | sector 用小写英文 |
| 市场成交额 | `data/market/minute/amount/{YYYY-MM-DD}.jsonl` | 日期格式 |
| 涨跌家数 | `data/market/minute/breadth-cache.jsonl` + `data/market/breadth-cache.json` | 固定路径 |
| AI 输出 | `data/market/ai/{report\|etf_report\|snapshot}.jsonl` | 固定路径 |
| 板块生命周期 | `data/lifecycle/lifecycle-{YYYY-MM-DD}.json` | 日期格式 |
| Warmup 缓存 | `data/warmup/warmup-{YYYY-MM-DD}-60.json` + `data/warmup/warmup-60.json` | 日期格式 |
| Archive 快照 | `data/archive-{YYYYMMDD}.jsonl` | 8位紧凑日期 |
| Overview 缓存 | `data/overview-history-{YYYYMMDD}.json` | 8位紧凑日期 |
| 交易日历 | `data/calendar.json` | 固定路径 |

**禁止**：
- 不得在 `data/` 根目录创建新的扁平文件（如 `data/minute-*.jsonl` 旧格式）
- 不得在 `data/` 下创建与 n8n 工作流规范不一致的自定义子目录
- 不得在 Python 脚本或 Node.js 代码中写死 `.env` 里的绝对路径

#### 4. 在线备份目录
- `online_debug_data/` 下的日期文件夹是线上数据快照，用于紧急回滚
- **git 不 track 此目录**，不 commit，不 push
- 只在用户明确要求时，从服务器 rsync 到此目录

### 五、Git & Agent 行为约束

- **Git 执行约束**：本地测试好后，待用户明确确认并发出 "git" 命令时，才允许执行 git 相关操作进行提交与推送，严禁擅自提前 commit 或 push。
- **Agent 防死循环强制约束**：在处理任务时，如果遇到报错、未找到预期代码或方案不通等情况，**最多只能进行 3 次内部循环重试/排查**。如果 3 次尝试后仍未解决，必须立即中止工具调用，并向用户如实汇报当前的卡点与发现，严禁在后台无限尝试。
