#!/usr/bin/env python3
"""
数据接口探测工具

功能：
1. 找到当前可用的最好接口
2. 自动修正 protocol.md 中的错误记录
3. 验证 protocol.md 与 数据接口清单.md 的一致性

使用：
  python scripts/check_data_sources.py etf_daily     # 测试ETF日线
  python scripts/check_data_sources.py breadth      # 测试涨跌家数
  python scripts/check_data_sources.py index_minute # 测试大盘指数分时
"""

import json
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path


class TradingTimeChecker:
    """交易时间检查器"""

    def __init__(self):
        self.now = datetime.now()
        self.hour = self.now.hour
        self.minute = self.now.minute

    def is_trading_day(self):
        """判断是否为交易日"""
        if self.now.weekday() >= 5:
            return False
        holidays_file = Path("config/holidays.json")
        if holidays_file.exists():
            with open(holidays_file, 'r') as f:
                holidays = json.load(f).get('holidays', [])
                if self.now.strftime('%Y-%m-%d') in holidays:
                    return False
        return True

    def is_trading_time(self):
        """判断是否为交易时间（09:30-11:30, 13:00-15:00）"""
        if not self.is_trading_day():
            return False
        # 早盘: 09:30-11:30
        if 9 < self.hour < 11:
            return True
        if self.hour == 9 and self.minute >= 30:
            return True
        if self.hour == 11 and self.minute <= 30:
            return True
        # 午盘: 13:00-15:00
        if 13 <= self.hour < 15:
            return True
        return False

    def is_after_close(self):
        """盘后（15:00后）"""
        return self.hour >= 15

    def get_expected_daily_date(self):
        """日线数据期望日期：盘前T-1，盘后T"""
        if self.is_after_close():
            if self.is_trading_day():
                return self.now.strftime('%Y-%m-%d')
            else:
                # 非交易日盘后，找最近交易日
                yesterday = self.now - timedelta(days=1)
                while yesterday.weekday() >= 5:
                    yesterday -= timedelta(days=1)
                return yesterday.strftime('%Y-%m-%d')
        else:
            # 盘前：T-1
            yesterday = self.now - timedelta(days=1)
            while yesterday.weekday() >= 5:
                yesterday -= timedelta(days=1)
            return yesterday.strftime('%Y-%m-%d')


class ProtocolUpdater:
    """自动更新 protocol.md"""

    def __init__(self):
        self.protocol_file = Path("docs/agents/data_protocol.md")

    def update_interface_status(self, data_type_name, best_interface, failed_interfaces):
        """更新 protocol.md 中的接口状态"""
        if not self.protocol_file.exists():
            print(f"⚠️  protocol.md 不存在，跳过更新")
            return False

        content = self.protocol_file.read_text(encoding='utf-8')
        updated = False

        # 查找并更新接口说明
        if best_interface:
            # 查找数据类型所在的行
            pattern = rf'(\|.*?\|.*?{data_type_name}.*?\|.*?\|)(.*?)(\|)'
            matches = list(re.finditer(pattern, content))

            if matches:
                for match in matches:
                    old_interface = match.group(2).strip()
                    new_interface = best_interface

                    if old_interface != new_interface:
                        replacement = match.group(1) + new_interface + match.group(3)
                        content = content[:match.start()] + replacement + content[match.end():]
                        updated = True
                        print(f"📝 已更新 protocol.md: {data_type_name} 接口改为 {new_interface}")

        # 标注废弃接口
        for failed in failed_interfaces:
            if failed in content:
                # 在接口名后添加 (已废弃)
                content = re.sub(
                    rf'(\|{failed}\|)',
                    rf'\1 ❌已废弃|',
                    content
                )
                updated = True
                print(f"📝 已标注废弃接口: {failed}")

        if updated:
            self.protocol_file.write_text(content, encoding='utf-8')
            print(f"✅ protocol.md 已自动更新")
            return True
        else:
            print(f"ℹ️  protocol.md 无需更新")
            return False


