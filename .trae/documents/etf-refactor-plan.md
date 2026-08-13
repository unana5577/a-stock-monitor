# ETF 数据架构重构规划

## 0. 核心设计原则

```
code = 唯一标识（如 sh512400）
api_name = 接口实名（如 "有色金属"、"半导体材料设备"）
category = 内部阵营分类（科技/资源/债券）
sub_category = 内部子分类（硬件/软件/大宗周期/泛能源/利率债/...）
```

**不同位置显示不同名字**：

| 位置 | 显示内容 | 来源 |
|------|---------|------|
| ETF 生命周期卡片标题 | `api_name`（接口实名） | 后端数据 `item.name` |
| ETF 单只成交量柱状图 X 轴 | `api_name`（接口实名） | API 分钟线数据中的 name |
| 阵营分类聚合柱状图 | `category`（科技/资源/债券） | sector-proxy.json |
| ETF 管理表格 | code + `api_name` + category + sub_category | proxy + API |
| 上涨周期统计 | `api_name`（接口实名） | 同上 |
| 相关性图表图例 | `api_name`（接口实名） | 同上 |

**关于资源分类（只有有色金属+新能源2只）的讨论结论**：
- 保留阵营分类聚合，即使只有 2 只也有意义
- 2 只资源 ETF 聚合后可以看到"资源板块整体资金流向"
- 后续可能增加更多资源 ETF（如煤炭ETF、钢铁ETF等）
- 单只 ETF 的成交量柱状图同时存在，两种视角互补
- **不改动既有分类体系，只把中文名从内部固定名称→API 实名**

---
## 1. 数据层重构（Agent A — 我先改）

### 🟢 关键约束

- `data/sector-proxy.json` **通过 Docker volume 在新老容器间共享**（`/opt/a-stock-monitor/data` → `/app/data`）
- **文件格式不能变**，否则老容器（8787/8780）会崩
- **只改新容器代码**（a-stock-v2 + a-stock-pages-v2），老容器代码不动

### 策略：内部转换层

```
sector-proxy.json（旧格式不变，新老容器共享）
  │
  ├── 老容器代码（不改）：直接读 {"半导体": "sh512480"} → 旧逻辑
  │
  └── 新容器代码（改造）：读旧格式 → 内部 transform → code 为 key 的新格式
       transform: for (name, code) of variants.etf
         → {code: {api_name: name, category, sub_category, hidden}}
```

### 1.1 `data/sector-proxy.json` — 仅补齐数据，格式不变

**文件格式保持：`{variants: {etf: {中文名: code}}, etf_meta: {中文名: {category, sub_category}}}`**

**数据补齐（手工一次）**：
- sh511130 → `"30年国债ETF"` → category: 债券, sub_category: 利率债
- sh511260 → `"10年国债ETF"` → category: 债券, sub_category: 利率债
- sh562590 → `"半导体材料设备ETF"` → category: 科技, sub_category: 硬件
- 删除 sh589020（无数据管线）

### 0.1 统一原则（最高优先级）

```
所有页面 → 唯一 API: POST /api/sector/manage → 后端统一处理注册+回补
                          │
                          ├── 校验 code 格式
                          ├── 调行情接口获取中文名
                          ├── 写 sector-proxy.json（旧格式）
                          ├── 自动触发回补流水线（backfill → minute_fetch → warmup → lifecycle）
                          └── 返回 {ok, etfs: {...}}
```

**任何页面不得**：
- 自己拼名字自己传到后端
- 自己写 `/api/m1/run` 回补逻辑
- 创建自己的 ETF 注册接口
- 前端重复 `triggerBackfill` 函数（当前 etf/ui.js 和 trade/ui.js 各有一份完全重复）

**前端只负责**：收集 code + category + sub_category → POST → 等后端返回 → 刷新列表

### 0.2 新增 ETF 的"存一次"流程（后端统一）

