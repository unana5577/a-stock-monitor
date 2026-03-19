# 前端数据需求文档

## 一、分时图数据需求

### 1.1 指数分时数据
**数据源**: `/api/minute/{code}`

**代码映射**:
```javascript
{
  'sse': '上证指数',
  'szi': '深证成指',
  'gem': '创业板指',
  'star': '科创50',
  'hs300': '沪深300',
  'csi2000': '中证2000',
  'avg': '平均股价',
  'tl': '30Y国债TL2603',
  't': '10Y国债T2603',
  'bank': '银行指数881155',
  'broker': '证券指数881157',
  'insure': '保险指数881156'
}
```

**必需字段**:
```typescript
interface MinuteData {
  series: Array<{
    time: string;      // 格式 "HH:MM" 或 "YYYY-MM-DD HH:MM:SS"
    close?: number;    // 收盘价（优先）
    open?: number;     // 开盘价（备选）
    price?: number;    // 最新价（备选��
    volume?: number;   // 成交量（累计值，单位：手）
  }>;
  prevClose?: number;  // 昨收价，用于计算涨跌幅
  day?: string;        // 日期 "YYYY-MM-DD"
  latest?: {           // 最新数据点
    time: string;
    price: number;
  };
}
```

**时间粒度**: 1分钟
**时间范围**: 当日 9:30 ~ 15:00（242个点）
**刷新频率**: 盘中每30秒
**缓存策略**: 2分钟（盘中）/ 10分钟（盘后）

### 1.2 板���分时数据
**数据源**: `/api/sector/history?rt=1&days=1&sectors=xxx`

**必需字段**:
```typescript
interface SectorMinuteData {
  minute: {
    [sectorName: string]: {
      series: MinuteData['series'];
      prevClose?: number;
    };
  };
}
```

---

## 二、日线图数据需求

### 2.1 指数日线
**时间跨度**: 默认180个交易日
**刷新频率**: 每日收盘后
**必需字段**:
```typescript
interface DailyData {
  date: string;        // "YYYY-MM-DD"
  close: number;       // 收盘价
  amount?: number;     // 成交额（万元）
}
```

### 2.2 板块日线
**数据源**: `/api/sector/history?days={1|5|30|60}&sectors=xxx`

**必需字段**:
```typescript
interface SectorHistoryData {
  history: {
    [sectorName: string]: Array<{
      date: string;
      close: number;
      pct: number;     // 日涨跌幅（%）
    }>;
  };
  indicators?: {
    [sectorName: string]: Array<{
      date: string;
      Alpha_5?: number;      // 5日超额收益
      Alpha_20?: number;     // 20日超额收益
      Bias_20?: number;      // 20日乖离率
      Amount_Share_Change?: number;  // 热度变化（成交额占比变化，%）
    }>;
  };
  watch?: string[];          // 关注板块列表
  correlations?: Array<{     // 板块相关性（可选）
    pair: [string, string];
    val: number;
  }>;
}
```

**时间范围选项**:
- 当日(1): 使用分时数据
- 5日: 最近5个交易日
- 30日: 最近30个交易日
- 60日: 最近60个交易日（默认）

---

## 三、热力图与排名数据

### 3.1 板块涨跌幅排名
**数据源**: `/api/sector/rank`

**必需字段**:
```typescript
interface SectorRankData {
  up: Array<{ name: string; pct: number | string }>;    // 涨幅榜
  down: Array<{ name: string; pct: number | string }>;  // 跌幅榜
}
```

**刷新频率**: 盘中每分钟
**显示数量**: Top 10

### 3.2 板块生命周期监测
**数据源**: `/api/sector/lifecycle?days=60&sectors=xxx`

**必需字段**:
```typescript
interface LifecycleData {
  items: Array<{
    "板块名称": string;        // ETF名称
    "板块位置": string;        // 位置描述
    "基准指数": string;        // 对应指数
    "阶段信号": string;        // 启动/加速/震荡/衰退/背离
    "显示名称": string;        // 显示标签
    "含义": string;           // 含义说明
    "动能": string;           // 动能描述
    "资金行为": string;       // 资金行为描述
    "操作建议": string;       // 建仓/持有/减仓等
    "归因说明": string;       // 归因说明
    "指标数据": {
      "Alpha_5": number;      // 5日超额收益
      "Alpha_20": number;     // 20日超额收益
      "Bias_20": number;      // 20日乖离率
      "Amount_Share_Change": number;  // 热度变化
    };
  }>;
}
```

