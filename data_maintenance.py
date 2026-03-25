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

from fetch_sector_data import get_minute_data_from_akshare, _fetch_ashare_minute


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


def is_trading_day(date_str):
    """判断是否交易日"""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    if dt.weekday() >= 5:  # 周末
        return False
    # 检查节假日
    holiday_file = os.path.join("data", "holiday.txt")
    if os.path.exists(holiday_file):
        try:
            with open(holiday_file, "r", encoding="utf-8") as f:
                holidays = set(line.strip() for line in f if line.strip())
            if date_str in holidays:
                return False
        except:
            pass
    return True

def get_latest_trading_day():
    """获取最新可交易日"""
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")

    # 判断是否在交易时间（9:30-15:00）
    hour = now.hour
    minute = now.minute
    total_minutes = hour * 60 + minute
    is_trading_hours = total_minutes >= 570 and total_minutes <= 900  # 9:30-15:00

    # 如果在交易时间，只能到昨天
    if is_trading_hours:
        for i in range(1, 8):
            prev_date = now - timedelta(days=i)
            prev_str = prev_date.strftime("%Y-%m-%d")
            if is_trading_day(prev_str):
                return prev_str
        return today_str

    # 非交易时间，可以到今天
    if is_trading_day(today_str):
        return today_str

    # 回退
    for i in range(1, 8):
        prev_date = now - timedelta(days=i)
        prev_str = prev_date.strftime("%Y-%m-%d")
        if is_trading_day(prev_str):
            return prev_str

    return today_str

def calculate_missing_trading_days(from_date, to_date):
    """计算两个日期之间的所有交易日"""
    try:
        from_dt = datetime.strptime(from_date, "%Y-%m-%d")
        to_dt = datetime.strptime(to_date, "%Y-%m-%d")

        missing = []
        current = from_dt + timedelta(days=1)

        while current <= to_dt:
            date_str = current.strftime("%Y-%m-%d")
            if is_trading_day(date_str):
                missing.append(date_str)
            current += timedelta(days=1)

        return missing
    except:
        return []

def minute_to_daily(etf_code, date):
    """
    用分时数据聚合生成日线数据

    :param etf_code: ETF代码，如 sh512480
    :param date: 日期，如 2026-03-18
    :return: {"date": "2026-03-18", "open": xxx, "close": xxx, ...} 或 None
    """
    # ETF名称映射
    etf_name_map = {
        "sh512480": "半导体",
        "sh516510": "云计算",
        "sh516160": "新能源",
        "sh563530": "商业航天",
        "sh515120": "创新药",
        "sh512400": "有色金属",
        "sh515880": "通讯设备",
        "sh516010": "游戏",
        "sh562500": "机器人",
    }

    etf_name = etf_name_map.get(etf_code, etf_code)

    # 方法1: 从 sector-minute-warmup.json 读取
    warmup_file = "data/sector-minute-warmup.json"
    if os.path.exists(warmup_file):
        try:
            with open(warmup_file, 'r', encoding='utf-8') as f:
                warmup_data = json.load(f)

            minute_data = warmup_data.get('minute', {}).get(etf_name)
            if minute_data and minute_data.get('series'):
                series = minute_data['series']
                prices = [float(item.get('close') or item.get('price') or 0) for item in series if item.get('close') or item.get('price')]
                volumes = [float(item.get('volume', 0)) for item in series]
                amounts = [float(item.get('amount', 0)) for item in series]

                if prices:
                    open_price = prices[0]
                    close_price = prices[-1]
                    high_price = max(prices)
                    low_price = min(prices)
                    total_volume = volumes[-1] if volumes else 0  # 取累计值
                    total_amount = amounts[-1] if amounts else 0  # 取累计值

                    if open_price > 0:
                        pct = (close_price - open_price) / open_price * 100
                    else:
                        pct = 0

                    # 从时间中提取日期
                    if series and series[0].get('time'):
                        time_str = series[0]['time']
                        actual_date = time_str.split(' ')[0] if ' ' in time_str else date

                    return {
                        "date": actual_date,
                        "open": open_price,
                        "close": close_price,
                        "high": high_price,
                        "low": low_price,
                        "volume": total_volume,
                        "amount": total_amount,
                        "pct": round(pct, 2),
                        "source": "minute"
                    }
        except Exception as e:
            print(f"      读取warmup失败: {e}")

    # 方法2: 从 minute_data 目录读取
    minute_dirs = ["data/minute_data", "data"]

    for minute_dir in minute_dirs:
        file_patterns = [
            f"{minute_dir}/minute_{etf_code}_{date}.jsonl",
            f"{minute_dir}/minute-{date}-{etf_code}.jsonl",
        ]

        for minute_file in file_patterns:
            if os.path.exists(minute_file):
                try:
                    with open(minute_file, 'r', encoding='utf-8') as f:
                        lines = f.readlines()

                    if not lines:
                        continue

                    prices = []
                    volumes = []
                    amounts = []

                    for line in lines:
                        try:
                            item = json.loads(line.strip())
                            price = item.get('price') or item.get('close')
                            vol = item.get('volume', 0)
                            amt = item.get('amount', 0)

                            if price:
                                prices.append(float(price))
                            if vol:
                                volumes.append(float(vol))
                            if amt:
                                amounts.append(float(amt))
                        except:
                            continue

                    if not prices:
                        continue

                    open_price = prices[0]
                    close_price = prices[-1]
                    high_price = max(prices) if prices else 0
                    low_price = min(prices) if prices else 0
                    total_volume = volumes[-1] if volumes else 0  # 取累计值
                    total_amount = amounts[-1] if amounts else 0  # 取累计值

                    if open_price > 0:
                        pct = (close_price - open_price) / open_price * 100
                    else:
                        pct = 0

                    return {
                        "date": date,
                        "open": open_price,
                        "close": close_price,
                        "high": high_price,
                        "low": low_price,
                        "volume": total_volume,
                        "amount": total_amount,
                        "pct": round(pct, 2),
                        "source": "minute"
                    }
                except Exception as e:
                    continue

    return None

