# A股新闻因子模块设计方案

> 版本: v1.0  
> 设计日期: 2026-02-23  
> 适用场景: A股量化策略系统

---

## 1. 新闻分类体系

### 1.1 一级分类：新闻类型

```
├── 宏观新闻（Macro）
│   ├── 中国（CN）
│   ├── 美国（US）
│   └── 日本（JP）
│
├── 地缘政治（Geopolitics）
│   ├── 战争/冲突
│   ├── 贸易摩擦
│   └── 制裁/政策变动
│
└── 行业新闻（Sector）
    ├── 利空（Bearish）
    ├── 利好（Bullish）
    └── 中性（Neutral）
```

### 1.2 影响等级体系

#### 宏观新闻影响等级

| 等级 | 中国（CN） | 美国（US） | 日本（JP） |
|------|-----------|-----------|-----------|
| **P0-极端** | 重大政策转向（地产救市、金融改革）<br>系统性风险事件（银行危机） | 美联储紧急加息/降息<br>债务违约危机<br>对华重大制裁 | 日央行货币政策转向<br>日元极端波动 |
| **P1-高** | 降准/降息<br>重要经济数据（GDP/CPI） | 美联储议息会议<br>非农数据<br>中美高层会谈 | 日央行议息<br>日美贸易协议 |
| **P2-中** | 行业监管政策<br>地方政策调整 | 美股重大波动<br>科技监管 | 日股波动<br>区域贸易 |
| **P3-低** | 常规经济数据<br>专家观点 | 常规数据发布 | 常规新闻 |

#### 地缘政治影响等级

| 等级 | 影响描述 | 资金情绪影响 | 操作建议 |
|------|---------|-------------|---------|
| **G0-极端** | 大规模战争、中美直接冲突 | 极端避险，资金外流 | 空仓/降仓至20% |
| **G1-高** | 局部冲突升级、重大制裁 | 强避险，板块分化 | 回避敏感板块 |
| **G2-中** | 贸易摩擦、外交争端 | 短期波动，情绪扰动 | 降低仓位 |
| **G3-低** | 常规外交事件 | 影响有限 | 正常操作 |

#### 行业新闻影响等级

| 等级 | 利空类型 | 利好类型 | 时效性判断 |
|------|---------|---------|-----------|
| **S0-极端** | 行业取缔/禁令<br>重大财务造假<br>龙头暴雷 | 重大政策扶持<br>颠覆性技术突破<br>行业整合机遇 | 长期影响（>6个月） |
| **S1-高** | 监管加强<br>产品事故<br>业绩大幅下滑 | 政策补贴<br>订单大幅增长<br>业绩超预期 | 中期影响（1-6个月） |
| **S2-中** | 价格下跌<br>竞争加剧<br>负面舆情 | 产品涨价<br>市场份额提升<br>正面宣传 | 短期影响（1-4周） |
| **S3-低** | 个股负面<br>分析师下调 | 个股利好<br>分析师上调 | 超短期（<1周） |

### 1.3 新闻标签系统

每条新闻应包含以下标签：

```json
{
  "news_id": "unique_id",
  "tags": {
    "type": ["macro", "geopolitics", "sector"],
    "region": ["CN", "US", "JP", null],
    "sector": ["新能源", "半导体", "医药", null],
    "sentiment": ["bullish", "bearish", "neutral"],
    "impact_level": [0, 1, 2, 3],
    "duration": ["long_term", "medium_term", "short_term"],
    "confidence": 0.0-1.0
  }
}
```

---

## 2. 新闻筛选规则

### 2.1 重要新闻判定标准

#### ✅ 必须收录（核心规则）

**宏观新闻：**
- 央行货币政策（利率、准备金）
- 政府重大政策发布
- 重要经济数据（GDP、CPI、PMI、社融）
- 监管部门重磅新规
- 中美日高层互动

**地缘政治：**
- 战争/冲突爆发或升级
- 重大制裁/反制措施
- 贸易协议签署/终止
- 台海、南海、朝鲜半岛局势

**行业新闻：**
- 行业政策变动
- 龙头企业重大事件
- 产业链核心环节变化
- 技术突破/颠覆

#### ⚠️ 条件收录（需判断）

