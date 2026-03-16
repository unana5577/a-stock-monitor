#!/usr/bin/env python3
"""
乖离率分布计算脚本

功能：
1. 计算所有ETF的5日乖离率（Bias_5）
2. 计算60日滚动窗口的分位数（95%/80%/60%/40%/20%/5%）
3. 持久化存储历史分位数数据
4. 生成乖离率分布报告
"""

import pandas as pd
import json
from pathlib import Path
from datetime import datetime, timedelta
import sys

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
OUTPUT_DIR = Path("data")
ROLLING_WINDOW = 60  # 60日滚动窗口

def load_etf_data(filename: str) -> pd.DataFrame:
    """加载ETF数据"""
    filepath = DATA_DIR / filename

    if not filepath.exists():
        print(f"❌ 文件不存在: {filepath}")
        return pd.DataFrame()

    # 读取jsonl文件
    data = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                data.append(json.loads(line))

    if not data:
        print(f"❌ 数据为空: {filepath}")
        return pd.DataFrame()

    df = pd.DataFrame(data)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)

    return df

def calculate_bias_5(df: pd.DataFrame) -> pd.DataFrame:
    """计算5日乖离率"""
    if len(df) < 5:
        return df

    df = df.copy()
    df['ma5'] = df['close'].rolling(window=5).mean()
    df['bias_5'] = (df['close'] - df['ma5']) / df['ma5'] * 100

    return df

def calculate_rolling_quantiles(df: pd.DataFrame, window: int = ROLLING_WINDOW) -> pd.DataFrame:
    """计算60日滚动分位数"""
    if len(df) < window:
        print(f"⚠️  数据不足{window}天，无法计算滚动分位数")
        return df

    df = df.copy()

    # 计算滚动分位数
    quantiles = [0.95, 0.80, 0.60, 0.40, 0.20, 0.05]
    quantile_names = ['bias_5_95', 'bias_5_80', 'bias_5_60', 'bias_5_40', 'bias_5_20', 'bias_5_05']

    for q, name in zip(quantiles, quantile_names):
        df[name] = df['bias_5'].rolling(window=window).quantile(q)

    return df

def get_current_bias_status(df: pd.DataFrame) -> dict:
    """获取最新乖离率状态"""
    if len(df) == 0:
        return {}

    latest = df.iloc[-1]

    # 检查是否有分位数数据
    if pd.isna(latest.get('bias_5')):
        return {
            "date": latest['date'].strftime('%Y-%m-%d'),
            "close": latest['close'],
            "bias_5": None,
            "status": "数据不足"
        }

    bias_5 = latest['bias_5']

    # 获取分位数
    quantiles = {
        '95': latest.get('bias_5_95'),
        '80': latest.get('bias_5_80'),
        '60': latest.get('bias_5_60'),
        '40': latest.get('bias_5_40'),
        '20': latest.get('bias_5_20'),
        '05': latest.get('bias_5_05'),
    }

    # 判断风险等级（7级风险等级）
    if pd.notna(quantiles['95']) and bias_5 > quantiles['95']:
        risk_level = "极度风险"
        risk_desc = "严重超涨，顶部信号"
        operation = "立即离场，禁止追涨"
    elif pd.notna(quantiles['80']) and bias_5 > quantiles['80']:
        risk_level = "高风险"
        risk_desc = "明显超涨，接近顶部"
        operation = "逐步减仓，锁定利润"
    elif pd.notna(quantiles['60']) and bias_5 > quantiles['60']:
        risk_level = "中高位风险"
        risk_desc = "偏高，加速期"
        operation = "谨慎持有，关注量价"
    elif pd.notna(quantiles['40']) and bias_5 > quantiles['40']:
        risk_level = "中位风险"
        risk_desc = "正常波动"
        operation = "观望"
    elif pd.notna(quantiles['20']) and bias_5 > quantiles['20']:
        risk_level = "中低位风险"
        risk_desc = "偏低"
        operation = "观望"
    elif pd.notna(quantiles['05']) and bias_5 > quantiles['05']:
        risk_level = "低风险"
        risk_desc = "超跌"
        operation = "结合量价判断"
    else:
        risk_level = "极度超跌"
        risk_desc = "严重超跌"
        operation = "结合量价判断"

    return {
        "date": latest['date'].strftime('%Y-%m-%d'),
        "close": round(latest['close'], 3),
        "bias_5": round(bias_5, 2),
        "quantiles": {k: round(v, 2) if pd.notna(v) else None for k, v in quantiles.items()},
        "risk_level": risk_level,
        "risk_desc": risk_desc,
        "operation": operation,
    }

def save_bias_quantiles(etf_name: str, df: pd.DataFrame):
    """持久化存储乖离率分位数数据"""
    output_file = OUTPUT_DIR / f"bias_quantiles_{etf_name}.jsonl"

    # 只保存有分位数数据的行
    df_to_save = df[df['bias_5_95'].notna()][[
        'date', 'bias_5_95', 'bias_5_80', 'bias_5_60',
        'bias_5_40', 'bias_5_20', 'bias_5_05'
    ]].copy()

    if len(df_to_save) == 0:
        print(f"⚠️  {etf_name}: 没有分位数数据可保存")
        return

    # 转换为JSON格式
    df_to_save['date'] = df_to_save['date'].dt.strftime('%Y-%m-%d')

    # 保存为jsonl
    with open(output_file, 'w', encoding='utf-8') as f:
        for _, row in df_to_save.iterrows():
            f.write(json.dumps(row.to_dict(), ensure_ascii=False) + '\n')

    print(f"✅ {etf_name}: 已保存{len(df_to_save)}条分位数数据")

