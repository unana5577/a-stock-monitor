# 📋 Codex 任务分配

**创建时间**: 2026-02-24 23:05
**任务清单**: 20 个任务（每个 5 分钟）
**预计总时间**: 100 分钟（约 2 小时）

---

## 🎯 立即开始第一个任务

### Task 1.1: 修改 fetch_news.py 支持时间分片（5分钟）

**文件**: `~/Documents/trae_projects/a-stock-monitor/fetch_news.py`

**具体操作**:
1. 添加参数解析：
   ```python
   parser.add_argument('--mode', type=str, default='daily', 
                       choices=['daily', 'realtime'],
                       help='运行模式：daily=每日汇总，realtime=实时更新')
   ```

2. 修改文件名生成逻辑：
   ```python
   def get_filename(mode, date_str):
       if mode == 'realtime':
           now = datetime.now()
           if now.hour < 9:
               return 'pre_market.json'
           else:
               time_slot = f"{now.hour:02d}:{(now.minute // 10) * 10:02d}"
               return f"{time_slot}.json"
       else:
           return f"{date_str}.json"
   ```

3. 测试：
   ```bash
   cd ~/Documents/trae_projects/a-stock-monitor
   python3 fetch_news.py --mode=realtime
   ```

**验收标准**:
- [ ] 添加 `--mode` 参数
- [ ] 根据 mode 决定文件名格式
- [ ] 测试通过

---

## 📋 所有任务清单

**位置**: `openclaw_workspace/docs/新闻模块任务清单-5分钟级别.md`

**任务数据**: `openclaw_workspace/data/tasks.json`

---

## 🚀 执行顺序

### Phase 1: 实时更新机制（30分钟）
1. Task 1.1 - 修改 fetch_news.py 支持时间分片 ⏳
2. Task 1.2 - 实现开盘前数据标记 ⏳
3. Task 1.3 - 实现交易时间分片 ⏳
4. Task 1.4 - 修改 classify_news.py 添加时间分片字段 ⏳
5. Task 1.5 - 创建目录结构生成脚本 ⏳
6. Task 1.6 - 编写定时任务脚本 ⏳

### Phase 2: 关注板块和股票（20分钟）
7. Task 2.1 - 创建关注板块配置文件 ⏳
8. Task 2.2 - 创建关注股票配置文件 ⏳
9. Task 2.3 - 修改 classify_news.py 读取配置 ⏳
10. Task 2.4 - 添加关注标记到新闻数据 ⏳

### Phase 4: API 接口开发（25分钟）
11. Task 4.1 - 实现 GET /api/news 接口 ⏳

### Phase 3: 数据库设计（25分钟）
12. Task 3.1 - 设计新闻主表 ⏳
13. Task 3.2 - 设计新闻-板块关联表 ⏳
14. Task 3.3 - 设计新闻-股票关联表 ⏳
15. Task 3.4 - 创建数据库初始化脚本 ⏳
16. Task 3.5 - 编写数据迁移脚本 ⏳

### Phase 4: API 接口开发（续）
17. Task 4.2 - 实现时间分片过滤 ⏳
18. Task 4.3 - 实现关注板块过滤 ⏳
19. Task 4.4 - 实现 GET /api/news/summary 接口 ⏳
20. Task 4.5 - 添加 API 测试脚本 ⏳

---

## 📝 完成后汇报

**每完成一个任务，请在对话中汇报**：
- ✅ Task X.X 完成
- 文件位置：`...`
- 测试结果：`...`

---

**Codex，请立即开始 Task 1.1！** 🚀
