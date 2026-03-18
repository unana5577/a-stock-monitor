#!/usr/bin/env python3
"""
ETF操作建议系统（模块化版本）

核心功能：
1. 动态基准选择（60天相关性）
2. 计算所有指标（Alpha、趋势、量能、乖离率）
3. 生成操作建议
4. 输出报告

作者：Claude
日期：2026-03-18
版本：v2.0（模块化）
"""

import json
import pandas as pd
from pathlib import Path
from datetime import datetime

# 导入sector_lifecycle模块
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from sector_lifecycle import (
    DataLoader,
    BenchmarkSelector,
    Indicators,
    AdviceGenerator
)

# ==================== 配置 ====================

# ETF列表
ETF_LIST = [
    {"name": "通讯设备", "code": "515880", "file": "etf_515880.jsonl"},
    {"name": "有色金属", "code": "512400", "file": "etf_512400.jsonl"},
    {"name": "半导体", "code": "512480", "file": "etf_512480.jsonl"},
    {"name": "云计算", "code": "516510", "file": "etf_516510.jsonl"},
    {"name": "新能源", "code": "516160", "file": "etf_516160.jsonl"},
    {"name": "游戏", "code": "516010", "file": "etf_516010.jsonl"},
    {"name": "机器人", "code": "562500", "file": "etf_562500.jsonl"},
    {"name": "商业航天", "code": "563530", "file": "etf_563530.jsonl"},
    {"name": "创新药", "code": "515120", "file": "etf_515120.jsonl"},
]

ROLLING_WINDOW = 60


# ==================== 主程序 ====================

def main():
    print("=" * 80)
    print("ETF操作建议报告（模块化版本）")
    print(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    results = []

    # 初始化模块
    loader = DataLoader()
    benchmark_selector = BenchmarkSelector(loader)
    indicators = Indicators()
    advice_generator = AdviceGenerator()

    # 加载全市场ETF成交额数据
    market_amount_data = loader.load_etf_amount_data()
    print(f"\n📈 全市场ETF成交额数据已加载: {len(market_amount_data)} 天")

    for etf in ETF_LIST:
        name = etf['name']
        code = etf['code']
        filename = etf['file']

        print(f"\n{'='*80}")
        print(f"📊 {name} ({code})")
        print(f"{'='*80}")

        # 加载数据
        etf_df = loader.load_etf_data(filename)
        if etf_df.empty or len(etf_df) < ROLLING_WINDOW:
            print("数据不足，跳过")
            continue

        # 动态基准选择
        benchmark_info = benchmark_selector.select_benchmark(etf_df)
        bench_df = benchmark_selector.load_benchmark_data(benchmark_info['code'])

        # 基本信息
        latest = etf_df.iloc[-1]
        close = latest['close']
        pct = latest.get('pct', 0)

        print(f"📍 基本信息")
        print(f"   收盘价：{close:.3f}  涨跌幅：{pct:+.2f}%")
        print(f"   基准指数：{benchmark_info['benchmark']} (相关性：{benchmark_info['correlation']})")

        # 展示指标：Alpha
        alpha_5 = indicators.calculate_alpha(etf_df, bench_df, 5)
        alpha_20 = indicators.calculate_alpha(etf_df, bench_df, 20)

        alpha_5_strength = Indicators.get_alpha_strength(alpha_5)
        alpha_20_strength = Indicators.get_alpha_strength(alpha_20)

        print(f"\n📊 展示指标（仅供参考）")
        print(f"   Alpha_5：{alpha_5:+.2f}% ({alpha_5_strength})")
        print(f"   Alpha_20：{alpha_20:+.2f}% ({alpha_20_strength})")

        # 判断指标：乖离率
        risk_level, bias_5 = indicators.calculate_risk_level(etf_df)
        print(f"\n🔻 乖离率")
        print(f"   风险等级：{risk_level} (bias_5: {bias_5:+.2f}%)")

        # 判断指标：趋势
        ma5_slope = indicators.calculate_ma_slope(etf_df, 5)
        ma20_slope = indicators.calculate_ma_slope(etf_df, 20)
        short_trend = "向上" if ma5_slope > 0 else "向下"
        medium_trend = "向上" if ma20_slope > 0 else "向下"
        print(f"\n📊 趋势")
        print(f"   短期（MA5）：{ma5_slope:+.2f}% ({short_trend})")
        print(f"   中期（MA20）：{ma20_slope:+.2f}% ({medium_trend})")

        # 判断指标：资金热度
        fund_status, fund_heat, fund_heat_change, fund_heat_display = indicators.calculate_fund_heat(etf_df, market_amount_data)
        print(f"\n📈 量能")
        print(f"   资金热度：{fund_status} (热度: {fund_heat_display:.2f}%, 变化: {fund_heat_change:.2f})")

        # 生成操作建议
        advice, reason = advice_generator.generate_advice(risk_level, fund_status, ma5_slope)

        print(f"\n✅ 操作建议：{advice}")
        print(f"📝 原因：{reason}")

        # 保存结果
        results.append({
            "etf_name": name,
            "etf_code": code,
            "close": close,
            "pct": pct,
            "benchmark": benchmark_info['benchmark'],
            "alpha_5": alpha_5,
            "alpha_20": alpha_20,
            "risk_level": risk_level,
            "bias_5": bias_5,
            "ma5_slope": ma5_slope,
            "ma20_slope": ma20_slope,
            "short_trend": short_trend,
            "medium_trend": medium_trend,
            "fund_status": fund_status,
            "fund_heat": fund_heat,
            "fund_heat_change": fund_heat_change,
            "advice": advice,
            "reason": reason
        })

    # 保存结果
    today = datetime.now().strftime('%Y%m%d')
    output_json = Path(f"logs/operation_advice_{today}.json")
    output_json.parent.mkdir(exist_ok=True)
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump({
            "date": datetime.now().strftime('%Y-%m-%d'),
            "results": results
        }, f, ensure_ascii=False, indent=2)

    # CSV格式
    output_csv = Path(f"logs/operation_advice_{today}.csv")
    with open(output_csv, 'w', encoding='utf-8') as f:
        f.write("ETF名称,ETF代码,收盘价,涨跌幅,基准指数,Alpha_5,Alpha_20,Alpha_5强弱,Alpha_20强弱,风险等级,Bias_5,MA5斜率,MA20斜率,短期趋势,中期趋势,资金热度,热度占比,热度变化,操作建议,原因\n")
        for r in results:
            alpha_5_strength = Indicators.get_alpha_strength(r['alpha_5'])
            alpha_20_strength = Indicators.get_alpha_strength(r['alpha_20'])
            f.write(f"{r['etf_name']},{r['etf_code']},{r['close']:.3f},{r['pct']:+.2f}%,{r['benchmark']},{r['alpha_5']:+.2f}%,{r['alpha_20']:+.2f}%,{alpha_5_strength},{alpha_20_strength},{r['risk_level']},{r['bias_5']:+.2f}%,{r['ma5_slope']:+.2f}%,{r['ma20_slope']:+.2f}%,{r['short_trend']},{r['medium_trend']},{r['fund_status']},{r['fund_heat']:.4f},{r['fund_heat_change']:.4f},{r['advice']},{r['reason']}\n")

    print(f"\n{'='*80}")
    print(f"✅ 结果已保存：")
    print(f"   JSON: {output_json}")
    print(f"   CSV:  {output_csv}")


if __name__ == "__main__":
    main()
