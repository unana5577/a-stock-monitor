"""数据健康巡检：ETF分时日线完整性、涨跌家数新鲜度、代码有效性"""
import json, os
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DAY = datetime.now().strftime("%Y-%m-%d")

def check_etf_minute():
    """检查所有可见 ETF 今天分时数据是否完整"""
    issues = []
    proxy = load_sector_proxy()
    etfs = {k: v for k, v in proxy.get("variants", {}).get("etf", {}).items()
            if not proxy.get("etf_meta", {}).get(k, {}).get("hidden", False)}
    for name, code in etfs.items():
        path = PROJECT_ROOT / f"data/etf/minute/{code}/{DAY}.jsonl"
        if not path.exists():
            issues.append(f"❌ {name}({code}): 今日分时文件不存在")
            continue
        lines = path.read_text().strip().split("\n")
        if len(lines) < 20:
            issues.append(f"⚠️ {name}({code}): 仅 {len(lines)} 条分时数据")
    return issues

def check_etf_daily():
    """检查 ETF 日线数据是否足够（至少 20 天）"""
    issues = []
    proxy = load_sector_proxy()
    etfs = {k: v for k, v in proxy.get("variants", {}).get("etf", {}).items()
            if not proxy.get("etf_meta", {}).get(k, {}).get("hidden", False)}
    for name, code in etfs.items():
        daily_path = PROJECT_ROOT / f"data/etf/daily/{code}/daily.jsonl"
        if not daily_path.exists():
            issues.append(f"❌ {name}({code}): 日线文件不存在")
            continue
        lines = daily_path.read_text().strip().split("\n")
        if len(lines) < 20:
            issues.append(f"⚠️ {name}({code}): 仅 {len(lines)} 天日线（需≥20）")
    return issues

def check_breadth():
    """涨跌家数数据新鲜度"""
    cache = PROJECT_ROOT / "data/market/minute/breadth-cache.jsonl"
    if not cache.exists() or cache.stat().st_size == 0:
        # 回退检查 breadth-cache.json
        snap = PROJECT_ROOT / "data/market/breadth-cache.json"
        if snap.exists():
            d = json.loads(snap.read_text())
            cached_day = str(d.get("updated", ""))[:10]
            if cached_day != DAY:
                return [f"⚠️ 涨跌家数缓存日期 {cached_day} (非今日)"]
        return ["❌ 涨跌家数无数据"]
    return []

def check_code_validity():
    """检查 sector-proxy.json 中代码前缀是否正确"""
    issues = []
    proxy = load_sector_proxy()
    for name, code in proxy.get("variants", {}).get("etf", {}).items():
        if code.startswith("sh") and len(code) == 8:
            num = code[2:]
            if num.startswith("0") or num.startswith("3"):
                issues.append(f"❌ {name}: {code} (深交所代码用了sh前缀，应为sz)")
        if code.startswith("sz") and len(code) == 8:
            num = code[2:]
            if num.startswith("5") or num.startswith("6"):
                issues.append(f"❌ {name}: {code} (上交所代码用了sz前缀，应为sh)")
    return issues

def load_sector_proxy():
    p = PROJECT_ROOT / "data/sector-proxy.json"
    return json.loads(p.read_text()) if p.exists() else {}

def run():
    dt = datetime.now().strftime("%Y-%m-%d %H:%M")
    results = {
        "time": dt,
        "checks": {
            "etf_minute": check_etf_minute(),
            "etf_daily": check_etf_daily(),
            "breadth": check_breadth(),
            "code_validity": check_code_validity(),
        }
    }
    
    total_issues = sum(len(v) for v in results["checks"].values())
    results["ok"] = total_issues == 0
    results["issue_count"] = total_issues
    
    print(json.dumps(results, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    run()
