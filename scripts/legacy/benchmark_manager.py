#!/usr/bin/env python3
"""
基准选择管理模块

功能：
1. 每日16:00自动计算每个ETF的最佳基准（相关性60%阈值判断）
2. 自检并补齐缺失的基准数据
3. JSON持久化存储，可追溯
"""

import os
import json
import pandas as pd
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

# 配置
LOG_DIR = "logs"
BENCHMARK_FILE = "data/etf_benchmarks.json"  # 单个JSON文件存储所有历史
CORRELATION_THRESHOLD = 0.6  # 相关性阈值60%

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

BENCHMARKS = {
    "上证": {"file": "index_000001.jsonl", "code": "000001"},
    "深证": {"file": "index_399001.jsonl", "code": "399001"},
    "创业板": {"file": "index_399006.jsonl", "code": "399006"},
    "科创板": {"file": "index_000688.jsonl", "code": "000688"},
}

# 创建目录
os.makedirs(LOG_DIR, exist_ok=True)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'{LOG_DIR}/benchmark_manager.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def load_jsonl_data(file_path: str, date_from: str = '2025-05-19') -> Optional[pd.DataFrame]:
    """加载JSONL数据"""
    if not os.path.exists(file_path):
        logger.warning(f"文件不存在: {file_path}")
        return None

    rows = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data = json.loads(line.strip())
                    rows.append(data)
                except:
                    continue

        if not rows:
            return None

        df = pd.DataFrame(rows)
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')

        if date_from:
            df = df[df['date'] >= date_from]

        return df
    except Exception as e:
        logger.error(f"加载数据失败 {file_path}: {e}")
        return None


def calculate_daily_benchmark(
    etf_file: str,
    target_date: pd.Timestamp,
    bench_dfs: Dict[str, pd.DataFrame],
    etf_df: pd.DataFrame,
    days: int = 60
) -> Tuple[Optional[str], Optional[float]]:
    """计算指定日期的ETF最佳基准

    Args:
        etf_file: ETF文件路径
        target_date: 目标日期
        bench_dfs: 基准数据字典
        etf_df: ETF完整数据
        days: 回测窗口天数（固定60天）

    Returns:
        (基准名称, 相关系数)
    """
    # 获取目标日期之前的数据
    etf_hist = etf_df[etf_df['date'] < pd.Timestamp(target_date)].tail(days)

    if len(etf_hist) < 10:
        logger.warning(f"数据不足: {etf_file}, {target_date.date()}, 仅{len(etf_hist)}天")
        return None, None

    best_name = None
    best_corr = -1

    for bench_name, bench_df in bench_dfs.items():
        if bench_df is None or bench_df.empty:
            continue

        bench_hist = bench_df[bench_df['date'] < pd.Timestamp(target_date)].tail(days)

        if len(bench_hist) < 10:
            continue

        # 合并计算相关性
        merged = pd.merge(
            etf_hist[['date', 'close']],
            bench_hist[['date', 'close']],
            on='date',
            how='inner'
        )

        if len(merged) < 10:
            continue

        try:
            corr = merged['close_x'].corr(merged['close_y'])
            if corr is not None and corr > best_corr:
                best_corr = corr
                best_name = bench_name
        except Exception as e:
            logger.warning(f"计算相关性失败: {bench_name}, {e}")
            continue

    return best_name, best_corr


