import os
import json
import urllib.request
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

def get_api_key():
    api_key = os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("BAILIAN_API_KEY")
    if not api_key:
        env_file = PROJECT_ROOT / ".env"
        if env_file.exists():
            with open(env_file, 'r') as f:
                for line in f:
                    if line.startswith("DASHSCOPE_API_KEY=") or line.startswith("BAILIAN_API_KEY="):
                        api_key = line.strip().split('=', 1)[1]
                        break
    return api_key

API_KEY = get_api_key()

def get_beijing_time():
    """获取当前的北京时间和日期"""
    now = datetime.utcnow()
    bj_time = now.timestamp() + 8 * 3600
    bj_dt = datetime.fromtimestamp(bj_time)
    return bj_dt.strftime("%Y-%m-%d"), bj_dt.strftime("%H:%M")

def load_jsonl_last(filepath: Path) -> dict | None:
    """读取 jsonl 文件的最后一行"""
    if not filepath.exists():
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
            if lines:
                return json.loads(lines[-1])
    except Exception as e:
        print(f"读取文件失败 {filepath}: {e}")
    return None

def call_bailian(prompt: str, user_data: str) -> str:
    """调用阿里云百炼 DeepSeek-V3 模型"""
    if not API_KEY:
        return "【错误】未配置 DASHSCOPE_API_KEY 环境变量，无法调用 AI。"
        
    url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "deepseek-v3",
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_data}
        ],
        "temperature": 0.3
    }
    
    req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            res_body = response.read().decode("utf-8")
            res_json = json.loads(res_body)
            return res_json["choices"][0]["message"]["content"]
    except Exception as e:
        return f"【错误】AI 接口调用失败: {str(e)}"

def run():
    day, asOf = get_beijing_time()
    print(f"\n[{asOf}] 正在执行 M1-ETF-AI-Reporter: 生成盘中板块轮动 AI 解析")
    
    # 1. 读取最新的盘中 ETF 快照
    snapshot_file = PROJECT_ROOT / "data" / "lifecycle" / "intraday" / f"etf_snapshot_{day}.jsonl"
    snapshot_data = load_jsonl_last(snapshot_file)
    
    if not snapshot_data:
        print(f"❌ 找不到当天的 ETF 盘中快照文件: {snapshot_file.relative_to(PROJECT_ROOT)}")
        return
        
    # 2. 读取 Prompt
    prompt_file = PROJECT_ROOT / "prompts" / "etf-rotation-v1.txt"
    if not prompt_file.exists():
        print(f"❌ 找不到 Prompt 文件: {prompt_file.relative_to(PROJECT_ROOT)}")
        return
    system_prompt = prompt_file.read_text(encoding="utf-8")
    
    # 3. 准备喂给 AI 的数据
    user_payload = json.dumps(snapshot_data, ensure_ascii=False, indent=2)
    print(">>> 正在请求百炼 DeepSeek-V3 模型...")
    
    # 4. 调用大模型
    ai_text = call_bailian(system_prompt, user_payload)
    
    # 5. 组装结果并落盘
    report_data = {
        "date": day,
        "asOf": asOf,
        "text": ai_text
    }
    
    out_dir = PROJECT_ROOT / "data" / "market" / "ai"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "etf_report.jsonl"
    
    with open(out_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(report_data, ensure_ascii=False) + "\n")
        
    print(f"✅ AI 解析生成成功！已追加至: {out_file.relative_to(PROJECT_ROOT)}")
    print("-" * 40)
    print(ai_text)
    print("-" * 40)

if __name__ == "__main__":
    run()