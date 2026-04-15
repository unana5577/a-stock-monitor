# 数据流程监控 - 架构图

## Mermaid流程图

```mermaid
graph TB
    Start([定时触发器<br/>每5分钟]) --> SetTime[设置当前时间戳]

    SetTime --> CheckHealth[调用健康检查API<br/>/api/data/health]

    CheckHealth --> ParseResponse[解析健康状态JSON<br/>ETF/指数/Warmup/Lifecycle]

    ParseResponse --> CalcHealth[计算整体健康度<br/>healthy/degraded/critical]

    CalcHealth --> UpdateFrontend[更新前端显示<br/>WebSocket或轮询]

    CalcHealth --> Decision{健康度判断}

    Decision --> |healthy| End1([正常结束])
    Decision --> |degraded/critical| LogError[记录异常日志<br/>logs/data-health-errors.log]
    LogError --> End2([结束])

    style Start fill:#e1f5fe
    style SetTime fill:#fff3e0
    style CheckHealth fill:#e8f5e9
    style ParseResponse fill:#f3e5f5
    style CalcHealth fill:#e8f5e9
    style UpdateFrontend fill:#e1f5fe
    style Decision fill:#fff9c4
    style LogError fill:#ffebee
    style End1 fill:#c8e6c9
    style End2 fill:#c8e6c9
```

## 数据流说明

### 1. 定时触发
- **频率**: 每5分钟
- **触发器**: n8n Cron节点
- **输出**: 当前时间戳

### 2. 健康检查
- **API**: `GET /api/data/health`
- **返回格式**:
```json
{
  "timestamp": "2026-04-15T12:00:00Z",
  "health": "healthy",
  "sources": {
    "etf": {
      "total": 9,
      "ok": 9,
      "delayed": 0,
      "failed": 0
    },
    "index": {...},
    "warmup": {...},
    "lifecycle": {...}
  },
  "summary": {
    "total": 15,
    "passed": 14,
    "failed": 1,
    "passRate": "93.3%"
  }
}
```

### 3. 健康度计算

#### healthy (健康)
- 通过率 ≥ 90%
- 所有数据源正常
- 前端显示绿色 ✅

#### degraded (降级)
- 通过率 70% - 90%
- 部分数据源延迟
- 前端显示黄色 ⚠️

#### critical (异常)
- 通过率 < 70%
- 多个数据源失败
- 前端显示红色 ❌

### 4. 异常处理

当健康度为 `degraded` 或 `critical` 时：
1. 记录异常日志到 `logs/data-health-errors.log`
2. 日志格式：
   ```
   2026-04-15 12:00:00 - 健康度异常: degraded
   {
     "timestamp": "2026-04-15T12:00:00Z",
     "health": "degraded",
     "sources": {...},
     "summary": {...}
   }
   ```

## 前端监控界面

### 位置
- 文件: `public/index.html`
- Section: "📊 数据流程状态监控"
- 显示在: "板块生命周期监测"之前

### 显示内容

#### 整体健康度
- ✅ 健康 (绿色)
- ⚠️ 降级 (黄色)
- ❌ 异常 (红色)

#### 数据源状态卡片
1. **📈 ETF数据**
   - 总数: 9
   - ✅ 正常: X
   - ⚠️ 延迟: X
   - ❌ 失败: X

2. **📊 指数数据**
   - 上证指数、深证成指、创业板指、科创板指

3. **🔥 Warmup缓存**
   - 最新日期
   - 记录数量

4. **🎯 Lifecycle分析**
   - 最新日期
   - 项目数量

#### 详细信息
- 可展开查看完整JSON
- 按钮: "显示详细信息 ▼"

## 自动刷新

- **频率**: 每5分钟
- **实现**: JavaScript `setInterval()`
- **首次加载**: 立即执行一次

## 文件结构

```
a-stock-monitor/
├── scripts/
│   └── get_data_health.py          # 数据健康检查脚本
├── server.js                        # 添加 /api/data/health 端点
├── public/
│   ├── index.html                   # 添加监控section
│   └── ui.js                        # 添加刷新逻辑
├── n8n-workflows/
│   ├── data-monitoring-workflow.json  # n8n工作流配置
│   ├── README.md                    # 使用说明
│   └── flowchart.md                # 架构图（本文件）
└── logs/
    └── data-health-errors.log      # 异常日志（自动创建）
```

## 部署步骤

### Step 1: 安装n8n
```bash
npm install -g n8n
```

### Step 2: 启动n8n
```bash
n8n start
# 访问: http://localhost:5678
```

### Step 3: 导入工作流
1. 打开n8n界面
2. 点击右上角 "..." → "Import from File"
3. 选择 `data-monitoring-workflow.json`

### Step 4: 激活工作流
1. 点击左上角的 "Inactive" 开关
2. 切换为 "Active"

### Step 5: 验证
1. 点击 "Execute Workflow" 手动测试
2. 打开前端页面查看监控界面
3. 检查日志文件 `logs/data-health-errors.log`

## 下一步扩展

### 阶段2: LangGraph智能分析

当检测到异常时，自动调用LangGraph进行问题分析：

```
[❌ 健康度异常]
      ↓
[🤖 LangGraph分析]
  ├─ Agent 1: 数据诊断专家
  ├─ Agent 2: 根因分析专家
  ├─ Agent 3: 解决方案专家
  └─ Agent 4: 影响评估专家
      ↓
[📊 分析报告]
  ├─ 问题原因
  ├─ 解决方案
  ├─ 影响范围
  └─ 可执行命令
```

### 阶段3: 通知和报警

- Email通知
- Slack集成
- Discord Webhook
- 企业微信机器人

### 阶段4: 自动修复

- 自动重试失败的数据采集
- 自动回填缺失数据
- 自动重启异常服务