def calculate_etf_benchmarks(etf_config: dict, date: pd.Timestamp) -> Optional[dict]:
    """计算单个ETF指定日期的基准

    Args:
        etf_config: ETF配置
        date: 目标日期

    Returns:
        {"date": str, "etf_name": str, "etf_code": str, "benchmark": str, "correlation": float, "use_relative": bool}
    """
    etf_file = f"data/etf_daily/{etf_config['file']}"
    etf_df = load_jsonl_data(etf_file)

    if etf_df is None or etf_df.empty:
        logger.warning(f"ETF数据加载失败: {etf_config['name']}")
        return None

    # 加载基准数据
    bench_dfs = {}
    for bench_name, bench_info in BENCHMARKS.items():
        bench_file = f"data/index_daily/{bench_info['file']}"
        bench_df = load_jsonl_data(bench_file)
        if bench_df is not None:
            bench_dfs[bench_name] = bench_df

    if not bench_dfs:
        logger.error("基准数据加载失败")
        return None

    # 计算基准（统一使用60天回测窗口）
    bench_name, corr = calculate_daily_benchmark(
        etf_config['file'],
        date,
        bench_dfs,
        etf_df,
        days=60
    )

    if bench_name is None:
        logger.warning(f"无法计算基准: {etf_config['name']}, {date.date()}")
        return None

    # 判断是否使用相对强度（相关性阈值60%）
    use_relative = corr >= CORRELATION_THRESHOLD

    return {
        "date": date.strftime('%Y-%m-%d'),
        "etf_name": etf_config['name'],
        "etf_code": etf_config['code'],
        "benchmark": bench_name if use_relative else "无",
        "correlation": round(float(corr), 4),
        "use_relative": bool(use_relative)  # 确保是Python bool，不是numpy bool
    }


