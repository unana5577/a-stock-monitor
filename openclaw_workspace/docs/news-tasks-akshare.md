# 新闻模块开发任务 - 基于 akshare

更新时间：2026-02-23 23:50
负责人：GLM-4.7
状态：待确认后启动

---

## 变更说明
- ❌ 取消：自己写爬虫
- ✅ 改用：akshare 官方接口

---

## Phase 2: 新闻模块（简化后预计 1-2 天）

### Task 2.1: 新闻获取脚本
**负责人**：GLM-4.7 → Codex 执行
**数据源**：
- `ak.stock_news_main_cx()` - 东方财富主力新闻（100条）
- `ak.stock_news_em(symbol)` - 个股新闻（按需）

**输出**：
```python
# fetch_news.py
import akshare as ak
import json
from datetime import datetime

def fetch_main_news():
    df = ak.stock_news_main_cx()
    news_list = []
    for _, row in df.iterrows():
        news_list.append({
            "news_id": hash(row['url']),
            "title": row['summary'][:50],
            "content": row['summary'],
            "source": "东方财富",
            "url": row['url'],
            "tag": row['tag'],
            "fetch_time": datetime.now().isoformat()
        })
    return news_list
```

**验收标准**：
- [ ] fetch_news.py 能正常运行
- [ ] 输出 data/news/2026-02-23.json
- [ ] 去重逻辑（按 url）

---

### Task 2.2: 新闻分类（NLP）
**负责人**：GLM-4.7
**分类维度**：
- 类型：宏观/地缘/行业/个股
- 板块：半导体/云计算/新能源/商业航天/创新药/有色金属/通讯设备
- 情绪：利好(+1)/中性(0)/利空(-1)
- 等级：P0(极端)/P1(高)/P2(中)/P3(低)

**实现方式**：
- 方案A：关键词匹配（简单，先实现）
- 方案B：调用 GLM-4.7 API（准确，后期优化）

**验收标准**：
- [ ] classify_news.py 能运行
- [ ] 输出包含 sentiment/sector/level 字段
- [ ] 准确率 > 70%

---

### Task 2.3: 新闻接口
**负责人**：GLM-4.7
**接口**：
- `GET /api/news` - 返回新闻列表
- `GET /api/news/heat` - 返回板块热度

**验收标准**：
- [ ] 接口可访问
- [ ] 支持参数：?date=2026-02-23&sector=半导体

---

## 存储格式

### data/news/2026-02-23.json
```json
{
  "date": "2026-02-23",
  "fetch_time": "2026-02-23T23:50:00",
  "total": 100,
  "news": [
    {
      "news_id": "abc123",
      "title": "证监会发布新规",
      "content": "...",
      "source": "东方财富",
      "url": "https://...",
      "tag": "监管",
      "fetch_time": "2026-02-23T23:50:00",
      "classify": {
        "type": "宏观",
        "sector": null,
        "sentiment": -1,
        "level": "P1"
      }
    }
  ]
}
```

---

## 定时任务

| 时间 | 动作 |
|------|------|
| 每日 8:00 | 获取隔夜新闻 |
| 每日 15:30 | 获取盘中新闻 |
| 每日 20:00 | 汇总当日新闻 |

---

## ✅ 待确认

1. akshare 接口满足需求？
2. 分类用关键词先实现，后期再上 GLM-4.7 API？
3. 确认后让 GLM-4.7 开始写代码？

---

## 云服务器评估

| 场景 | 本地够用？ |
|------|-----------|
| 开发测试 | ✅ 够 |
| 每日定时获取新闻 | ✅ 够（手动或定时任务）|
| 7x24 自动运行 | ❌ 需要云 |

**建议：先本地验证，稳定后再上云**
