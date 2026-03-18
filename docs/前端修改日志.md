# 前端修改日志

## 2026-03-18

### 1. 涨跌家数数据源统一

**问题**：前端涨跌家数显示旧数据（2231/3124），即使缓存文件已更新为3554/1830

**原因**：
1. 前端有两个数据源获取 breadth：`/api/market/breadth` 和 `/api/snapshot`
2. 两个接口可能返回不同的数据，导致前端混乱
3. `fetchBreadth()` 函数直接操作DOM，没有更新Vue响应式变量

**修改文件**：
- `server.js`：删除 snapshot 中的 breadth 字段和相关缓存逻辑
- `public/ui.js`：
  - 删除从 snapshot 更新 breadth 的逻辑
  - 修复 fetchBreadth() 函数，改为更新 breadth.value 响应式变量
- `scripts/market_breadth_spot.py`：添加缓存写入功能

**数据流**：
- 前端 `fetchBreadth()` → `/api/market/breadth` → `readBreadthCache()` → 缓存文件

**提交**：`c4d9164` - fix: 统一涨跌家数数据源，修复前端显示为空的问题

---

### 2. UI简化

**修改内容**：
1. 删除了页面右上角的刷新按钮和时间显示
2. 修复了 AI 解读卡片的"上次更新时间"显示逻辑

**修改文件**：
- `public/index.html`：删除刷新按钮和时间显示，修复HTML格式
- `public/ui.js`：修复 aiUpdatedAt 更新逻辑（只要有AI数据就更新时间）

**提交**：`d0987f9` - feat: 简化UI，修复AI更新时间显示

---

### 3. 成交额曲线显示问题修复

**问题**：成交额曲线先展示蓝线（昨日均线），才展示正确的数据

**原因**：ECharts `setOption` 默认会合并数据，而不是替换旧数据

**修复**：在 `renderVolumeSpark` 函数中添加 `notMerge:true` 选项

**提交**：`39b4fc5` - fix: 修复成交额曲线显示旧蓝线的问题

---

## 2026-03-17

### 1. 涨跌家数实时更新

**修改内容**：
- 实现午休时间显示当日数据逻辑
- 添加涨跌家数显示与修复数据更新逻辑

**提交**：`6acfa7b`, `9275632`
