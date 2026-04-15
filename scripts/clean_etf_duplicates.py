#!/usr/bin/env python3
"""
清理 ETF 数据文件中的重复记录
"""

import json
from pathlib import Path


def clean_etf_file(file_path):
    """清理单个 ETF 文件的重复数据"""
    if not Path(file_path).exists():
        return

    # 读取所有数据
    data = []
    dates_seen = set()
    duplicates = 0

    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                item = json.loads(line.strip())
                date = item.get('date')
                if date:
                    if date in dates_seen:
                        duplicates += 1
                    else:
                        dates_seen.add(date)
                        data.append(item)
            except:
                pass

    if duplicates == 0:
        return 0

    # 按日期排序
    data.sort(key=lambda x: x.get('date', ''))

    # 写回文件
    with open(file_path, 'w', encoding='utf-8') as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')

    return duplicates


def main():
    """清理所有 ETF 数据文件"""
    etf_dir = Path('data/etf_daily')

    print('🔍 检查 ETF 数据文件...')

    etf_files = list(etf_dir.glob('etf_*.jsonl'))
    total_duplicates = 0

    for etf_file in etf_files:
        duplicates = clean_etf_file(etf_file)
        if duplicates > 0:
            print(f'  ✅ {etf_file.name}: 清理了 {duplicates} 条重复数据')
            total_duplicates += duplicates

    if total_duplicates == 0:
        print('  ✅ 没有发现重复数据')
    else:
        print(f'\\n✅ 总共清理了 {total_duplicates} 条重复数据')

        # 重新生成 warmup
        print('\\n🔄 重新生成 warmup 数据...')
        import subprocess
        result = subprocess.run(
            ['python3', '-c', '''
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
'''],
            capture_output=True,
            text=True
        )
        print(result.stdout)


if __name__ == '__main__':
    main()
