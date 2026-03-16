#!/usr/bin/env python3
"""
ETF乖离率风险评估

功能：
1. 计算所有ETF的60日滚动分位数
2. 判断当前风险等级（7级）
3. 展示动态阈值和当前状态
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

def get_risk_level(bias_5: float, quantiles: dict) -> str:
    """获取风险等级"""
    if bias_5 > quantiles['95%']:
        return "极度风险"
    elif bias_5 > quantiles['80%']:
        return "高风险"
    elif bias_5 > quantiles['60%']:
        return "中高位风险"
    elif bias_5 > quantiles['40%']:
        return "中位风险"
    elif bias_5 > quantiles['20%']:
        return "中低位风险"
    elif bias_5 > quantiles['5%']:
        return "低风险"
    else:
        return "极度超跌"

def analyze_etf(etf_config: dict) -> dict:
    """分析单个ETF"""
    name = etf_config['name']
    code = etf_config['code']
    filename = etf_config['file']

    # 加载数据
    df = load_etf_data(filename)
    if len(df) < ROLLING_WINDOW:
        return None

    # 计算乖离率和分位数
    df = calculate_bias_and_quantiles(df)

    # 获取最新分位数
    latest = df.iloc[-1]
    q95 = latest.get('bias_5_95')

    if pd.isna(q95):
        return None

    # 当前状态
    bias_5 = latest.get('bias_5')

    # 风险等级判断
    quantiles = {
        '95%': latest.get('bias_5_95'),
        '80%': latest.get('bias_5_80'),
        '60%': latest.get('bias_5_60'),
        '40%': latest.get('bias_5_40'),
        '20%': latest.get('bias_5_20'),
        '5%': latest.get('bias_5_05'),
    }

    risk_level = get_risk_level(bias_5, quantiles)

    return {
        "name": name,
        "code": code,
        "date": latest['date'].strftime('%Y-%m-%d'),
        "close": round(latest['close'], 3),
        "bias_5": round(bias_5, 2) if pd.notna(bias_5) else None,
        "quantiles": {k: round(v, 2) if pd.notna(v) else None for k, v in quantiles.items()},
        "risk_level": risk_level,
    }

def main():
    """主函数"""
    print(f"\n{'='*90}")
    print(f"ETF乖离率风险评估（7级风险等级）")
    print(f"分析日期: {datetime.now().strftime('%Y-%m-%d')}")
    print(f"{'='*90}")

    results = []
    for etf_config in ETF_LIST:
        result = analyze_etf(etf_config)
        if result:
            results.append(result)

    # 打印详细分析
    for r in results:
        print(f"\n{'='*90}")
        print(f"📊 {r['name']} ({r['code']}) - {r['date']}")
        print(f"{'='*90}")

        print(f"\n📍 当前状态:")
        print(f"   收盘价: {r['close']}")
        print(f"   Bias_5: {r['bias_5']}%")
        print(f"   风险等级: {r['risk_level']}")

        print(f"\n📊 60日滚动分位数:")
        q = r['quantiles']
        print(f"   95%分位: {q['95%']}% ← 极度风险阈值")
        print(f"   80%分位: {q['80%']}% ← 高风险阈值")
        print(f"   60%分位: {q['60%']}% ← 中高位风险阈值")
        print(f"   40%分位: {q['40%']}% ← 中位风险阈值")
        print(f"   20%分位: {q['20%']}% ← 中低位风险阈值")
        print(f"   5%分位:  {q['5%']}%  ← 低风险阈值")

    # 汇总表格
    print(f"\n\n{'='*90}")
    print(f"📋 汇总表格")
    print(f"{'='*90}")

    print(f"\n{'ETF名称':<12} {'95%分位':<10} {'当前Bias_5':<12} {'风险等级':<12}")
    print(f"{'-'*90}")

    for r in results:
        name = r['name']
        q95 = f"{r['quantiles']['95%']}%"
        bias_5 = f"{r['bias_5']}%" if r['bias_5'] is not None else "N/A"
        risk_level = r['risk_level']

        print(f"{name:<12} {q95:<10} {bias_5:<12} {risk_level:<12}")

    # 风险等级统计
    print(f"\n{'='*90}")
    print(f"📊 风险等级分布统计")
    print(f"{'='*90}")

    risk_count = {}
    for r in results:
        risk_level = r['risk_level']
        risk_count[risk_level] = risk_count.get(risk_level, 0) + 1

    for risk_level, count in sorted(risk_count.items()):
        print(f"  {risk_level}: {count}个")

if __name__ == "__main__":
    main()
