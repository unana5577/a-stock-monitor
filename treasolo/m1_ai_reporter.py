import json
import os
import sys
import requests
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

def run():
    asOf = datetime.now().strftime("%H:%M")
    print(f"[{asOf}] 正在调用阿里云百炼 (DeepSeek) 生成盘中播报...")
    
    # 1. Load prompt
    prompt_path = PROJECT_ROOT / "prompts/stock-daily-v2.txt"
    if not prompt_path.exists():
        print(json.dumps({"ok": False, "error": "Prompt file not found"}))
        return
    with open(prompt_path, "r", encoding="utf-8") as f:
        prompt_text = f.read()

    # 2. Load the latest snapshot
    snapshot_path = PROJECT_ROOT / "data/market/ai/snapshot.jsonl"
    if not snapshot_path.exists():
        print(json.dumps({"ok": False, "error": "Snapshot file not found"}))
        return
    
    with open(snapshot_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
        if not lines:
            print(json.dumps({"ok": False, "error": "Snapshot is empty"}))
            return
        snapshot = json.loads(lines[-1])

    # 3. Get API Key
    api_key = os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("BAILIAN_API_KEY")
    if not api_key:
        # Fallback: try to read from .env file directly if not in env vars (for cron jobs)
        env_file = PROJECT_ROOT / ".env"
        if env_file.exists():
            with open(env_file, 'r') as f:
                for line in f:
                    if line.startswith("DASHSCOPE_API_KEY=") or line.startswith("BAILIAN_API_KEY="):
                        api_key = line.strip().split('=', 1)[1]
                        break
                        
    if not api_key:
        print(json.dumps({"ok": False, "error": "API Key not found"}))
        return

    # 4. Call Bailian API
    url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "deepseek-v3",
        "messages": [
            {"role": "system", "content": prompt_text},
            {"role": "user", "content": f"以下是当前盘中快照数据：\n{json.dumps(snapshot, ensure_ascii=False, indent=2)}"}
        ],
        "temperature": 0.2
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=45)
        resp.raise_for_status()
        data = resp.json()
        content = data['choices'][0]['message']['content']
        
        # 5. Save report
        report_record = {
            "asOf": snapshot.get("asOf", asOf),
            "date": snapshot.get("date", datetime.now().strftime("%Y-%m-%d")),
            "content": content
        }
        
        report_path = PROJECT_ROOT / "data/market/ai/report.jsonl"
        with open(report_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(report_record, ensure_ascii=False) + "\n")
            
        print(json.dumps({"ok": True, "asOf": report_record["asOf"]}))
        
    except Exception as e:
        err_msg = str(e)
        if 'resp' in locals() and hasattr(resp, 'text'):
            err_msg += f" | {resp.text}"
        print(json.dumps({"ok": False, "error": err_msg}))

if __name__ == "__main__":
    run()
