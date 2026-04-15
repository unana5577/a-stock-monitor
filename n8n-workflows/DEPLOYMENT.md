# 部署和测试指南

## 已完成的工作

### ✅ 1. 数据健康检查脚本
**文件**: `scripts/get_data_health.py`

功能：
- 检查9个ETF数据文件状态
- 检查4个指数数据文件状态
- 检查Warmup缓存状态
- 检查Lifecycle数据状态
- 计算整体健康度 (healthy/degraded/critical)

**测试**:
```bash
python3 scripts/get_data_health.py
```

### ✅ 2. API端点
**文件**: `server.js` (已修改)

新增端点: `GET /api/data/health`

**测试**:
```bash
# 需要重启服务器后才能测试
curl http://localhost:8787/api/data/health
```

### ✅ 3. 前端监控界面
**文件**:
- `public/index.html` (已添加监控section)
- `public/ui.js` (已添加刷新逻辑)

功能：
- 显示整体健康度（绿色/黄色/红色）
- 显示4个数据源状态卡片
- 每5分钟自动刷新
- 可展开查看详细JSON

### ✅ 4. n8n工作流配置
**文件**: `n8n-workflows/data-monitoring-workflow.json`

工作流节点：
1. 定时触发器（每5分钟）
2. 设置时间戳
3. 调用健康检查API
4. 健康度判断
5. 记录异常日志（可选）
6. 正常结束

## 部署步骤

### Step 1: 重启Node.js服务器

**重要**: 需要重启服务器才能加载新的API端点

```bash
# 方法1: 如果服务器在后台运行
kill 51156
node server.js &

# 方法2: 如果使用了pm2
pm2 restart server

# 方法3: 如果直接在前台运行，按Ctrl+C停止，然后重新运行
node server.js
```

### Step 2: 验证API端点

```bash
curl http://localhost:8787/api/data/health | python3 -m json.tool
```

**预期输出**:
```json
{
  "timestamp": "2026-04-15T08:33:33.762186+00:00",
  "health": "healthy",
  "sources": {
    "etf": {
      "total": 9,
      "ok": 9,
      "delayed": 0,
      "failed": 0
    },
    ...
  },
  "summary": {
    "total": 15,
    "passed": 15,
    "failed": 0,
    "passRate": "100.0%"
  }
}
```

### Step 3: 验证前端界面

1. 打开浏览器访问: `http://localhost:8787`
2. 在"概览"标签页，找到"📊 数据流程状态监控"section
3. 应该能看到：
   - 整体健康度徽章（绿色/黄色/红色）
   - 4个数据源状态卡片
   - "显示详细信息 ▼" 按钮

### Step 4: 安装和配置n8n

```bash
# 1. 安装n8n（如果还没安装）
npm install -g n8n

# 2. 启动n8n
n8n start

# 3. 打开浏览器
# http://localhost:5678

# 4. 首次使用需要注册账号
#（可以随意填写，不需要真实邮箱，因为只是本地使用）

# 5. 导入工作流
# - 点击右上角 "..." 菜单
# - 选择 "Import from File"
# - 选择 n8n-workflows/data-monitoring-workflow.json
# - 点击 "Import"

# 6. 激活工作流
# - 点击工作流左上角的 "Inactive" 开关
# - 切换为 "Active"
```

### Step 5: 测试n8n工作流

```bash
# 1. 在n8n界面，点击第一个节点（定时触发器）
# 2. 点击右上角 "Execute Workflow" 按钮
# 3. 查看每个节点的执行结果
# 4. 确认最后一个节点返回健康状态

# 5. 检查日志文件（如果有异常）
tail -f logs/data-health-errors.log
```

## 验证清单

### 基础功能
- [ ] Python脚本正常运行: `python3 scripts/get_data_health.py`
- [ ] API端点可访问: `curl http://localhost:8787/api/data/health`
- [ ] 前端显示监控界面: 访问 `http://localhost:8787`
- [ ] 前端自动刷新: 等待5分钟，观察数据更新

### n8n集成
- [ ] n8n成功安装并启动: 访问 `http://localhost:5678`
- [ ] 工作流成功导入: 在n8n界面能看到工作流
- [ ] 工作流激活成功: 左上角显示 "Active"
- [ ] 手动执行成功: 点击 "Execute Workflow" 无错误
- [ ] 定时执行成功: 等待5分钟，自动触发

### 异常处理
- [ ] 手动删除某个ETF数据文件，5分钟后能看到红色警告
- [ ] 异常日志正确记录: `logs/data-health-errors.log`

## 当前数据状态

根据刚才的测试：
- **ETF数据**: ✅ 全部正常 (9/9)
- **指数数据**: ⚠️ 全部延迟 (4个都是昨天的数据)
- **Warmup缓存**: ✅ 正常
- **Lifecycle数据**: ⚠️ 延迟（昨天的数据）
- **整体健康度**: ❌ 异常 (critical, 通过率66.7%)

这是正常的，因为：
- 指数数据今天还没更新
- Lifecycle数据今天还没重新生成

## 常见问题

### Q1: API端点返回404
**原因**: 服务器没有重启
**解决**: 重启Node.js服务器

### Q2: 前端显示"检查中..."不更新
**原因**: API端点不可用或浏览器缓存
**解决**:
1. 检查API端点: `curl http://localhost:8787/api/data/health`
2. 清除浏览器缓存: Ctrl+Shift+R (Windows) / Cmd+Shift+R (Mac)

### Q3: n8n工作流执行失败
**原因**: Node.js服务器未启动
**解决**: 确保服务器运行在 `http://localhost:8787`

### Q4: 健康度一直是"critical"
**原因**: 这是正常的！指数数据每天盘后才更新
**解决**: 等到下午3点后，数据更新后健康度会变为"healthy"

## 下一步

### 阶段1完成后的功能
- ✅ 每5分钟自动检查数据健康状态
- ✅ 前端实时显示监控界面
- ✅ n8n自动化监控流程
- ✅ 异常自动记录日志

### 阶段2: LangGraph智能分析（待实施）
- 当检测到异常时，自动分析原因
- 提供解决方案
- 评估影响范围

### 阶段3: 通知和报警（待实施）
- Email通知
- Slack/Discord集成
- 企业微信机器人

## 文件清单

```
a-stock-monitor/
├── scripts/
│   └── get_data_health.py              # ✅ 新增
├── server.js                           # ✅ 已修改
├── public/
│   ├── index.html                      # ✅ 已修改
│   └── ui.js                           # ✅ 已修改
├── n8n-workflows/                      # ✅ 新增目录
│   ├── data-monitoring-workflow.json  # ✅ n8n工作流
│   ├── README.md                       # ✅ 使用说明
│   ├── flowchart.md                    # ✅ 架构图
│   └── DEPLOYMENT.md                   # ✅ 部署指南（本文件）
└── logs/
    └── data-health-errors.log          # 自动创建
```

## 技术支持

遇到问题请检查：
1. Node.js服务器状态: `http://localhost:8787/health`
2. Python脚本测试: `python3 scripts/get_data_health.py`
3. API端点测试: `curl http://localhost:8787/api/data/health`
4. n8n界面: `http://localhost:5678`
5. 浏览器控制台: F12查看是否有JavaScript错误
