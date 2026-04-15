#!/usr/bin/env python3
"""
修复 ETF 成交额数据 - 强制从东财接口重新获取
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, '.')
from fetch_sector_data import _fetch_akshare_sina_etf, _get_etf_file_path


def fix_etf_amount_data(etf_code):
    """修复单个ETF的成交额数据"""
    filepath = _get_etf_file_path(etf_code)

    if not Path(filepath).exists():
        print(f'  ❌ 文件不存在: {filepath}')
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

    # 找出需要修复的数据（amount=0 且 source=minute）
    problem_dates = [
        item['date'] for item in existing_data
        if item.get('amount', 0) == 0 and item.get('source') == 'minute'
    ]

    if not problem_dates:
        print(f'  ✅ 无需修复')
        return 0

    print(f'  📅 发现 {len(problem_dates)} 条问题数据')

    # 从东财接口重新获取最近60天数据
    try:
        result = _fetch_akshare_sina_etf(etf_code, limit=60)
        new_data = result.get('data', [])

        # 按日期建立映射
        new_data_map = {item['date']: item for item in new_data}

        # 替换问题数据
        fixed_count = 0
        for i, item in enumerate(existing_data):
            if item['date'] in problem_dates and item['date'] in new_data_map:
                existing_data[i] = new_data_map[item['date']]
                fixed_count += 1

        if fixed_count > 0:
            # 写回文件
            with open(filepath, 'w', encoding='utf-8') as f:
                for item in existing_data:
                    f.write(json.dumps(item, ensure_ascii=False) + '\n')

            print(f'  ✅ 修复了 {fixed_count} 条数据')
            return fixed_count
        else:
            print(f'  ⚠️  无法从接口获取修复数据')
            return 0

    except Exception as e:
        print(f'  ❌ 修复失败: {e}')
        return 0


def main():
    """主函数"""
    # ETF代码列表
    etf_codes = [
        'sh512480',  # 半导体
        'sh516510',  # 云计算
        'sh516160',  # 新能源
        'sh563530',  # 商业航天
        'sh515120',  # 创新药
        'sh512400',  # 有色金属
        'sh515880',  # 通讯设备
        'sh516010',  # 游戏
        'sh562500',  # 机器人
    ]

    print('🔧 开始修复 ETF 成交额数据...')

    total_fixed = 0
    for code in etf_codes:
        print(f'\\n处理 {code}:')
        fixed = fix_etf_amount_data(code)
        total_fixed += fixed

    print(f'\\n✅ 总共修复了 {total_fixed} 条数据')

    # 重新生成 warmup
    if total_fixed > 0:
        print('\\n🔄 重新生成 warmup 数据...')
        import subprocess
        subprocess.run([
            'python3', '-c',
            '''
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
        ])


if __name__ == '__main__':
    main()
