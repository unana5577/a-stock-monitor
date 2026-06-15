# 后端骨架迁移计划

## 目标

将 6000+ 行的单文件 `server.js` 拆分为 `server/` 目录模块结构，让 4 个 Agent 各自只改自己的路由文件，互不冲突。**一次性做好，不留下"先拆路由、变量后面再改"的技术债。**

## 关键结论：n8n 工作流不需要修改

n8n 工作流请求的是 HTTP 端点（`/api/m1/run`、`/api/runner/run` 等），不关心服务端内部是单文件还是多文件。只要端口和路由匹配规则不变，工作流零改动。

## 端口策略

| 端口 | 用途 | 说明 |
|------|------|------|
| `8787` | 旧 `server.js` 继续跑 | 线上不动，n8n 不停，所有人开发不中断 |
| `8788` | 新 `server/server.js` 验证 | 新骨架验证通过后，一次性切换回 8787 |

## 路由分配（基于旧 server.js 逐条盘点结果）

| 域 | 文件 | 路由数 | Agent |
|----|------|--------|-------|
| shared | `server/api/shared.js` | 38 条 | 所有人只读 |
| overview | `server/api/overview.js` | 13 条 | Agent A |
| astro | `server/api/astro.js` | 4 条 | Agent D |
| etf | `server/api/etf.js` | 0 条（骨架） | Agent B |
| trade | `server/api/trade.js` | 0 条（骨架） | Agent C |
| 主入口 | `server/server.js` | — | 公共 |

## 文件变更清单

### 新建文件

```
server/
  context.js        → 共享状态 + 工具函数（从旧 server.js 提取，一次性抽干净）
  server.js         → 主入口：require context + 各路由模块 → 分发 → listen(8788)
  api/
    shared.js       → 38 条公共路由（快照/成交额/板块/日历/health/runner 等）
    overview.js     → 13 条盘中概览路由（/api/m1/*）
    astro.js        → 4 条天时路由（bazi/day_astro/astro_calendar/bazi_prompts）
    etf.js          → Agent B 空骨架
    trade.js        → Agent C 空骨架
```

### 旧文件

- `server.js`：**不改动**，在 8787 继续服务直到全部迁移验证完成后删除。

## context.js 设计（一次性抽干净）

这是整个拆分的核心。旧 server.js 里所有路由共用的东西全在这里：

```js
// 模块导入
const http = require('http');
const https = require('https');
const fs = require('fs');
const path = require('path');
const { execFile } = require('child_process');
const crypto = require('crypto');

// .env 加载
function loadEnv(dirname) { ... }

// 常量
const PORT = 8788;  // 新端口
const CACHE_TTL_MS = 30_000;
const OVERVIEW_CACHE_REV = 2;
const PROXY_FILE = path.join(__dirname, '..', 'data', 'sector-proxy.json');
const HOLIDAY_FILE = path.join(__dirname, '..', 'config', 'holidays.json');

// 共享状态（所有路由读写同一个对象，和旧 server.js 行为完全一致）
const cache = new Map();
let lastAiText = '';
const lastGoodSnapshot = { payload: null, ts: 0 };
const lastGoodMinute = new Map();
let lastWarmupDay = '';
const lastIntradayRotation = { payload: null, ts: 0, day: '', leader: '', signal: '', reason: [], signalTs: 0 };
const INTRADAY_DEBOUNCE_MS = 10 * 60 * 1000;
const INTRADAY_CACHE_TTL_MS = 2 * 60 * 1000;
let lastDailyBackfillDay = '';

// 工具函数
function isNum(v) { ... }
function now() { return Date.now(); }
function pickNum(...vals) { ... }
// ... 所有旧 server.js 里的工具函数全部搬到这里

// 数据获取辅助函数
function getBeijingDate() { ... }
// ... 被多条路由共用的 fetch 辅助函数

module.exports = {
  http, https, fs, path, execFile, crypto,
  PORT, CACHE_TTL_MS, OVERVIEW_CACHE_REV,
  PROXY_FILE, HOLIDAY_FILE,
  cache, lastAiText, lastGoodSnapshot, lastGoodMinute,
  lastWarmupDay, lastIntradayRotation,
  INTRADAY_DEBOUNCE_MS, INTRADAY_CACHE_TTL_MS,
  lastDailyBackfillDay,
  isNum, now, pickNum,
  getBeijingDate,
  // ... 所有导出
};
```

每个 `api/*.js` 文件格式：

