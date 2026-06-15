# ETF 页面三项优化方案

## 一、现状诊断

### 1.1 半导体材料回补失败
- **根因**：本地 Python 缺少 `akshare` 模块，`m1_backfill.py` 启动即报错
- **现状**：`sh562590` 已在 `sector-proxy.json`，但 `data/etf/minute/sh562590/` 和 `data/etf/daily/sh562590/` 目录不存在
- **影响**：柱状图、归一分析、生命周期卡片里都看不到这只 ETF

### 1.2 隐藏功能缺失
- 当前管理面板无隐藏/可见开关
- `sector-proxy.json` 的 `etf_meta` 里无 `hidden` 字段

### 1.3 涨跌分布用的是 pct
- 当前左右柱状图都基于 `currentPrices[code].pct`
- 用户希望换成成交额对比

---

## 二、改动方案

### 2.1 回补进度弹窗（一个下拉面板）

**位置**：ETF 管理弹窗底部，点击"回补数据"展开

**结构**：
```
┌─ ETF 板块管理 ─────────────────────────────────┐
│  共 10 只 ETF                    [新增 ETF] [回补数据 ▾] │
│  ┌────────────────────────────────────────┐   │
│  │  回补数据 (点击行触发)                    │   │
│  │  半导体材料  sh562590  [回补] ● 完成     │   │
│  │  云计算      sh516510  [回补] ● 完成     │   │
│  │  ...                                   │   │
│  └────────────────────────────────────────┘   │
│  table...                                     │
└────────────────────────────────────────────────┘
```

**逻辑**：
- 点击"回补数据"展开一个 `q-panel` 内嵌列表
- 每行：名称 + 代码 + `[回补]` 按钮 + 状态指示（● 空闲 / ◌ 请求中 / ✓ 完成 / ✗ 失败）
- 点击某只 ETF 的 `[回补]` → `POST /api/m1/run` → 轮询检查 `data/etf/daily/{code}/daily.jsonl` 是否生成
- **不轮询**，改为：请求发出后 8 秒自动检查文件是否存在，存在 = 成功，不存在 = 失败
- 回补成功后自动刷新 overview + minute

### 2.2 隐藏开关

**数据模型**：`sector-proxy.json` 的 `etf_meta` 加 `hidden: true`

**前端**：
- 管理面板表格加一列 "显示"：checkbox，勾选 = 可见（默认），取消 = 隐藏
- 页面各板块过滤：`etfSymbols` → 实际显示用 `visibleEtfSymbols` = filter 掉 hidden 的
- `server/api/etf.js` 的 POST/PUT 支持 `hidden` 字段
- `buildEtfManagerRows()` 返回 `hidden` 字段

### 2.3 涨跌分布改为成交额对比

**数据源**：`currentPrices[code]` 新增 `amount` 字段（从 minute data 最后一笔取）

**左图（阵营均值）**：科技平均成交额 vs 资源平均成交额（元）

**右图（个股权重）**：每只 ETF 当天累计成交额，科技蓝/资源绿

**刷新频率**：`fetchMinuteData` 改为 10 分钟间隔（从 60 秒 → 600 秒）

**单位**：自动格式化（亿/万/元），y 轴标签 `formatter` 处理

---

## 三、涉及文件

| 文件 | 改动 |
|------|------|
| `pages/etf/index.html` | 管理弹窗加显示列 + 回补面板 + 回补状态标签 |
| `pages/etf/ui.js` | `visibleEtfSymbols` computed + `triggerBackfillRow` + `hidden` 字段 + 10min 刷新 + amount 图表 |
| `pages/etf/server.js` | debug lifecycle 读取 hidden 字段过滤 |
| `server/api/etf.js` | POST/PUT 支持 `hidden` 字段 |
| `data/sector-proxy.json` | 存量 `etf_meta` 加 `hidden: false` |

---

## 四、不影响

- 不碰 `server/api/shared.js`、`server/api/overview.js`
- 不碰其他 Agent 目录
- 不碰 `data/` 存量日线/分钟数据文件

---

## 五、验证步骤

1. 刷新页面 → 管理弹窗 → 看到"显示"列 + "回补数据"按钮
2. 点击"回补数据"展开 → 看到 10 只 ETF 列表
3. 取消某只 ETF 勾选 → 该 ETF 从页面消失，管理面板里仍显示（隐藏状态）
4. 刷新页面 → 隐藏的 ETF 确实不出现在柱状图/归一分析/生命周期里
5. 等 10 分钟 → 涨跌分布图表数据自动刷新
