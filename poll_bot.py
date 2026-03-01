import requests
import json
import time
import os

APP_ID = "cli_a910d0572478dcc9"
APP_SECRET = "59DaUApsr84YMLENYJ1osf6r5KNGmSDt"
APP_TOKEN = "V2q5bpviVaLIqisaQmzcegHqnye"
TABLE_ID = "tblmhrdBW1Y3VN28"  # 根据之前的测试结果

def get_token():
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    res = requests.post(url, json={"app_id": APP_ID, "app_secret": APP_SECRET})
    return res.json().get("tenant_access_token")

def list_records(token, page_token=None):
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_ID}/records"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"page_size": 20}
    if page_token:
        params["page_token"] = page_token
    
    try:
        res = requests.get(url, headers=headers, params=params)
        return res.json()
    except Exception as e:
        print(f"[ERROR] List records: {e}")
        return None

def main():
    print(f"Starting Polling Bot on Table: {APP_TOKEN} / {TABLE_ID}")
    last_processed_ids = set()
    
    # 第一次运行先加载现有数据，避免重复处理
    token = get_token()
    if token:
        res = list_records(token)
        if res and res.get("code") == 0:
            items = res.get("data", {}).get("items", [])
            for item in items:
                last_processed_ids.add(item.get("record_id"))
            print(f"Loaded {len(last_processed_ids)} existing records.")
    
    while True:
        try:
            # 1. 获取 Token (Token 有效期 2 小时，这里简单起见每次循环检查，实际可优化)
            token = get_token()
            if not token:
                print("Failed to get token, retrying in 5s...")
                time.sleep(5)
                continue

            # 2. 查询最新记录
            res = list_records(token)
            if res and res.get("code") == 0:
                items = res.get("data", {}).get("items", [])
                
                # 3. 检查是否有新记录
                for item in items:
                    record_id = item.get("record_id")
                    if record_id not in last_processed_ids:
                        fields = item.get("fields", {})
                        print(f"[NEW RECORD] {json.dumps(fields, ensure_ascii=False)}")
                        
                        # 在这里处理新记录逻辑，比如发消息通知你
                        # process_new_record(item)
                        
                        last_processed_ids.add(record_id)
            
            # 4. 休眠
            time.sleep(5)
            
        except KeyboardInterrupt:
            print("Stopping...")
            break
        except Exception as e:
            print(f"[ERROR] Loop exception: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