```js
module.exports = function(ctx) {
  // ctx 就是 context.js 的 exports
  // 路由匹配逻辑，和旧 server.js 完全一致，只是用 ctx.xxx 替代直接引用
  return function handle(req, res) {
    const url = new URL(req.url, `http://127.0.0.1:${ctx.PORT}`);
    if (url.pathname === '/api/m1/data/overview' && req.method === 'GET') {
      // ... 原有逻辑，用 ctx.cache, ctx.execFile 等
    }
    // ... 更多路由
    return false; // 没命中返回 false
  };
};
```

## server/server.js 主入口设计

```js
const ctx = require('./context');

// 加载 .env 到 ctx
ctx.fs.existsSync(...) // .env 读取

// 注册各路由模块
const routes = [
  require('./api/shared')(ctx),
  require('./api/overview')(ctx),
  require('./api/astro')(ctx),
  require('./api/etf')(ctx),
  require('./api/trade')(ctx),
];

// 静态文件服务
function serveStatic(req, res) { ... }

http.createServer((req, res) => {
  // 1. 尝试路由分发
  for (const handle of routes) {
    if (handle(req, res)) return; // 命中则返回
  }
  // 2. 尝试静态文件
  serveStatic(req, res);
}).listen(ctx.PORT);

console.log(`proxy server on http://localhost:${ctx.PORT} [Ashare+Tencent]`);
```

## 执行步骤

### 第 1 步：创建 context.js（1 小时）
- 从旧 server.js 逐段复制：模块导入 → .env 加载 → 常量 → 共享状态 → 工具函数 → 数据辅助函数
- 全部 `module.exports` 导出
- **目标**：context.js 跑 `node -e "require('./server/context')"` 不报错

### 第 2 步：创建 server/api/shared.js（1-2 小时）
- 从旧 server.js 复制 38 条路由的处理逻辑
- 替换直接引用为 ctx.xxx
- 格式：`module.exports = function(ctx) { return function handle(req, res) { ... }; };`

### 第 3 步：创建 server/api/overview.js 和 server/api/astro.js（1 小时）
- 从旧 server.js 复制 overview 13 条 + astro 4 条
- 特别处理 `/api/m1/` 命名空间冲突：overview.js 和 astro.js 的路由前缀都是 `/api/m1/`，但路径不同，需要按 pathname 精确匹配，不会冲突

### 第 4 步：创建 server/api/etf.js 和 server/api/trade.js（10 分钟）
- 只写骨架：Module.exports 返回空的 handle 函数，Agent B/C 后续自己填充

### 第 5 步：创建 server/server.js（30 分钟）
- 主入口：require context → 注册路由 → 静态文件服务 → listen
- 复制旧 server.js 的静态文件服务逻辑（public/ 目录）

### 第 6 步：8788 端口验证（30 分钟）
- 启动 `node server/server.js`
- curl 关键端点验证：`/api/snapshot`、`/api/m1/data/overview`、`/api/market/status`、`/health`
- 对比 8787 和 8788 的返回是否一致

### 第 7 步（未来）：切换回 8787
- 所有路由迁移 + 验证通过后
- 停旧 server.js，改 context.js 里 PORT 为 8787，启动新骨架
- 删旧 server.js

## 验证清单

| 验证项 | 命令 | 预期 |
|--------|------|------|
| 骨架启动不报错 | `node server/server.js` | 打印 listening on 8788 |
| 公共路由正常 | `curl http://127.0.0.1:8788/api/snapshot` | 返回 JSON 快照 |
| 概览路由正常 | `curl http://127.0.0.1:8788/api/m1/data/overview` | 返回概览 JSON |
| 天时路由正常 | `curl http://127.0.0.1:8788/api/m1/data/astro_calendar` | 返回日历 JSON |
| 静态文件正常 | `curl http://127.0.0.1:8788/` | 返回 HTML |
| 旧 8787 不受影响 | `curl http://127.0.0.1:8787/api/snapshot` | 仍然正常 |
| n8n 工作流不受影响 | n8n 手动执行 M1-C | stdout 正常 |

## 风险与应对

| 风险 | 应对 |
|------|------|
| context.js 漏抽了某个变量 | 运行时报错 `ctx.xxx is undefined`，对照旧 server.js 补上 |
| 路由分发顺序导致匹配错误 | 按 shared → overview → astro → etf → trade 顺序注册，精确匹配优先 |
| `/api/m1/` 前缀冲突 | overview 和 astro 都是精确 pathname 匹配，不会覆盖 |
| 8788 验证通过但 8787 切换时翻车 | 切换前在服务器上同时跑双端口观察一天 |