def update_etf_data(etf_code, etf_name):
    """
    更新单个ETF数据（增量更新 + 分时fallback + 对账覆盖）

    流程：
    1. 计算缺失的交易日
    2. 尝试东财日线数据
    3. 如果失败，用分时数据聚合
    4. 如果东财成功，对比分时数据，有差异则覆盖
    """
    from fetch_sector_data import _fetch_akshare_sina_etf

    file_path = f"data/etf_daily/etf_{etf_code}.jsonl"
    latest_date = get_latest_date(file_path)

    # 添加sh/sz前缀
    full_code = f"sh{etf_code}" if etf_code.startswith('5') else f"sz{etf_code}"

    # 计算最新可交易日
    latest_trading_day = get_latest_trading_day()

    print(f"检查 {etf_name} ({etf_code})... 本地最新: {latest_date}, 最新可交易日: {latest_trading_day}")

    # 如果本地数据已最新
    if latest_date and latest_date >= latest_trading_day:
        print(f"  ✅ {etf_name} 已是最新")
        return True

    # 计算缺失的交易日
    from_date = latest_date or "2025-01-01"
    missing_days = calculate_missing_trading_days(from_date, latest_trading_day)

    if not missing_days:
        print(f"  ✅ {etf_name} 无缺失交易日")
        return True

    print(f"  📊 缺失交易日: {missing_days}")

    # ============ 步骤1: 尝试请求东财日线 ============
    eastmoney_data = None

    try:
        # 增量请求：只请求缺失的日期范围
        start_date = missing_days[0].replace('-', '')
        end_date = missing_days[-1].replace('-', '')

        result = _fetch_akshare_sina_etf(full_code, start_date=start_date, end_date=end_date)

        if result and result.get('data'):
            eastmoney_data = result['data']
            print(f"  🌐 东财接口成功获取 {len(eastmoney_data)} 条数据")
    except Exception as e:
        print(f"  ⚠️ 东财接口请求失败: {str(e)[:50]}")

    # ============ 步骤2: 获取分时数据作为fallback/对账 ============
    minute_data_list = []
    for day in missing_days:
        minute_daily = minute_to_daily(full_code, day)
        if minute_daily:
            minute_data_list.append(minute_daily)
            print(f"  📊 分时数据: {day} -> open={minute_daily['open']}, close={minute_daily['close']}")

    # ============ 步骤3: 决定使用哪种数据 ============
    new_data = []

    if eastmoney_data:
        # 东财成功，检查是否需要对账
        if minute_data_list:
            # 对比分时数据
            for em_item in eastmoney_data:
                em_date = em_item.get('date')
                # 找对应的分时数据
                minute_item = next((m for m in minute_data_list if m.get('date') == em_date), None)

                if minute_item:
                    # 对比收盘价差异
                    em_close = em_item.get('close', 0)
                    min_close = minute_item.get('close', 0)

                    if em_close > 0 and min_close > 0:
                        diff = abs(em_close - min_close) / em_close
                        if diff > 0.001:  # 差异超过0.1%
                            print(f"  🔄 对账覆盖: {em_date} 东财close={em_close} vs 分时close={min_close} (差异{diff*100:.2f}%)")
                            # 用东财数据覆盖
                            new_data.append(em_item)
                        else:
                            # 差异小，使用东财数据
                            new_data.append(em_item)
                    else:
                        new_data.append(em_item)
                else:
                    new_data.append(em_item)
        else:
            # 没有分时数据，直接使用东财数据
            new_data = eastmoney_data

        source = "东财"
    elif minute_data_list:
        # 东财失败，使用分时数据
        new_data = minute_data_list
        source = "分时聚合"
    else:
        # 都失败
        print(f"  ❌ {etf_name}: 东财和分时数据均获取失败")
        return False

    # ============ 步骤4: 写入数据 ============
    if new_data:
        # 读取现有数据，去重
        existing_dates = set()
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        item = json.loads(line.strip())
                        if item.get('date'):
                            existing_dates.add(item['date'])
                    except:
                        pass

        # 过滤已存在的日期
        to_save = [item for item in new_data if item.get('date') not in existing_dates]

        if to_save:
            print(f"  📝 写入 {len(to_save)} 条数据 ({source}): {to_save[0]['date']} ~ {to_save[-1]['date']}")
            for item in to_save:
                save_jsonl(file_path, item)
            print(f"  ✅ {etf_name} 更新完成 ({source})")
        else:
            print(f"  ✅ {etf_name} 无新数据需要写入")
        return True
    else:
        print(f"  ❌ {etf_name}: 无有效数据")
        return False


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
        if last_data:
            # 支持两种格式：数组["2026-03-18", ...] 或 字典{"date": "2026-03-18", ...}
            if isinstance(last_data, dict):
                latest_date = last_data.get('date')
            elif isinstance(last_data, (list, tuple)) and len(last_data) > 0:
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


