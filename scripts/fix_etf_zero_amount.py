#!/usr/bin/env python3
"""
修复 ETF 日线数据中的0值问题

问题：分时转日线时写入了 amount=0 的错误数据
解决方案：从东财接口重新获取数据替换0值记录
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, '.')
from fetch_sector_data import _fetch_akshare_sina_etf


def fix_etf_zero_amount(etf_code):
    """修复单个ETF的0值数据"""
    # 映射 ETF代码
    code_map = {
        '512400': 'sh512400',  # 有色金属
        '512480': 'sh512480',  # 半导体
        '515120': 'sz515120',  # 创新药
        '515880': 'sz515880',  # 通讯设备
        '516010': 'sh516010',  # 游戏
        '516160': 'sh516160',  # 新能源
        '516510': 'sh516510',  # 云计算
        '562500': 'sh562500',  # 机器人
        '563530': 'sh563530',  # 商业航天
    }

    full_code = code_map.get(etf_code, f'sh{etf_code}')

    filepath = f"data/etf_daily/etf_{etf_code}.jsonl"

    if not Path(filepath).exists():
        print(f"  ❌ 文件不存在: {filepath}")
        return 0

    # 读取现有数据
    existing_data = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                item = json.loads(line.strip())
                existing_data.append(item)
            except:
                pass

    # 找出 amount=0 的记录
    zero_dates = [
        item['date'] for item in existing_data
        if item.get('amount', 0) == 0 and item.get('source') == 'minute'
    ]

    if not zero_dates:
        print(f"  ✅ {etf_code}: 无0值数据")
        return 0

    print(f"  📅 {etf_code}: 发现 {len(zero_dates)} 条0值数据")

    # 从东财接口重新获取最近60天数据
    try:
        result = _fetch_akshare_sina_etf(full_code, limit=60)
        new_data = result.get('data', [])

        if not new_data:
            print(f"  ❌ {etf_code}: 接口无数据")
            return 0

        # 建立日期映射
        new_data_map = {item['date']: item for item in new_data}

        # 替换0值数据
        fixed_count = 0
        for i, item in enumerate(existing_data):
            if item['date'] in zero_dates and item['date'] in new_data_map:
                new_item = new_data_map[item['date']]

                # 验证新数据的成交额
                if new_item.get('amount', 0) > 0:
                    existing_data[i] = new_item
                    fixed_count += 1

        if fixed_count > 0:
            # 写回文件
            with open(filepath, 'w', encoding='utf-8') as f:
                for item in existing_data:
                    f.write(json.dumps(item, ensure_ascii=False) + '\n')

            print(f"  ✅ {etf_code}: 修复了 {fixed_count} 条数据")
            return fixed_count
        else:
            print(f"  ⚠️  {etf_code}: 无可用数据修复")
            return 0

    except Exception as e:
        print(f"  ❌ {etf_code}: 修复失败 - {e}")
        return 0


def main():
    """主函数"""
    print("=" * 60)
    print("修复 ETF 日线数据的0值问题")
    print("=" * 60)

    # ETF代码列表
    etf_codes = [
        '512400',  # 有色金属
        '512480',  # 半导体
        '515120',  # 创新药
        '515880',  # 通讯设备
        '516010',  # 游戏
        '516160',  # 新能源
        '516510',  # 云计算
        '562500',  # 机器人
        '563530',  # 商业航天
    ]

    print(f"共 {len(etf_codes)} 个ETF需要检查\n")

    total_fixed = 0
    for code in etf_codes:
        fixed = fix_etf_zero_amount(code)
        total_fixed += fixed

    print("\n" + "=" * 60)
    print(f"✅ 总共修复了 {total_fixed} 条数据")
    print("=" * 60)

    # 重新生成 warmup
    if total_fixed > 0:
        print("\n🔄 重新生成 warmup 数据...")
        import subprocess
        result = subprocess.run([
            'python3', '-c', '''
import sys
sys.path.insert(0, ".")
from fetch_sector_data import _proxy_history_payload
import json

sectors = "半导体,云计算,新能源,商业航天,创新药,有色金属,通讯设备,游戏,机器人"
sectors_list = [s.strip() for s in sectors.split(",")]

result = _proxy_history_payload(sectors_list, days=60, variant="etf")

with open("data/sector-history-warmup-60.json", "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print("✅ Warmup 数据已更新")
'''
        ], capture_output=True, text=True)

        print(result.stdout)


if __name__ == "__main__":
    main()
