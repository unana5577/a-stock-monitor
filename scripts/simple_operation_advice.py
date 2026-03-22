#!/usr/bin/env python3
"""
简化版ETF操作建议系统（单脚本MVP）

核心功能：
1. 动态基准选择（60天相关性）
2. 计算所有指标（Alpha、趋势、量能、乖离率）
3. 生成操作建议
4. 输出报告

作者：Claude
日期：2026-03-17
"""

import json
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime

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

# 基准指数列表
BENCHMARKS = [
    {"name": "上证指数", "code": "sh000001", "file": "index_000001.jsonl"},
    {"name": "深证成指", "code": "sz399001", "file": "index_399001.jsonl"},
    {"name": "创业板指", "code": "sz399006", "file": "index_399006.jsonl"},
    {"name": "科创50", "code": "sh000680", "file": "index_000680.jsonl"},
]

# 数据路径
DATA_DIR = Path("data")
ETF_DIR = DATA_DIR / "etf_daily"
INDEX_DIR = DATA_DIR / "index_daily"
ROLLING_WINDOW = 60
MARKET_SHARE_RATIO = 0.20  # ETF占市场成交额的比例

# ==================== 数据加载 ====================

def load_etf_data(filename: str) -> pd.DataFrame:
    """加载ETF日线数据"""
    filepath = ETF_DIR / filename
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


def load_index_data(filename: str) -> pd.DataFrame:
    """加载指数日线数据"""
    filepath = INDEX_DIR / filename
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


def load_etf_amount_data() -> dict:
    """加载全市场ETF成交额数据"""
    filepath = DATA_DIR / "market" / "etf-amount-daily.jsonl"
    if not filepath.exists():
        return {}

    amount_data = {}
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                item = json.loads(line)
                date = item[0]
                amount = item[1]
                amount_data[date] = amount

    return amount_data


# ==================== 动态基准选择 ====================

def select_benchmark(etf_df: pd.DataFrame) -> dict:
    """选择最相关的基准指数"""
    if len(etf_df) < ROLLING_WINDOW:
        return {"benchmark": "上证指数", "correlation": 0, "code": "sh000001"}

    # 获取ETF过去60日收盘价
    etf_recent = etf_df.tail(ROLLING_WINDOW)['close'].values

    best_benchmark = None
    best_correlation = -1

    for bench in BENCHMARKS:
        bench_df = load_index_data(bench['file'])
        if bench_df.empty or len(bench_df) < ROLLING_WINDOW:
            continue

        # 获取基准过去60日收盘价
        bench_recent = bench_df.tail(ROLLING_WINDOW)['close'].values

        # 计算相关系数
        if len(etf_recent) == len(bench_recent):
            correlation = np.corrcoef(etf_recent, bench_recent)[0, 1]
            if not np.isnan(correlation) and correlation > best_correlation:
                best_correlation = correlation
                best_benchmark = bench

    if best_benchmark:
        return {
            "benchmark": best_benchmark['name'],
            "code": best_benchmark['code'],
            "correlation": round(best_correlation, 3)
        }
    else:
        return {"benchmark": "上证指数", "correlation": 0, "code": "sh000001"}


# ==================== 指标计算 ====================

def calculate_alpha(etf_df: pd.DataFrame, bench_df: pd.DataFrame, period: int = 5) -> float:
    """计算Alpha超额收益"""
    if len(etf_df) < period or len(bench_df) < period:
        return 0

    # 计算涨幅
    etf_return = (etf_df.iloc[-1]['close'] - etf_df.iloc[-period]['close']) / etf_df.iloc[-period]['close'] * 100
    bench_return = (bench_df.iloc[-1]['close'] - bench_df.iloc[-period]['close']) / bench_df.iloc[-period]['close'] * 100

    return round(etf_return - bench_return, 2)


def calculate_ma_slope(df: pd.DataFrame, window: int) -> float:
    """计算MA斜率（支持MA5和MA20）"""
    if len(df) < window + 3:  # 需要足够数据
        return 0

    df = df.copy()
    df['ma'] = df['close'].rolling(window=window).mean()

    # 获取当前和3天前的MA
    current_ma = df.iloc[-1]['ma']
    past_ma = df.iloc[-4]['ma']  # 3天前

    if pd.isna(current_ma) or pd.isna(past_ma) or past_ma == 0:
        return 0

    slope = (current_ma - past_ma) / past_ma * 100
    return round(slope, 2)