class DataSourceChecker:
    """数据源探测器"""

    # 接口定义（基于 protocol.md 和 数据接口清单.md）
    DATA_SOURCES = {
        'etf_daily': {
            'name': 'ETF日线（关注ETF）',
            'protocol_keyword': 'ETF日线',
            'type': 'daily',
            'description': '9个ETF：半导体、云计算、新能源、商业航天、创新药、有色金属、通讯设备、游戏、机器人',
            'interfaces': [
                {
                    'name': '新浪 fund_etf_hist_sina',
                    'func': 'ak.fund_etf_hist_sina(symbol="sh512480")',
                    'source': 'akshare',
                    'status': 'primary'
                }
            ]
        },
        'index_daily': {
            'name': '大盘指数日线',
            'protocol_keyword': '大盘指数日线',
            'type': 'daily',
            'description': '上证/深证/创业板/科创',
            'interfaces': [
                {
                    'name': '东财 stock_zh_index_daily_em',
                    'func': 'ak.stock_zh_index_daily_em(symbol="sh000001")',
                    'source': 'akshare',
                    'status': 'primary'
                }
            ]
        },
        'breadth': {
            'name': '涨跌家数',
            'protocol_keyword': '涨跌家数',
            'type': 'special',  # 特殊接口：不受时间限制
            'description': '全市场上涨/下跌/持平家数（可做分时/日线）',
            'interfaces': [
                {
                    'name': '东财 stock_zh_a_spot',
                    'func': 'ak.stock_zh_a_spot()',
                    'source': 'akshare',
                    'status': 'primary'
                }
            ]
        },
        'index_minute': {
            'name': '大盘指数分时',
            'protocol_keyword': '大盘指数分时',
            'type': 'minute',
            'description': '上证/深证/创业板/科创/沪深300',
            'interfaces': [
                {
                    'name': '新浪分时接口',
                    'url': 'http://hq.sinajs.cn/list=sh000001',
                    'source': 'http',
                    'status': 'primary'
                }
            ]
        }
    }

    def __init__(self):
        self.time_checker = TradingTimeChecker()
        self.protocol_updater = ProtocolUpdater()
        self.results = {}

    def log(self, message, level="info"):
        """打印日志"""
        prefix = {
            'info': '📋',
            'success': '✅',
            'error': '❌',
            'warn': '⚠️'
        }
        print(f"{prefix.get(level, '📋')} {message}")

    def check_time_valid(self, data_type):
        """检查时间是否合理"""
        if data_type not in self.DATA_SOURCES:
            self.log(f"未知数据类型: {data_type}", "error")
            return False

        config = self.DATA_SOURCES[data_type]

        # 特殊类型接口（如涨跌家数）不受时间限制
        if config['type'] == 'special':
            return True

        if config['type'] == 'minute':
            # 分时接口必须在交易时段
            if not self.time_checker.is_trading_time():
                self.log(f"当前非交易时段，无法测试分时接口", "warn")
                self.log(f"分时接口仅在 09:30-11:30, 13:00-15:00 可用", "info")
                return False

        return True

    def test_akshare_interface(self, func_str):
        """测试 akshare 接口"""
        try:
            import akshare as ak
            start = time.time()
            result = eval(func_str)
            elapsed = time.time() - start

            if result is not None and len(result) > 0:
                # 获取最新数据日期
                latest_date = None
                if hasattr(result, 'iloc'):
                    if 'date' in result.columns:
                        latest_date = result.iloc[-1]['date']
                    elif '日期' in result.columns:
                        latest_date = result.iloc[-1]['日期']

                return {
                    'success': True,
                    'elapsed': round(elapsed, 3),
                    'data_count': len(result),
                    'latest_date': latest_date,
                    'error': None
                }
            else:
                return {
                    'success': False,
                    'elapsed': round(elapsed, 3),
                    'data_count': 0,
                    'latest_date': None,
                    'error': '返回数据为空'
                }
        except ImportError:
            return {
                'success': False,
                'elapsed': None,
                'data_count': None,
                'latest_date': None,
                'error': 'akshare未安装'
            }
        except Exception as e:
            return {
                'success': False,
                'elapsed': None,
                'data_count': None,
                'latest_date': None,
                'error': str(e)[:100]
            }

    def test_http_interface(self, url):
        """测试 HTTP 接口"""
        try:
            from urllib.request import Request, urlopen
            from urllib.error import URLError, HTTPError

            request = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            start = time.time()
            with urlopen(request, timeout=5) as response:
                data = response.read()
                elapsed = time.time() - start

                return {
                    'success': True,
                    'elapsed': round(elapsed, 3),
                    'data_size': len(data),
                    'error': None
                }
        except HTTPError as e:
            return {
                'success': False,
                'elapsed': None,
                'data_size': None,
                'error': f'HTTP {e.code}'
            }
        except URLError as e:
            return {
                'success': False,
                'elapsed': None,
                'data_size': None,
                'error': str(e.reason)
            }
        except Exception as e:
            return {
                'success': False,
                'elapsed': None,
                'data_size': None,
                'error': str(e)[:80]
            }

    def test_interface(self, interface_config):
        """测试单个接口"""
        if interface_config['source'] == 'akshare':
            return self.test_akshare_interface(interface_config['func'])
        elif interface_config['source'] == 'http':
            return self.test_http_interface(interface_config['url'])
        else:
            return {
                'success': False,
                'error': f"未知数据源: {interface_config['source']}"
            }

    def check_data_type(self, data_type):
        """检查指定数据类型的所有接口"""
        if not self.check_time_valid(data_type):
            return

        config = self.DATA_SOURCES[data_type]

        print("\n" + "=" * 60)
        print(f"📊 数据类型: {config['name']}")
        print(f"📝 说明: {config['description']}")
        type_label = {
            'daily': '日线数据',
            'minute': '分时数据',
            'special': '特殊接口（不受时间限制）'
        }
        print(f"🔍 接口类型: {type_label.get(config['type'], config['type'])}")
        print("=" * 60)

        # 标注期望数据日期
        if config['type'] == 'daily':
            expected_date = self.time_checker.get_expected_daily_date()
            if self.time_checker.is_after_close():
                self.log(f"期望数据日期: {expected_date} (收盘后)")
            else:
                self.log(f"期望数据日期: {expected_date} (盘前，检查T-1)")
        else:
            self.log(f"当前时段: {'交易时段' if self.time_checker.is_trading_time() else '非交易时段'}")

        results = []

        for interface in config['interfaces']:
            print(f"\n测试接口: {interface['name']}")
            result = self.test_interface(interface)

            if result['success']:
                self.log(f"接口可用 ({result['elapsed']}秒)", "success")
                if 'latest_date' in result and result['latest_date']:
                    print(f"   最新数据: {result['latest_date']}")
                if 'data_count' in result:
                    print(f"   数据量: {result['data_count']}条")
                if 'data_size' in result:
                    print(f"   数据大小: {result['data_size']} bytes")
            else:
                self.log(f"接口失败: {result['error']}", "error")

            results.append({
                'name': interface['name'],
                'status': interface.get('status', 'unknown'),
                'result': result
            })

        self.results[data_type] = {
            'config': config,
            'interfaces': results
        }

        return results

    def generate_report(self):
        """生成测试报告并更新 protocol.md"""
        print("\n" + "=" * 60)
        print("📋 测试报告")
        print("=" * 60)

        for data_type, data in self.results.items():
            config = data['config']
            interfaces = data['interfaces']

            print(f"\n【{config['name']}】")

            # 找到最好接口
            working = [i for i in interfaces if i['result']['success']]
            failed_interfaces = []

            if working:
                best = working[0]
                print(f"✅ 最好接口: {best['name']}")
                if 'latest_date' in best['result'] and best['result']['latest_date']:
                    print(f"   最新数据: {best['result']['latest_date']}")
                    if config['type'] == 'daily':
                        expected = self.time_checker.get_expected_daily_date()
                        if best['result']['latest_date'] == expected:
                            print(f"   数据状态: ✅ 数据最新")
                        else:
                            print(f"   数据状态: ⚠️  数据延迟（{best['result']['latest_date']} vs {expected}）")
            else:
                print(f"❌ 无可用接口")

            # 失败接口
            failed = [i for i in interfaces if not i['result']['success']]
            if failed:
                for f in failed:
                    print(f"❌ 已废弃接口: {f['name']} ({f['result']['error']})")
                    failed_interfaces.append(f['name'])

            # 自动更新 protocol.md
            if working:
                self.protocol_updater.update_interface_status(
                    config['protocol_keyword'],
                    working[0]['name'],
                    failed_interfaces
                )


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法: python scripts/check_data_sources.py <数据类型>")
        print("\n可用数据类型:")
        for key, val in DataSourceChecker.DATA_SOURCES.items():
            print(f"  - {key}: {val['name']}")
        sys.exit(1)

    data_type = sys.argv[1]

    checker = DataSourceChecker()
    checker.check_data_type(data_type)
    checker.generate_report()


if __name__ == "__main__":
    main()
