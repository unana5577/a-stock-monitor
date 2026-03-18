#!/usr/bin/env python3
"""
ETF操作建议��统（前端兼容版本）

核心功能：
1. 动态基准选择（60天相关性）
2. 计算所有指标（Alpha、趋势、量能、乖离率）
3. 生成操作建议（含仓位指导）
4. 输出前端兼容格式

作者：Claude
日期：2026-03-18
版本：v3.0（前端兼容）
"""

import json
import pandas as pd
import numpy as np
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
    print("ETF操作建议报告（前端兼容版本）")
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

    # 加载市场广度数据（用于错杀检测）
    market_breadth = loader.load_market_breadth_latest()
    market_return = loader.load_market_return_latest()
    print(f"📊 市场广度数据：下跌{market_breadth.get('down', 0)}家（占比{market_breadth.get('down_ratio', 0)*100:.1f}%），大盘涨跌幅{market_return:+.2f}%")

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

        # ========== 新增：前端兼容字段 ==========

        # 1. 昨日涨跌幅
        yesterday_pct = indicators.calculate_yesterday_pct(etf_df)

        # 2. 计算MA5（用于动能判断）
        etf_df_copy = etf_df.copy()
        etf_df_copy['ma5'] = etf_df_copy['close'].rolling(window=5).mean()
        ma5 = etf_df_copy.iloc[-1]['ma5'] if len(etf_df_copy) >= 5 else close

        # 3. 计算动能
        momentum = indicators.calculate_momentum(alpha_5, ma5_slope, close, ma5)

        # 4. 计算资金行为（需要bias_20，这里简化为0）
        bias_20 = 0  # 简化版暂不使用bias_20
        fund_behavior = indicators.calculate_fund_behavior(fund_heat, fund_heat_change, pct, bias_20)

        # 5. 生成操作建议（含仓位指导）
        action, reason = advice_generator.generate_action_with_risk(risk_level, momentum, fund_behavior)

        print(f"\n✅ 动能：{momentum}")
        print(f"✅ 资金行为：{fund_behavior}")
        print(f"✅ 操作建议：{action}")
        print(f"📝 原因：{reason}")

        # ========== 新增：评分计算 ==========
        item_score = indicators.calculate_score(
            momentum=momentum,
            fund_behavior=fund_behavior,
            alpha_5=alpha_5,
            alpha_20=alpha_20,
            amount_share_change=fund_heat_change,
            action=action
        )

        # ========== 新增：错杀检测 ==========
        is_false_kill = indicators.detect_false_kill(
            alpha_20=alpha_20,
            amount_share_pct=fund_heat,
            market_down_ratio=market_breadth.get('down_ratio', 0),
            market_return=market_return
        )
        sig = "false_kill" if is_false_kill else "neutral"

        print(f"📊 综合得分：{item_score:.2f}  信号：{sig}")

        # ========== 保存结果（前端兼容格式）==========
        results.append({
            "板块名称": name,
            "昨日涨跌幅": round(yesterday_pct, 2),
            "今日涨跌幅": round(pct, 2),
            "动能": momentum,
            "资金行为": fund_behavior,
            "操作建议": action,
            "_score": item_score,
            "sig": sig,
            "指标数据": {
                "Amount_Share_Change": round(fund_heat_change, 3),
                "Alpha_5": round(alpha_5, 2),
                "Alpha_20": round(alpha_20, 2),
                "Bias_5": round(bias_5, 2),
                "MA5_Slope": round(ma5_slope, 2),
                "MA20_Slope": round(ma20_slope, 2),
                "Risk_Level": risk_level,
                "Fund_Status": fund_status,
                "Fund_Heat": round(fund_heat, 4),
                "Short_Trend": short_trend,
                "Medium_Trend": medium_trend
            }
        })

    # ========== 按得分排序，标记Top1-3 ==========
    results.sort(key=lambda x: x.get("_score", 0), reverse=True)
    for idx, item in enumerate(results):
        if idx < 3:
            item["topRank"] = idx + 1
        else:
            item["topRank"] = None

    # 保存结���（前端兼容格式）
    today = datetime.now().strftime('%Y%m%d')
    output_json = Path(f"logs/operation_frontend_{today}.json")
    output_json.parent.mkdir(exist_ok=True)
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump({
            "date": datetime.now().strftime('%Y-%m-%d'),
            "items": results
        }, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*80}")
    print(f"✅ 结果已保存：")
    print(f"   JSON: {output_json}")


if __name__ == "__main__":
    main()
