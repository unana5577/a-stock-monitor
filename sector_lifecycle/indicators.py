#!/usr/bin/env python3
"""
指标计算模块

功能：
- Alpha超额收益
- MA斜率（短期MA5、中期MA20）
- 乖离率风险等级
- 资金热度（基于真实成交额或量比）
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple


ROLLING_WINDOW = 60


class Indicators:
    """技术指标计算器"""

    @staticmethod
    def calculate_alpha(etf_df: pd.DataFrame, bench_df: pd.DataFrame, period: int = 5) -> float:
        """计算Alpha超额收益

        Args:
            etf_df: ETF日线数据
            bench_df: 基准指数数据
            period: 周期（5或20）

        Returns:
            Alpha值（百分比）
        """
        if len(etf_df) < period or len(bench_df) < period:
            return 0

        # 计算涨幅
        etf_return = (etf_df.iloc[-1]['close'] - etf_df.iloc[-period]['close']) / etf_df.iloc[-period]['close'] * 100
        bench_return = (bench_df.iloc[-1]['close'] - bench_df.iloc[-period]['close']) / bench_df.iloc[-period]['close'] * 100

        return round(etf_return - bench_return, 2)

    @staticmethod
    def calculate_ma_slope(df: pd.DataFrame, window: int) -> float:
        """计算MA斜率

        Args:
            df: 价格数据
            window: MA窗口（5或20）

        Returns:
            MA斜率（百分比）
        """
        if len(df) < window + 3:
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

    @staticmethod
    def calculate_risk_level(df: pd.DataFrame) -> Tuple[str, float]:
        """计算乖离率风险等级

        Args:
            df: 价格数据

        Returns:
            (风险等级, bias_5值)
        """
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

    @staticmethod
    def calculate_fund_heat(etf_df: pd.DataFrame, market_amount_data: Dict[str, float]) -> Tuple[str, float, float, float]:
        """计算资金热度

        优先使用真实成交额，备选使用量比

        Args:
            etf_df: ETF日线数据
            market_amount_data: 全市场ETF成交额数据

        Returns:
            (状态, 热度占比, 热度变化, 显示热度)
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

    @staticmethod
    def get_alpha_strength(alpha: float) -> str:
        """获取Alpha强弱描述

        Args:
            alpha: Alpha值

        Returns:
            强弱描述
        """
        if alpha > 3:
            return "显著强势 ✅"
        elif alpha > 0:
            return "小幅强势"
        elif alpha >= -3:
            return "小幅弱势"
        else:
            return "显著弱势 ❌"

    @staticmethod
    def calculate_yesterday_pct(etf_df: pd.DataFrame) -> float:
        """获取昨日涨跌幅

        Args:
            etf_df: ETF日线数据

        Returns:
            昨日涨跌幅（百分比）
        """
        if len(etf_df) < 2:
            return 0
        return etf_df.iloc[-2].get('pct', 0)

    @staticmethod
    def calculate_momentum(alpha_5: float, ma5_slope: float, close: float, ma5: float) -> str:
        """计算动能标签（简化版，不使用分位数）

        复用sector_lifecycle.py的逻辑，但使用绝对值判断

        Args:
            alpha_5: 5日超额收益率（百分比）
            ma5_slope: MA5斜率
            close: 当前收盘价
            ma5: MA5均线值

        Returns:
            动能标签
        """
        above = close > ma5 if not pd.isna(ma5) else False
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

    @staticmethod
    def calculate_fund_behavior(
        amount_share_pct: float,
        amount_share_change: float,
        pct: float,
        bias_20: float = 0
    ) -> str:
        """计算资金行为标签（简化版）

        复用sector_lifecycle.py的逻辑，但简化参数

        Args:
            amount_share_pct: 当前成交占比（%）
            amount_share_change: 成交占比变化率
            pct: 日涨跌幅
            bias_20: 20日乖离率（可选）

        Returns:
            资金行为标签
        """
        # 简化版：基于绝对值判断
        if pct < -3 and amount_share_pct > 0.3:  # 成交占比>0.3%作为"高位"简化判断
            return "恐慌出逃"
        elif pct > 0 and amount_share_change >= 0.5:
            return "放量启动"
        elif amount_share_change < 0.8:  # 下跌>20%简化为缩量
            return "资金撤退"
        elif bias_20 > 8 and pct > 0:
            return "加速赶顶"
        elif bias_20 < -8 and pct < 0:
            return "超跌反弹"
        else:
            return "横盘整理"

