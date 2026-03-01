# A 股监控（a-stock-monitor）

给“日常看盘 + 板块轮动 + 新闻聚合”用的轻量站点：部署到服务器后，打开域名即可用。非交易日会自动回退到最近交易日数据，避免空白。

## 能做什么

- **看盘概览**：指数/量能/情绪（含涨跌家数）快速浏览，支持分钟线与历史序列
- **板块轮动**：关注板块池（可配置）、板块历史/生命周期/轮动分析，支持盘中结构（summary/detail）
- **新闻聚合**：按类型/行业/情绪/级别分类与热度统计，支持按日期筛选
- **本地缓存**：数据落盘到 `data/` 与 `runtime/`，减少重复抓取与接口延迟
- **可选 AI**：接入百炼兼容接口（DashScope），生成看盘简报与板块轮动分析

## 技术栈与结构

- **Node**：`server.js` 提供 API + 静态托管前端
- **前端**：`public/` 下的静态页面（内置 CDN 版本的 Vue/ECharts）
- **Python**：抓取与计算（akshare 为主），脚本在仓库根目录
- **存储**：默认仅使用本地文件（无需数据库）

```
a-stock-monitor/
├── public/                 # 前端静态页
├── server.js               # Node API + 静态托管
├── fetch_*.py              # 数据抓取/计算脚本
├── data/                   # 缓存与归档（本地文件）
└── runtime/                # 运行时缓存（本地文件）
```

## 快速开始（本地）

```bash
npm install
pip install -U pip
pip install akshare pandas numpy
PORT=8787 node server.js
```

打开：`http://localhost:8787/`

## 常用接口（节选）

- `GET /api/snapshot`：看盘快照（可带 `?ai=0` 关闭 AI 文本）
- `GET /api/overview/history`：概览历史序列
- `GET /api/news?date=YYYY-MM-DD&limit=50`：新闻列表
- `GET /api/news/heat?date=YYYY-MM-DD`：新闻热度统计
- `GET /api/sector/history?sectors=云计算,半导体&days=20`：板块历史（可不传，走默认板块池）
- `GET /api/sector/lifecycle?sectors=...&days=60`：板块生命周期
- `GET /api/sector/rotation?sectors=...&days=90`：板块轮动
- `GET /api/sector/rotation/intraday?view=summary`：盘中结构

## 可选：开启 AI 简报

在 `.env` 中配置（可参考 `.env.example`）：

- `DASHSCOPE_API_KEY`（或 `BAILIAN_API_KEY`）
- `BAILIAN_MODEL`（可选）

不配置 Key 也能正常使用，只是不生成 AI 文本。

## 免责声明

本工具仅供学习和参考，不构成任何投资建议。股市有风险，入市需谨慎，盈亏自负。