```
前端（任意页面） POST {code: "sh562590", category: "科技", sub_category: "硬件"}
  │
  ▼
POST /api/sector/manage（唯一入口，在 server/api/trade.js 中实现）
  │ 1. 校验 code 格式 sh/sz + 6位数字
  │ 2. 调用腾讯行情 API 获取中文名（如 "半导体材料设备"）
  │ 3. 写 sector-proxy.json（旧格式）:
  │      variants.etf["半导体材料设备"] = "sh562590"
  │      etf_meta["半导体材料设备"] = {category, sub_category}
  │ 4. 异步触发回补流水线（不阻塞响应）:
  │      m1_backfill.py → m1_minute_fetch_etf.py → m1_warmup.py → m1_lifecycle.py
  │ 5. 返回 {ok, etfs: {sh562590: {api_name: "半导体材料设备", category: "科技", sub_category: "硬件"}}}
  │
  ▼
中文名存入 sector-proxy.json → 永不过期，不再重查
```

### 1.3 `server/api/trade.js` — 内部转换 + API 改造

新增 `readEtfMapFromProxy()` 工具函数（内部转换层）：

```js
function readEtfMapFromProxy() {
  const raw = JSON.parse(fs.readFileSync(proxyPath, 'utf8'));
  const map = {};
  for (const [name, code] of Object.entries(raw.variants?.etf || {})) {
    map[code] = {
      api_name: name,           // ← 旧格式的 key 变成 api_name
      category: raw.etf_meta?.[name]?.category || '科技',
      sub_category: raw.etf_meta?.[name]?.sub_category || '硬件',
      hidden: raw.etf_meta?.[name]?.hidden || false
    };
  }
  return map;
}
```

**GET `/api/sector/manage`**：返回 `{etfs: {sh512480: {api_name, category, sub_category, hidden}, ...}}`

**POST `/api/sector/manage`**（唯一新增入口）：
- 接受 `{code, category, sub_category}`
- 校验 code → 调行情接口获取中文名 → 写旧格式 → 异步触发回补 → 返回 etf Map
- 回补流水线在后端异步执行，前端只等返回的 etf Map

**DELETE `/api/sector/manage`**：用 `?code=` 定位，从旧格式中反向查找中文名 key 再删除。

**`POST /api/sector/manage?action=backfill`**：已存在 ETF 的"重新回补"（不重复注册，仅触发回补流水线）。

**重要**：回补逻辑从两个前端移除，统一到 `POST /api/sector/manage` 后端自动完成。

### 1.4 `server/api/overview.js` — 概览 API

已有从 `sector-proxy.json` 读取 ETF 列表的逻辑。改为调用 `readEtfMapFromApi()`（走 server/api/shared.js 的统一转换入口）。

### 1.5 `server/api/shared.js` — 共享路由统一转换

在 `shared.js` 中提供 `readEtfMapFromProxy()` 导出版本，所有旧路由内部调用此函数做转换：

- `/api/sector/proxy`
- `/api/sector/history_proxy`
- `/api/sector/rotation_proxy`
- `/api/sector/lifecycle`

### 1.6 `treasolo/m1_lifecycle.py` — 删硬编码映射

**现状**：`SYMBOL_TO_NAME` 硬编码 11 只 ETF 的中文名
**目标**：删掉 `SYMBOL_TO_NAME`，改为从 `sector-proxy.json` 读取 `variants.etf`。遍历得到 code→中文名 映射，`ETF名称` 字段统一用 proxy 中的中文名（即存一次的结果）。

### 1.7 `treasolo/analysis/m1_etf_intraday_features.py`

内部遍历 `variants.etf` 时做转换：遍历 `variants.etf` 得到 `(name, code)` 对，用 code 读分时数据，用 name 做展示标签。

### 1.8 `treasolo/m1_warmup.py`

**无需改动** — 已动态扫描 `data/etf/daily/` 目录，自动发现新 ETF。

---

## 2. 前端重构（Agent B — ETF 页面）

### 2.1 `pages/etf/ui.js` — 核心逻辑

