#!/bin/bash
# Agent 同步状态检查工具
# 用于 Agent C 复查前验证文件是否包含所有预期的改动

echo "🔍 Agent 协作一致性检查"
echo "================================"
echo ""

# 检查1: Git 状态
echo "📌 1. Git 文件状态"
git status --short | grep -E "\.(js|py)$" || echo "   ✅ 无未提交改动"
echo ""

# 检查2: 关键特性检测
echo "📌 2. 关键特性检测"
echo "   检查 Agent B 的时间逻辑..."
if grep -q "mockTimeEnabled" public/ui.js 2>/dev/null; then
    echo "   ✅ B 的全局时间逻辑 (mockTimeEnabled) 已存在"
else
    echo "   ❌ 缺少 B 的全局时间逻辑"
fi

echo ""
echo "   检查 Agent A 的分时数据逻辑..."
if grep -q "当日分时走势" public/ui.js 2>/dev/null; then
    echo "   ✅ A 的分时数据显示逻辑已存在"
else
    echo "   ❌ 缺少 A 的分时数据显示逻辑"
fi
echo ""

# 检查3: 文件修改时间
echo "📌 3. 文件修改时间"
ls -lh public/ui.js 2>/dev/null | awk '{print "   ui.js 最后修改: " $6 " " $7 " " $8}'
echo ""

# 检查4: Git 提交历史
echo "📌 4. 最近的 Git 提交"
git log --oneline -5 2>/dev/null || echo "   ⚠️  无提交历史"
echo ""

# 检查5: 代码行数变化
echo "📌 5. 代码规模"
wc -l public/ui.js 2>/dev/null | awk '{print "   ui.js 总行数: " $1}'
echo ""

# 检查6: 潜在问题检测
echo "📌 6. 潜在问题检测"

# 检查是否有明显的重复代码块
if grep -c "const myChart = window.echarts.init" public/ui.js 2>/dev/null | xargs test $(grep -c "const myChart = window.echarts.init" public/ui.js) -gt 1; then
    echo "   ⚠️  可能存在重复的图表初始化代码"
fi

# 检查是否有未完成的 TODO
if grep -i "TODO\|FIXME\|XXX" public/ui.js 2>/dev/null; then
    echo "   ⚠️  发现未完成的 TODO 项:"
    grep -n "TODO\|FIXME\|XXX" public/ui.js | head -5
fi

echo ""
echo "================================"
echo "✅ 检查完成"
echo ""
echo "💡 建议："
echo "   1. 如果发现缺失逻辑，请对应的 Agent 重新执行修改"
echo "   2. 修改完成后执行: git add public/ui.js && git commit -m 'feat: 合并改动'"
echo "   3. 复查前执行: git pull --rebase 确保拿到最新代码"