### 3.3 板块轮动分析
**数据源**: `/api/sector/rotation?days=90&sectors=xxx`

**必需字段**:
```typescript
interface RotationData {
  mainline: Array<{
    "板块名称": string;
    groups?: string[];       // 所属分组
    news_view?: {
      risk_tags: string[];   // 风险标签
    };
    exec_view?: {
      position?: {
        max: number;         // 仓位上限
      };
    };
  }>;
  groups?: Array<{
    "组别": string;          // 分组名称
    "均值得分": number;      // 得分
  }>;
}
```

**更新频率**: 盘后更新一次

---

## 四、实时数据刷新需求

### 4.1 概览页（Tab=overview）

#### AI解读
- **数据源**: `/api/snapshot/latest?ai=1`
- **刷新频率**: 盘中每30分钟
- **必需字段**:
```typescript
interface AIData {
  aiBrief?: {
    title: string;
    detail: string;
  };
  aiText?: string;          // 完整AI文本
  ts?: number;              // 时间戳
}
```

#### 市场宽度（涨跌家数）
- **数据源**: `/api/market/breadth`
- **刷新频率**: 盘中每分钟
- **必需字段**:
```typescript
interface BreadthData {
  up: number;               // 上涨家数
  down: number;             // 下跌家数
  total: number;            // 总数
  ratio: number;            // 上涨占比
  sentiment: string;        // 情绪描述
}
```

#### 成交额数据
- **数据源**: `/api/snapshot/latest`
- **刷新频率**: 盘中每分钟
- **必需字段**:
```typescript
interface VolumeData {
  volume: number;                      // 当前成交额（万元）
  volumeStr: string;                   // 格式化显示 "XXXX亿"
  volumeSeries?: Array<{               // 当日累计成交曲线
    time: string;      // "HH:MM"
    volume: number;    // 累计成交额（万元）
  }>;
  volumeSeriesYday?: Array<{           // 昨日累计成交曲线（对比）
    time: string;
    volume: number;
  }>;
  volumeCmp?: {
    pct: number;          // 较昨日变化百分比
    delta: number;        // 较昨日变化量（万元）
    ydayFull: number;     // 昨日全天成交额（万元）
  };
}
```

**特殊逻辑**:
- 预估全天量能 = 当前累计 + 前一分钟成交量 × 剩余分钟数
- 剩余分钟数计算需考虑午休（240分钟全天：120上午 + 120下午）

#### 风险门控（恐慌指数）
- **数据源**: `/api/panic`
- **刷新频率**: 盘中每分钟
- **必需字段**:
```typescript
interface PanicData {
  is_panic: boolean;       // 是否恐慌
  ratio: number;           // 下跌占比
  up: number;              // 上涨家数
  down: number;            // 下跌家数
}
```

#### 信号数据
- **数据源**: `/api/signals`
- **刷新频率**: 盘中每分钟
- **必需字段**:
```typescript
interface SignalsData {
  signals: Array<{
    sector: string;        // 板块名称
    signal: string;        // 信号：long/false_kill
  }>;
}
```

### 4.2 行情页（Tab=market）

#### 板块轮动（盘中）
- **数据源**: `/api/sector/rotation/intraday?view=summary|detail`
- **刷新频率**: 盘中每2分钟
- **必需字段**:
```typescript
interface IntradayRotationData {
  intraday: {
    signal: string;        // 轮动信号描述
    reason: string[];      // 原因列表
    bars: Array<{         // summary视图
      group: string;       // 大类分组（资源/硬件/软件）
      today_pct: number;   // 今日涨跌幅
      top?: Array<{       // detail视图（细分板块）
        name: string;
        pct: number;
      }>;
    }>;
  };
}
```

#### 板块历史数据（含分时）
- **数据源**: `/api/sector/history?rt={0|1}&days=60`
- **刷新频率**:
  - 盘中(rt=1): 每60秒
  - 盘后(rt=0): 每5分钟
- **必需字段**: 见 2.2（需额外返回分时数据）

---

## 五、60日 Warmup 数据需求

