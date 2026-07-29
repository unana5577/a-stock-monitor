"""容器 + API 健康巡检（从容器内部运行）"""
import json, shutil, urllib.request
from datetime import datetime

def run():
    dt = datetime.now().strftime("%Y-%m-%d %H:%M")
    issues = []

    # 1. API 响应
    try:
        resp = urllib.request.urlopen("http://127.0.0.1:8788/api/snapshot/latest", timeout=10)
        data = json.loads(resp.read())
        if "sentiment" not in data:
            issues.append(f"API /snapshot/latest 返回异常")
    except Exception as e:
        issues.append(f"API 8788 无响应: {str(e)[:60]}")

    # 2. 页面端口
    for port, name in [(8789,"overview"),(8790,"etf"),(8791,"trade"),(8784,"astro"),(8793,"shell")]:
        try:
            resp = urllib.request.urlopen(f"http://a-stock-pages-v2:{port}/", timeout=5)
            if resp.status != 200:
                issues.append(f"页面 {name}:{port} 返回 {resp.status}")
        except:
            issues.append(f"页面 {name}:{port} 无响应")

    # 3. 磁盘 (/app/data)
    try:
        usage = shutil.disk_usage("/app/data")
        pct = (1 - usage.free / usage.total) * 100
        if pct > 80:
            issues.append(f"磁盘使用率 {pct:.0f}%")
    except Exception as e:
        issues.append(f"磁盘检查失败: {str(e)[:50]}")

    result = {
        "time": dt,
        "ok": len(issues) == 0,
        "issue_count": len(issues),
        "issues": issues,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    run()