def calculate_risk_level(df: pd.DataFrame) -> tuple:
    """计算乖离率风险等级"""
    if len(df) < ROLLING_WINDOW:
        return "数据不足", 0

    df = df.copy()
    df['ma5'] = df['close'].rolling(window=5).mean()
    df['bias_5'] = (df['close'] - df['ma5']) / df['ma5'] * 100

    # 计算分位数
    recent = df.tail(ROLLING_WINDOW)
    bias_5 = df.iloc[-1]['bias_5']

    if pd.isna(bias_5):
        return "数据不足", 0

    quantiles = [0.95, 0.80, 0.60, 0.40, 0.20, 0.05]
    quantile_values = [recent['bias_5'].quantile(q) for q in quantiles]

    # 判断风险等级
    if bias_5 > quantile_values[0]:
        return "极度风险", round(bias_5, 2)
    elif bias_5 > quantile_values[1]:
        return "高风险", round(bias_5, 2)
    elif bias_5 > quantile_values[2]:
        return "中高位风险", round(bias_5, 2)
    elif bias_5 > quantile_values[3]:
        return "中位风险", round(bias_5, 2)
    elif bias_5 > quantile_values[4]:
        return "中低位风险", round(bias_5, 2)
    elif bias_5 > quantile_values[5]:
        return "低风险", round(bias_5, 2)
    else:
        return "极度超跌", round(bias_5, 2)


def calculate_fund_heat(etf_df: pd.DataFrame, market_amount_data: dict) -> tuple:
    """计算资金热度（优先使用真实成交额，备选使用量比）

    方法1（真实成交额）：
    ETF热度 = (ETF成交额 / 全市场ETF成交额) × 100%
    热度变化 = 今日热度 / 昨日热度

    方法2（备选 - 量比）：
    量比 = 今日成交量 / 3日均成交量
    """
    if len(etf_df) < 2:
        return "数据不足", 0, 0, 0

    # 获取ETF今日和昨日成交额
    etf_today = etf_df.iloc[-1]
    etf_yesterday = etf_df.iloc[-2]

    etf_amount_today = etf_today.get('amount', 0)
    etf_amount_yesterday = etf_yesterday.get('amount', 0)

    # 获取全市场ETF成交额
    today_str = etf_today['date'].strftime('%Y-%m-%d')
    yesterday_str = etf_yesterday['date'].strftime('%Y-%m-%d')

    market_amount_today = market_amount_data.get(today_str, 0)
    market_amount_yesterday = market_amount_data.get(yesterday_str, 0)

    # 优先使用真实成交额计算热度
    if etf_amount_today > 0 and market_amount_today > 0:
        # 计算ETF热度（占比）
        fund_heat = (etf_amount_today / market_amount_today) * 100

        # 计算热度变化
        if market_amount_yesterday > 0 and etf_amount_yesterday > 0:
            heat_yesterday = (etf_amount_yesterday / market_amount_yesterday) * 100
            heat_change = fund_heat / heat_yesterday if heat_yesterday > 0 else 1.0
        else:
            # 如果没有昨日数据，使用量比作为变化参考
            volumes = etf_df.tail(3)['volume'].values
            if len(volumes) >= 3:
                avg_volume = volumes.mean()
                heat_change = (etf_today['volume'] / avg_volume) if avg_volume > 0 else 1.0
            else:
                heat_change = 1.0

        # 判断放量/缩量
        if heat_change > 1.1:
            status = "放量"
        elif heat_change < 0.9:
            status = "缩量"
        else:
            status = "持平"

        return status, round(fund_heat, 4), round(heat_change, 4), round(fund_heat, 2)

    # 备选方案：使用量比
    else:
        volumes = etf_df.tail(3)['volume'].values
        if len(volumes) < 3:
            return "数据不足", 0, 0, 0

        current_volume = etf_today['volume']
        avg_volume = volumes.mean()

        if avg_volume == 0:
            return "数据不足", 0, 0, 0

        volume_ratio = current_volume / avg_volume

        # 判断放量/缩量
        if volume_ratio > 1.2:
            status = "放量"
        elif volume_ratio < 0.8:
            status = "缩量"
        else:
            status = "持平"

        # 量比模式下，热度设为0（无法计算占比）
        return status, 0, round(volume_ratio, 4), 0


