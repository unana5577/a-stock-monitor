# n8n 数据监控工作流

## 工作流说明

这个工作流用于监控A股数据系统的健康状态，每5分钟自动检查一次。

## 工作流结构

```
[⏰ 定时触发器] 每5分钟
      ↓
[⚙️ 设置时间戳]
      ↓
[🌐 检查所有数据源] → 调用 /api/data/health
      ↓
   [❓ 健康度判断]
   ↙          ↘
[✅ 健康]    [❌ 异常]
              ↓
        [📝 记录异常日志]
```

## 导入步骤

### 1. 启动n8n

```bash
# 如果还没安装n8n
npm install -g n8n

# 启动n8n
n8n start

# 打开浏览器访问
# http://localhost:5678
```

### 2. 导入工作流

1. 在n8n界面点击右上角 **"..."** 菜单
2. 选择 **"Import from File"**
3. 选择 `data-monitoring-workflow.json` 文件
4. 点击 **"Import"**

### 3. 激活工作流

1. 导入后，点击工作流左上角的 **"Inactive"** 开关
2. 切换为 **"Active"** 状态
3. 工作流开始运行

## 工作流节点说明

### 节点1: 定时触发器 (Cron)
- **类型**: Schedule Trigger
- **配置**: 每5分钟执行一次
- **作用**: 定时启动监控流程

### 节点2: 设置时间戳 (Set)
- **类型**: Set
- **输出**:
  - `timestamp`: ISO格式时间戳
  - `checkTime`: HH:mm:ss格式时间
- **作用**: 记录检查时间

### 节点3: 检查所有数据源 (HTTP Request)
- **类型**: HTTP Request
- **URL**: `http://localhost:8787/api/data/health`
- **方法**: GET
- **返回**: JSON格式的健康状态
  ```json
  {
    "timestamp": "2026-04-15T12:00:00Z",
    "health": "healthy",
    "sources": {
      "etf": {...},
      "index": {...},
      "warmup": {...},
      "lifecycle": {...}
    }
  }
  ```

### 节点4: 健康度判断 (If)
- **类型**: If
- **条件**: `health == 'healthy'`
- **true分支**: → 正常结束
- **false分支**: → 记录异常日志

### 节点5: 记录异常日志 (Write File)
- **类型**: Write Binary File
- **文件**: `logs/data-health-errors.log`
- **内容**: 时间戳 + 异常详情
- **作用**: 记录所有异常情况，便于后续分析

### 节点6: 正常结束 (NoOp)
- **类型**: No Operation
- **作用**: 工作流正常结束

## 验证工作流

### 手动测试

1. 在n8n界面，点击第一个节点（定时触发器）
2. 点击右上角 **"Execute Workflow"** 按钮
3. 查看每个节点的执行结果
4. 确认最后一个节点返回健康状态

### 查看执行历史

1. 点击左侧菜单 **"Executions"**
2. 可以看到每次执行的详细记录
3. 点击某次执行可以看到每个节点的输入输出

### 查看日志

```bash
# 查看异常日志
tail -f logs/data-health-errors.log

# 如果有异常，会看到类似这样的内容：
# 2026-04-15 12:00:00 - 健康度异常: degraded
# {
#   "health": "degraded",
#   "sources": {...}
# }
```

## 自定义配置

### 修改检查频率

在"定时触发器"节点中：
- 默认: 每5分钟
- 可以改为: `*/1 * * * *` (每分钟)
- 或者: `*/10 * * * *` (每10分钟)

### 修改日志路径

在"记录异常日志"节点中：
- 默认: `logs/data-health-errors.log`
- 可以改为任意路径

### 添加通知

可以在"记录异常日志"节点后面添加：
- Email节点：发送邮件通知
- Slack节点：发送Slack消息
- Webhook节点：调用自定义webhook

## 健康度说明

- **healthy** (健康): 所有数据源正常，通过率≥90%
- **degraded** (降级): 部分数据源延迟，通过率70%-90%
- **critical** (异常): 多个数据源失败，通过率<70%

## 故障排查

### 问题1: 工作流执行失败

**可能原因**:
- Node.js服务器未启动
- API端点 `/api/data/health` 不存在

**解决方案**:
```bash
# 检查服务器是否运行
ps aux | grep "node.*server.js"

# 如果没有运行，启动服务器
node server.js
```

### 问题2: API返回错误

**可能原因**:
- Python脚本 `get_data_health.py` 不存在
- Python依赖缺失

**解决方案**:
```bash
# 测试Python脚本
python3 scripts/get_data_health.py

# 测试API端点
curl http://localhost:8787/api/data/health
```

### 问题3: 日志文件无法写入

**可能原因**:
- `logs/` 目录不存在
- 权限不足

**解决方案**:
```bash
# 创建logs目录
mkdir -p logs

# 修改权限
chmod 755 logs
```

## 下一步优化

1. **添加通知**: 当健康度异常时，发送邮件或Slack通知
2. **添加LangGraph**: 当检测到异常时，自动调用LangGraph进行问题分析
3. **添加前端实时更新**: 使用WebSocket实时推送健康状态到前端
4. **添加更多数据源**: 监控更多数据源的健康状态

## 技术支持

如有问题，请检查：
1. Node.js服务器是否正常运行: `http://localhost:8787/health`
2. Python脚本是否正常: `python3 scripts/get_data_health.py`
3. n8n是否正常运行: `http://localhost:5678`
4. 日志文件: `logs/data-health-errors.log`