- 个股利空/利好：仅限龙头股或权重股
- 分析师观点：仅限知名机构
- 市场传闻：需验证源可信度
- 季节性新闻：需过滤重复性

#### ❌ 不收录

- 常规公司公告
- 媒体重复报道
- 无实质内容的评论
- 营销性质文章

### 2.2 利好长期性判断框架

#### 判断维度

| 维度 | 长期利好 | 短期炒作 |
|------|---------|---------|
| **政策支持** | 写入国家战略<br>有配套资金 | 口头表态<br>无具体措施 |
| **业绩影响** | 订单可见、业绩可测算 | 概念性强、业绩模糊 |
| **行业格局** | 提升行业集中度<br>改善竞争格局 | 无实质变化 |
| **技术壁垒** | 有核心技术<br>难以复制 | 技术门槛低 |
| **持续性** | 政策周期3-5年 | 事件驱动型 |

#### 利好质量评分

```
长期性得分 = 
  政策支持度 × 0.25 +
  业绩确定性 × 0.30 +
  行业改善度 × 0.20 +
  技术壁垒度 × 0.15 +
  持续时间 × 0.10

得分 >= 0.7 → 长期利好
得分 0.4-0.7 → 中期利好
得分 < 0.4 → 短期炒作
```

#### 利好信号示例

**✅ 真利好（长期）：**
- 新能源汽车购置税减免延长 → 直接影响销量，政策确定性高
- 半导体国产替代扶持 → 国家战略，持续3-5年
- 医保集采落地 → 不确定性消除，格局明朗

**⚠️ 需观察（中期）：**
- 某行业"十四五"规划 → 需看具体措施
- 龙头公司订单增长 → 需看可持续性

**❌ 伪利好（短期）：**
- 某概念股蹭热点 → 无业绩支撑
- 市场传闻某政策 → 未官宣
- 技术突破报道 → 无商业化路径

---

## 3. 数据结构设计

### 3.1 新闻存储格式

```python
# 新闻主表
class News:
    news_id: str              # UUID
    title: str                # 标题
    content: str              # 正文（可选存储）
    summary: str              # 摘要（AI生成）
    source: str               # 来源
    url: str                  # 原文链接
    publish_time: datetime    # 发布时间
    crawl_time: datetime      # 抓取时间
    
    # 分类标签
    news_type: str            # macro/geopolitics/sector
    region: str               # CN/US/JP/OTHER
    sector: List[str]         # ["新能源", "半导体"]
    sentiment: str            # bullish/bearish/neutral
    impact_level: int         # 0-3
    duration: str             # long/medium/short
    
    # 因子值
    impact_score: float       # 综合影响分数 [-1, 1]
    confidence: float         # 分类置信度 [0, 1]
    
    # 去重标识
    content_hash: str         # 内容哈希
    cluster_id: str           # 聚类ID（相似新闻）

# 新闻-板块关联表
class NewsSectorImpact:
    news_id: str
    sector_code: str          # 申万行业代码
    impact_direction: int     # 1利好 / -1利空 / 0中性
    impact_magnitude: float   # 影响强度 [0, 1]
    duration_months: int      # 预期持续时间

# 新闻热度表（按板块聚合）
class SectorNewsHeat:
    date: date
    sector_code: str
    news_count: int           # 新闻总数
    bullish_count: int        # 利好数
    bearish_count: int        # 利空数
    net_sentiment: float      # 净情绪 = (利好-利空)/总数
    weighted_score: float     # 加权影响分
    p0_count: int             # P0级新闻数
    p1_count: int             # P1级新闻数
```

### 3.2 去重逻辑

#### 多级去重机制

```python
# 1. URL去重（快速）
if url in url_set:
    skip

# 2. 标题相似度去重
title_similarity = cosine_similarity(title_embedding, existing_titles)
if title_similarity > 0.85:
    # 检查是否同一事件
    merge_or_skip()

# 3. 内容哈希去重
content_hash = hash(normalized_content)
if content_hash in hash_set:
    skip

# 4. 语义聚类去重（定期运行）
# 将24小时内的新闻聚类
clusters = semantic_clustering(news_list, threshold=0.75)
# 每个cluster保留最早或最权威的来源
```

#### 去重流程图

