#!/usr/bin/env python3
"""
动态基准选择模块

功能：
- 为每个ETF选择最相关的基准指数
- 基于60天滚动相关系数计算
"""

import numpy as np
import pandas as pd
from typing import Dict, List


# 基准指数配置
BENCHMARKS = [
    {"name": "上证指数", "code": "sh000001", "file": "index_000001.jsonl"},
    {"name": "深证成指", "code": "sz399001", "file": "index_399001.jsonl"},
    {"name": "创业板指", "code": "sz399006", "file": "index_399006.jsonl"},
    {"name": "科创50", "code": "sh000680", "file": "index_000680.jsonl"},
]

ROLLING_WINDOW = 60


class BenchmarkSelector:
    """动态基准选择器"""

    def __init__(self, data_loader):
        self.data_loader = data_loader

    def select_benchmark(self, etf_df: pd.DataFrame) -> Dict:
        """选择最相关的基准指数

        Args:
            etf_df: ETF日线数据

        Returns:
            基准信息字典：
            {
                "benchmark": "上证指数",
                "code": "sh000001",
                "correlation": 0.85
            }
        """
        if len(etf_df) < ROLLING_WINDOW:
            return {
                "benchmark": "上证指数",
                "correlation": 0,
                "code": "sh000001"
            }

        # 获取ETF过去60日收盘价
        etf_recent = etf_df.tail(ROLLING_WINDOW)['close'].values

        best_benchmark = None
        best_correlation = -1

        for bench in BENCHMARKS:
            bench_df = self.data_loader.load_index_data(bench['file'])
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
            return {
                "benchmark": "上证指数",
                "correlation": 0,
                "code": "sh000001"
            }

    def load_benchmark_data(self, code: str) -> pd.DataFrame:
        """加载基准指数数据

        Args:
            code: 基准代码（如 "sh000001"）

        Returns:
            基准指数DataFrame
        """
        filename = f"index_{code[2:]}.jsonl"
        return self.data_loader.load_index_data(filename)
