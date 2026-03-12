#!/bin/bash

# A-Stock-Monitor 数据刷新脚本
# 用法: bash refresh_data.sh [rank|history|news]
# 不带参数则刷新全部数据

set -e

CONTAINER_NAME="a-stock-monitor"
DEFAULT_SECTORS="半导体,云计算,有色金属,煤炭"

# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查容器是否运行
check_container() {
    if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        log_error "容器 ${CONTAINER_NAME} 未运行"
        log_info "请先启动容器: docker start ${CONTAINER_NAME}"
        exit 1
    fi
}

# 刷新排行数据
refresh_rank() {
    log_info "刷新板块排行数据..."
    docker exec ${CONTAINER_NAME} python fetch_sector_data.py rank
    if [ $? -eq 0 ]; then
        log_info "排行数据刷新成功"
    else
        log_error "排行数据刷新失败"
        return 1
    fi
}

# 刷新历史数据
refresh_history() {
    log_info "刷新板块历史数据 (${DEFAULT_SECTORS})..."
    docker exec ${CONTAINER_NAME} python fetch_sector_data.py history_dynamic "${DEFAULT_SECTORS}" 20
    if [ $? -eq 0 ]; then
        log_info "历史数据刷新成功"
    else
        log_error "历史数据刷新失败"
        return 1
    fi
}

# 刷新新闻数据
refresh_news() {
    log_info "刷新新闻数据..."
    docker exec ${CONTAINER_NAME} python fetch_news.py
    if [ $? -eq 0 ]; then
        log_info "新闻数据刷新成功"
    else
        log_error "新闻数据刷新失败"
        return 1
    fi
}

# 主逻辑
main() {
    local cmd=${1:-"all"}

    echo "=========================================="
    echo "  A-Stock-Monitor 数据刷新工具"
    echo "  时间: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "=========================================="
    echo

    check_container

    case $cmd in
        rank)
            refresh_rank
            ;;
        history)
            refresh_history
            ;;
        news)
            refresh_news
            ;;
        all)
            log_info "开始刷新全部数据..."
            refresh_rank && refresh_history && refresh_news
            ;;
        *)
            log_error "未知命令: $cmd"
            echo "用法: $0 [rank|history|news]"
            echo "  不带参数则刷新全部数据"
            exit 1
            ;;
    esac

    if [ $? -eq 0 ]; then
        echo
        log_info "数据刷新完成！"
        echo "查看日志: docker logs -f ${CONTAINER_NAME}"
    else
        echo
        log_error "数据刷新失败，请检查容器日志"
        exit 1
    fi
}

main "$@"