# ==================== 操作建议生成 ====================

def generate_advice(risk_level: str, fund_status: str, ma5_slope: float) -> tuple:
    """生成操作建议（与完整映射表保持一致）"""

    is_up = ma5_slope > 0

    # 极度风险/高风险 → 减仓/离场
    if risk_level == "极度风险":
        return "减仓/离场", "乖离率过高，注意回调风险"
    elif risk_level == "高风险":
        return "逐步减仓", "锁定利润，防范回调"

    # 极度超跌
    elif risk_level == "极度超跌":
        if fund_status == "放量":
            return "关注企稳/抄底", "超跌+资金进场，关注反弹"
        else:
            return "等待放量", "等待底部信号"

    # 低风险
    elif risk_level == "低风险":
        if fund_status == "放量" and is_up:
            return "关注企稳/试水", "低位+资金进场，关注机会"
        elif fund_status == "放量" and not is_up:
            return "关注企稳", "关注企稳信号"
        else:
            return "继续观察", "等待资金进场"

    # 中低位风险
    elif risk_level == "中低位风险":
        if fund_status == "放量" and is_up:
            return "小仓位试水", "风险较低+资金进场"
        elif fund_status == "放量" and not is_up:
            return "关注", "关注企稳机会"
        elif fund_status == "缩量" and is_up:
            return "继续观察", "等待放量确认"
        else:
            return "继续观察", "等待企稳信号"

    # 中位风险
    elif risk_level == "中位风险":
        if fund_status == "放量" and is_up:
            return "小仓位试水", "趋势向上+资金确认"
        elif fund_status == "放量" and not is_up:
            return "观望", "等待方向明确"
        else:  # 缩量
            return "观望", "缩量震荡，等待突破"

    # 中高位风险
    elif risk_level == "中高位风险":
        if fund_status == "放量" and is_up:
            return "小仓位试水", "风险适中+资金进场"
        elif fund_status == "放量" and not is_up:
            return "观望", "等待企稳信号"
        else:  # 缩量
            return "观望", "缺乏资金支持"

    # 其他
    else:
        return "观望", "等待信号"


def calculate_momentum(alpha_5: float, ma5_slope: float, close: float, ma5: float) -> str:
    """计算动能标签（简化版）"""
    import numpy as np
    above = close > ma5 if not np.isnan(ma5) else False
    a = alpha_5

    if a > 3 and ma5_slope > 0 and above:
        return "强势向上"
    elif 1 <= a <= 3 and ma5_slope > 0 and above:
        return "偏强向上"
    elif -1 <= a <= 1:
        return "中性震荡"
    elif a < -1 and ma5_slope < 0 and not above:
        return "弱势向下"
    elif a < -1 and ma5_slope > 0 and above:
        return "弱势反弹"
    else:
        return "中性震荡"


def calculate_fund_behavior(
    amount_share_pct: float,
    amount_share_change: float,
    pct: float,
    bias_20: float = 0
) -> str:
    """计算资金行为标签（简化版）"""
    if pct < -3 and amount_share_pct > 0.3:
        return "恐慌出逃"
    elif pct > 0 and amount_share_change >= 0.5:
        return "放量启动"
    elif amount_share_change < 0.8:
        return "资金撤退"
    elif bias_20 > 8 and pct > 0:
        return "加速赶顶"
    elif bias_20 < -8 and pct < 0:
        return "超跌反弹"
    else:
        return "横盘整理"


# ==================== 主程序 ====================

