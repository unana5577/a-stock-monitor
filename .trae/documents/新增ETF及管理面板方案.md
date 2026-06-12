# 新增 ETF 及管理面板方案

## 目标

1. 新增 2 只 ETF：sh562590（半导体材料ETF）、sh513870（纳指科技ETF），归入科技/硬件
2. 在 ETF行情 Tab 的"归一分析"卡片右上角加一个 **[管理]** 按钮，点击弹出 ETF 管理弹窗，支持增删改查
3. 后续新增 ETF 不再需要改代码，直接页面操作即可

## 入口位置

```
┌─ ETF行情 Tab ─────────────────────────────────────────────┐
│  归一分析 (Normalized Analysis)      [当日][5日][20日][60日] [管理] │  ← 新增按钮
│  ┌──────────────────────────────────────────────────┐    │
│  │           归一曲线图 (ECharts)                     │    │
│  └──────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────┘
```

点击 **[管理]** → 弹出弹窗，弹窗内：
- 顶部：标题"ETF 板块管理" + 关闭按钮
- 表格：名称 | 代码 | 阵营 | 子分类 | 操作（编辑/删除），列出所有 ETF
- 表格上方：**[+ 新增 ETF]** 按钮 + "共 N 只 ETF"
- 新增/编辑：子弹窗表单（名称输入 + 代码输入 + 阵营下拉 + 子分类级联下拉 + 保存/取消）
- 风格：与现有 `tradeConfirmOpen` 弹窗一致，遮罩层 + 白色圆角卡片

## 后端改动

在 `server.js` 中新增 3 个 API（紧挨现有 `/api/sector/profile`）：

- **GET `/api/sector/manage`** — 读取 `sector-proxy.json`，返回所有 ETF 及分类信息
- **POST `/api/sector/manage`** — 新增或更新 ETF，校验代码格式，写入 `sector-proxy.json`
- **DELETE `/api/sector/manage?name=xxx`** — 删除 ETF 映射，不删历史数据文件

## 关键脚本动态化

以下脚本当前硬编码 ETF 列表，改为从 `sector-proxy.json` 读取：

- `treasolo/m1_minute_fetch_etf.py`：`--symbols` 未传时自动读配置文件
- `treasolo/m1_lifecycle.py`：ETF 名称从配置文件读取
- `波段策略/policy_runner.py`：ETF 列表从配置文件读取
- `波段策略/market_state.py`：按 category 字段动态分组科技/资源
- `public/ui_m1.js`：页面加载时调用 API 获取 ETF 列表，保留硬编码作为 fallback

## 不需要改动的

- n8n workflows（通过 server.js 触发，参数由 n8n 传入）
- `m1_backfill.py`（已有 fallback 逻辑）
- `m1_warmup.py`、`m1_ai_aggregator.py`、`m1_etf_intraday_features.py`（已从配置文件动态读取）
- 生命周期卡片网格、持仓分布进度条（自动适配 ETF 数量变化）

## 实施步骤

1. 编辑 `data/sector-proxy.json`，追加 2 只新 ETF
2. 在 `server.js` 中新增 3 个管理 API
3. 在 `index_m1.html` 归一分析区域加按钮 + 弹窗 HTML
4. 在 `ui_m1.js` 中加弹窗状态和 CRUD 方法
5. 改造 5 个 Python/JS 文件从配置文件动态读取
6. rsync 到服务器 + 重启，验证

## 验证

- 前端展示 11 只 ETF（含新增 2 只）
- 归一分析右上角 **[管理]** 可打开弹窗
- 弹窗内可查看、新增、编辑、删除 ETF
- 新增/编辑保存后前端实时刷新
- 删除后对应卡片消失
- 非法 ETF 代码被后端拒绝
