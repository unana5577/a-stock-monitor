#!/usr/bin/env python3
"""
问题诊断助手 - 快速定位问题根因

功能：
1. 根据症状类型，引导执行诊断步骤
2. 自动分析检查结果
3. 生成诊断报告

使用：
  python scripts/diagnose_issue.py
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# 项目根目录
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# 诊断流程配置
DIAGNOSIS_FLOWS = {
    "1": {
        "name": "前端不显示/显示错误",
        "steps": [
            {
                "name": "测试Python脚本",
                "command": "python3 fetch_sector_data.py lifecycle 60",
                "description": "验证数据层和业务层是否正常",
                "analysis": "check_python_output"
            },
            {
                "name": "测试HTTP接口",
                "command": "curl -s 'http://127.0.0.1:8787/api/sector/lifecycle?days=60'",
                "description": "验证API接口是否正常",
                "analysis": "check_http_output"
            },
            {
                "name": "查看服务器日志",
                "command": "tail -30 server.log",
                "description": "查找验证失败的关键日志",
                "interactive": True,
                "prompt": "请在日志中查找包含'验证失败'或'lifecycle'的行，然后输入关键信息"
            }
        ],
        "conclusions": {
            "normal_normal": "Layer 3 (API接口层) - Python和接口都正常，可能是前端问题",
            "normal_empty": "Layer 3 (API接口层) - Python正常但接口返回空，验证逻辑问题",
            "abnormal_any": "Layer 1/2 (数据/业务层) - Python脚本本身就异常"
        }
    },
    "2": {
        "name": "API接口返回空/错误",
        "steps": [
            {
                "name": "检查warmup文件",
                "command": "cat data/sector-history-warmup-60.json | jq '.day'",
                "description": "查看warmup文件的日期",
                "analysis": "check_warmup_date"
            },
            {
                "name": "测试Python脚本",
                "command": "python3 fetch_sector_data.py lifecycle 60",
                "description": "验证Python层是否正常",
                "analysis": "check_python_output"
            },
            {
                "name": "测试HTTP接口",
                "command": "curl -s 'http://127.0.0.1:8787/api/sector/lifecycle?days=60' | jq",
                "description": "查看HTTP接口返回详情",
                "analysis": "check_http_detailed"
            }
        ],
        "conclusions": {
            "stale_warmup": "Layer 1 (数据层) - warmup数据过期",
            "python_ok_http_empty": "Layer 3 (API层) - 验证逻辑问题",
            "python_abnormal": "Layer 1/2 (数据/业务层) - Python脚本异常"
        }
    },
    "3": {
        "name": "数据计算结果不对",
        "steps": [
            {
                "name": "检查原始数据",
                "command": "tail -3 data/etf_daily/etf_512480.jsonl | jq",
                "description": "查看原始日线数据",
                "interactive": True,
                "prompt": "请检查close、amount等字段值是否正常"
            },
            {
                "name": "查看warmup数据",
                "command": "cat data/sector-history-warmup-60.json | jq '.history | keys | .[0:3]'",
                "description": "查看warmup中的板块数据",
                "interactive": True,
                "prompt": "请检查数据结构和最新日期"
            },
            {
                "name": "测试公式计算",
                "command": "python3 -c \"from fetch_sector_data import get_sector_lifecycle; import json; print(json.dumps(get_sector_lifecycle([], 60)['items'][0]['指标数据'], indent=2, ensure_ascii=False))\"",
                "description": "查看指标计算结果",
                "interactive": True,
                "prompt": "请检查Alpha、MA、Bias等指标值"
            }
        ],
        "conclusions": {
            "data_abnormal": "Layer 1 (数据层) - 原始数据有问题",
            "formula_abnormal": "Layer 2 (业务层) - 公式计算有问题"
        }
    },
    "4": {
        "name": "数据过期/缺失",
        "steps": [
            {
                "name": "检查warmup日期",
                "command": "cat data/sector-history-warmup-60.json | jq '.day'",
                "description": "查看warmup文件日期",
                "analysis": "check_warmup_date"
            },
            {
                "name": "查看定时任务",
                "command": "crontab -l | grep -E 'data_maintenance|warmup'",
                "description": "检查数据更新定时任务",
                "interactive": True,
                "prompt": "请确认是否有定时任务配置"
            },
            {
                "name": "查看更新日志",
                "command": "tail -50 logs/data_daily.log | tail -20",
                "description": "查看数据维护日志",
                "interactive": True,
                "prompt": "请查找最新的更新记录和错误信息"
            }
        ],
        "conclusions": {
            "no_crontab": "调度层 - 定时任务未配置",
            "update_failed": "Layer 1 (数据层) - 数据更新失败",
            "update_delayed": "Layer 1 (数据层) - 数据更新延迟"
        }
    }
}


def log(msg, emoji="📋"):
    """统一日志输出"""
    print(f"{emoji} {msg}")


def execute_command(cmd):
    """执行命令并返回结果"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=ROOT
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return None, "命令执行超时", -1
    except Exception as e:
        return None, str(e), -1


