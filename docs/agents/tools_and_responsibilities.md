# 工具清单与职责分工

> 更新时间：2026-03-23

---

## 一、Agent 职责分工

### Leader 职责

#### 1. 项目管理
- 制定开发计划
- 分配任务给各Agent
- 审核代码质量
- Git版本管理
- 协调跨Agent协作

#### 2. 文档审核
- 审核Data Agent更新的data_protocol.md
- 维护task_status.md
- 维护schedule.md

#### 3. 数据质量监督
- 运行验证工具检查Data Agent工作质量
- 发现问题并分配任务

#### 4. 权限
- ✅ 可操作：docs/、scripts/（验证工具）、.git/
- ✅ 审核所有代码提交
- ❌ 不直接修改数据层、业务层代码

---

### Data Agent 职责

#### 1. 数据获取与持久化
- ETF分时/日线数据
- 大盘指数数据
- 市场数据（成交额、涨跌家数）

#### 2. Warmup + AI接口数据准备
- 生成warmup数据
- 准备AI分析所需数据

#### 3. 数据验证
- 字段完整性检查
- 数据连续性验证
- 接口健康监控

#### 4. 定时任务执行
- data_maintenance.py（数据维护主脚本）
- market_breadth_spot.py（涨跌家数）
- save_breadth_history.py（涨跌家数持久化）

#### 5. 接口维护
- 接口探测与修复（check_data_sources.py）
- 维护data_protocol.md

#### 6. 权限
- ✅ 可操作：data/、fetch_sector_data.py、data_maintenance.py
- ❌ 不能操作：业务层代码、前端代码

---

### Business Agent 职责

#### 1. 业务逻辑
- Alpha超额收益计算
- MA斜率计算
- 乖离率风险等级
- 资金热度计算
- 动能标签判断

#### 2. 状态管理
- 维护 stores/ 业务状态
- 数据缓存策略
- 状态同步机制

#### 3. 错误兜底
- 数据异常时返回默认值
- 防止UI崩溃
- 降级方案

#### 4. 权限
- ✅ 可操作：src/analysis/、src/composables/、src/stores/
- ❌ 不能操作：数据获取接口、前端UI代码

---

### UI Agent 职责

#### 1. 前端界面
- Vue组件开发
- 样式调整
- 交互优化

#### 2. 权限
- ✅ 可操作：src/components/、src/views/、public/
- ❌ 不能操作：数据层、业务层代码

---

## 二、核心脚本

### 数据维护脚本（Data Agent）

| 脚本 | 功能 |
|------|------|
| **data_maintenance.py** | 主脚本：包含所有数据类型的获取、存储、warmup、AI数据准备 |
| fetch_sector_data.py | ETF日线获取 |
| market_breadth_spot.py | 涨跌家数请求 |
| save_breadth_history.py | 涨跌家数持久化 |
| etf_amount_daily_sina.py | ETF成交额统计 |

---

## 三、工具清单

### 数据验证工具（Leader用）

| 工具名称 | 功能 | 运行频率 |
|---------|------|---------|
| verify_minute_data.py | 检查分时数据点数 | 09:31、13:01 |
| verify_daily_data.py | 检查日线数据完整性 | 09:15、15:30 |
| verify_warmup_data.py | 检查warmup文件完整性 | 15:30 |
| verify_ai_data.py | 测试/api/snapshot | 09:31 |
| **leader_daily_check.py** | **检查warmup日期 + lifecycle接口 + 触发Data Agent修复** | **盘中/盘后** |

---

### 接口探测工具（Data Agent用）

| 工具名称 | 功能 |
|---------|------|
| check_data_sources.py | 测试接口可用性，自动修复data_protocol.md |
| **diagnose_sector_api.py** | **诊断板块接口问题，测试ETF源 + 修复warmup + 分时回补** |

### 缓存清理工具（Cleanup Agent用）

| 工具名称 | 功能 |
|---------|------|
| cleanup_cache.py scan | 扫描所有缓存，生成过期报告 |
| cleanup_cache.py clean | 扫描 + 确认后删除过期缓存 |
| cleanup_cache.py check \<类型\> | 检查特定类型缓存 |

---

### 工具脚本

| 类型 | 工具 |
|------|------|
| MCP | pencil（设计工具）、4.5v_mcp（图片分析）、web_reader（网页抓取） |
| Tool | 各类验证和数据脚本 |
| Skill | commit、check-data等 |

---

## 四、定时任务配置

### Leader 定时任务

| 时间 | 任务 | 执行脚本 | 日志文件 |
|------|------|---------|---------|
| 09:15 | 日线验证 | verify_daily_data.py | verify_YYYY-MM-DD.log |
| 09:31 | AI接口验证 | verify_ai_data.py | verify_YYYY-MM-DD.log |
| 09:31 | 分时验证 | verify_minute_data.py | verify_YYYY-MM-DD.log |
| 13:01 | 分时验证 | verify_minute_data.py | verify_YYYY-MM-DD.log |
| 15:30 | 日线+warmup验证 | verify_daily_data.py + verify_warmup_data.py | verify_YYYY-MM-DD.log |
| **盘中** | **warmup + lifecycle监控** | **leader_daily_check.py watch** | - |
| **发现问题时** | **触发Data Agent修复** | **leader_daily_check.py full** | - |

---

### Data Agent 定时任务