```
新新闻 → URL检查 → 标题相似度 → 内容哈希 → 语义聚类 → 入库
           ↓            ↓           ↓           ↓
         跳过      合并/跳过     跳过      保留最优
```

### 3.3 热度计算方式

#### 板块新闻热度公式

```python
# 基础热度
raw_heat = news_count_24h

# 加权热度（考虑影响等级）
weighted_heat = (
    p0_count * 4 +
    p1_count * 2 +
    p2_count * 1 +
    p3_count * 0.3
)

# 情绪加权热度
sentiment_heat = weighted_heat * (1 + 0.5 * abs(net_sentiment))

# 时间衰减热度（新闻时效性）
time_decay_heat = sum(
    impact_score * exp(-hours_ago / 24)
    for each news in 72h
)

# 最终热度（归一化到0-100）
final_heat = min(sentiment_heat * 10, 100)
```

#### 热度等级划分

| 热度值 | 等级 | 说明 |
|-------|------|------|
| 80-100 | 🔥 极热 | 市场高度关注，可能引发异动 |
| 60-80 | 🔥 热门 | 关注度较高，需要重点跟踪 |
| 40-60 | 📊 正常 | 常规关注度 |
| 20-40 | 📉 冷清 | 关注度低 |
| 0-20 | ❄️ 冰冷 | 几乎无新闻 |

---

## 4. 与策略的集成

### 4.1 新闻因子构建

#### 单因子设计

```python
# 1. 情绪因子
sector_sentiment_factor = net_sentiment  # [-1, 1]

# 2. 热度因子
sector_heat_factor = log(weighted_heat + 1) / log(max_heat + 1)  # [0, 1]

# 3. 影响强度因子
sector_impact_factor = (
    sum(impact_score * impact_level_weight)
    for news in sector_24h
) / normalizer

# 4. 时效性因子
sector_timeliness_factor = time_decay_heat / max_time_decay
```

#### 复合新闻因子

```python
# 新闻综合因子
news_factor = (
    sentiment_factor * 0.35 +
    heat_factor * 0.25 +
    impact_factor * 0.25 +
    timeliness_factor * 0.15
)

# 分板块因子值
sector_news_scores = {
    '新能源': 0.72,
    '半导体': 0.65,
    '医药': 0.45,
    '地产': 0.38,
    ...
}
```

### 4.2 与板块信号的融合

#### 信号融合框架

```python
# 原始板块信号（来自技术面/基本面）
raw_signal = {
    '新能源': 0.8,
    '半导体': 0.6,
    '医药': 0.5,
    ...
}

# 新闻因子调整
def adjust_signal_with_news(raw_signal, news_factor, market_state):
    adjusted = {}
    
    for sector, signal in raw_signal.items():
        news = news_factor.get(sector, 0.5)
        
        # 根据市场状态调整权重
        if market_state == 'extreme_fear':  # 地缘危机等
            news_weight = 0.5  # 新闻权重提高
        elif market_state == 'normal':
            news_weight = 0.2
        else:
            news_weight = 0.3
        
        # 融合信号
        adjusted[sector] = (
            signal * (1 - news_weight) +
            news * news_weight
        )
    
    return adjusted
```

#### 调整示例

| 板块 | 原始信号 | 新闻因子 | 调整后信号 | 调整原因 |
|------|---------|---------|-----------|---------|
| 新能源 | 0.80 | 0.72 | 0.784 | 利好确认 |
| 半导体 | 0.60 | 0.35 | 0.535 | 利空压制 |
| 医药 | 0.50 | 0.65 | 0.530 | 利好提升 |
| 地产 | 0.40 | 0.20 | 0.340 | 持续利空 |

### 4.3 权重动态调整机制

#### 基于波动率的调整

```python
def calculate_news_weight(market_volatility, news_intensity):
    """
    market_volatility: 市场波动率（0-1）
    news_intensity: 新闻强度（P0/P1数量）
    """
    base_weight = 0.2
    
    # 高波动时新闻更重要
    volatility_adj = base_weight * (1 + market_volatility)
    
    # 重大新闻密集时提高权重
    if news_intensity['p0'] > 0:
        intensity_adj = 0.5
    elif news_intensity['p1'] > 3:
        intensity_adj = 0.4
    else:
        intensity_adj = volatility_adj
    
    return min(intensity_adj, 0.6)  # 上限60%
```

