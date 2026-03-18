#!/usr/bin/env python3
"""
数据加载模块

功能：
- 加载ETF日线数据
- 加载指数日线数据
- 加载全市场ETF成交额数据
"""

import json
import pandas as pd
from pathlib import Path
from typing import Dict


class DataLoader:
    """数据加载器"""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.etf_dir = self.data_dir / "etf_daily"
        self.index_dir = self.data_dir / "index_daily"

    def load_etf_data(self, filename: str) -> pd.DataFrame:
        """加载ETF日线数据

        Args:
            filename: ETF文件名（如 "etf_515880.jsonl"）

        Returns:
            DataFrame with columns: date, close, volume, amount, pct, etc.
        """
        filepath = self.etf_dir / filename
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

    def load_index_data(self, filename: str) -> pd.DataFrame:
        """加载指数日线数据

        Args:
            filename: 指数文件名（如 "index_000001.jsonl"）

        Returns:
            DataFrame with columns: date, close, volume, etc.
        """
        filepath = self.index_dir / filename
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

    def load_etf_amount_data(self) -> Dict[str, float]:
        """加载全市场ETF成交额数据

        Returns:
            字典，格式：{"2026-03-17": 545613396034.0, ...}
        """
        filepath = self.data_dir / "etf-amount-daily.jsonl"
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

    def load_market_breadth_latest(self) -> Dict[str, float]:
        """加载最新的市场广度数据

        Returns:
            字典，格式：{"up": 866, "down": 4541, "flat": 81, "total": 5488, "down_ratio": 0.827}
        """
        filepath = self.data_dir / "breadth-history.jsonl"
        if not filepath.exists():
            return {}

        latest_data = {}
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            if lines:
                latest = json.loads(lines[-1].strip())
                # 格式：[timestamp, date, up, down, flat, total]
                if len(latest) >= 6:
                    latest_data = {
                        "up": latest[2],
                        "down": latest[3],
                        "flat": latest[4],
                        "total": latest[5],
                        "down_ratio": latest[3] / latest[5] if latest[5] > 0 else 0
                    }

        return latest_data

    def load_market_return_latest(self) -> float:
        """加载最新的大盘涨跌幅

        从上证指数数据中获取最新涨跌幅

        Returns:
            最新涨跌幅（百分比）
        """
        df = self.load_index_data("index_000001.jsonl")
        if df.empty:
            return 0

        return df.iloc[-1].get('pct', 0)