def update_etf_amount_daily():
    """更新ETF成交额日线"""
    import subprocess

    print("\n" + "="*50)
    print("📊 更新ETF成交额日线")
    print("="*50)

    script_path = "scripts/etf_amount_daily_sina.py"
    if not os.path.exists(script_path):
        print(f"❌ 脚本不存在: {script_path}")
        return False

    print("📊 执行ETF成交额抓取...")

    try:
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode == 0:
            try:
                output = json.loads(result.stdout.strip())
                if output.get("ok"):
                    if output.get("exists"):
                        print(f"⏭️ 今日数据已存在: {output.get('day')}")
                    else:
                        print(f"✅ 更新成功: {output.get('day')}, 成交额: {output.get('total_yi', 0):.2f}亿, ETF数量: {output.get('count')}")
                    return True
                else:
                    print(f"❌ 更新失败: {output.get('error')}")
                    return False
            except json.JSONDecodeError:
                print(f"❌ JSON解析失败: {result.stdout[:200]}")
                return False
        else:
            print(f"❌ 脚本执行失败: {result.stderr[:200]}")
            return False

    except subprocess.TimeoutExpired:
        print("❌ 脚本执行超时（60秒）")
        return False
    except Exception as e:
        print(f"❌ 执行异常: {e}")
        return False


