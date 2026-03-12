#!/bin/bash
# Agent 协作工具 - 防止代码漂移
# 使用方法: source .claude/agent-coordinator.sh

AGENT_WORK_DIR="/tmp/agent_work_$$"
mkdir -p "$AGENT_WORK_DIR"

# Agent 开始工作前
agent_start() {
    local agent_name=$1
    local task_desc=$2

    echo "=== Agent $agent_name 开始: $task_desc ==="

    # 1. 拉取最新代码
    git pull --rebase 2>/dev/null || true

    # 2. 记录工作状态
    cat > "$AGENT_WORK_DIR/${agent_name}_status.json" <<EOF
{
  "agent": "$agent_name",
  "task": "$task_desc",
  "start_time": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "git_head": "$(git rev-parse HEAD)",
  "status": "working"
}
EOF

    # 3. 检查是否有其他 Agent 正在工作
    for f in /tmp/agent_work_*/*_status.json; do
        if [ -f "$f" ]; then
            local other_agent=$(jq -r '.agent' "$f" 2>/dev/null)
            local other_status=$(jq -r '.status' "$f" 2>/dev/null)
            if [ "$other_agent" != "$agent_name" ] && [ "$other_status" = "working" ]; then
                echo "⚠️  检测到 Agent $other_agent 也在工作中，请协调避免冲突"
            fi
        fi
    done
}

# Agent 完成工作后
agent_done() {
    local agent_name=$1
    local files_changed=$2

    echo "=== Agent $agent_name 完成 ==="

    # 1. 显示改动
    if [ -n "$files_changed" ]; then
        echo "修改的文件:"
        git diff --stat $files_changed
    fi

    # 2. 更新状态
    if [ -f "$AGENT_WORK_DIR/${agent_name}_status.json" ]; then
        jq ".status = \"done\" | .end_time = \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"" \
           "$AGENT_WORK_DIR/${agent_name}_status.json" > "${AGENT_WORK_DIR}/${agent_name}_status.json.tmp"
        mv "${AGENT_WORK_DIR}/${agent_name}_status.json.tmp" "$AGENT_WORK_DIR/${agent_name}_status.json"
    fi

    # 3. 提示是否提交
    echo ""
    echo "✅ 工作完成！建议执行以下命令："
    echo "   git add $files_changed"
    echo "   git commit -m \"feat($agent_name): $task_desc\""
    echo ""
}

# Agent 复查前
agent_review_start() {
    local reviewer_name=$1

    echo "=== Agent $reviewer_name 开始复查 ==="

    # 1. 检查是否有未完成的工作
    local has_incomplete=0
    for f in /tmp/agent_work_*/*_status.json; do
        if [ -f "$f" ]; then
            local status=$(jq -r '.status' "$f" 2>/dev/null)
            if [ "$status" = "working" ]; then
                echo "⚠️  检测到未完成的工作:"
                jq -r '"Agent: \(.agent) | Task: \(.task) | Start: \(.start_time)"' "$f"
                has_incomplete=1
            fi
        fi
    done

    if [ $has_incomplete -eq 1 ]; then
        echo "❌ 建议等待其他 Agent 完成后再复查"
        return 1
    fi

    # 2. 拉取最新代码
    git pull --rebase 2>/dev/null || true

    # 3. 显示最近改动
    echo "最近的改动:"
    git log --oneline -10
    echo ""
}

# 快速检查文件状态
check_file_status() {
    local file=$1

    echo "=== 文件状态检查: $file ==="

    # 1. Git 状态
    echo "Git 状态:"
    git status $file --short

    # 2. 最近修改
    echo "最近修改行:"
    git diff $file | grep "^[+-]" | head -20

    # 3. 关键时间戳
    echo ""
    echo "文件时间戳:"
    ls -lh $file
}

# 导出函数
export -f agent_start
export -f agent_done
export -f agent_review_start
export -f check_file_status