#### 基于新闻准确率的调整

```python
# 跟踪历史新闻对股价的实际影响
class NewsAccuracyTracker:
    def calculate_accuracy(self, sector, lookback_days=90):
        # 对比新闻因子方向 vs 实际涨跌方向
        predictions = get_news_predictions(sector, lookback_days)
        actuals = get_sector_returns(sector, lookback_days)
        
        accuracy = directional_accuracy(predictions, actuals)
        return accuracy
    
    def adjust_weight(self, sector, base_weight):
        accuracy = self.calculate_accuracy(sector)
        
        # 准确率越高，权重越大
        if accuracy > 0.7:
            return base_weight * 1.5
        elif accuracy > 0.55:
            return base_weight
        else:
            return base_weight * 0.5
```

### 4.4 风控规则

#### 新闻驱动的风控

```python
class NewsRiskControl:
    def check_risk(self, portfolio, news_events):
        alerts = []
        
        # 1. 极端新闻检查
        if news_events.has_p0_news():
            alerts.append({
                'level': 'CRITICAL',
                'action': 'REDUCE_POSITION',
                'target': 'ALL',
                'reason': '极端事件，建议降仓至50%'
            })
        
        # 2. 板块利空检查
        for sector, exposure in portfolio.exposures.items():
            if news_events.has_s0_bearish(sector):
                alerts.append({
                    'level': 'HIGH',
                    'action': 'EXIT_SECTOR',
                    'target': sector,
                    'reason': f'{sector}出现极端利空'
                })
        
        # 3. 连续利空检查
        for sector in portfolio.sectors:
            bearish_days = news_events.consecutive_bearish_days(sector)
            if bearish_days >= 3:
                alerts.append({
                    'level': 'MEDIUM',
                    'action': 'REDUCE_SECTOR',
                    'target': sector,
                    'reason': f'{sector}连续{bearish_days}天利空'
                })
        
        return alerts
```

---

## 5. 技术实现建议

### 5.1 数据源推荐

#### 专业数据源

| 数据源 | 优势 | 成本 | 推荐度 |
|-------|------|------|--------|
| **TrendRadar** | 实时舆情、情绪分析 | 高 | ⭐⭐⭐⭐⭐ |
| **同花顺iFinD** | A股专业、数据全面 | 中高 | ⭐⭐⭐⭐⭐ |
| **万得Wind** | 专业机构标准 | 高 | ⭐⭐⭐⭐ |
| **东方财富** | 数据丰富、性价比高 | 低 | ⭐⭐⭐⭐ |
| **财联社** | 快讯及时 | 中 | ⭐⭐⭐⭐ |

#### 免费数据源

| 数据源 | 用途 | 限制 |
|-------|------|------|
| 新浪财经 | 快讯、公告 | 需爬虫 |
| 东方财富网 | 行业新闻 | 需爬虫 |
| 雪球 | 用户情绪 | 需清洗 |
| 金十数据 | 全球宏观 | 部分免费 |

#### 数据源优先级

```python
DATA_SOURCES = [
    # 一级：权威+及时
    {'name': '财联社', 'type': 'realtime', 'priority': 1},
    {'name': '金十数据', 'type': 'macro', 'priority': 1},
    
    # 二级：全面+深度
    {'name': '同花顺iFinD', 'type': 'comprehensive', 'priority': 2},
    {'name': '东方财富', 'type': 'comprehensive', 'priority': 2},
    
    # 三级：补充
    {'name': '新浪财经', 'type': 'supplement', 'priority': 3},
]
```

### 5.2 NLP需求分析

#### ✅ 必需的NLP功能

1. **文本分类**
   - 新闻类型分类（宏观/地缘/行业）
   - 情绪分类（利好/利空/中性）
   - 影响等级预测

2. **实体识别**
   - 国家/地区识别
   - 行业/板块识别
   - 公司/机构识别

3. **事件抽取**
   - 事件类型（政策/冲突/业绩等）
   - 事件主体
   - 事件影响范围

#### 🔧 推荐技术栈

