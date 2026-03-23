# 开发权限规则

> 日期：2026-03-20
> 状态：已生效

## 无需确认的操作

### 1. 代码编写与测试
- ✅ 创建新脚本文件
- ✅ 修改代码逻辑
- ✅ 运行测试脚本
- ✅ 执行语法检查（python3 -m py_compile, npm run lint）
- ✅ 运行数据验证脚本

### 2. Git 操作
- ✅ git add（��个文件或目录）
- ✅ git commit（自动生成提交信息）
- ✅ git status / git diff / git log

### 3. Bash 命令
- ✅ python3 执行脚本
- ✅ npm run lint / npm run typecheck
- ✅ ls / cat / head / tail（查看文件）
- ✅ grep（搜索内容）

## 需要确认的操作

### 1. 危险命令
- ❌ rm -rf（删除目录）
- ❌ rm .*（删除隐藏文件）
- ❌ git clean（清理未追踪文件）
- ❌ git reset --hard（强制重置）
- ❌ git push --force（强制推送）

### 2. 删除文件
- ❌ 删除 .py / .js / .json 源代码文件
- ❌ 删除 data/ 中的数据文件（需确认）
- ❌ 删除 docs/ 中的文档（需确认）

### 3. Git 推送
- ❌ git push（需确认后再推送）

### 4. 最终验证
- ❌ 提交前的最终验收（确认功能正常）

## 工作流程

```
1. 编写代码 → 自动
2. 运行测试 → 自动
3. 语法检查 → 自动
4. Git Add → 自动
5. Git Commit → 自动
6. 功能验证 → 等待用户确认
7. Git Push → 用户确认后执行
```

## 示例

### 无需确认
```bash
python3 test_etf_data.py
python3 -m py_compile fetch_sector_data.py
git add fetch_sector_data.py
git commit -m "fix: 修复ETF数据接口"
```

### 需要确认
```bash
rm -rf data/              # 危险
git push origin main      # 需确认
rm fetch_sector_data.py   # 删除源码
```

---

## 数据复核标准

> 数据Agent完成任务后，必须按以下标准自动输出验证结果

### 1. ETF/指数日线更新

| 检查项 | 预期结果 | 验证命令 |
|--------|---------|---------|
| 最新日期 | 昨天（盘前）或今天（盘后） | `tail -1 data/etf_daily/etf_512480.jsonl` |
| amount非0 | > 0 | 检查最后一条记录的amount字段 |

### 2. 分时数据更新

| 检查项 | 预期结果 | 验证命令 |
|--------|---------|---------|
| 交易时段有数据 | 每分钟有新记录 | `wc -l data/minute-*.jsonl` |
| 数据时间戳 | 从09:30开始 | `head -1 data/minute-*.jsonl` |

### 3. 成交额聚合

| 检查项 | 预期结果 | 验证命令 |
|--------|---------|---------|
| 今日有数据 | 存在今日记录 | `tail -1 data/market/market-amount-daily.jsonl` |
| amount非0 | > 0 | 检查最后一条记录的amount |

### 4. 涨跌家持久化

| 检查项 | 预期结果 | 验证命令 |
|--------|---------|---------|
| 11:30快照 | 存在 | `grep "11:30" data/market/breadth-history.jsonl` |
| 15:00快照 | 存在 | `grep "15:00" data/market/breadth-history.jsonl` |

### 5. 分时清理

| 检查项 | 预期结果 | 验证命令 |
|--------|---------|---------|
| 只保留5个交易日 | ≤ 5个文件 | `ls data/minute-*.jsonl \| wc -l` |

### 输出格式

完成任务后，必须输出：

```
=== 数据复核报告 ===
ETF日线: ✅ 最新日期2026-03-19
指数日线: ✅ 最新日期2026-03-19
分时数据: ✅ 241条记录
成交额: ✅ 今日有数据
涨跌家: ✅ 11:30和15:00快照已保存
分时清理: ✅ 保留5个交易日
状态: 全部通过
```
