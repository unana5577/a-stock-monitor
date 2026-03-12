#!/bin/bash
# 详细逻辑验证 - 找出 Agent C 看到的具体问题

echo "🔍 详细逻辑验证"
echo "================================"
echo ""

echo "📌 Agent B 的时间逻辑详情:"
echo "--------------------------------"
grep -n "mockTimeEnabled" public/ui.js | head -5
echo ""

echo "📌 Agent A 的分时数据逻辑详情:"
echo "--------------------------------"
grep -n "当日分时走势" public/ui.js | head -5
grep -n "data.minute" public/ui.js | head -3
echo ""

echo "📌 检查是否有旧逻辑残留:"
echo "--------------------------------"
# 检查是否有旧的 history 数据处理逻辑
grep -n "data.history" public/ui.js | head -5
echo ""

echo "📌 关键代码行定位:"
echo "--------------------------------"
echo "mockTime 变量定义在行:"
grep -n "mockTimeEnabled = ref" public/ui.js
echo ""
echo "分时数据处理在行:"
grep -n "days === 1 && data.minute" public/ui.js
echo ""

echo "================================"
echo ""
echo "💡 如果 Agent C 说没有这些逻辑，请检查："
echo "   1. 浏览器是否刷新了缓存 (Ctrl+Shift+R)"
echo "   2. 查看的文件路径是否正确 (pwd)"
echo "   3. 是否在 node_modules 或其他目录有旧的 ui.js"
