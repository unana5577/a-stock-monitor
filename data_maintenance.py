#!/usr/bin/env python3
"""
数据收集和维护脚本
负责更新大盘指数、ETF日线数据和分时数据
"""
import os
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def load_jsonl(file_path):
    """读取JSONL文件最后一行"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            if lines:
                return json.loads(lines[-1].strip())
    except Exception as e:
        print(f"读取文件失败 {file_path}: {e}")
    return None


def save_jsonl(file_path, data):
    """追加数据到JSONL文件"""
    try:
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(data, ensure_ascii=False) + '\n')
        return True
    except Exception as e:
        print(f"写入文件失败 {file_path}: {e}")
        return False


def get_latest_date(file_path):
    """获取文件最新数据日期"""
    last_data = load_jsonl(file_path)
    if last_data and 'date' in last_data:
        return last_data['date']
    return None


def update_index_data(index_code, index_name):
    """更新单个指数数据"""
    from fetch_sector_data import get_index_history

    file_path = f"data/index_daily/index_{index_code}.jsonl"
    latest_date = get_latest_date(file_path)

    print(f"检查 {index_name} ({index_code})... 最新数据: {latest_date}")

    # 获取最近180天数据
    data = get_index_history(f"sh{index_code}" if index_code.startswith('00') else f"sz{index_code}", days=180)

    if not data:
        print(f"  ❌ 获取数据失败")
        return False

    # 找出需要更新的数据
    new_data = []
    for item in data:
        if latest_date is None or item['date'] > latest_date:
            new_data.append(item)

    if new_data:
        print(f"  📝 更新 {len(new_data)} 条数据: {new_data[0]['date']} ~ {new_data[-1]['date']}")
        for item in new_data:
            save_jsonl(file_path, item)
        print(f"  ✅ {index_name} 更新完成")
        return True
    else:
        print(f"  ✅ {index_name} 已是最新")
        return True


def update_etf_data(etf_code, etf_name):
    """更新单个ETF数据"""
    from fetch_sector_data import _fetch_akshare_sina_etf

    file_path = f"data/etf_daily/etf_{etf_code}.jsonl"
    latest_date = get_latest_date(file_path)

    print(f"检查 {etf_name} ({etf_code})... 最新数据: {latest_date}")

    # 添加sh/sz前缀
    full_code = f"sh{etf_code}" if etf_code.startswith('5') else f"sz{etf_code}"

    # 获取最近365天数据
    result = _fetch_akshare_sina_etf(full_code, limit=365)

    if not result or not result['data']:
        print(f"  ❌ 获取数据失败")
        return False

    # 找出需要更新的数据
    new_data = []
    for item in result['data']:
        if latest_date is None or item['date'] > latest_date:
            new_data.append(item)

    if new_data:
        print(f"  📝 更新 {len(new_data)} 条数据: {new_data[0]['date']} ~ {new_data[-1]['date']}")
        for item in new_data:
            save_jsonl(file_path, item)
        print(f"  ✅ {etf_name} 更新完成")
        return True
    else:
        print(f"  ✅ {etf_name} 已是最新")
        return True


def update_market_amount_daily():
    """更新市场日线成交额"""
    import subprocess

    print("\n" + "="*50)
    print("💰 更新市场日线成交额")
    print("="*50)

    # 读取本地最新日期
    file_path = "data/market-amount-daily.jsonl"
    latest_date = None

    if os.path.exists(file_path):
        last_data = load_jsonl(file_path)
        if last_data and len(last_data) > 0:
            latest_date = last_data[0]

    print(f"本地最新数据: {latest_date or '无'}")

    # 计算起始日期
    if latest_date:
        start_date = (datetime.strptime(latest_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        start_date = "2025-05-19"

    # 调用回补脚本
    script_path = "scripts/backfill_market_amount_daily.py"
    if not os.path.exists(script_path):
        print(f"❌ 回补脚本不存在: {script_path}")
        return False

    print(f"📊 调用回补脚本: {start_date} → 今天")

    try:
        result = subprocess.run(
            [sys.executable, script_path, start_date],
            capture_output=True,
            text=True,
            timeout=180
        )

        if result.returncode == 0:
            output = json.loads(result.stdout.strip())
            if output.get("ok"):
                rows = output.get("rows", 0)
                print(f"✅ 成功更新 {rows} 条数据")
                return True
            else:
                print(f"❌ 更新失败: {output.get('error')}")
                return False
        else:
            print(f"❌ 脚���执行失败: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        print("❌ 脚本执行超时（180秒）")
        return False
    except Exception as e:
        print(f"❌ 执行异常: {e}")
        return False


def update_minute_data():
    """更新分时数据"""
    from fetch_sector_data import get_etf_minute_data, _is_trading_day_session

    # 检查是否在交易时间
    if not _is_trading_day_session():
        print("⏰ 当前非交易时间，跳过分时数据更新")
        return

    # 创建目录
    os.makedirs("data/minute_data", exist_ok=True)

    # 主要ETF和指数
    targets = {
        "sh512480": "半导体",
        "sh515120": "新能源",
        "sz159995": "芯片ETF",
        "sh000001": "上证指数",
        "sz399001": "深证成指",
    }

    today = datetime.now().strftime("%Y-%m-%d")

    for code, name in targets.items():
        file_path = f"data/minute_data/minute_{code}_{today}.jsonl"

        # 检查是否已有今日数据
        if os.path.exists(file_path):
            print(f"⏭️  {name} 分时数据已存在")
            continue

        print(f"📊 获取 {name} 分时数据...")
        result = get_etf_minute_data(code)

        if result and result['data']:
            # 写入分时数据
            for item in result['data']:
                save_jsonl(file_path, item)
            print(f"  ✅ {name} 分时数据更新完成 ({len(result['data'])} 条)")
        else:
            print(f"  ❌ {name} 分时数据获取失败")


def update_all_index_data():
    """更新所有指数数据"""
    print("\n" + "="*50)
    print("📈 更新大盘指数数据")
    print("="*50)

    indexes = [
        ("000001", "上证指数"),
        ("399001", "深证成指"),
        ("399006", "创业板指"),
    ]

    success_count = 0
    for code, name in indexes:
        if update_index_data(code, name):
            success_count += 1

    print(f"\n✅ 指数更新完成: {success_count}/{len(indexes)}")
    return success_count == len(indexes)


def update_all_etf_data():
    """更新所有ETF数据"""
    print("\n" + "="*50)
    print("📊 更新ETF日线数据")
    print("="*50)

    # 读取ETF配置
    try:
        with open("data/etf_benchmarks.json", 'r', encoding='utf-8') as f:
            etf_config = json.load(f)
    except Exception as e:
        print(f"❌ 读取ETF配置失败: {e}")
        return False

    # 提取唯一ETF代码
    etf_list = {}
    for item in etf_config:
        code = item['etf_code']
        name = item['etf_name']
        if code not in etf_list:
            etf_list[code] = name

    success_count = 0
    for code, name in etf_list.items():
        if update_etf_data(code, name):
            success_count += 1

    print(f"\n✅ ETF更新完成: {success_count}/{len(etf_list)}")
    return success_count == len(etf_list)


def main():
    """主函数"""
    print("\n" + "="*50)
    print(f"🔄 数据维护任务 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*50)

    # 1. 更新指数数据
    index_ok = update_all_index_data()

    # 2. 更新ETF数据
    etf_ok = update_all_etf_data()

    # 3. 更新市场日线成交额
    amount_ok = update_market_amount_daily()

    # 4. 更新分时数据（交易时间内）
    update_minute_data()

    # 总结
    print("\n" + "="*50)
    print("📋 任务总结")
    print("="*50)
    print(f"指数数据:     {'✅ 成功' if index_ok else '❌ 失败'}")
    print(f"ETF数据:      {'✅ 成功' if etf_ok else '❌ 失败'}")
    print(f"日线成交额:   {'✅ 成功' if amount_ok else '❌ 失败'}")
    print(f"执行时间:     {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*50 + "\n")


if __name__ == "__main__":
    main()
