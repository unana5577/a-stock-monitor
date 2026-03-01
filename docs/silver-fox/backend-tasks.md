# 后端任务执行计划

创建时间：2026-02-24
负责人：银狐
执行者：Codex

---

## 紧急任务：修复 /api/snapshot

**问题**：API 返回 2026-02-13 的旧数据，而不是今天的实时数据
**影响**：前端分时图无法显示今天的实时行情
**位置**：`~/Documents/trae_projects/a-stock-monitor/server.js`
**修复方案**：
1. 检查 `/api/snapshot` 的逻辑
2. 确保返回今天的日期（2026-02-24）
3. 检查数据缓存逻辑是否正确

---

## 任务 2：实现新闻 API

### /api/news
**功能**：返回当日新闻列表
**参数**：
- `date`：日期（默认今天）
- `sector`：板块过滤（可选）
- `type`：类型过滤（可选，宏观/地缘/行业）
- `level`：优先级过滤（可选，P0/P1/P2/P3）

**响应格式**：
```json
{
  "date": "2026-02-24",
  "total": 50,
  "filtered": 30,
  "news": [
    {
      "news_id": "xxx",
      "title": "...",
      "content": "...",
      "source": "财联社",
      "url": "https://...",
      "classify": {
        "type": "宏观",
        "sector": null,
        "sentiment": 1,
        "level": "P1"
      }
    }
  ]
}
```

### /api/news/heat
**功能**：返回板块热度统计
**响应格式**：
```json
{
  "date": "2026-02-24",
  "heat": {
    "半导体": { "count": 10, "sentiment": 0.5 },
    "云计算": { "count": 8, "sentiment": 0.3 },
    "新能源": { "count": 5, "sentiment": -0.2 },
    ...
  }
}
```

---

## 任务 3：数据格式规范
详见 `news-rules.md`

---

## 执行顺序
1. 先修复 snapshot bug（紧急）
2. 实现新闻 API
3. 确保数据格式符合 Trae 的要求

---

## 验收标准
- [ ] `/api/snapshot` 返回今天的数据
- [ ] `/api/news` 返回正确的格式
- [ ] `/api/news/heat` 返回正确的统计
- [ ] 新闻数据文件格式正确（纯数组 JSON）