def update_breadth_history():
    """更新涨跌家数历史"""
    import subprocess

    print("\n" + "="*50)
    print("📈 更新涨跌家数历史")
    print("="*50)

    script_path = "scripts/save_breadth_history.py"
    if not os.path.exists(script_path):
        # 如果脚本不存在，尝试直接读取缓存
        cache_file = "data/breadth-cache.json"
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if data.get('ok'):
                    day = datetime.now().strftime("%Y-%m-%d")
                    history_file = "data/breadth-history.jsonl"

                    # 检查是否已存在
                    existing = False
                    if os.path.exists(history_file):
                        with open(history_file, 'r', encoding='utf-8') as f:
                            for line in f:
                                row = json.loads(line.strip())
                                if isinstance(row, dict) and row.get('date') == day:
                                    existing = True
                                    break

                    if existing:
                        print(f"⏭️ 今日涨跌家数已存在: {day}")
                        return True

                    # 写入
                    with open(history_file, 'a', encoding='utf-8') as f:
                        row = {
                            "timestamp": int(datetime.now().timestamp() * 1000),
                            "date": day,
                            "up": data.get('up', 0),
                            "down": data.get('down', 0),
                            "flat": data.get('flat', 0),
                            "total": data.get('total', 0)
                        }
                        f.write(json.dumps(row, ensure_ascii=False) + '\n')

                    print(f"✅ 涨跌家数已更新: {day}")
                    return True
            except Exception as e:
                print(f"❌ 读取缓存失败: {e}")
                return False
        print(f"❌ 脚本不存在: {script_path}")
        return False

    print("📊 执行涨跌家数保存...")

    try:
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            try:
                output = json.loads(result.stdout.strip())
                if output.get("ok"):
                    if output.get("exists"):
                        print(f"⏭️ 今日涨跌家数已存在: {output.get('day')}")
                    else:
                        print(f"✅ 涨跌家数已更新: {output.get('day')}, 上涨: {output.get('up')}, 下跌: {output.get('down')}")
                    return True
                else:
                    print(f"❌ 更新失败: {output.get('error')}")
                    return False
            except json.JSONDecodeError:
                print(f"❌ JSON解析失败: {result.stdout[:200]}")
                return False
        else:
            print(f"❌ 脚本执行失败: {result.stderr[:200]}")
            return False

    except subprocess.TimeoutExpired:
        print("❌ 脚本执行超时（30秒）")
        return False
    except Exception as e:
        print(f"❌ 执行异常: {e}")
        return False