def check_python_output(stdout, stderr):
    """分析Python脚本输出"""
    if not stdout:
        return "abnormal", "Python脚本无输出"

    try:
        data = json.loads(stdout)
        if "items" in data:
            if len(data.get("items", [])) > 0:
                day = data.get("day", "未知")
                count = len(data.get("items", []))
                return "normal", f"返回正常数据 (日期:{day}, 板块数:{count})"
            else:
                return "empty", f"返回空数据 (日期:{data.get('day', '未知')})"
        else:
            return "abnormal", "返回数据格式异常"
    except json.JSONDecodeError:
        if "error" in stdout.lower() or "exception" in stdout.lower():
            return "abnormal", "Python脚本执行出错"
        return "normal", "返回非JSON格式但可能有数据"


def check_http_output(stdout, stderr):
    """分析HTTP接口输出"""
    if not stdout:
        return "empty", "HTTP接口无输出"

    try:
        data = json.loads(stdout)
        if "items" in data:
            if len(data.get("items", [])) > 0:
                return "normal", f"HTTP返回数据 (日期:{data.get('day')}, 板块数:{len(data['items'])})"
            else:
                reason = data.get("reason", "未知")
                return "empty", f"HTTP返回空数据 (原因:{reason})"
        else:
            return "abnormal", "HTTP返回格式异常"
    except json.JSONDecodeError:
        return "abnormal", "HTTP返回非JSON数据"


def check_http_detailed(stdout, stderr):
    """详细分析HTTP接口输出"""
    return check_http_output(stdout, stderr)


def check_warmup_date(stdout, stderr):
    """检查warmup日期"""
    if not stdout:
        return "abnormal", "无法读取warmup文件"

    date_str = stdout.strip().strip('"')
    today = datetime.now().strftime("%Y-%m-%d")

    # 简单判断：如果日期是今天或昨天，都算正常
    # 具体逻辑需要结合交易时间判断
    return "normal", f"warmup日期: {date_str}"


def analyze_step(step, stdout, stderr, returncode):
    """分析单步检查结果"""
    if step.get("interactive"):
        return "interactive", "用户观察"

    analysis_func = step.get("analysis")
    if analysis_func:
        func = globals().get(analysis_func)
        if func:
            return func(stdout, stderr)

    # 默认分析
    if returncode != 0:
        return "abnormal", f"命令执行失败 (返回码:{returncode})"
    elif stderr and "error" in stderr.lower():
        return "abnormal", f"执行出错: {stderr[:100]}"
    else:
        return "normal", "命令执行成功"


def run_diagnosis(flow_key):
    """执行诊断流程"""
    flow = DIAGNOSIS_FLOWS[flow_key]
    log(f"开始诊断：{flow['name']}", "🔍")

    results = []
    step_num = 0

    for step in flow["steps"]:
        step_num += 1
        print(f"\n{'='*60}")
        log(f"步骤 {step_num}/{len(flow['steps'])}：{step['name']}", "➡️")
        print(f"描述：{step['description']}")
        print(f"命令：{step['command']}")

        if step.get("interactive"):
            print(f"\n💡 {step.get('prompt', '请手动执行命令并观察结果')}")
            user_input = input("\n请输入观察到的关键信息（或按Enter跳过）：").strip()
            results.append({
                "step": step["name"],
                "status": "interactive",
                "output": user_input or "用户未输入"
            })
            continue

        # 自动执行命令
        choice = input("\n是否自动执行？(y/n，默认y): ").strip().lower()
        if choice and choice != 'y':
            output = input("请手动复制命令执行结果：").strip()
            status = input("结果状态 (normal/abnormal/empty，默认normal): ").strip().lower() or "normal"
            results.append({
                "step": step["name"],
                "status": status,
                "output": output[:500]  # 限制长度
            })
            continue

        stdout, stderr, returncode = execute_command(step["command"])

        status, message = analyze_step(step, stdout, stderr, returncode)
        log(f"结果：{message}", "✅" if status == "normal" else "❌")

        if stdout and len(stdout) < 500:
            print(f"输出：\n{stdout}")

        results.append({
            "step": step["name"],
            "status": status,
            "output": (stdout or stderr)[:500] if (stdout or stderr) else "无输出"
        })

    return results


