#!/usr/bin/env python3
"""
乖离率���险等级实时判断展示

功能：
1. 展示每个ETF的当前Bias_5值
2. 展示60日滚动分位数阈值
3. 清晰展示风险等级判断过程
4. 当前位置描述
"""

import pandas as pd
import json
from pathlib import Path
from datetime import datetime

# ETF配置
ETF_LIST = [
    {"name": "半导体", "code": "512480", "file": "etf_512480.jsonl"},
    {"name": "云计算", "code": "516510", "file": "etf_516510.jsonl"},
    {"name": "新能源", "code": "516160", "file": "etf_516160.jsonl"},
    {"name": "有色金属", "code": "512400", "file": "etf_512400.jsonl"},
    {"name": "通讯设备", "code": "515880", "file": "etf_515880.jsonl"},
    {"name": "游戏", "code": "516010", "file": "etf_516010.jsonl"},
    {"name": "机器人", "code": "562500", "file": "etf_562500.jsonl"},
    {"name": "商业航天", "code": "563530", "file": "etf_563530.jsonl"},
    {"name": "创新药", "code": "515120", "file": "etf_515120.jsonl"},
]

# 数据目录
DATA_DIR = Path("data/etf_daily")
ROLLING_WINDOW = 60

def load_etf_data(filename: str) -> pd.DataFrame:
    """加载ETF数据"""
    filepath = DATA_DIR / filename

    if not filepath.exists():
        return pd.DataFrame()

    data = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                data.append(json.loads(line))

    df = pd.DataFrame(data)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)

    return df

def calculate_bias_and_quantiles(df: pd.DataFrame) -> pd.DataFrame:
    """计算乖离率和分位数"""
    if len(df) < 5:
        return df

    df = df.copy()
    df['ma5'] = df['close'].rolling(window=5).mean()
    df['bias_5'] = (df['close'] - df['ma5']) / df['ma5'] * 100

    if len(df) >= ROLLING_WINDOW:
        quantiles = [0.95, 0.80, 0.60, 0.40, 0.20, 0.05]
        quantile_names = ['bias_5_95', 'bias_5_80', 'bias_5_60', 'bias_5_40', 'bias_5_20', 'bias_5_05']

        for q, name in zip(quantiles, quantile_names):
            df[name] = df['bias_5'].rolling(window=ROLLING_WINDOW).quantile(q)

    return df

def analyze_etf_status(etf_config: dict) -> dict:
    """分析单个ETF的当前状态"""
    name = etf_config['name']
    code = etf_config['code']
    filename = etf_config['file']

    # 加载数据
    df = load_etf_data(filename)
    if len(df) == 0:
        return None

    # 计算乖离率和分位数
    df = calculate_bias_and_quantiles(df)

    # 获取最新数据
    latest = df.iloc[-1]

    if pd.isna(latest.get('bias_5')):
        return {
            "name": name,
            "code": code,
            "date": latest['date'].strftime('%Y-%m-%d'),
            "close": latest['close'],
            "bias_5": None,
            "error": "数据不足，无法计算Bias_5"
        }

    bias_5 = latest['bias_5']

    # 获取分位数
    quantiles = {
        '95%': latest.get('bias_5_95'),
        '80%': latest.get('bias_5_80'),
        '60%': latest.get('bias_5_60'),
        '40%': latest.get('bias_5_40'),
        '20%': latest.get('bias_5_20'),
        '5%': latest.get('bias_5_05'),
    }

    # 判断风险等级
    if pd.isna(quantiles['95%']):
        return {
            "name": name,
            "code": code,
            "date": latest['date'].strftime('%Y-%m-%d'),
            "close": latest['close'],
            "bias_5": bias_5,
            "quantiles": quantiles,
            "error": f"数据不足{ROLLING_WINDOW}天，无法计算历史分位数"
        }

    # 风险等级判断逻辑（7级风险等级）
    if bias_5 > quantiles['95%']:
        risk_level = "极度风险"
        position = "顶部区"
        risk_desc = "严重超涨，顶部信号"
        operation = "立即离场，禁止追涨"
        position_percentile = "> 95%"
    elif bias_5 > quantiles['80%']:
        risk_level = "高风险"
        position = "冲刺期"
        risk_desc = "明显超涨，接近顶部"
        operation = "逐步减仓，锁定利润"
        position_percentile = "80%-95%"
    elif bias_5 > quantiles['60%']:
        risk_level = "中高位风险"
        position = "加速期"
        risk_desc = "偏高，加速期"
        operation = "谨慎持有，关注量价"
        position_percentile = "60%-80%"
    elif bias_5 > quantiles['40%']:
        risk_level = "中位风险"
        position = "启动期"
        risk_desc = "正常波动"
        operation = "观望"
        position_percentile = "40%-60%"
    elif bias_5 > quantiles['20%']:
        risk_level = "中低位风险"
        position = "底部区"
        risk_desc = "偏低"
        operation = "观望"
        position_percentile = "20%-40%"
    elif bias_5 > quantiles['5%']:
        risk_level = "低风险"
        position = "超跌区"
        risk_desc = "超跌"
        operation = "结合量价判断"
        position_percentile = "5%-20%"
    else:
        risk_level = "极度超跌"
        position = "严重超跌区"
        risk_desc = "严重超跌"
        operation = "结合量价判断"
        position_percentile = "< 5%"

    return {
        "name": name,
        "code": code,
        "date": latest['date'].strftime('%Y-%m-%d'),
        "close": round(latest['close'], 3),
        "bias_5": round(bias_5, 2),
        "quantiles": {k: round(v, 2) if pd.notna(v) else None for k, v in quantiles.items()},
        "risk_level": risk_level,
        "position": position,
        "position_percentile": position_percentile,
        "risk_desc": risk_desc,
        "operation": operation,
    }

