#!/usr/bin/env python3
"""
新闻获取脚本 - 使用 akshare 获取 A股新闻数据
"""

import json
import hashlib
import os
import re
from datetime import datetime
from pathlib import Path
import pandas as pd
import akshare as ak


def get_news_id(url: str) -> str:
    """使用 MD5 生成 news_id"""
    return hashlib.md5(url.encode('utf-8')).hexdigest()


def extract_title(summary: str, max_length: int = 20) -> str:
    """
    从摘要中提取标题（最多20字）
    策略：重要机构 + 核心主体 + 动作，保留有冲击力的词
    """
    if len(summary) <= max_length:
        return summary
    
    # 重要机构（发布方，需要保留）
    publishers = ['瑞银', '高盛', '摩根', '美联储', '央行', '证监会', '财政部', 'IMF', '世界银行']
    
    # 主体词（谁）- 按重要性排序
    subjects = [
        '锂市场', '锂价', '铜价', '金价', '油价', '半导体', '芯片', '黄金', '原油', '新能源', '锂', '铜',
        '韩国股市', '日本股市', 'A股', '港股', '美股', '创业板', '科创板',
        '特斯拉', '苹果', '华为', '英伟达', 'OpenAI', 'Anthropic', 'Stripe', 'PayPal', 'Salesforce',
        '韩国', '日本', '美国', '中国', '欧洲', '俄罗斯', '印度',
        'AI', '股市',
    ]
    
    # 动作词
    actions = [
        '实质性短缺', '严重过剩', '大幅上涨', '大幅下跌', '暴涨', '暴跌', 
        '创新高', '创新低', '突破', '跌破',
        '全部收购', '收购', '并购', '合并', '上市', '退市', 
        '发布', '推出', '获批', '称',
        '短缺', '过剩', '降息', '加息', '降准',
        '维持震荡', '震荡', '走弱', '走强', '稳定',
        '上涨', '下跌', '涨', '跌', '反弹', '回调',
    ]
    
    # 冲击力词汇
    impact_words = ['大关', '里程碑', '历史新高', '历史新低', '暴跌', '暴涨', '崩盘', '血洗', '蒸发']
    
    # 发布类动作（优先级排序）
    publish_actions = ['发布', '报告', '预测', '称']

    # 数字模式
    num_pattern = r'[\d,.]+[%万千百亿]?[点美元元]'
    num_match = re.search(num_pattern, summary)
    num_str = num_match.group() if num_match else ''
    num_idx = num_match.start() if num_match else -1

    # 1. 找发布机构
    found_publisher = None
    publisher_idx = -1
    for pub in publishers:
        if pub in summary:
            found_publisher = pub
            publisher_idx = summary.index(pub)
            break
    
    # 2. 找主体（去重）
    found_subjects = []
    for sub in subjects:
        if sub in summary:
            idx = summary.index(sub)
            is_contained = False
            for other_sub in subjects:
                if other_sub != sub and sub in other_sub and other_sub in summary:
                    is_contained = True
                    break
            if not is_contained:
                found_subjects.append((sub, idx))
    found_subjects.sort(key=lambda x: x[1])
    
    # 3. 找动作
    found_action = None
    action_idx = -1
    for act in sorted(actions, key=len, reverse=True):
        if act in summary:
            found_action = act
            action_idx = summary.index(act)
            break
    
    # 4. 找冲击力词
    found_impact = None
    for word in impact_words:
        if word in summary:
            found_impact = word
            break
    
    # 5. 找核心主体
    core_subject = None
    core_subject_idx = -1
    if found_action and found_subjects:
        for subj, idx in found_subjects:
            if idx < action_idx:
                core_subject = subj
                core_subject_idx = idx
            else:
                break
    
    if not core_subject and found_subjects:
        core_subject = found_subjects[0][0]
        core_subject_idx = found_subjects[0][1]

    # 6. 智能组合
    # 情况1：收购类 - 主体1 + 收购 + 主体2
    if found_action and '收购' in found_action and len(found_subjects) >= 2:
        subj1 = found_subjects[0][0]
        subj2 = found_subjects[1][0]
        if found_subjects[0][1] < action_idx < found_subjects[1][1]:
            title = subj1 + found_action + subj2
            if len(title) <= max_length:
                return title
    
    # 情况2：有发布机构 + 核心主体 + 动作（如：瑞银发布锂市场短缺）
    if found_publisher and core_subject and found_action and publisher_idx < core_subject_idx:
        # 找发布动作（必须是动词，在机构后面）
        publish_act = None
        
        # 优先找"发表"，用"发布"替代
        if '发表' in summary:
            pub_idx = summary.index('发表')
            if publisher_idx < pub_idx < core_subject_idx:
                publish_act = '发布'
        
        # 如果没找到"发表"，再找其他发布动作
        if not publish_act:
            for act in publish_actions:
                if act in summary:
                    pub_idx = summary.index(act)
                    if publisher_idx < pub_idx < core_subject_idx:
                        publish_act = act
                        break
        
        if publish_act and core_subject_idx < action_idx:
            # 组合：机构 + 发布 + 核心内容
            end_idx = min(len(summary), action_idx + len(found_action) + 4)
            core_content = summary[core_subject_idx:end_idx]
            for punct in ['，', '。', '！', '？']:
                if punct in core_content:
                    core_content = core_content[:core_content.index(punct)]
                    break
            title = found_publisher + publish_act + core_content
            if len(title) <= max_length:
                return title
            # 太长，简化
            title = found_publisher + publish_act + core_subject + found_action
            if len(title) <= max_length:
                return title
    
    # 情况3：核心主体 + 动作 + 数字 + 冲击力词（如：韩国股市突破5,000点大关）
    if core_subject and found_action and num_str and found_impact:
        if core_subject_idx < action_idx < num_idx:
            title = core_subject + found_action + num_str + found_impact
            if len(title) <= max_length:
                return title
            # 太长，去掉动作
            title = core_subject + num_str + found_impact
            if len(title) <= max_length:
                return title
    
    # 情况4：核心主体 + 动作 + 数字（如：特斯拉暴跌10%）
    if core_subject and found_action and num_str and core_subject_idx < action_idx:
        title = core_subject + found_action + num_str
        if len(title) <= max_length:
            return title
    
    # 情况5：核心主体 + 动作
    if core_subject and found_action and core_subject_idx < action_idx:
        title = core_subject + found_action
        if 4 <= len(title) <= max_length:
            return title
    
    # 情况6：只有核心主体
    if core_subject and core_subject_idx >= 0:
        next_punct = len(summary)
        for punct in ['，', '。', '！', '？', '、']:
            idx = summary.find(punct, core_subject_idx + 1)
            if idx != -1 and idx < next_punct:
                next_punct = idx
        segment = summary[core_subject_idx:next_punct]
        if 4 <= len(segment) <= max_length:
            return segment
        if len(segment) > max_length:
            return segment[:max_length]
    
    # 7. 兜底
    first_part = re.split(r'[，。！？]', summary)[0]
    if len(first_part) <= max_length:
        return first_part
    
    return first_part[:max_length]