def analyze_etf(etf_config: dict) -> dict:
    """分析单个ETF"""
    name = etf_config['name']
    code = etf_config['code']
    filename = etf_config['file']

    print(f"\n{'='*60}")
    print(f"分析 {name} ({code})")
    print(f"{'='*60}")

    # 加载数据
    df = load_etf_data(filename)
    if len(df) == 0:
        return None

    print(f"📊 数据范围: {df['date'].min().strftime('%Y-%m-%d')} 至 {df['date'].max().strftime('%Y-%m-%d')} ({len(df)}天)")

    # 计算乖离率
    df = calculate_bias_5(df)

    # 计算滚动分位数
    df = calculate_rolling_quantiles(df)

    # 获取最新状态
    status = get_current_bias_status(df)

    print(f"\n📈 最新乖离率状态 ({status['date']}):")
    print(f"   收盘价: {status['close']}")
    print(f"   Bias_5: {status['bias_5']}%")

    if status['bias_5'] is not None and status.get('quantiles'):
        q = status['quantiles']
        print(f"\n📊 60日滚动分位数:")
        print(f"   95%分位: {q['95']}% (极度风险阈值)")
        print(f"   80%分位: {q['80']}% (高风险阈值)")
        print(f"   60%分位: {q['60']}% (中高位阈值)")
        print(f"   40%分位: {q['40']}% (中低位阈值)")
        print(f"   20%分位: {q['20']}% (低风险阈值)")
        print(f"   5%分位:  {q['05']}% (极度机会阈值)")

        print(f"\n⚠️  风险等级: {status['risk_level']}")
        print(f"📝 描述: {status['risk_desc']}")
        print(f"💡 操作建议: {status['operation']}")

    # 保存分位数数据
    save_bias_quantiles(name, df)

    # 统计Bias_5分布
    bias_stats = df['bias_5'].describe()
    print(f"\n📊 Bias_5 历史统计:")
    print(f"   最大值: {bias_stats['max']:.2f}%")
    print(f"   75%分位: {bias_stats['75%']:.2f}%")
    print(f"   中位数: {bias_stats['50%']:.2f}%")
    print(f"   25%分位: {bias_stats['25%']:.2f}%")
    print(f"   最小值: {bias_stats['min']:.2f}%")

    return {
        "name": name,
        "code": code,
        "status": status,
        "bias_stats": {
            "max": round(bias_stats['max'], 2),
            "min": round(bias_stats['min'], 2),
            "mean": round(bias_stats['mean'], 2),
            "std": round(bias_stats['std'], 2),
        }
    }

def generate_summary_report(results: list):
    """生成汇总报告"""
    print(f"\n\n{'='*80}")
    print(f"乖离率分布汇总报告")
    print(f"{'='*80}")

    print(f"\n{'ETF名称':<10} {'最新Bias_5':<12} {'风险等级':<12} {'操作建议'}")
    print(f"{'-'*80}")

    for r in results:
        if r is None:
            continue

        name = r['name']
        bias_5 = f"{r['status']['bias_5']}%" if r['status']['bias_5'] is not None else "N/A"
        risk = r['status']['risk_level']
        operation = r['status']['operation']

        print(f"{name:<10} {bias_5:<12} {risk:<12} {operation}")

    # 分类统计
    print(f"\n{'='*80}")
    print(f"风险等级分布")
    print(f"{'='*80}")

    risk_count = {}
    for r in results:
        if r is None:
            continue
        risk = r['status']['risk_level']
        risk_count[risk] = risk_count.get(risk, 0) + 1

    for risk, count in sorted(risk_count.items()):
        print(f"{risk}: {count}个")

    # ETF类型分析
    print(f"\n{'='*80}")
    print(f"ETF类型分析（基于95%分位）")
    print(f"{'='*80}")

    for r in results:
        if r is None or not r['status'].get('quantiles'):
            continue

        name = r['name']
        q95 = r['status']['quantiles']['95']

        if q95 is None:
            etf_type = "数据不足"
        elif q95 >= 8:
            etf_type = "主线ETF（波动大）"
        elif q95 >= 4:
            etf_type = "震荡ETF（波动中）"
        else:
            etf_type = "衰退ETF（波动小）"

        print(f"{name}: 95%分位={q95}% → {etf_type}")

def main():
    """主函数"""
    print(f"开始计算乖离率分布...")
    print(f"数据目录: {DATA_DIR}")
    print(f"滚动窗口: {ROLLING_WINDOW}日")

    results = []

    for etf_config in ETF_LIST:
        result = analyze_etf(etf_config)
        if result:
            results.append(result)

    # 生成汇总报告
    generate_summary_report(results)

    print(f"\n{'='*80}")
    print(f"✅ 计算完成！")
    print(f"{'='*80}")

if __name__ == "__main__":
    main()