def main():
    print("=" * 80)
    print("简化版ETF操作建议报告")
    print(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    results = []

    # ========== 数据新鲜度检查 ==========
    stale_count = 0
    for etf in ETF_LIST:
        etf_df = load_etf_data(etf['file'])
        if etf_df.empty:
            print(f"⚠️  {etf['name']}: 数据为空")
            stale_count += 1
            continue
        latest_date = etf_df.iloc[-1]['date']
        today = datetime.now().date()
        days_diff = (today - latest_date.date()).days
        if days_diff > 1:
            print(f"⚠️  {etf['name']}: 数据过期 {days_diff} 天（最新: {latest_date.date()}）")
            stale_count += 1

    if stale_count > 0:
        print(f"\n⚠️  警告: {stale_count}个ETF数据已过期")
        print(f"   建议运行: python3 data_maintenance.py")
        print(f"   继续使用过期数据进行分析...\n")

    # 加载全市场ETF成交额数据
    market_amount_data = load_etf_amount_data()
    print(f"\n📈 全市场ETF成交额数据已加载: {len(market_amount_data)} 天")

    for etf in ETF_LIST:
        name = etf['name']
        code = etf['code']
        filename = etf['file']

        print(f"\n{'='*80}")
        print(f"📊 {name} ({code})")
        print(f"{'='*80}")

        # 加载数据
        etf_df = load_etf_data(filename)
        if etf_df.empty or len(etf_df) < ROLLING_WINDOW:
            print("数据不足，跳过")
            continue

        # 动态基准选择
        benchmark_info = select_benchmark(etf_df)
        bench_df = load_index_data(f"index_{benchmark_info['code'][2:]}.jsonl")

        # 基本信息
        latest = etf_df.iloc[-1]
        close = latest['close']
        pct = latest.get('pct', 0)

        print(f"📍 基本信息")
        print(f"   收盘价：{close:.3f}  涨跌幅：{pct:+.2f}%")
        print(f"   基准指数：{benchmark_info['benchmark']} (相关性：{benchmark_info['correlation']})")

        # 展示指标：Alpha
        alpha_5 = calculate_alpha(etf_df, bench_df, 5)
        alpha_20 = calculate_alpha(etf_df, bench_df, 20)

        # 判断Alpha强弱
        def get_alpha_strength(alpha):
            if alpha > 3:
                return "显著强势 ✅"
            elif alpha > 0:
                return "小幅强势"
            elif alpha >= -3:
                return "小幅弱势"
            else:
                return "显著弱势 ❌"

        alpha_5_strength = get_alpha_strength(alpha_5)
        alpha_20_strength = get_alpha_strength(alpha_20)

        print(f"\n📊 展示指标（仅供参考）")
        print(f"   Alpha_5：{alpha_5:+.2f}% ({alpha_5_strength})")
        print(f"   Alpha_20：{alpha_20:+.2f}% ({alpha_20_strength})")

        # 判断指标：乖离率
        risk_level, bias_5 = calculate_risk_level(etf_df)
        print(f"\n🔻 乖离率")
        print(f"   风险等级：{risk_level} (bias_5: {bias_5:+.2f}%)")

        # 判断指标：趋势（MA5斜率 = 短期5日趋势，MA20斜率 = 中期20日趋势）
        ma5_slope = calculate_ma_slope(etf_df, 5)
        ma20_slope = calculate_ma_slope(etf_df, 20)
        short_trend = "向上" if ma5_slope > 0 else "向下"
        medium_trend = "向上" if ma20_slope > 0 else "向下"
        print(f"\n📊 趋势")
        print(f"   短期（MA5）：{ma5_slope:+.2f}% ({short_trend})")
        print(f"   中期（MA20）：{ma20_slope:+.2f}% ({medium_trend})")

        # 判断指标：资金热度（使用真实成交额）
        fund_status, fund_heat, fund_heat_change, fund_heat_display = calculate_fund_heat(etf_df, market_amount_data)
        print(f"\n📈 量能")
        print(f"   资金热度：{fund_status} (热度: {fund_heat_display:.2f}%, 变化: {fund_heat_change:.2f})")

        # 生成操作建议
        advice, reason = generate_advice(risk_level, fund_status, ma5_slope)

        print(f"\n✅ 操作建议：{advice}")
        print(f"📝 原因：{reason}")

        # ========== 新增字段计算 ==========
        # 昨日涨跌幅
        yesterday_pct = etf_df.iloc[-2].get('pct', 0) if len(etf_df) >= 2 else 0

        # 计算MA5（用于动能判断）
        etf_df_copy = etf_df.copy()
        etf_df_copy['ma5'] = etf_df_copy['close'].rolling(window=5).mean()
        ma5 = etf_df_copy.iloc[-1]['ma5'] if len(etf_df_copy) >= 5 else close

        # 计算动能
        momentum = calculate_momentum(alpha_5, ma5_slope, close, ma5)

        # 计算资金行为
        bias_20 = 0  # 简化版暂不使用bias_20
        fund_behavior = calculate_fund_behavior(fund_heat, fund_heat_change, pct, bias_20)

        print(f"   昨日涨跌幅：{yesterday_pct:+.2f}%")
        print(f"   动能：{momentum}")
        print(f"   资金行为：{fund_behavior}")

        # 保存结果
        results.append({
            "etf_name": name,
            "etf_code": code,
            "close": close,
            "pct": pct,
            "yesterday_pct": round(yesterday_pct, 2),
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
            "momentum": momentum,
            "fund_behavior": fund_behavior,
            "advice": advice,
            "reason": reason
        })

    # ========== 添加评分和排序 ==========
    # 计算综合得分
    momentum_map = {
        "强势向上": 3, "偏强向上": 2, "中性震荡": 1,
        "弱势反弹": 1, "偏强向下": -1, "弱势向下": -2, "强势向下": -3
    }
    behavior_map = {
        "放量启动": 3, "横盘整理": 1, "超跌反弹": 1,
        "资金撤退": -1, "加速赶顶": -1, "恐慌出逃": -3
    }

    for r in results:
        base = momentum_map.get(r.get("momentum", ""), 0) + behavior_map.get(r.get("fund_behavior", ""), 0)
        score = base + r.get("alpha_5", 0) * 0.15 + r.get("alpha_20", 0) * 0.05 + r.get("fund_heat_change", 0) * 2.0
        # 操作建议惩罚
        if "回避" in r.get("advice", "") or "离场" in r.get("advice", "") or "止损" in r.get("advice", ""):
            score -= 4
        elif "止盈" in r.get("advice", ""):
            score -= 1
        r["_score"] = round(score, 4)

    # 排序并标记Top1-3
    results.sort(key=lambda x: x.get("_score", 0), reverse=True)
    for idx, r in enumerate(results):
        r["_rank"] = idx + 1 if idx < 3 else None

    # 保存结果
    output_json = Path("logs/operation_simple_20260318.json")
    output_json.parent.mkdir(exist_ok=True)
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump({
            "date": datetime.now().strftime('%Y-%m-%d'),
            "results": results
        }, f, ensure_ascii=False, indent=2)

    # CSV格式
    output_csv = Path("logs/operation_simple_20260318.csv")
    with open(output_csv, 'w', encoding='utf-8') as f:
        f.write("ETF名称,ETF代码,收盘价,涨跌幅,基准指数,Alpha_5,Alpha_20,Alpha_5强弱,Alpha_20强弱,风险等级,Bias_5,MA5斜率,MA20斜率,短期趋势,中期趋势,资金热度,热度占比,热度变化,操作建议,原因\n")
        for r in results:
            alpha_5_strength = get_alpha_strength(r['alpha_5'])
            alpha_20_strength = get_alpha_strength(r['alpha_20'])
            f.write(f"{r['etf_name']},{r['etf_code']},{r['close']:.3f},{r['pct']:+.2f}%,{r['benchmark']},{r['alpha_5']:+.2f}%,{r['alpha_20']:+.2f}%,{alpha_5_strength},{alpha_20_strength},{r['risk_level']},{r['bias_5']:+.2f}%,{r['ma5_slope']:+.2f}%,{r['ma20_slope']:+.2f}%,{r['short_trend']},{r['medium_trend']},{r['fund_status']},{r['fund_heat']:.4f},{r['fund_heat_change']:.4f},{r['advice']},{r['reason']}\n")

    print(f"\n{'='*80}")
    print(f"✅ 结果已保存：")
    print(f"   JSON: {output_json}")
    print(f"   CSV:  {output_csv}")


if __name__ == "__main__":
    main()
