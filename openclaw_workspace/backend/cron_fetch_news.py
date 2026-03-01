#!/usr/bin/env python3
"""
定时新闻抓取脚本 - P1-1
每天收盘后自动抓取并分类新闻

执行时间建议：每天 15:35（收盘后35分钟）
crontab: 35 15 * * 1-5 python3 /path/to/cron_fetch_news.py
"""

import sys
import os
from datetime import datetime
from pathlib import Path

# 添加当前目录到路径，确保能导入其他模块
sys.path.insert(0, str(Path(__file__).parent))

# 导入新闻抓取和分类模块
from fetch_news import fetch_news
from classify_news import process_news_file


def main():
    """主函数：抓取并分类新闻"""
    # 日志目录
    log_dir = Path('/Users/una5577/Documents/trae_projects/a-stock-monitor/openclaw_workspace/logs')
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / 'news_fetch.log'

    # 获取今天日期
    today = datetime.now().strftime('%Y-%m-%d')
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    log_messages = [f"\n{'='*50}", f"[{timestamp}] 开始执行新闻抓取任务"]

    try:
        # 步骤1：抓取新闻
        log_messages.append("步骤1: 抓取新闻数据...")
        fetch_news(today)
        log_messages.append("✓ 新闻抓取完成")

        # 步骤2：分类新闻
        log_messages.append("步骤2: 分类新闻数据...")
        news_dir = Path('/Users/una5577/Documents/trae_projects/a-stock-monitor/data/news')
        news_file = news_dir / f'{today}.json'

        if news_file.exists():
            result = process_news_file(str(news_file))
            log_messages.append(f"✓ 新闻分类完成: 保留 {result['stats']['kept']} 条，过滤 {result['stats']['filtered']} 条")
        else:
            log_messages.append(f"⚠ 未找到今日新闻文件: {news_file}")

        log_messages.append(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 任务完成 ✓")

    except Exception as e:
        log_messages.append(f"✗ 任务失败: {str(e)}")
        # 写入错误日志
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write('\n'.join(log_messages) + '\n')
        raise

    # 写入日志
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write('\n'.join(log_messages) + '\n')

    # 打印到控制台
    print('\n'.join(log_messages))


if __name__ == "__main__":
    main()