#### 删除硬编码（L19-L37）

```js
// ❌ 删除
const etfSymbols = ref([...]);
const symbolNames = { ... };
const etfCategoryMap = { ... };
const etfSubCategoryMap = { ... };

// ✅ 改为从 API 初始化
const etfSymbols = ref([]);
const symbolNames = ref({});  // code → api_name
const etfCategoryMap = ref({});  // code → category
const etfSubCategoryMap = ref({});  // code → sub_category
```

#### `syncMapsFromApi()` 改造（L380-L394）

API 新格式为 `{sh512480: {category, sub_category, api_name}, ...}`：

```js
const syncMapsFromApi = (apiEtfs) => {
  const newSymbols = [];
  const newNames = {};
  const newCat = {};
  const newSub = {};
  Object.entries(apiEtfs).forEach(([code, info]) => {
    newSymbols.push(code);
    newNames[code] = info.api_name || code;
    newCat[code] = info.category;
    newSub[code] = info.sub_category;
    if (info.hidden) hiddenSymbols[code] = true;
  });
  etfSymbols.value = newSymbols;
  symbolNames.value = newNames;
  etfCategoryMap.value = newCat;
  etfSubCategoryMap.value = newSub;
};
```

#### `etfLifecycleItems` 兜底逻辑（L112-L121）

继续保留兜底：如果后端数据中 `ETF名称` 缺失或等于 code，从 `symbolNames` 补。

#### `etfPctBarData`（L521-L531）

```js
// name 字段改为: symbolNames.value[code] || code
name: symbolNames.value[code] || code,
```

#### `buildEtfManagerRows`（L357-L364）

```js
const name = symbolNames.value[code] || code;
```

#### `submitEtfForm()`（L472-L494）

```js
// ❌ 删除 name 字段 + 删除整个 triggerBackfill 调用
const body = { code, category: etfForm.category, sub_category: etfForm.sub_category };
// POST /api/sector/manage → 后端统一注册+回补，前端只等返回刷新列表
```

#### `triggerBackfill()` + `triggerBackfillRow()` → 删除

回补逻辑统一到 `POST /api/sector/manage` 后端，前端不再手动触发回补流水线。

`triggerBackfillRow` 改为：`POST /api/sector/manage?action=backfill` `{code}`。

#### `openEtfForm()`（L369-L377）

mode='add' 时不设 name（表单没有 name 输入框了）。

#### `deleteEtfRow()`（L496-L508）

DELETE URL 改为 `?code=`。

### 2.2 `pages/etf/index.html` — 模板

#### ETF 新增表单（L298-L316）

删除 "ETF 名称" 输入框，只保留：

```html
<label>ETF 代码</label>
<input v-model="etfForm.code" placeholder="例如：sh562590" />
<label>阵营</label>
<select v-model="etfForm.category">...</select>
<label>子分类</label>
<select v-model="etfForm.sub_category">...</select>
```

#### ETF 管理表格（L271-L278）

name 列数据来源从 `row.name`（旧内部名）→ `symbolNames[row.code]`（API 实名），无需改 HTML 模板。

#### ETF 生命周期卡片（L167, L190, L213）

名字展示 `{{ (item.ETF名称 || item.名称 || item.name || item.symbol || '') }}` 已经是从后端数据取，无需改 HTML。后端数据（Python）改造后自然带上 API 实名。

#### 代码对比输入框（L101）

placeholder 改为 "输入代码对比 (如 sh512480)" — 去掉"名称"提示。

---

## 3. 前端重构（Agent C — 交易助手）

### 3.1 `pages/trade/ui.js`

#### OCR 匹配（L740-L759）

**删除 L1/L2/L3 中文名模糊匹配**，只保留 L0 代码匹配：

```js
// L0: 直接 code 匹配 /^(sh|sz)\d{6}$/
// 其他匹配逻辑全部删除
// 无法匹配的进入 ocrUnmapped，由用户手动输入 code
```