def load_benchmark_data() -> Dict[str, list]:
    """加载基准数据（从JSON文件）"""
    if not os.path.exists(BENCHMARK_FILE):
        return {}

    try:
        with open(BENCHMARK_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 转换为按日期索引的字典
        result = {}
        for item in data:
            date = item['date']
            if date not in result:
                result[date] = []
            result[date].append(item)

        return result
    except Exception as e:
        logger.error(f"加载基准数据失败: {e}")
        return {}


def save_benchmark_data(new_data: list):
    """保存基准数据（追加到JSON文件）

    Args:
        new_data: 新的基准数据列表
    """
    # 加载现有数据
    existing_data = []
    if os.path.exists(BENCHMARK_FILE):
        try:
            with open(BENCHMARK_FILE, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
        except Exception as e:
            logger.error(f"加载现有数据失败: {e}")

    # 合并数据（去重）
    existing_dates = {item['date'] for item in existing_data}
    for item in new_data:
        key = f"{item['date']}_{item['etf_code']}"
        if key not in existing_dates:
            existing_data.append(item)
            existing_dates.add(key)

    # 按日期排序
    existing_data.sort(key=lambda x: x['date'])

    # 保存
    try:
        with open(BENCHMARK_FILE, 'w', encoding='utf-8') as f:
            json.dump(existing_data, f, ensure_ascii=False, indent=2)
        logger.info(f"基准数据已保存: {BENCHMARK_FILE}, 总记录数: {len(existing_data)}")
    except Exception as e:
        logger.error(f"保存基准数据失败: {e}")


def check_missing_dates(start_date: pd.Timestamp, end_date: pd.Timestamp) -> list:
    """检查缺失的日期"""
    existing_data = load_benchmark_data()
    existing_dates = set(existing_data.keys())

    missing = []
    current = start_date

    while current <= end_date:
        # 跳过周末
        if current.weekday() < 5:  # 0=周一, 4=周五
            date_str = current.strftime('%Y-%m-%d')
            if date_str not in existing_dates:
                missing.append(current)

        current += timedelta(days=1)

    return missing


def fill_missing_dates(dates: list):
    """自动补齐缺失的基准数据"""
    logger.info(f"开始自动补齐 {len(dates)} 天的基准数据")

    for date in dates:
        logger.info(f"计算: {date.strftime('%Y-%m-%d')}")

        results = []
        for etf in ETF_LIST:
            result = calculate_etf_benchmarks(etf, date)
            if result:
                results.append(result)

        if results:
            save_benchmark_data(results)

            # 统计独立行情数量
            independent = sum(1 for r in results if not r['use_relative'])
            logger.info(f"✅ 完成: {date.strftime('%Y-%m-%d')}, {len(results)}个ETF, {independent}个独立行情")
        else:
            logger.error(f"❌ 失败: {date.strftime('%Y-%m-%d')}")


def daily_update():
    """每日更新任务（定时16:00执行）"""
    logger.info("="*80)
    logger.info("开始每日基准选择更新")
    logger.info("="*80)

    # 获取最新交易日
    today = pd.Timestamp(datetime.now().date())

    # 检查是否为交易日（周一到周五）
    if today.weekday() >= 5:  # 5=周六, 6=周日
        logger.info("周末，跳过更新")
        return

    results = []
    for etf in ETF_LIST:
        result = calculate_etf_benchmarks(etf, today)
        if result:
            results.append(result)

            # 日志输出
            if result['use_relative']:
                logger.info(f"{etf['name']:8s}: {result['benchmark']:6s} (相关系数 {result['correlation']:.4f})")
            else:
                logger.warning(f"{etf['name']:8s}: 独立行情 (相关系数 {result['correlation']:.4f} < {CORRELATION_THRESHOLD})")

    if results:
        save_benchmark_data(results)

        # 统计独立行情
        independent = sum(1 for r in results if not r['use_relative'])
        logger.info(f"✅ 每日更新完成: {len(results)}个ETF, {independent}个独立行情")
    else:
        logger.error("❌ 每日更新失败: 没有有效结果")


def self_check():
    """自检并自动补齐缺失数据"""
    logger.info("="*80)
    logger.info("开始自检")
    logger.info("="*80)

    # 检查最近30天
    end_date = pd.Timestamp(datetime.now().date())
    start_date = end_date - timedelta(days=30)

    missing = check_missing_dates(start_date, end_date)

    if missing:
        logger.warning(f"发现缺失数据: {len(missing)}天")
        logger.info(f"缺失日期: {[d.strftime('%Y-%m-%d') for d in missing]}")
        logger.info("开始自动补齐...")
        fill_missing_dates(missing)
    else:
        logger.info("✅ 自检通过: 最近30天数据完整")


def query_benchmark(date: str, etf_name: str = None) -> list:
    """查询指定日期的基准选择结果

    Args:
        date: 日期 (YYYY-MM-DD)
        etf_name: ETF名称（可选，不指定则返回所有ETF）

    Returns:
        基准选择结果列表
    """
    data = load_benchmark_data()

    if date not in data:
        logger.warning(f"日期不存在: {date}")
        return []

    results = data[date]

    if etf_name:
        results = [r for r in results if r['etf_name'] == etf_name]

    return results


def main():
    """主函数"""
    import sys

    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "update":
            # 执行每日更新
            daily_update()

        elif command == "check":
            # 执行自检
            self_check()

        elif command == "query":
            # 查询基准
            if len(sys.argv) > 2:
                date = sys.argv[2]
                etf_name = sys.argv[3] if len(sys.argv) > 3 else None

                results = query_benchmark(date, etf_name)

                if results:
                    print(f"\n基准查询结果: {date}")
                    print(f"{'ETF名称':>12} {'基准':>12} {'相关系数':>10} {'是否使用相对强度':>15}")
                    print("-" * 70)
                    for r in results:
                        use_rel = "是" if r['use_relative'] else "否"
                        print(f"{r['etf_name']:>12} {r['benchmark']:>12} {r['correlation']:>10.4f} {use_rel:>15}")
                else:
                    print(f"未找到数据: {date}")
            else:
                print("用法: python benchmark_manager.py query YYYY-MM-DD [ETF名称]")

        else:
            print("用法:")
            print("  python benchmark_manager.py update  # 每日更新（16:00执行）")
            print("  python benchmark_manager.py check   # 自检并自动补齐")
            print("  python benchmark_manager.py query YYYY-MM-DD [ETF名称]  # 查询基准")
    else:
        # 默认执行自检 + 更新
        self_check()
        daily_update()


if __name__ == "__main__":
    main()
