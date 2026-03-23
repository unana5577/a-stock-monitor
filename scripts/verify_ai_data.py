#!/usr/bin/env python3
"""
AI接口数据验证工具 - 时间感知版本
运行时间: 09:31
检查内容: /api/snapshot 可访问性、数据结构完整性
"""

import sys
import json
from datetime import datetime
from pathlib import Path
import urllib.request
import urllib.error


def log_output(message):
    """输出到stdout和日志"""
    print(message)


def test_snapshot_api():
    """测试/api/snapshot接口可访问性"""
    log_output("\n📊 AI实时接口测试")

    url = "http://localhost:8787/api/snapshot"

    try:
        # 设置超时时间
        request = urllib.request.Request(url)
        with urllib.request.urlopen(request, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))

            log_output(f"   ✅ 接口可访问：{url}")

            # 检查数据结构
            required_fields = ['snaps', 'em']

            missing_fields = [field for field in required_fields if field not in data]

            if missing_fields:
                log_output(f"   ⚠️  数据结构不完整，缺少字段：{', '.join(missing_fields)}")
                return False

            # 检查snaps数据
            snaps = data.get('snaps', {})
            if snaps:
                log_output(f"   ✅ snaps数据：{len(snaps)} 个")
            else:
                log_output(f"   ⚠️  snaps数据为空")
                return False

            # 检查em数据
            em = data.get('em', {})
            if em:
                log_output(f"   ✅ em数据：{len(em)} 个")
            else:
                log_output(f"   ⚠️  em数据为空")
                return False

            # 详细数据项检查
            log_output(f"\n📋 数据项明细：")

            log_output(f"\n   大盘指数快照（snaps）：")
            expected_indices = ['sh000001', 'sz399001', 'sz399006', 'sh000688']
            for code in expected_indices:
                if code in snaps:
                    item = snaps[code]
                    if 'price' in item:
                        log_output(f"      ✅ {code}：{item.get('name', 'N/A')} 价格={item.get('price', 'N/A')}")
                    else:
                        log_output(f"      ⚠️  {code}：缺少price字段")
                else:
                    log_output(f"      ❌ {code}：缺失")

            log_output(f"\n   板块快照（em）：")
            expected_sectors = ['90.BK0475', '90.BK0473', '90.BK0474']
            for code in expected_sectors:
                if code in em:
                    item = em[code]
                    if 'price' in item:
                        log_output(f"      ✅ {code}：{item.get('name', 'N/A')} 价格={item.get('price', 'N/A')}")
                    else:
                        log_output(f"      ⚠️  {code}：缺少price字段")
                else:
                    log_output(f"      ❌ {code}：缺失")

            log_output(f"\n   国债期货快照（snaps）：")
            expected_bonds = ['sh000012', 'sz399106']
            for code in expected_bonds:
                if code in snaps:
                    item = snaps[code]
                    if 'price' in item:
                        log_output(f"      ✅ {code}：{item.get('name', 'N/A')} 价格={item.get('price', 'N/A')}")
                    else:
                        log_output(f"      ⚠️  {code}：缺少price字段")
                else:
                    log_output(f"      ❌ {code}：缺失")

            return True

    except urllib.error.URLError as e:
        log_output(f"   ❌ 接口不可访问：{e.reason}")
        return False
    except json.JSONDecodeError as e:
        log_output(f"   ❌ 数据解析失败：{e}")
        return False
    except Exception as e:
        log_output(f"   ❌ 测试失败：{e}")
        return False


def verify_ai_data_source():
    """验证AI数据源"""
    log_output(f"\n📊 AI数据源说明：")
    log_output(f"   - 大盘指数：新浪快照接口")
    log_output(f"   - 板块数据：东财快照接口")
    log_output(f"   - 国债期货：新浪快照接口")
    log_output(f"   - 更新频率：实时拉取（15:00后停止更新）")


def main():
    """主函数"""
    now = datetime.now()
    log_file = Path(f"logs/verify_{now.strftime('%Y-%m-%d')}.log")

    # 创建日志目录
    log_file.parent.mkdir(exist_ok=True)

    # 重定向输出到日志文件
    original_stdout = sys.stdout
    sys.stdout = open(log_file, 'a', encoding='utf-8')

    try:
        # 写入时间戳
        timestamp = now.strftime('%Y-%m-%d %H:%M:%S')
        log_output(f"\n{'='*80}")
        log_output(f"📊 AI接口数据验证报告 - {timestamp}")
        log_output(f"{'='*80}")

        # 验证AI数据源
        verify_ai_data_source()

        # 测试snapshot接口
        api_ok = test_snapshot_api()

        # 汇总结果
        log_output(f"\n{'='*80}")
        if api_ok:
            log_output("✅ AI接口数据验证通过")
        else:
            log_output("⚠️  AI接口存在问题，Task #11列入溯源分析")
        log_output(f"{'='*80}")

    finally:
        sys.stdout.close()
        sys.stdout = original_stdout


if __name__ == "__main__":
    main()