```python
# 方案一：传统NLP + 规则（适合初期）
- jieba分词
- 关键词匹配
- 规则引擎
- 优势：可控、解释性强
- 劣势：覆盖不全

# 方案二：深度学习（推荐）
- 预训练模型：ChatGLM-6B / Qwen
- Fine-tune任务：分类、NER、情感分析
- 优势：准确率高、泛化强
- 劣势：需要标注数据

# 方案三：API调用（快速上线）
- 通义千问 / 文心一言
- Prompt Engineering
- 优势：无需训练、快速上线
- 劣势：成本高、隐私
```

#### 推荐实现方案

```python
class NewsAnalyzer:
    def __init__(self):
        # 1. 使用开源模型（成本控制）
        self.llm = load_model("Qwen-7B-Chat")
        
        # 2. 规则引擎（兜底）
        self.rules = RuleEngine()
        
        # 3. 向量数据库（去重+检索）
        self.vector_db = Milvus()
    
    def analyze(self, news_text):
        # Step 1: 快速规则匹配
        quick_result = self.rules.match(news_text)
        if quick_result.confidence > 0.8:
            return quick_result
        
        # Step 2: LLM深度分析
        prompt = self._build_prompt(news_text)
        result = self.llm.generate(prompt)
        
        # Step 3: 结构化输出
        return self._parse_result(result)
```

### 5.3 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                    新闻因子模块架构                       │
└─────────────────────────────────────────────────────────┘

┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  数据采集层   │────▶│  处理分析层   │────▶│  因子计算层   │
└──────────────┘     └──────────────┘     └──────────────┘
       │                     │                     │
       ▼                     ▼                     ▼
  ┌─────────┐          ┌─────────┐          ┌─────────┐
  │爬虫/API │          │NLP引擎  │          │因子库   │
  │调度器   │          │分类器   │          │计算引擎 │
  │去重器   │          │NER      │          │信号融合 │
  └─────────┘          └─────────┘          └─────────┘
       │                     │                     │
       └─────────────────────┴─────────────────────┘
                             │
                             ▼
                      ┌──────────────┐
                      │  存储层       │
                      │ - PostgreSQL │
                      │ - Milvus     │
                      │ - Redis      │
                      └──────────────┘
                             │
                             ▼
                      ┌──────────────┐
                      │  应用层       │
                      │ - 仪表盘     │
                      │ - API接口    │
                      │ - 告警系统   │
                      └──────────────┘
```

### 5.4 关键代码框架

```python
# main.py - 新闻因子计算主程序

class NewsFactorEngine:
    def __init__(self):
        self.collector = NewsCollector()
        self.analyzer = NewsAnalyzer()
        self.deduplicator = NewsDeduplicator()
        self.factor_calculator = FactorCalculator()
        self.storage = NewsStorage()
    
    def run_daily(self):
        """每日运行"""
        # 1. 采集新闻
        news_list = self.collector.collect_24h()
        
        # 2. 去重
        unique_news = self.deduplicator.deduplicate(news_list)
        
        # 3. NLP分析
        analyzed_news = [
            self.analyzer.analyze(news)
            for news in unique_news
        ]
        
        # 4. 存储
        self.storage.batch_save(analyzed_news)
        
        # 5. 计算因子
        factors = self.factor_calculator.calculate(
            date=today(),
            news_list=analyzed_news
        )
        
        # 6. 生成报告
        report = self.generate_report(factors)
        
        # 7. 触发告警
        self.check_alerts(factors)
        
        return factors
    
    def generate_report(self, factors):
        """生成每日新闻报告"""
        return {
            'date': today(),
            'summary': {
                'total_news': factors['news_count'],
                'macro_news': factors['macro_count'],
                'sector_news': factors['sector_count'],
            },
            'top_sectors': factors['top_5_sectors'],
            'alerts': factors['alerts'],
            'factor_values': factors['sector_factors'],
        }
```

### 5.5 部署建议

#### 开发环境

```bash
# Python环境
Python >= 3.9

