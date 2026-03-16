#!/usr/bin/env python3
"""
乖离率7级风险等级回测验证

回测目标：
1. ���证7级风险等级的准确性
2. 评估风险等级转换的成功率
3. 对比不同ETF类型的阈值有效性
"""

import pandas as pd
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict

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
    if pd.isna(quantiles['95%']):
        return "数据不足"

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

def backtest_risk_transitions(etf_config: dict) -> dict:
    """回测风险等级转换"""
    name = etf_config['name']
    code = etf_config['code']
    filename = etf_config['file']

    # 加载数据
    df = load_etf_data(filename)
    if len(df) < ROLLING_WINDOW:
        return None

    # 计算乖离率和分位数
    df = calculate_bias_and_quantiles(df)

    # 只保留有分位数数据的行
    df_valid = df[df['bias_5_95'].notna()].copy()

    if len(df_valid) == 0:
        return None

    # 计算每日风险等级
    df_valid['risk_level'] = df_valid.apply(
        lambda row: get_risk_level(
            row['bias_5'],
            {
                '95%': row['bias_5_95'],
                '80%': row['bias_5_80'],
                '60%': row['bias_5_60'],
                '40%': row['bias_5_40'],
                '20%': row['bias_5_20'],
                '5%': row['bias_5_05'],
            }
        ),
        axis=1
    )

    # 统计风险等级转换
    transitions = defaultdict(int)
    for i in range(1, len(df_valid)):
        prev_level = df_valid.iloc[i-1]['risk_level']
        curr_level = df_valid.iloc[i]['risk_level']
        transitions[(prev_level, curr_level)] += 1

    # 验证"极度风险"后的下跌
    extreme_risk_count = 0
    extreme_risk_down = 0
    for i in range(len(df_valid) - 1):
        if df_valid.iloc[i]['risk_level'] == "极度风险":
            extreme_risk_count += 1
            # 检查未来3天是否下跌
            if i + 3 < len(df_valid):
                future_close = df_valid.iloc[i+3]['close']
                current_close = df_valid.iloc[i]['close']
                if future_close < current_close:
                    extreme_risk_down += 1

    # 验证"极度超跌"后的上涨
    extreme_oversold_count = 0
    extreme_oversold_up = 0
    for i in range(len(df_valid) - 1):
        if df_valid.iloc[i]['risk_level'] == "极度超跌":
            extreme_oversold_count += 1
            # 检查未来3天是否上涨
            if i + 3 < len(df_valid):
                future_close = df_valid.iloc[i+3]['close']
                current_close = df_valid.iloc[i]['close']
                if future_close > current_close:
                    extreme_oversold_up += 1

    # 获取最新状态
    latest = df_valid.iloc[-1]
    q95 = latest['bias_5_95']

    return {
        "name": name,
        "code": code,
        "q95": round(q95, 2),
        "total_days": len(df_valid),
        "transitions": dict(transitions),
        "extreme_risk": {
            "count": extreme_risk_count,
            "down_count": extreme_risk_down,
            "accuracy": extreme_risk_down / extreme_risk_count if extreme_risk_count > 0 else 0
        },
        "extreme_oversold": {
            "count": extreme_oversold_count,
            "up_count": extreme_oversold_up,
            "accuracy": extreme_oversold_up / extreme_oversold_count if extreme_oversold_count > 0 else 0
        }
    }

def print_backtest_results(results: list):
    """打印回测结果"""
    print(f"\n{'='*90}")
    print(f"乖离率7级风险等级回测验证")
    print(f"回测日期: {datetime.now().strftime('%Y-%m-%d')}")
    print(f"{'='*90}")

    # 打印每个ETF的回测结果
    for r in results:
        print(f"\n{r['name']} ({r['code']}) - 95%分位: {r['q95']}%")
        print(f"   回测天数: {r['total_days']}天")

        # 极度风险验证
        er = r['extreme_risk']
        if er['count'] > 0:
            print(f"   极度风险信号: {er['count']}次")
            print(f"   3日后下跌: {er['down_count']}次 (准确率: {er['accuracy']:.1%})")
        else:
            print(f"   极度风险信号: 0次")

        # 极度超跌验证
        eos = r['extreme_oversold']
        if eos['count'] > 0:
            print(f"   极度超跌信号: {eos['count']}次")
            print(f"   3日后上涨: {eos['up_count']}次 (准确率: {eos['accuracy']:.1%})")
        else:
            print(f"   极度超跌信号: 0次")

    # 全局汇总
    print(f"\n{'='*90}")
    print(f"📊 全局汇总（所有ETF）")
    print(f"{'='*90}")

    all_er_count = sum(r['extreme_risk']['count'] for r in results)
    all_er_down = sum(r['extreme_risk']['down_count'] for r in results)
    all_eos_count = sum(r['extreme_oversold']['count'] for r in results)
    all_eos_up = sum(r['extreme_oversold']['up_count'] for r in results)

    print(f"\n极度风险信号: {all_er_count}次")
    if all_er_count > 0:
        print(f"  3日后下跌: {all_er_down}次")
        print(f"  准确率: {all_er_down/all_er_count:.1%}")

    print(f"\n极度超跌信号: {all_eos_count}次")
    if all_eos_count > 0:
        print(f"  3日后上涨: {all_eos_up}次")
        print(f"  准确率: {all_eos_up/all_eos_count:.1%}")

def main():
    """主函数"""
    results = []

    for etf_config in ETF_LIST:
        result = backtest_risk_transitions(etf_config)
        if result:
            results.append(result)

    print_backtest_results(results)

if __name__ == "__main__":
    main()
