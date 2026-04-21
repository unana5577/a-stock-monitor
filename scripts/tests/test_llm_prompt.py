import json
import os
import requests
from pathlib import Path

def run():
    # 1. Load prompt
    prompt_path = "prompts/stock-daily-v2.txt"
    if not os.path.exists(prompt_path):
        print("Prompt file not found.")
        return
    with open(prompt_path, "r", encoding="utf-8") as f:
        prompt_text = f.read()

    # 2. Load the snapshot we just generated
    snapshot_path = "data/market/ai/snapshot.jsonl"
    if not os.path.exists(snapshot_path):
        print("Snapshot file not found.")
        return
    
    with open(snapshot_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
        if not lines:
            print("Snapshot is empty.")
            return
        snapshot = json.loads(lines[-1])

    # 3. Call Bailian API
    api_key = os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("BAILIAN_API_KEY")
    if not api_key:
        print("Error: DASHSCOPE_API_KEY not set in environment.")
        return

    url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "deepseek-v3", # Use v3 or qwen-plus
        "messages": [
            {"role": "system", "content": prompt_text},
            {"role": "user", "content": f"以下是当前盘中快照数据：\n{json.dumps(snapshot, ensure_ascii=False, indent=2)}"}
        ],
        "temperature": 0.2
    }

    print("Sending request to Bailian (DeepSeek-V3)...")
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        content = data['choices'][0]['message']['content']
        print("\n=== AI 盘中播报 ===")
        print(content)
        print("===================\n")
    except Exception as e:
        print(f"API Error: {e}")
        if 'resp' in locals() and hasattr(resp, 'text'):
            print(resp.text)

if __name__ == "__main__":
    run()
