# Agent 协作复查清单

## 给 Agent C 的复查指令

当你需要复查其他 Agent 的修改时，按以下步骤操作：

### 1️⃣ 复查前准备
```bash
# 在 VS Code 终端执行
cd /Users/una5577/Documents/trae_projects/a-stock-monitor

# 确保拿到最新代码
git pull --rebase 2>/dev/null || true

# 检查文件状态
git status public/ui.js

# 运行自动检查
./scripts/check_agent_sync.sh
```

### 2️⃣ 查看具体改动
```bash
# 查看最近的 Git 提交
git log --oneline -5

# 查看未提交的改动
git diff public/ui.js | head -100

# 查看特定关键代码是否存在
grep -n "mockTimeEnabled" public/ui.js      # Agent B 的逻辑
grep -n "当日分时走势" public/ui.js         # Agent A 的逻辑
grep -n "data.minute" public/ui.js          # Agent A 的逻辑
```

### 3️⃣ 验证关键代码行
```bash
# 执行详细验证
./scripts/verify_logic_details.sh
```

### 4️⃣ 如果发现问题
```bash
# 查看完整差异
git diff public/ui.js > /tmp/ui_js_diff.txt
cat /tmp/ui_js_diff.txt

# 或者在 VS Code 中查看
# 1. 打开源代码管理面板 (Ctrl+Shift+G)
# 2. 点击 public/ui.js 查看改动
```

### 5️⃣ 确认无误后提交
```bash
git add public/ui.js
git commit -m "feat: 合并 Agent A 和 B 的改动

- Agent A: 分时数据显示逻辑
- Agent B: 全局时间模拟逻辑
- 复查: Agent C"
```

## 常见问题排查

### ❌ "看不到 B 的逻辑"
- 执行：`grep -n "mockTimeEnabled" public/ui.js`
- 如果没有输出，说明文件确实缺失，需要让 Agent B 重新执行

### ❌ "看到的是旧逻辑"
- 执行：`grep -n "data.history" public/ui.js | head -5`
- 检查是否是旧代码残留，或者浏览器缓存问题

### ❌ "代码混乱"
- 执行：`git diff public/ui.js | grep "^@@"`
- 查看改动的时间线和作者，判断是否有冲突

## VS Code 操作提示

1. **刷新文件**：右键文件 → "Revert File" 或重新打开
2. **查看历史**：右键文件 → "Open Timeline" 查看修改历史
3. **对比版本**：源代码管理面板 → 点击文件查看 diff

---

**最后修改**: 2026-03-10
**适用场景**: 多 Agent 协作修改同一文件