def transform_news_item(item: dict, fetch_time: str) -> dict:
    """转换单条新闻数据格式"""
    url = item['url']
    summary = item['summary']
    tag = item['tag']

    return {
        "news_id": get_news_id(url),
        "title": extract_title(summary),
        "content": summary,
        "source": "东方财富",
        "url": url,
        "tag": tag,
        "fetch_time": fetch_time
    }


def load_existing_news(file_path: str) -> dict:
    """加载已存在的新闻数据"""
    if not os.path.exists(file_path):
        return None

    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def merge_news(existing_data: dict, new_items: list) -> dict:
    """合并新闻数据，去重逻辑基于 url"""
    existing_urls = {news['url'] for news in existing_data['news']}
    items_to_add = [
        item for item in new_items
        if item['url'] not in existing_urls
    ]
    merged_news = existing_data['news'] + items_to_add
    existing_data['news'] = merged_news
    existing_data['total'] = len(merged_news)
    return existing_data


def fetch_news(date_str: str = None):
    """获取新闻数据并保存"""
    if date_str is None:
        date_str = datetime.now().strftime('%Y-%m-%d')

    fetch_time = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')

    print(f"[{fetch_time}] 开始获取新闻数据...")

    try:
        df = ak.stock_news_main_cx()
        print(f"成功获取 {len(df)} 条新闻")
    except Exception as e:
        print(f"获取新闻失败: {e}")
        return

    if len(df) == 0:
        print("未获取到任何新闻数据")
        return

    news_list = df.to_dict('records')
    transformed_items = [transform_news_item(item, fetch_time) for item in news_list]

    data_dir = Path('/Users/una5577/Documents/trae_projects/a-stock-monitor/data/news')
    data_dir.mkdir(parents=True, exist_ok=True)
    file_path = data_dir / f"{date_str}.json"

    existing_data = load_existing_news(str(file_path))

    if existing_data:
        print(f"发现已有数据文件，合并去重...")
        existing_urls = {news['url'] for news in existing_data['news']}
        items_to_add = [item for item in transformed_items if item['url'] not in existing_urls]
        final_data = merge_news(existing_data, transformed_items)
        print(f"新增 {len(items_to_add)} 条新闻")
    else:
        print(f"创建新的数据文件...")
        final_data = {
            "date": date_str,
            "fetch_time": fetch_time,
            "source": "akshare/stock_news_main_cx",
            "total": len(transformed_items),
            "news": transformed_items
        }

    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(final_data, f, ensure_ascii=False, indent=2)

    print(f"✓ 数据已保存到: {file_path}")
    print(f"✓ 总新闻数: {final_data['total']}")


if __name__ == "__main__":
    fetch_news()