def generate_conclusion(flow_key, results):
    """生成诊断结论"""
    flow = DIAGNOSIS_FLOWS[flow_key]

    print(f"\n{'='*60}")
    log("诊断分析", "📊")

    # 根据结果组合生成结论
    if flow_key == "1":  # 前端不显示
        if results[0]["status"] == "normal" and results[1]["status"] == "empty":
            conclusion = flow["conclusions"]["normal_empty"]
            next_steps = [
                "1. 检查 server.js 中的 /api/sector/lifecycle 验证逻辑",
                "2. 查找关键词：latestTradingDay、交易日验证",
                "3. 确认验证逻辑是否正确使用了warmup日期"
            ]
        elif results[0]["status"] == "normal":
            conclusion = flow["conclusions"]["normal_normal"]
            next_steps = [
                "1. 检查前端Vue组件是否正确绑定API",
                "2. 查看浏览器控制台是否有错误",
                "3. 确认前端路由配置"
            ]
        else:
            conclusion = flow["conclusions"]["abnormal_any"]
            next_steps = [
                "1. 检查数据获取接口是否正常",
                "2. 查看 fetch_sector_data.py 的错误日志",
                "3. 验证数据源（AkShare、新浪等）是否可用"
            ]

    elif flow_key == "2":  # API返回空
        if "stale" in results[0].get("output", ""):
            conclusion = flow["conclusions"]["stale_warmup"]
            next_steps = [
                "1. 检查数据更新定时任务",
                "2. 手动运行：python3 data_maintenance.py",
                "3. 确认warmup生成流程"
            ]
        elif results[1]["status"] == "normal" and results[2]["status"] == "empty":
            conclusion = flow["conclusions"]["python_ok_http_empty"]
            next_steps = [
                "1. 检查 server.js 的验证逻辑",
                "2. 查看 server.log 中的验证失败日志",
                "3. 确认 latestTradingDay() 的使用是否正确"
            ]
        else:
            conclusion = flow["conclusions"]["python_abnormal"]
            next_steps = [
                "1. 检查 fetch_sector_data.py 错误",
                "2. 验证warmup文件完整性",
                "3. 检查数据依赖（指数日线等）"
            ]

    elif flow_key == "3":  # 计算不对
        if "异常" in results[0].get("output", ""):
            conclusion = flow["conclusions"]["data_abnormal"]
            next_steps = [
                "1. 检查数据源接口",
                "2. 验证数据解析逻辑",
                "3. 查看数据完整性"
            ]
        else:
            conclusion = flow["conclusions"]["formula_abnormal"]
            next_steps = [
                "1. 检查公式计算逻辑（sector_lifecycle.py）",
                "2. 验证边界条件（除零、空值等）",
                "3. 查看单元测试是否通过"
            ]

    elif flow_key == "4":  # 数据过期
        if "no" in results[1].get("output", "").lower():
            conclusion = flow["conclusions"]["no_crontab"]
            next_steps = [
                "1. 配置crontab定时任务",
                "2. 参考文档：docs/agents/schedule.md",
                "3. 测试定时任务执行"
            ]
        elif "失败" in results[2].get("output", ""):
            conclusion = flow["conclusions"]["update_failed"]
            next_steps = [
                "1. 检查接口可用性",
                "2. 查看错误日志",
                "3. 手动运行数据更新脚本"
            ]
        else:
            conclusion = flow["conclusions"]["update_delayed"]
            next_steps = [
                "1. 确认当前时间（是否到15:30）",
                "2. 检查warmup更新时间",
                "3. 等待定时任务执行"
            ]

    print(f"\n📍 边界定位：{conclusion}")
    print(f"\n🎯 下一步检查：")
    for step in next_steps:
        print(f"   {step}")

    return conclusion, next_steps


def save_report(flow_key, results, conclusion, next_steps):
    """保存诊断报告"""
    flow = DIAGNOSIS_FLOWS[flow_key]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = ROOT / "docs" / "diagnoses"
    report_dir.mkdir(exist_ok=True)

    report_file = report_dir / f"{timestamp}_{flow['name'].replace('/', '_')}.md"

    report_content = f"""# 诊断报告：{flow['name']}

**时间**：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**症状类型**：{flow['name']}

## 检查步骤

"""

    for i, result in enumerate(results, 1):
        status_emoji = "✅" if result["status"] == "normal" else "❌" if result["status"] == "abnormal" else "⚠️"
        report_content += f"\n### {i}. {result['step']} {status_emoji}\n\n"
        report_content += f"**状态**：{result['status']}\n\n"
        if result.get("output"):
            report_content += f"**输出**：\n```\n{result['output']}\n```\n\n"

    report_content += f"""
## 诊断结论

**边界定位**：{conclusion}

## 下一步检查

"""
    for step in next_steps:
        report_content += f"- {step}\n"

    report_content += f"\n---\n\n*本报告由 diagnose_issue.py 自动生成*"

    report_file.write_text(report_content, encoding='utf-8')
    log(f"诊断报告已保存：{report_file.relative_to(ROOT)}", "💾")


def main():
    print("\n" + "="*60)
    print("🔍 问题诊断助手")
    print("="*60 + "\n")

    print("请选择症状类型：")
    for key, flow in DIAGNOSIS_FLOWS.items():
        print(f"[{key}] {flow['name']}")

    print("\n[0] 退出")
    choice = input("\n请输入选项：").strip()

    if not choice or choice == "0":
        print("退出诊断")
        return

    if choice not in DIAGNOSIS_FLOWS:
        log("无效选项", "❌")
        return

    # 执行诊断
    results = run_diagnosis(choice)

    # 生成结论
    conclusion, next_steps = generate_conclusion(choice, results)

    # 保存报告
    save_report(choice, results, conclusion, next_steps)

    print(f"\n{'='*60}")
    log("诊断完成", "✅")


if __name__ == "__main__":
    main()
