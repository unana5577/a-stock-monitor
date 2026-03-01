# 新闻板块 API 对接文档

**更新时间**: 2026-02-25 13:52
**对接人**: Trae

---

## 📁 数据文件位置

```
/Users/una5577/Documents/trae_projects/a-stock-monitor/data/news/
```

**文件命名**: `YYYY-MM-DD.json`（如 `2026-02-25.json`）

> ⚠️ 注意：数据统一存储在 `data/news/` 目录，不是 `openclaw_workspace/data/news/`

---

## 📊 数据结构

### 文件结构（JSON 文件存储）

```json
{
  "date": "2026-02-25",
  "fetch_time": "2026-02-25T13:00:16",
  "source": "akshare/stock_news_main_cx",
  "stats": {
    "total": 100,
    "kept": 55,
    "filtered": 45,
    "by_type": {"宏观": 8, "地缘": 20, "行业": 27},
    "by_sector": {"半导体": 8, "云计算": 12, "有色金属": 10, "新能源": 2},
    "by_sentiment": {"利好": 6, "中性": 37, "利空": 12}
  },
  "news": [...]
}
```

### 单条新闻字段

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `news_id` | string | 新闻唯一ID（MD5） | `"143a0a675703dd927ceadf0c1cf1a3b4"` |
| `title` | string | 标题（最多20字，提取机构+主体+动作） | `"瑞银发布锂市场将出现实质性短缺"` |
| `content` | string | 内容摘要 | `"就在一个月前，韩国股市基准指数..."` |
| `source` | string | 来源 | `"东方财富"` |
| `url` | string | 原文链接 | `"https://database.caixin.com/..."` |
| `tag` | string | 标签 | `"市场动态"` |
| `fetch_time` | string | 抓取时间 | `"2026-02-25T13:00:16"` |

### classify 分类字段

| 字段 | 类型 | 说明 | 可能值 |
|------|------|------|--------|
| `type` | string | 新闻类型 | `"宏观"` / `"地缘"` / `"行业"` |
| `type_keywords` | array | 匹配的类型关键词 | `["央行", "利率"]` |
| `sector` | string \| null | 所属板块 | `"半导体"` / `"云计算"` / `"新能源"` / `"有色金属"` / `"商业航天"` / `"创新药"` / `"通讯设备"` / `null` |
| `sector_keywords` | array | 匹配的板块关键词 | `["芯片", "存储芯片"]` |
| `sentiment` | number | 情绪值 | `1`（利好）/ `0`（中性）/ `-1`（利空） |
| `sentiment_text` | string | 情绪文本 | `"利好"` / `"中性"` / `"利空"` |
| `level` | string | 优先级等级 | `"P0"` / `"P1"` / `"P2"` / `"P3"` |

### 单条新闻示例

```json
{
  "news_id": "143a0a675703dd927ceadf0c1cf1a3b4",
  "title": "瑞银发布锂市场将出现实质性短缺",
  "content": "近日瑞银报告发表观点，称2026 年全球锂市场将出现实质性短缺，锂价进入"第三次锂价超级周期"，并大幅上调锂价预期",
  "source": "东方财富",
  "url": "https://database.caixin.com/2026-02-25/102416745.html?cxapp_link=true",
  "tag": "市场动态",
  "fetch_time": "2026-02-25T13:00:16",
  "classify": {
    "type": "行业",
    "type_keywords": [],
    "sector": "有色金属",
    "sector_keywords": ["锂市场", "锂价"],
    "sentiment": 1,
    "sentiment_text": "利好",
    "level": "P1"
  }
}
```

---

## 🌐 API 接口

### 1. GET /api/news - 获取新闻列表

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `date` | string | ✅ | 日期，格式 `YYYY-MM-DD` |
| `sector` | string | ❌ | 板块筛选 |
| `level` | string | ❌ | 等级筛选 `P0`/`P1`/`P2`/`P3` |
| `limit` | number | ❌ | 返回数量，默认50，最大500 |