| 时间 | 任务 | 执行脚本 | 日志文件 |
|------|------|---------|---------|
| 11:30 | 分时数据保存（早盘，120点） | data_maintenance.py | data_minute.log |
| 15:00 | 分时数据保存（全天，240点） | data_maintenance.py | data_minute.log |
| 15:00 | 涨跌家数持久化 | market_breadth_spot.py + save_breadth_history.py | breadth.log |
| 15:30 | 日线数据更新 | data_maintenance.py | data_daily.log |

---

## 五、工作流程

### Leader 日常检查流程

```
1. 09:15 / 盘中监控 / 盘后检查
   ↓
2. 运行 leader_daily_check.py check
   ↓
3. 检查 warmup 日期是否最新（盘后期望今天，盘中期望T-1）
   ↓
4. 检查 /api/sector/lifecycle 接口是否返回空数据
   ↓
5. 如发现问题 → 运行 leader_daily_check.py full
   ↓
6. 自动触发 Data Agent 修复（diagnose_sector_api.py）
   ↓
7. 验证修复后 warmup + lifecycle 正常
```

### 数据问题排查流程

```
1. Leader 发现数据问题
   ↓
2. Leader 运行 check_data_sources.py 测试接口
   ↓
3. Leader 确认问题并分配任务给 Data Agent
   ↓
4. Data Agent 修复数据接口
   ↓
5. Leader 运行验证工具检查修复结果
   ↓
6. Leader 审核通过，更新 task_status.md
   ↓
7. Git 提交
```

### 日常数据维护流程

```
1. 定时任务自动执行（Data Agent 负责）
   ↓
2. 验证工具自动检查（Leader 负责）
   ↓
3. 日志记录到 logs/verify_YYYY-MM-DD.log
   ↓
4. Leader 查看日志确认状态
   ↓
5. 如有问题，Leader 排查并分配给 Data Agent 处理
```

### 分时转日线流程（Data Agent 独立完成）

```
1. 15:00 定时任务触发
   ↓
2. 优先请求日线接口
   ↓
3. 如日线接口成功 → 写入日线数据 → 结束
   ↓
4. 如日线接口失败 → 执行分时转日线 → 保存临时数据
   ↓
5. 18:00 后定时任务
   ↓
6. 重新请求日线接口（复核数据）
   ↓
7. 如发现差异 → 用日线数据覆盖 → 重新Warmup
   ↓
8. 如连续3天无差异 → 停止复核
```

---

## 六、重要文档

| 文档 | 位置 | 维护人 | 用途 |
|------|------|--------|------|
| 数据协议 | docs/agents/data_protocol.md | Leader（每天检查） | 接口定义、存储规则、定时任务 |
| 定时任务配置 | docs/agents/schedule.md | Leader | Crontab配置说明 |
| 任务状态 | docs/agents/task_status.md | Leader | 待办任务、进度跟踪 |
| 开发规则 | docs/agents/CLAUDE_DEV_RULES.md | - | 权限、工作流程（宪法） |
| 每日检查清单 | docs/agents/daily_checklist.md | Leader | 每日启动检查项 |
| 数据Agent规范 | docs/agents/agent_data.md | Data Agent | 数据层工作规范 |
| 业务Agent规范 | docs/agents/agent_business.md | Business Agent | 业务层工作规范 |
| UI Agent规范 | docs/agents/agent_ui.md | UI Agent | 前端层工作规范 |
| 清洁工规范 | docs/agents/agent_cleanup.md | Cleanup Agent | 数据清理规范 |

---

## 七、工具使用规范

### Leader 使用工具

```bash
# 验证数据质量
python3 scripts/verify_daily_data.py
python3 scripts/verify_minute_data.py
python3 scripts/verify_warmup_data.py
python3 scripts/verify_ai_data.py

# 查看日志
tail -100 logs/verify_$(date +%Y-%m-%d).log
```

### Data Agent 使用工具

```bash
# 数据维护
python3 data_maintenance.py

# 接口探测与修复
python3 scripts/check_data_sources.py etf_daily
python3 scripts/check_data_sources.py breadth

# 板块接口诊断与修复
python3 scripts/diagnose_sector_api.py check   # 只诊断
python3 scripts/diagnose_sector_api.py fix      # 诊断 + 修复
python3 scripts/diagnose_sector_api.py full    # 完整流程

# 数据回补
python3 scripts/backfill_etf_daily.py
```

---

## 八、紧急问题处理

### 接口失效
1. Leader 运行 check_data_sources.py 测试
2. Leader 确认问题类型
3. Data Agent 使用 check_data_sources.py 修复
4. Data Agent 更新 data_protocol.md
5. Leader 验证修复结果

### 数据异常
1. Leader 查看验证日志
2. Leader 定位问题类型
3. 分配给 Data Agent 处理
4. Data Agent 修复后
5. Leader 运行验证工具确认

### 数据完整性问题
1. Leader 发现数据缺失
2. Leader 通知 Data Agent
3. Data Agent 执行数据回补
4. Leader 验证数据完整性

---

## 九、启动必读

### Leader 启动必读

1. **docs/agents/CLAUDE_DEV_RULES.md** - 开发规则（宪法）
2. **docs/agents/daily_checklist.md** - 每日检查清单
3. **docs/agents/data_protocol.md** - 数据协议
4. **docs/agents/task_status.md** - 任务状态

### Data Agent 启动必读

1. **docs/agents/CLAUDE_DEV_RULES.md** - 开发规则
2. **docs/agents/agent_data.md** - Data Agent 工作规范
3. **docs/agents/data_protocol.md** - 数据协议

---

**维护者**：Leader
