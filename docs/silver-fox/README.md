# A股量化项目 - 文档结构说明

## 📁 文档分类

### 核心文档
| 文档 | 说明 | 状态 |
|------|------|------|
| 需求.md | 项目需求、功能、回测结果 | ✅ 已创建 |
| 数据文档.md | 数据来源、存储、API设计 | ✅ 已创建 |
| 回测配置.md | 阈值配置、优化计划 | ✅ 已创建 |

### 项目相关文档（从 workspace/memory/projects 迁移）
| 文档 | 说明 |
|------|------|
| a-share-quant.md | A股量化软件进展记录 |
| a-share-quant-workflow.md | 工作流追踪 |
| a-share-quant-backtest.md | 回测报告 |
| a-share-quant-todo.md | 待办事项 |
| a-share-quant-result-table.md | 回测结果表格 |
| a-share-quant-review.md | 回测复盘 |
| a-share-quant-fixed.md | 修复记录 |
| backend-tasks.md | 后端任务列表 |
| backend-news-tasks.md | 新闻模块任务 |
| news-rules.md | 新闻规则 |
| news-tasks-akshare.md | Akshare 新闻任务 |
| 2026-02-24-morning-report.md | 早报记录 |
| work-plan.md | 工作计划 |
| news_factor_module_design.md | 新闻因子模块设计 |

---

## 📊 数据文件

### 后端代码
- `classify_news.py` - 新闻分类
- `fetch_news.py` - 新闻获取

### 数据文件
- `data/news/2026-02-23.json` - 新闻数据（2026-02-23）
- `data/tasks.json` - VidClaw 任务列表

---

## 🗂️ 待整理文件（仍留在 workspace）

### 个人配置文件（不动）
- `AGENTS.md` - Agent 配置
- `IDENTITY.md` - 身份信息
- `MEMORY.md` - 长期记忆
- `MISSION_CONTROL.md` - 任务控制
- `SOUL.md` - 灵魂定义
- `TOOLS.md` - 工具配置
- `USER.md` - 用户信息
- `WORKFLOW.md` - 工作流程
- `HEARTBEAT.md` - 心跳任务
- `LESSONS_LEARNED.md` - 教训记录

### 日志文件（可定期清理）
- `memory/2026-02-21.md` - 2026-02-21 日志
- `memory/2026-02-23.md` - 2026-02-23 日志

---

## ✅ 已完成的迁移

1. ✅ 创建项目目录结构
2. ✅ 移动后端代码（classify_news.py, fetch_news.py）
3. ✅ 移动新闻数据（2026-02-23.json）
4. ✅ 移动 tasks.json
5. ✅ 迁移所有项目相关文档
6. ✅ 创建文档结构说明

---

## 🗑️ 可以删除的文件

以下文件已迁移到新项目，旧文件可以删除：

### Backend 代码（已复制到 ~/股票项目/backend/）
- `~/.openclaw/workspace/classify_news.py`
- `~/.openclaw/workspace/fetch_news.py`

### 项目文档（已复制到 ~/股票项目/docs/）
- `~/.openclaw/workspace/memory/projects/a-share-quant.md`
- `~/.openclaw/workspace/memory/projects/a-share-quant-workflow.md`
- `~/.openclaw/workspace/memory/projects/a-share-quant-backtest.md`
- `~/.openclaw/workspace/memory/projects/a-share-quant-todo.md`
- `~/.openclaw/workspace/memory/projects/a-share-quant-result-table.md`
- `~/.openclaw/workspace/memory/projects/a-share-quant-review.md`
- `~/.openclaw/workspace/memory/projects/a-share-quant-fixed.md`
- `~/.openclaw/workspace/memory/projects/backend-tasks.md`
- `~/.openclaw/workspace/memory/projects/backend-news-tasks.md`
- `~/.openclaw/workspace/memory/projects/news-rules.md`
- `~/.openclaw/workspace/memory/projects/news-tasks-akshare.md`
- `~/.openclaw/workspace/memory/projects/2026-02-24-morning-report.md`
- `~/.openclaw/workspace/memory/projects/work-plan.md`
- `~/.openclaw/workspace/news_factor_module_design.md`

### 数据文件（已复制到 ~/股票项目/data/）
- `~/.openclaw/workspace/vidclaw/server/data/tasks.json`
- `~/.openclaw/workspace/data/news/2026-02-23.json`

---

## ⚠️ 可能丢失的文件

### 未找到的后端代码
- `sector_lifecycle.py` - 核心判断逻辑
- `sector_lifecycle_config.py` - 阈值配置
- `fetch_sector_data.py` - 数据获取
- `backtest_thresholds.py` - 回测脚本

**原因**：这些文件可能在其他位置或尚未创建

### 未找到的数据文件
- 板块数据（*.csv）
- 指数数据（*.csv）
- 市场情绪数据（market-breadth.json）

**原因**：这些文件可能存储在 VidClaw 的其他位置或尚未生成

---

## 📋 下一步建议

1. **搜索后端代码**：
   ```bash
   find ~ -name "sector_lifecycle.py" 2>/dev/null
   find ~ -name "fetch_sector_data.py" 2>/dev/null
   ```

2. **搜索数据文件**：
   ```bash
   find ~ -name "*.csv" -path "*/sector/*" 2>/dev/null
   find ~ -name "market-breadth.json" 2>/dev/null
   ```

3. **清理旧文件**：
   删除已迁移的旧文件（见"可以删除的文件"部分）

---

更新时间：2026-02-24