# 核心依赖
pip install pandas numpy scikit-learn
pip install transformers torch
pip install jieba paddleocr
pip install psycopg2 redis pymilvus
pip install fastapi uvicorn
```

#### 生产环境

```yaml
# docker-compose.yml
version: '3.8'
services:
  news-api:
    build: ./news_api
    ports:
      - "8000:8000"
    depends_on:
      - postgres
      - redis
      - milvus
  
  news-collector:
    build: ./collector
    environment:
      - SCHEDULE=0 */1 * * *  # 每小时
  
  postgres:
    image: postgres:14
    volumes:
      - pgdata:/var/lib/postgresql/data
  
  milvus:
    image: milvusdb/milvus:latest
  
  redis:
    image: redis:7
```

---

## 6. 监控与评估

### 6.1 核心指标

```python
# 新闻因子质量指标
metrics = {
    'coverage_rate': '新闻覆盖率（重要事件是否遗漏）',
    'classification_accuracy': '分类准确率',
    'sentiment_accuracy': '情绪判断准确率',
    'impact_prediction_accuracy': '影响预测准确率',
    'deduplication_precision': '去重精确率',
    'factor_ic': '因子IC值',
    'factor_icir': '因子ICIR',
}
```

### 6.2 回测框架

```python
def backtest_news_factor(start_date, end_date):
    """回测新闻因子表现"""
    results = []
    
    for date in date_range(start_date, end_date):
        # 1. 获取当日新闻因子
        news_factor = get_news_factor(date)
        
        # 2. 获取次日板块收益
        next_return = get_sector_return(date + 1day)
        
        # 3. 计算预测准确性
        ic = correlation(news_factor, next_return)
        results.append(ic)
    
    return {
        'mean_ic': mean(results),
        'icir': mean(results) / std(results),
        'win_rate': sum(r > 0 for r in results) / len(results),
    }
```

---

## 7. 扩展方向

### 7.1 短期优化（1-3个月）

- [ ] 完善新闻源接入（至少5个稳定源）
- [ ] 优化NLP模型（准确率>80%）
- [ ] 建立历史新闻数据库（3年+）
- [ ] 完善规则引擎（覆盖常见场景）

### 7.2 中期增强（3-6个月）

- [ ] 引入另类数据（社交媒体、搜索指数）
- [ ] 实时新闻推送（秒级延迟）
- [ ] 个性化过滤（按用户关注板块）
- [ ] 因子有效性动态监控

### 7.3 长期演进（6-12个月）

- [ ] 多语言支持（英文、日文新闻）
- [ ] 知识图谱构建（事件关联分析）
- [ ] 预测模型（新闻→市场反应）
- [ ] 自动化交易接口

---

## 附录

### A. 行业分类映射表

```python
SECTOR_MAPPING = {
    '申万行业': {
        '801010.SI': '农林牧渔',
        '801020.SI': '采掘',
        '801030.SI': '化工',
        '801040.SI': '钢铁',
        '801050.SI': '有色金属',
        # ... 申万31个行业
    },
    '概念板块': {
        '新能源汽车': ['锂电池', '充电桩', '整车'],
        '半导体': ['芯片设计', '设备', '材料'],
        '碳中和': ['光伏', '风电', '储能'],
        # ... 热门概念
    }
}
```

### B. 关键词词典（示例）

```python
BEARISH_KEYWORDS = {
    '极端': ['暴雷', '造假', '退市', '破产', '立案调查'],
    '高': ['监管', '处罚', '下架', '召回', '诉讼'],
    '中': ['下滑', '亏损', '裁员', '降价', '违约'],
}

BULLISH_KEYWORDS = {
    '极端': ['国家战略', '千亿补贴', '技术突破', '独家专利'],
    '高': ['政策扶持', '订单激增', '业绩翻倍', '并购重组'],
    '中': ['价格上涨', '市场扩张', '份额提升', '合作签约'],
}
```

### C. 参考资源

- [申万行业分类标准](https://www.swsresearch.com/)
- [中国证券报数据中心](http://www.cs.com.cn/)
- [Wind金融终端API文档](https://www.wind.com.cn/)
- [HuggingFace中文NLP模型](https://huggingface.co/models?language=zh)

---

**文档结束**

> 本设计文档提供了A股新闻因子模块的完整框架。实际实施时，建议：
> 1. 先实现MVP版本（核心功能+1-2个数据源）
> 2. 积累数据后优化NLP模型
> 3. 持续回测验证因子有效性
> 4. 根据实盘表现迭代规则