**示例**:
```bash
# 获取今日全部新闻
curl "http://localhost:8787/api/news?date=2026-02-25"

# 筛选半导体板块
curl "http://localhost:8787/api/news?date=2026-02-25&sector=半导体"

# 筛选 P0 级新闻，返回10条
curl "http://localhost:8787/api/news?date=2026-02-25&level=P0&limit=10"
```

**响应**:
```json
{
  "date": "2026-02-25",
  "total": 55,
  "filtered": 55,
  "news": [
    {
      "news_id": "xxx",
      "title": "...",
      "content": "...",
      "source": "东方财富",
      "url": "...",
      "publish_time": "2026-02-25T13:00:16",
      "related_stocks": [],
      "country": "中国",
      "classify": {
        "type": "行业",
        "sector": "半导体",
        "sentiment": 1,
        "level": "P1"
      }
    }
  ]
}
```

---

### 2. GET /api/news/heat - 获取热度统计

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `date` | string | ✅ | 日期，格式 `YYYY-MM-DD` |

**示例**:
```bash
curl "http://localhost:8787/api/news/heat?date=2026-02-25"
```

**响应**:
```json
{
  "date": "2026-02-25",
  "total_news": 55,
  "by_type": {
    "行业": 27,
    "地缘": 20,
    "宏观": 8
  },
  "by_sector": {
    "半导体": 8,
    "云计算": 12,
    "有色金属": 10,
    "新能源": 2
  },
  "by_sentiment": {
    "利好": 6,
    "中性": 37,
    "利空": 12
  },
  "by_level": {
    "P0": 24,
    "P1": 4,
    "P2": 23,
    "P3": 4
  },
  "by_type_sentiment": {
    "行业": {"利好": 4, "中性": 19, "利空": 4},
    "地缘": {"利好": 1, "中性": 14, "利空": 5},
    "宏观": {"利好": 1, "中性": 4, "利空": 3}
  },
  "by_sector_sentiment": {
    "半导体": {"利好": 2, "中性": 5, "利空": 1},
    "云计算": {"利好": 0, "中性": 8, "利空": 4},
    "有色金属": {"利好": 1, "中性": 8, "利空": 1},
    "新能源": {"利好": 1, "中性": 1, "利空": 0}
  }
}
```

---

## 📋 统计字段说明

| 字段 | 说明 |
|------|------|
| `by_type` | 按新闻类型统计数量 |
| `by_sector` | 按行业板块统计数量 |
| `by_sentiment` | 总体情绪分布 |
| `by_level` | 按优先级等级统计 |
| `by_type_sentiment` | 按类型分组的情绪分布（如：宏观新闻中利好/中性/利空各多少） |
| `by_sector_sentiment` | 按行业分组的情绪分布（如：半导体新闻中利好/中性/利空各多少） |

---

## 🏷️ 分类定义

### 新闻类型 (type)
- **宏观**: 央行、美联储、利率、GDP、CPI、PMI、政策、监管等
- **地缘**: 战争、冲突、制裁、关税、贸易战、中美关系等
- **行业**: 行业相关新闻

### 关注板块 (sector)
1. 半导体
2. 云计算
3. 新能源
4. 商业航天
5. 创新药
6. 有色金属
7. 通讯设备

### 情绪 (sentiment)
- `1` / `"利好"`: 扶持、补贴、增长、突破、超预期、政策支持等
- `0` / `"中性"`: 无明显利好/利空
- `-1` / `"利空"`: 限制、监管、处罚、下跌、暴雷、造假等

### 等级 (level)
- **P0**: 宏观+利空/利好，或地缘重大事件
- **P1**: 行业核心利好新闻
- **P2**: 行业一般新闻
- **P3**: 其他

---

## ⏰ 数据更新频率

每天 12 个时间点自动抓取：
- 开盘前：09:00
- 上午盘中：09:30, 10:00, 10:30, 11:00, 11:30
- 下午盘中：13:00, 13:30, 14:00, 14:30, 15:00
- 晚间总结：21:30

---

## 🔗 相关文件

- 后端代码: `openclaw_workspace/backend/`
- 数据文件: `data/news/`
- 日志文件: `openclaw_workspace/logs/`
- 详细文档: `openclaw_workspace/docs/新闻板块后端文档.md`

---

**如有问题，联系银狐 🦊**
