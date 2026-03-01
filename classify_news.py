#!/usr/bin/env python3
"""
新闻分类脚本 - P0-2.2
对A股新闻进行多维度分类：类型、行业、情绪、等级
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set


# 关键词定义
class Keywords:
    # 类型分类关键词
    MACRO = ["央行", "美联储", "利率", "GDP", "CPI", "PMI", "政策", "监管", "通胀", "通缩", "货币政策", "财政政策"]
    GEOPOLITICS = ["战争", "冲突", "制裁", "关税", "贸易战", "中美", "美国", "日本", "地缘政治", "台海", "南海"]

    # 行业板块关键词
    SECTOR_SEMICONDUCTOR = ["芯片", "半导体", "晶圆", "光刻", "国产替代", "华为", "集成电路", "存储芯片", "GPU", "CPU", "存储器"]
    SECTOR_CLOUD = ["云计算", "数据中心", "服务器", "AI", "大模型", "人工智能", "算力", "云服务", "云计算"]
    SECTOR_NEW_ENERGY = ["电动车", "电池", "光伏", "风电", "储能", "碳中和", "新能源", "锂电", "固态电池", "充电桩", "新能源汽车"]
    SECTOR_SPACE = ["卫星", "火箭", "航天", "低空", "飞行汽车", "商业航天", "卫星互联网", "运载火箭", "空间站"]
    SECTOR_DRUG = ["医药", "药品", "生物", "医保", "集采", "创新药", "疫苗", "生物制药", "临床试验", "药物"]
    SECTOR_METAL = ["铜", "铝", "锂", "稀土", "黄金", "大宗商品", "有色金属", "钴", "镍", "贵金属"]
    SECTOR_COMM = ["5G", "通信", "基站", "光通信", "通讯设备", "光纤", "通信设备", "基站建设", "网络设备"]

    # 情绪关键词
    POSITIVE = ["扶持", "补贴", "增长", "突破", "超预期", "政策支持", "利好", "上涨", "创新", "业绩", "营收增长", "利润增长", "复苏", "回暖"]
    NEGATIVE = ["限制", "监管", "处罚", "下跌", "暴雷", "造假", "利空", "亏损", "下滑", "下降", "萎缩", "危机", "风险", "调查", "违规"]


def get_matching_keywords(text: str, keywords: List[str]) -> List[str]:
    """找出文本中匹配的关键词"""
    matched = []
    for kw in keywords:
        if kw in text:
            matched.append(kw)
    return matched


def classify_type(title: str, content: str) -> tuple[str, List[str]]:
    """
    分类新闻类型：宏观、地缘、行业
    返回: (类型, 匹配的关键词列表)
    """
    text = title + " " + content

    # 检查宏观
    macro_matches = get_matching_keywords(text, Keywords.MACRO)
    if macro_matches:
        return "宏观", macro_matches

    # 检查地缘
    geo_matches = get_matching_keywords(text, Keywords.GEOPOLITICS)
    if geo_matches:
        return "地缘", geo_matches

    return "行业", []


def classify_sector(title: str, content: str) -> tuple[Optional[str], List[str]]:
    """
    分类新闻所属行业板块
    返回: (板块名称, 匹配的关键词列表) 或 (None, []) 如果不属于任何板块
    """
    text = title + " " + content

    sectors = [
        ("半导体", Keywords.SECTOR_SEMICONDUCTOR),
        ("云计算", Keywords.SECTOR_CLOUD),
        ("新能源", Keywords.SECTOR_NEW_ENERGY),
        ("商业航天", Keywords.SECTOR_SPACE),
        ("创新药", Keywords.SECTOR_DRUG),
        ("有色金属", Keywords.SECTOR_METAL),
        ("通讯设备", Keywords.SECTOR_COMM),
    ]

    for sector_name, sector_keywords in sectors:
        matches = get_matching_keywords(text, sector_keywords)
        if matches:
            return sector_name, matches

    return None, []


def classify_sentiment(title: str, content: str) -> tuple[int, str]:
    """
    分类新闻情绪：利好(+1)、中性(0)、利空(-1)
    返回: (情绪值, 情绪描述)
    """
    text = title + " " + content

    positive_matches = get_matching_keywords(text, Keywords.POSITIVE)
    negative_matches = get_matching_keywords(text, Keywords.NEGATIVE)

    if positive_matches and negative_matches:
        # 如果同时有利好和利空词，简单按数量判断
        return (1, "利好") if len(positive_matches) > len(negative_matches) else (-1, "利空")
    elif positive_matches:
        return 1, "利好"
    elif negative_matches:
        return -1, "利空"
    else:
        return 0, "中性"


def classify_level(news_type: str, sector: Optional[str], sentiment: int) -> str:
    """
    分类新闻等级：P0、P1、P2、P3
    """
    # P0: 宏观+利空/利好，或地缘+战争
    if news_type == "宏观" and sentiment != 0:
        return "P0"
    if news_type == "地缘" and "战争" in Keywords.GEOPOLITICS:
        return "P0"

    # P1: 行业核心新闻
    if news_type == "行业" and sector and sentiment == 1:
        return "P1"

    # P2: 行业一般新闻
    if news_type == "行业" and sector:
        return "P2"

    # P3: 其他
    return "P3"


def should_keep_news(news_type: str, sector: Optional[str]) -> bool:
    """
    判断新闻是否应该保留
    - 宏观：保留
    - 地缘：保留
    - 行业：只保留属于7个板块的新闻
    """
    if news_type == "宏观":
        return True
    if news_type == "地缘":
        return True
    if news_type == "行业":
        return sector is not None
    return False


def transform_news_item(news: Dict, default_crawl_time: str = "") -> Dict:
    """
    转换新闻字段以匹配前端需求
    """
    crawl_time = news.get("fetch_time", default_crawl_time)
    tag = news.get("tag")
    tags = tag if isinstance(tag, list) else ([tag] if tag else [])

    level = news.get("classify", {}).get("level", "P3")
    importance_map = {
        "P0": 5,
        "P1": 4,
        "P2": 3,
        "P3": 2,
    }

    transformed = {
        **news,
        "source_url": news.get("url", ""),
        "tags": tags,
        "crawl_time": crawl_time,
        "summary": news.get("content", ""),
        "publish_time": crawl_time,
        "importance": importance_map.get(level, 2),
        "related_stocks": [],
        "status": "new",
    }

    # 移除已被替换的旧字段
    transformed.pop("url", None)
    transformed.pop("tag", None)
    transformed.pop("fetch_time", None)
    return transformed


def process_news_file(file_path: str) -> Dict:
    """
    处理新闻文件，添加分类信息和统计
    """
    # 读取原始数据
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    date_str = data["date"]
    news_list = data["news"]

    # 初始化统计
    stats = {
        "total": len(news_list),
        "kept": 0,
        "filtered": 0,
        "by_type": {"宏观": 0, "地缘": 0, "行业": 0},
        "by_sector": {
            "半导体": 0,
            "云计算": 0,
            "新能源": 0,
            "商业航天": 0,
            "创新药": 0,
            "有色金属": 0,
            "通讯设备": 0
        },
        "by_sentiment": {"利好": 0, "中性": 0, "利空": 0}
    }

    # 处理每条新闻
    classified_news = []
    for news in news_list:
        title = news.get("title", "")
        content = news.get("content", "")

        # 类型分类
        news_type, type_keywords = classify_type(title, content)

        # 行业分类
        sector, sector_keywords = classify_sector(title, content)

        # 判断是否保留
        if should_keep_news(news_type, sector):
            # 情绪分类
            sentiment, sentiment_text = classify_sentiment(title, content)

            # 等级分类
            level = classify_level(news_type, sector, sentiment)

            # 添加分类字段
            classified_item = {
                **news,
                "classify": {
                    "type": news_type,
                    "type_keywords": type_keywords,
                    "sector": sector,
                    "sector_keywords": sector_keywords,
                    "sentiment": sentiment,
                    "sentiment_text": sentiment_text,
                    "level": level
                }
            }
            classified_news.append(transform_news_item(classified_item, data.get("fetch_time", "")))

            # 更新统计
            stats["kept"] += 1
            stats["by_type"][news_type] += 1
            if sector:
                stats["by_sector"][sector] += 1
            stats["by_sentiment"][sentiment_text] += 1
        else:
            stats["filtered"] += 1

    # 构建输出数据
    output = {
        "date": date_str,
        "fetch_time": data.get("fetch_time", ""),
        "source": data.get("source", ""),
        "classify_time": datetime.now().isoformat(),
        "stats": stats,
        "news": classified_news
    }

    return output


def main():
    """主函数"""
    # 确定输入文件路径
    data_dir = Path("data/news")

    # 默认处理最新日期的文件
    json_files = list(data_dir.glob("*.json"))
    if len(json_files) > 0:
        latest_file = max(json_files)
        input_file = str(latest_file)
        print(f"处理文件: {input_file}")
    else:
        print("错误: 未找到新闻数据文件")
        return

    # 处理新闻
    output_data = process_news_file(input_file)

    # 输出结果
    output_file = input_file
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"\n分类完成！")
    print(f"原始新闻数: {output_data['stats']['total']}")
    print(f"保留新闻数: {output_data['stats']['kept']}")
    print(f"过滤新闻数: {output_data['stats']['filtered']}")
    print(f"\n按类型分布:")
    for k, v in output_data['stats']['by_type'].items():
        if v > 0:
            print(f"  {k}: {v}")
    print(f"\n按行业分布:")
    for k, v in output_data['stats']['by_sector'].items():
        if v > 0:
            print(f"  {k}: {v}")
    print(f"\n按情绪分布:")
    for k, v in output_data['stats']['by_sentiment'].items():
        if v > 0:
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
