#!/usr/bin/env python3
"""
新闻获取脚本 - 使用 akshare 获取 A股新闻数据
"""

import json
import hashlib
import os
import re
import argparse
from datetime import datetime
from pathlib import Path
import akshare as ak


def get_news_id(url: str) -> str:
    """使用 MD5 生成 news_id"""
    return hashlib.md5(url.encode('utf-8')).hexdigest()


def truncate_title(summary: str, max_length: int = 50) -> str:
    """从摘要中截取前50字作为标题"""
    if len(summary) <= max_length:
        return summary
    return summary[:max_length]


def parse_publish_time(item: dict, fallback: str) -> str:
    """优先使用 akshare 返回的发布时间字段"""
    candidates = [
        item.get("publish_time"),
        item.get("发布时间"),
        item.get("time"),
        item.get("date"),
    ]
    for val in candidates:
        if val is None:
            continue
        text = str(val).strip()
        if text:
            return text
    return fallback


def detect_related_stocks(text: str) -> list[str]:
    """提取 A 股 6 位股票代码（去重）"""
    if not text:
        return []
    # 沪深京常见证券代码，简单按 6 位数字抽取
    matches = re.findall(r"\b\d{6}\b", text)
    out = []
    seen = set()
    for code in matches:
        if code in seen:
            continue
        seen.add(code)
        out.append(code)
    return out


def detect_country(text: str) -> str:
    """国家优先级：美国 > 日本 > 中国"""
    body = text or ""
    us_keywords = ["美国", "美联储", "美股", "华盛顿", "FOMC", "Fed"]
    jp_keywords = ["日本", "日元", "日经", "日本央行", "BOJ"]
    cn_keywords = ["中国", "A股", "央行", "证监会", "国务院", "人民银行", "两会"]

    if any(k in body for k in us_keywords):
        return "美国"
    if any(k in body for k in jp_keywords):
        return "日本"
    if any(k in body for k in cn_keywords):
        return "中国"
    return "中国"


def transform_news_item(item: dict, fetch_time: str) -> dict:
    """转换单条新闻数据格式"""
    url = str(item.get('url') or item.get('链接') or '').strip()
    summary = str(item.get('summary') or item.get('摘要') or item.get('title') or item.get('标题') or '').strip()
    tag = item.get('tag') or item.get('标签') or ''
    publish_time = parse_publish_time(item, fetch_time)
    related_stocks = detect_related_stocks(f"{summary} {url}")
    country = detect_country(summary)

    return {
        "news_id": get_news_id(url),
        "title": truncate_title(summary),
        "content": summary,
        "source": "东方财富",  # akshare stock_news_main_cx 数据来源
        "url": url,
        "tag": tag,
        "fetch_time": fetch_time,
        "publish_time": publish_time,
        "related_stocks": related_stocks,
        "country": country
    }


def load_existing_news(file_path: str) -> dict:
    """加载已存在的新闻数据"""
    if not os.path.exists(file_path):
        return None

    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def merge_news(existing_data: dict, new_items: list) -> dict:
    """合并新闻数据，去重逻辑基于 url（兼容旧格式的 source_url）"""
    # 创建现有新闻的 url 集合（兼容两种格式）
    existing_urls = set()
    for news in existing_data['news']:
        url = news.get('url') or news.get('source_url')
        if url:
            existing_urls.add(url)

    # 筛选新增的新闻（url 不重复的）
    items_to_add = [
        item for item in new_items
        if item['url'] not in existing_urls
    ]

    # 合并数据
    merged_news = existing_data['news'] + items_to_add
    existing_data['news'] = merged_news
    existing_data['total'] = len(merged_news)

    return existing_data


def fetch_news(date_str: str = None, time_slot: str = None):
    """
    获取新闻数据并保存

    Args:
        date_str: 日期字符串 (YYYY-MM-DD)，默认为今天
        time_slot: 时间槽标识，用于 realtime 模式（如 pre_market, 09:10）
    """
    # 确定日期
    if date_str is None:
        date_str = datetime.now().strftime('%Y-%m-%d')

    fetch_time = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')

    print(f"[{fetch_time}] 开始获取新闻数据...")

    # 获取新闻数据
    try:
        df = ak.stock_news_main_cx()
        print(f"成功获取 {len(df)} 条新闻")
    except Exception as e:
        print(f"获取新闻失败: {e}")
        return

    if len(df) == 0:
        print("未获取到任何新闻数据")
        return

    # 转换为字典列表
    news_list = df.to_dict('records')

    # 转换数据格式
    transformed_items = [transform_news_item(item, fetch_time) for item in news_list]

    # 构建数据目录
    data_dir = Path(__file__).resolve().parent / 'data' / 'news'
    data_dir.mkdir(parents=True, exist_ok=True)

    # 文件路径
    if time_slot:
        # realtime 模式：保存到 data/news/YYYY-MM-DD/time_slot.json
        date_dir = data_dir / date_str
        date_dir.mkdir(parents=True, exist_ok=True)
        file_path = date_dir / f"{time_slot}.json"
    else:
        # daily 模式：保存到 data/news/YYYY-MM-DD.json
        file_path = data_dir / f"{date_str}.json"

    # 检查文件是否存在
    existing_data = load_existing_news(str(file_path))

    if existing_data:
        print(f"发现已有数据文件，合并去重...")
        # 计算新增数量（兼容旧格式 source_url）
        existing_urls = set()
        for news in existing_data['news']:
            url = news.get('url') or news.get('source_url')
            if url:
                existing_urls.add(url)
        items_to_add = [item for item in transformed_items if item['url'] not in existing_urls]
        # 合并去重
        final_data = merge_news(existing_data, transformed_items)
        print(f"新增 {len(items_to_add)} 条新闻")
    else:
        print(f"创建新的数据文件...")
        # 创建新数据
        final_data = {
            "date": date_str,
            "fetch_time": fetch_time,
            "source": "akshare/stock_news_main_cx",
            "total": len(transformed_items),
            "news": transformed_items
        }

    # 保存文件
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(final_data, f, ensure_ascii=False, indent=2)

    print(f"✓ 数据已保存到: {file_path}")
    print(f"✓ 总新闻数: {final_data['total']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='抓取新闻并写入 data/news/YYYY-MM-DD.json')
    parser.add_argument('--date', type=str, default=None, help='日期，格式 YYYY-MM-DD，默认今天')
    parser.add_argument('--mode', type=str, choices=['daily', 'realtime'], default='daily',
                        help='运行模式：daily（按日归档，文件名 YYYY-MM-DD.json）或 realtime（实时模式，按时间段分片）')
    args = parser.parse_args()

    # 根据模式决定 date 参数和 time_slot
    if args.mode == 'realtime':
        # realtime 模式：使用日期 + 时间槽
        date_str = datetime.now().strftime('%Y-%m-%d')
        now = datetime.now()
        # 判断是否开盘前（<9:00）
        if now.hour < 9:
            time_slot = 'pre_market'
        elif now.hour > 15 or (now.hour == 15 and now.minute > 0):
            # 收盘后（>15:00）
            time_slot = 'post_market'
        else:
            # 交易时间：按10分钟分片（9:00-15:00）
            minute_slot = (now.minute // 10) * 10
            time_slot = f"{now.hour:02d}:{minute_slot:02d}"
    else:
        # daily 模式：只使用日期
        date_str = args.date
        time_slot = None

    fetch_news(date_str, time_slot)