def minute_to_daily_for_etf(etf_code, today, etf_name=None):
    """
    用分时数据生成日线数据并写入 ETF 日线文件

    :param etf_code: ETF代码，如 sh512480
    :param today: 日期，如 2026-03-18
    :param etf_name: ETF名称，如 "云计算"
    """
    # ETF名称映射
    etf_name_map = {
        "sh512480": "半导体",
        "sh516510": "云计算",
        "sh516160": "新能源",
        "sh563530": "商业航天",
        "sh515120": "创新药",
        "sh512400": "有色金属",
        "sh515880": "通讯设备",
        "sh516010": "游戏",
        "sh562500": "机器人",
    }

    series = None

    # 方法1: 从 minute_data 目录读取
    minute_file = f"data/minute_data/minute_{etf_code}_{today}.jsonl"
    if os.path.exists(minute_file):
        try:
            with open(minute_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            if lines:
                # 解析分时数据
                series = []
                for line in lines:
                    try:
                        item = json.loads(line.strip())
                        series.append(item)
                    except:
                        continue
        except:
            pass

    # 方法2: 从 warmup 读取（更可靠）
    if not series:
        try:
            warmup_file = "data/sector-minute-warmup.json"
            if os.path.exists(warmup_file):
                with open(warmup_file, 'r', encoding='utf-8') as f:
                    warmup_data = json.load(f)

                # 查找对应的ETF名称
                name = etf_name or etf_name_map.get(etf_code, etf_code)
                minute_data = warmup_data.get('minute', {}).get(name)
                if minute_data and minute_data.get('series'):
                    series = minute_data['series']
        except:
            pass

    if not series:
        print(f"    ⏭️ {etf_code} 无分时数据")
        return None

    # 获取昨日收盘价（用于计算pct）
    prev_close = None
    etf_code_only = etf_code.replace('sh', '').replace('sz', '')
    etf_file = f"data/etf_daily/etf_{etf_code_only}.jsonl"
    if os.path.exists(etf_file):
        try:
            with open(etf_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                for line in reversed(lines):
                    item = json.loads(line.strip())
                    if item.get('date') and item['date'] != today:
                        prev_close = item.get('close')
                        if prev_close:
                            break
        except:
            pass

    try:
        # 解析并聚合
        prices = []
        volumes = []
        amounts = []

        for item in series:
            try:
                price = item.get('price') or item.get('close')
                vol = item.get('volume', 0)
                amt = item.get('amount', 0)

                if price:
                    prices.append(float(price))
                if vol:
                    volumes.append(float(vol))
                if amt:
                    amounts.append(float(amt))
            except:
                continue

        if not prices:
            return None

        # 聚合计算
        # 分时数据是累计值，volume/amount取最后一笔（15:00）
        open_price = prices[0]
        close_price = prices[-1]
        high_price = max(prices)
        low_price = min(prices)
        total_volume = volumes[-1] if volumes else 0  # 取累计值
        total_amount = amounts[-1] if amounts else 0  # 取累计值

        # pct应基于昨日收盘价计算，而非当日开盘价
        if prev_close and prev_close > 0:
            pct = (close_price - prev_close) / prev_close * 100
        elif open_price > 0:
            pct = (close_price - open_price) / open_price * 100
        else:
            pct = 0

        daily_data = {
            "date": today,
            "open": open_price,
            "close": close_price,
            "high": high_price,
            "low": low_price,
            "volume": total_volume,
            "amount": total_amount,
            "pct": round(pct, 2),
            "source": "minute_15:00"
        }

        # 写入 ETF 日线文件
        # ETF代码转换：sh512480 -> 512480
        etf_code_only = etf_code.replace('sh', '').replace('sz', '')
        etf_file = f"data/etf_daily/etf_{etf_code_only}.jsonl"

        # 检查是否已存在
        existing_dates = set()
        if os.path.exists(etf_file):
            with open(etf_file, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        item = json.loads(line.strip())
                        if item.get('date'):
                            existing_dates.add(item['date'])
                    except:
                        pass

        if today not in existing_dates:
            save_jsonl(etf_file, daily_data)
            print(f"    📝 分时15:00写入日线: {etf_code_only}")
            return daily_data
        else:
            print(f"    ⏭️ {etf_code_only} 今日日线已存在")
            return daily_data

    except Exception as e:
        print(f"    ❌ 分时转日线失败: {e}")
        return None


def update_minute_data():
    """更新分时数据，并写入ETF日线"""
    from fetch_sector_data import get_etf_minute_data, _is_trading_day_session

    # 检查是否在交易时间
    if not _is_trading_day_session():
        print("⏰ 当前非交易时间，跳过分时数据更新")
        return

    # 创建目录
    os.makedirs("data/minute_data", exist_ok=True)

    # 主要ETF（完整列表，用于写入日线）
    etf_targets = [
        ("sh512480", "半导体"),
        ("sh516510", "云计算"),
        ("sh516160", "新能源"),
        ("sh563530", "商业航天"),
        ("sh515120", "创新药"),
        ("sh512400", "有色金属"),
        ("sh515880", "通讯设备"),
        ("sh516010", "游戏"),
        ("sh562500", "机器人"),
    ]

    today = datetime.now().strftime("%Y-%m-%d")

    # 所有9个ETF都需要获取分时数据（用于生成日线的volume/amount）
    minute_targets = etf_targets  # 使用上面的完整列表

    # 获取所有ETF的分时数据
    for code, name in minute_targets:
        file_path = f"data/minute_data/minute_{code}_{today}.jsonl"

        # 检查文件是否存在及完整性
        last_time = None
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                if lines:
                    try:
                        last_record = json.loads(lines[-1])
                        last_time = last_record.get('time')
                    except:
                        pass

            # 判断是否已收盘（15:05后）
            now = datetime.now()
            if now.hour > 15 or (now.hour == 15 and now.minute >= 5):
                print(f"⏭️  {name} 分时数据已完成（收盘后）")
                continue
            elif last_time:
                print(f"📊 {name} 分时数据更新")
                os.remove(file_path)
            else:
                print(f"⚠️  {name} 文件异常，删除重建")
                os.remove(file_path)
        else:
            print(f"📊 获取 {name} 分时数据...")
        result = get_etf_minute_data(code)

        if result and result['data']:
            # 写入分时数据（带volume/amount）
            for item in result['data']:
                save_jsonl(file_path, item)

            # 写入prevClose到文件头（下一行）
            if result.get('prevClose'):
                prev_file = file_path.replace('.jsonl', '_prev.jsonl')
                with open(prev_file, 'w', encoding='utf-8') as f:
                    f.write(json.dumps({"prevClose": result['prevClose']}, ensure_ascii=False) + '\n')

            print(f"  ✅ {name} 分时数据更新完成 ({len(result['data'])} 条), prevClose={result.get('prevClose')}")
        else:
            print(f"  ⚠️  {name} 分时数据获取失败，将使用warmup")

    # 大盘指数分时数据保存到 data/minute/
    print("\n📈 保存大盘指数分时数据...")
    os.makedirs("data/minute", exist_ok=True)

    large_cap_indices = [
        ("sh000001", "sse"),      # 上证指数
        ("sz399001", "szi"),      # 深证成指
        ("sz399006", "gem"),      # 创业板指
        ("sh000688", "star"),     # 科创板指
        ("sh000300", "hs300"),    # 沪深300
    ]

    for code, name in large_cap_indices:
        file_path = f"data/minute/minute-{today}-{name}.jsonl"

        # 检查是否需要更新
        if os.path.exists(file_path):
            now = datetime.now()
            if now.hour > 15 or (now.hour == 15 and now.minute >= 5):
                print(f"  ⏭️  {name} 分时数据已完成")
                continue

        print(f"  📊 获取 {code}({name}) 分时数据...")
        result = _fetch_ashare_minute(code, count=240)

        if result and result.get('data'):
            with open(file_path, 'w', encoding='utf-8') as f:
                for item in result['data']:
                    # 格式: [time, open, close, pct]
                    row = [item['time'], item.get('open'), item['close'], item.get('pct')]
                    f.write(json.dumps(row, ensure_ascii=False) + '\n')
            print(f"    ✅ {name} 分时数据保存完成 ({len(result['data'])} 条)")
        else:
            print(f"    ⚠️  {name} 分时数据获取失败")

    # 板块分时数据保存到 data/minute/
    print("\n🏢 保存板块分时数据...")
    sectors = {
        '90.BK0475': 'bank',      # 银行
        '90.BK0473': 'broker',    # 证券
        '90.BK0474': 'insure',    # 保险
    }

    for secid, name in sectors.items():
        file_path = f"data/minute/minute-{today}-{name}.jsonl"

        # 检查是否需要更新
        if os.path.exists(file_path):
            now = datetime.now()
            if now.hour > 15 or (now.hour == 15 and now.minute >= 5):
                print(f"  ⏭️  {name} 分时数据已完成")
                continue

        print(f"  📊 获取 {name}({secid}) 分时数据...")
        result = get_minute_data_from_akshare(secid)

        if result and result.get('data'):
            with open(file_path, 'w', encoding='utf-8') as f:
                for item in result['data']:
                    # 格式: [time, open, close, pct]
                    pct = item.get('pct')
                    if pct is None and result.get('prevClose'):
                        pct = round((item['close'] - result['prevClose']) / result['prevClose'] * 100, 2)
                    row = [item['time'], item.get('open'), item['close'], pct]
                    f.write(json.dumps(row, ensure_ascii=False) + '\n')
            print(f"    ✅ {name} 分时数据保存完成 ({len(result['data'])} 条)")
        else:
            print(f"    ⚠️  {name} 分时数据获取失败")

    # 遍历所有ETF，用分时数据写入日线（15:00数据）
    print("\n📝 用分时15:00数据写入ETF日线...")
    for code, name in etf_targets:
        minute_file = f"data/minute_data/minute_{code}_{today}.jsonl"
        if os.path.exists(minute_file):
            minute_to_daily_for_etf(code, today)
        else:
            print(f"    ⏭️ {name} 无分时数据，跳过")


def update_all_index_data():
    """更新所有指数数据"""
    print("\n" + "="*50)
    print("📈 更新大盘指数数据")
    print("="*50)

    indexes = [
        ("000001", "上证指数"),
        ("399001", "深证成指"),
        ("399006", "创业板指"),
        ("000688", "科创板指"),
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

    # 4. 更新ETF成交额
    etf_amount_ok = update_etf_amount_daily()

    # 5. 更新涨跌家数历史
    breadth_ok = update_breadth_history()

    # 6. 更新分时数据（交易时间内）并写入日线
    update_minute_data()

    # 7. 同步更新warmup缓存
    print("\n" + "="*50)
    print("🔄 同步更新Warmup缓存")
    print("="*50)
    from fetch_sector_data import warmup_proxy_files
    DEFAULT_SECTORS = ["半导体", "云计算", "新能源", "商业航天", "创新药", "有色金属", "通讯设备", "游戏", "机器人"]
    warmup_result = warmup_proxy_files(DEFAULT_SECTORS, days=60)
    print(f"✅ Warmup缓存已更新: {warmup_result.get('day')}")

    # 总结
    print("\n" + "="*50)
    print("📋 任务总结")
    print("="*50)
    print(f"指数数据:     {'✅ 成功' if index_ok else '❌ 失败'}")
    print(f"ETF数据:      {'✅ 成功' if etf_ok else '❌ 失败'}")
    print(f"日线成交额:   {'✅ 成功' if amount_ok else '❌ 失败'}")
    print(f"ETF成交额:    {'✅ 成功' if etf_amount_ok else '❌ 失败'}")
    print(f"涨跌家数:     {'✅ 成功' if breadth_ok else '❌ 失败'}")
    print(f"Warmup缓存:   ✅ 已同步")
    print(f"执行时间:     {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*50 + "\n")


if __name__ == "__main__":
    main()
