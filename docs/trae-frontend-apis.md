# 前端接口说明（Trae）

## 概览页

### /api/snapshot/latest
- 用途：卡片数值、情绪与量能、AI 文本
- 查询：ai=1 获取 AI 文本
- 字段：
  - day: YYYY-MM-DD
  - ts: number
  - indices: { sse, szi, gem, star, hs300, csi2000, avg }
    - price: number|null
    - pct: number|null
    - series: array
  - bonds: { gov, tl, t, tl2603, t2603 }
    - price: number|null
    - pct: number|null
    - series: array
  - sectors: { bank, broker, insure }
    - pct: number|null
    - series: array
  - sentiment:
    - volume: number
    - volumeStr: string
    - volumeCmp: { pct:number, delta:number }|null
    - volumeSeries: [{ time, volume }]
    - volumeSeriesYday: [{ time, volume }]
  - aiBrief: { title, detail }
  - aiText: string

### /api/minute/:code
- 用途：分钟曲线（指数/国债/金融板块）
- code：sse/szi/gem/star/hs300/csi2000/avg/t/tl/bank/broker/insure/gov
- 字段：
  - day: YYYY-MM-DD
  - prevClose: number|null
  - latest: { time, open, close }|null
  - series: [{ time, open, close }]

### /api/overview/history
- 用途：180 日小曲线与成交额历史
- 字段：
  - day: YYYY-MM-DD
  - series: { key: [{ date, open, high, low, close, pct, amount, volume }] }
  - volume: [{ date, amount }]

### /api/market/breadth
- 用途：涨跌家数
- 字段：{ up:number, down:number, total?:number }

### /api/prompt/stock-daily
- 用途：Prompt 调试
- 字段：{ text:string }

### /api/ai/debug
- 用途：AI 调试
- 方法：POST { prompt }
- 字段：{ text } | { error }

## 行情页

### /api/sector/history
- 用途：板块历史走势与分钟补充
- 查询：rt=0/1、days、sectors
- 字段：
  - history: { name: [{ date, open, high, low, close, pct, amount, volume, turnover }] }
  - minute: { name: { series:[{ time, open, close }], prevClose } }
  - indicators: object
  - correlations: [{ pair:[a,b], val }]
  - watch: string[]

### /api/sector/rank
- 用途：涨跌幅榜
- 字段：{ up:[{ name, pct }], down:[{ name, pct }] }

### /api/sector/lifecycle
- 用途：板块生命周期
- 查询：rt=0/1、days、sectors
- 字段：{ items:[{ 板块名称, 基准指数, 相关性, 板块位置, 动能, 资金行为, 阶段信号, 显示名称, 含义, 操作建议, 归因说明, 乖离对比, 指标数据 }] }

### /api/ai/sector-analysis
- 用途：板块 AI 文本
- 字段：{ text } | { error }

### /api/prompt/sector-analysis
- 用途：板块 Prompt 调试
- 字段：{ text }

### /api/sector/watch-list
- 用途：自选板块
- GET 字段：{ watch_list:string[] }
- POST 入参：{ watch_list:string[] }

## 新闻页

### /api/news
- 用途：新闻列表
- 查询：date, sector, level, limit
- 字段：
  - date: YYYY-MM-DD
  - total: number
  - filtered: number
  - news: [{ news_id, title, content, source, url, publish_time, related_stocks, country, classify }]
  - classify: { type, sector, sentiment, level }

### /api/news/heat
- 用途：新闻热度
- 查询：date
- 字段：{ date, total_news, by_type, by_sector, by_sentiment, by_level }

## 说明
- 前端当前新闻为 mock，接入后直接用 /api/news 与 /api/news/heat。
- 盘中展示优先分钟序列，收盘后用日线历史。