#### DEFAULT 常量（L9-L19）

删除硬编码，改为 `onMounted` 时从 `GET /api/sector/manage` 获取：
- `etfSymbols` → `GET /api/sector/manage`
- `symbolNames` → API 返回的 `api_name`

#### `registerAndBackfill()`（L251-L261）→ 改为统一 API 调用

删除现有的 `registerAndBackfill` 和 `triggerBackfillForTrade` 两个函数（etf/ui.js 也有完全相同的副本），改为：

```js
const registerEtfViaApi = async (code) => {
  const res = await fetch('/api/sector/manage', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code, category: '科技', sub_category: '硬件' })
  });
  return await res.json();
};
```

**不再自定义触发回补** — 后端 `POST /api/sector/manage` 自动完成回补。

### 3.2 `pages/trade/index.html`

添加持仓时只输入 code，名称自动从 `symbolNames` 填充。

---

## 4. 前端重构（Agent D — 天时实验）

### 4.1 `pages/astro/ui.js`

L499-L504：删除硬编码 `etfSymbols` / `symbolNames`，改为从 API 获取。

---

## 5. 前端收尾（Agent A — 盘中概览）

### 5.1 `pages/overview/ui.js`

L27-L40：
- 大盘指数部分保持硬编码（sh000001 等不变）
- ETF 部分（sh511130, sh511260, sh562590）从 API 动态获取 `symbolNames`

---

## 6. N8N 工作流收尾（Agent A）

### 6.1 `M1-D-ETF-Minute2Daily.json`

删除硬编码 ETF 列表，改为从 `GET /api/sector/manage` 动态获取后展开。

### 6.2 `M1-E-Backfill-Universal.json`

同上。

---

## 7. 执行顺序与依赖图

```
           Phase 1（Agent A，先改）
        ┌──────────────────────────────┐
        │ sector-proxy.json（手工补数据）│ ← 补齐3只ETF，格式不变
        │ server/api/trade.js          │
        │ server/api/overview.js       │
        │ server/api/shared.js         │
        │ treasolo/m1_lifecycle.py     │
        │ treasolo/m1_etf_intraday*.py │
        └──────────────┬───────────────┘
                       │ API 格式稳定 (code-keyed)
        ┌──────────────┼───────────────┐
        │              │               │
   Phase 2a       Phase 2b        Phase 2c
   Agent B        Agent C         Agent A
   ETF 页面       交易助手         盘中概览
        │              │               │
        └──────────────┼───────────────┘
                       │
                  Phase 3（Agent A）
                  n8n 工作流更新
```

**并行度**：Phase 2 的三个 Agent 可以并行（各自独立文件）

---

## 8. 兼容性保证

| 事项 | 策略 |
|------|------|
| `sector-proxy.json` 格式 | **不变**（中文名→code），新老容器共享 |
| 老容器（8787/8780） | 代码完全不动，直接读 proxy 旧格式 → 行为不变 |
| 新容器（8788/8793） | 内部 transform 层，读旧格式输出 code-keyed |
| 新增 ETF | 存一次：POST {code} → 调行情API得中文名 → 写旧格式 → 永不过期 |
| 展示回退 | 卡片模板 `item.ETF名称 \| item.名称 \| item.name \| item.symbol` 已健壮 |
| Python 脚本 | 只在 `m1_lifecycle.py` 和 `m1_etf_intraday_features.py` 中做内部转换（仅2个文件） |

### 8.1 为什么不能用镜像（image）部署

本项目的 Docker 部署方式是 **bind mount**（`/opt/a-stock-monitor/data` → `/app/data`），而非 COPY。这意味着：

- `sector-proxy.json` 在宿主机，不在镜像内
- 修改 proxy 后只需重建 `app_v2` 和 `pages_v2` 两个容器
- 老容器的 server.js 代码不动（在镜像内），读 proxy 旧格式正常
- `pages_v2` 只改了前端 HTML/JS，通过 COPY 进镜像，不涉及 proxy 读写