def print_risk_level_analysis(result: dict):
    """打印单个ETF的风险等级分析"""
    if result is None or result.get('error'):
        return

    print(f"\n{'='*80}")
    print(f"📊 {result['name']} ({result['code']}) - {result['date']}")
    print(f"{'='*80}")

    bias_5 = result['bias_5']
    q = result['quantiles']

    # 当前位置
    print(f"\n📍 当前位置:")
    print(f"   收盘价: {result['close']}")
    print(f"   Bias_5: {bias_5}%")

    # 分位数阈值
    print(f"\n📊 60日滚动分位数阈值（参考过去60天的Bias_5分布）:")
    print(f"   95%分位: {q['95%']}% ← 极度风险阈值")
    print(f"   80%分位: {q['80%']}% ← 高风险阈值")
    print(f"   60%分位: {q['60%']}% ← 中高位风险阈值")
    print(f"   40%分位: {q['40%']}% ← 中低位机会阈值")
    print(f"   20%分位: {q['20%']}% ← 低风险机会阈值")
    print(f"   5%分位:  {q['5%']}%  ← 极度机会阈值")

    # 判断过程
    print(f"\n🔍 风险等级判断过程:")
    print(f"   第1步: 当前Bias_5 = {bias_5}%")

    comparisons = [
        (q['95%'], "> 95%分位", "极度风险"),
        (q['80%'], "> 80%分位", "高风险"),
        (q['60%'], "> 60%分位", "中高位风险"),
        (q['40%'], "> 40%分位", "中低位机会"),
        (q['20%'], "> 20%分位", "低风险机会"),
    ]

    for threshold, condition, level in comparisons:
        if bias_5 > threshold:
            print(f"   第2步: {bias_5}% {condition} ({threshold}%) → {level}")
            break
    else:
        print(f"   第2步: {bias_5}% <= 20%分位 ({q['20%']}%) → 极度机会")

    # 判断结果
    print(f"\n⚠️  判断结果:")
    print(f"   风险等级: {result['risk_level']}")
    print(f"   当前位置: {result['position']} ({result['position_percentile']})")
    print(f"   描述: {result['risk_desc']}")

    # 操作建议
    print(f"\n💡 操作建议:")
    print(f"   {result['operation']}")

def main():
    """主函数"""
    print(f"\n{'='*80}")
    print(f"ETF乖离率风险等级实时判断")
    print(f"判断规则: 当前Bias_5 vs 过去60日滚动分位数")
    print(f"数据日期: {datetime.now().strftime('%Y-%m-%d')}")
    print(f"{'='*80}")

    results = []
    for etf_config in ETF_LIST:
        result = analyze_etf_status(etf_config)
        if result:
            results.append(result)
            print_risk_level_analysis(result)

    # 汇总表格
    print(f"\n\n{'='*80}")
    print(f"📋 汇总表格")
    print(f"{'='*80}")
    print(f"\n{'ETF名称':<12} {'Bias_5':<10} {'风险等级':<12} {'当前位置':<12} {'操作建议'}")
    print(f"{'-'*80}")

    for r in results:
        if r.get('error'):
            continue

        name = r['name']
        bias_5 = f"{r['bias_5']}%"
        risk = r['risk_level']
        position = r['position']
        operation = r['operation']

        print(f"{name:<12} {bias_5:<10} {risk:<12} {position:<12} {operation}")

    # 风险等级统计
    print(f"\n{'='*80}")
    print(f"📊 风险等级分布统计")
    print(f"{'='*80}")

    risk_count = {}
    position_count = {}

    for r in results:
        if r.get('error'):
            continue

        risk = r['risk_level']
        position = r['position']

        risk_count[risk] = risk_count.get(risk, 0) + 1
        position_count[position] = position_count.get(position, 0) + 1

    print(f"\n按风险等级:")
    for risk, count in sorted(risk_count.items()):
        print(f"  {risk}: {count}个")

    print(f"\n按当前位置:")
    for position, count in sorted(position_count.items()):
        print(f"  {position}: {count}个")

if __name__ == "__main__":
    main()
