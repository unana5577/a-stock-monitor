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
        filepath = self.data_dir / "market" / "etf-amount-daily.jsonl"
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