### 5.1 Warmup触发条件
- 页面加载时自动触发
- 切换关注板块时触发
- 切换时间范围时触发（days参数取最大值）

### 5.2 Warmup API
**数据源**: `/api/sector/warmup?days=60&sectors=xxx`

**目的**: 预热缓存，确保后续历史查询快速响应

**预期行为**:
- 后台异步执行，不阻塞前端
- 缓存时长: 10分钟
- 包含数据:
  - 60日日线历史
  - 当日分时数据（如盘中）
  - 各类技术指标（Alpha/Bias/热度变化）

---

## 六、新闻数据需求

### 6.1 新闻分类
- **宏观**: tags包含 ['宏观', '政策', '数据', '央行', '货币', '经济', '财政', '利率', '通胀']
- **地缘**: tags包含 ['地缘', '海外', '国际', '战争', '中东', '俄乌', '巴以', '美联储']
- **关注行业**: tags匹配用户关注板块列表

### 6.2 新闻数据结构
```typescript
interface NewsItem {
  news_id: string;
  title: string;
  summary: string;
  source: string;
  source_url: string;
  publish_time: string;    // "YYYY-MM-DD HH:MM:SS"
  crawl_time: string;
  importance: number;      // 1-5星级
  tags: string[];          // 标签列表
  related_stocks: string[]; // 关联股票代码
  status: string;          // new/processed/archived
}
```

**刷新频率**: 每5分钟
**排序规则**: 优先级降序 → 发布时间降序

---

## 七、缓存策略总结

| 数据类型 | 盘中频率 | 盘后频率 | 缓存时长 |
|---------|---------|---------|---------|
| 分时数据 | 30秒 | - | 2分钟 |
| 涨跌幅排名 | 1分钟 | - | 2分钟 |
| 市场宽度 | 1分钟 | - | 2分钟 |
| 成交额 | 1分钟 | - | 2分钟 |
| 板块历史 | 60秒 | 5分钟 | 5分钟 |
| 板块轮动 | 2分钟 | 10分钟 | 2/10分钟 |
| 生命周期 | 60秒 | 5分钟 | 5分钟 |
| AI解读 | 30分钟 | - | 30分钟 |
| 新闻 | 5分钟 | 5分钟 | 5分钟 |
| Warmup缓存 | - | - | 10分钟 |

---

## 八、特殊需求

### 8.1 交易日历判断
- **需求**: 前端需要判断当前是否在交易时间内
- **用途**: 决定数据刷新频率
- **判断规则**:
  - 周一至周五
  - 9:30-11:30, 13:00-15:00
  - 排除节假日

### 8.2 数据回补
- **场景**: 分时数据存在缺失点时
- **前端处理**: 使用前一个有效数据点填充（forward fill）
- **示例**: 10:05缺失，使用10:04的数据

### 8.3 多语言支持
- 当前版本仅支持中文
- 日期格式: "YYYY-MM-DD"
- 时间格式: "HH:MM"
- 数值格式: 保留2位小数

### 8.4 错误降级
- 数据加载失败时显示 "数据加载中" 或 "暂无数据"
- 部分字段缺失时显示 "-"
- 不阻断页面其他模块渲染

---

## 九、API响应格式要求

### 9.1 统一响应结构
```typescript
interface APIResponse<T> {
  data?: T;
  error?: string;
  ts?: number;    // 数据时间戳
}
```

### 9.2 时间戳处理
- 所有时间戳使用毫秒级 Unix timestamp
- 日期字符串统一使用 "YYYY-MM-DD" 格式
- 时间字符串统一使用 "HH:MM" 或 "HH:MM:SS" 格式

### 9.3 数值精度
- 价格: 保留2位小数
- 百分比: 保留2位小数
- 成交额: 单位万元，整数
- 成交量: 单位手，整数

---

## 十、优先级说明

### P0 (核心功能)
- 指数分时数据
- 板块分时数据
- 涨跌幅排名
- 市场宽度
- 成交额数据

### P1 (重要功能)
- 板块历史日线
- 生命周期监测
- 板块轮动分析
- 风险门控
- 信号数据

### P2 (辅助功能)
- AI解读
- 新闻数据
- 相关性分析
- Warmup缓存

### P3 (优化功能)
- 板块热力图
- 导出JSON
- Markdown复制
