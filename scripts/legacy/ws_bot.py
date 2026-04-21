import lark_oapi as lark
from lark_oapi.api.im.v1 import *
import lark_oapi.ws as lark_ws
import logging
import asyncio
import os
import json
import requests

# 配置
APP_ID = "cli_a910d0572478dcc9"
APP_SECRET = "59DaUApsr84YMLENYJ1osf6r5KNGmSDt"

# 客户端
client = lark.Client.builder() \
    .app_id(APP_ID) \
    .app_secret(APP_SECRET) \
    .log_level(lark.LogLevel.DEBUG) \
    .build()

def get_token():
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    res = requests.post(url, json={"app_id": APP_ID, "app_secret": APP_SECRET})
    return res.json().get("tenant_access_token")

def create_bitable(token):
    url = "https://open.feishu.cn/open-apis/bitable/v1/apps"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    data = {
        "name": "Stock Monitor Control Panel",
        "folder_token": ""  # 空字符串会在根目录创建
    }
    try:
        res = requests.post(url, headers=headers, json=data)
        res_json = res.json()
        if res_json.get("code") == 0:
            app_token = res_json.get("data", {}).get("app", {}).get("app_token")
            name = res_json.get("data", {}).get("app", {}).get("name")
            return app_token, name
        else:
            print(f"[ERROR] Create bitable failed: {res_json}")
            return None, None
    except Exception as e:
        print(f"[ERROR] Create bitable exception: {e}")
        return None, None

def do_p2p_message_handler(data: lark_ws.P2PMessageEvent):
    content = data.event.message.content
    print(f"[RECV] {content}")
    
    # 解析消息内容
    try:
        msg_obj = json.loads(content)
        msg_text = msg_obj.get("text", "")
    except:
        msg_text = content

    reply_text = f"收到指令：{msg_text}"
    
    # 如果是创建表格指令
    if "创建表格" in msg_text or "create table" in msg_text.lower():
        token = get_token()
        if token:
            app_token, name = create_bitable(token)
            if app_token:
                reply_text = f"✅ 表格已创建！\n名称：{name}\nApp Token：{app_token}\n请去云文档查看。"
            else:
                reply_text = "❌ 表格创建失败，请检查权限。"
        else:
            reply_text = "❌ 获取 Token 失败。"

    # 回复消息
    request = CreateMessageRequest.builder() \
        .receive_id_type("open_id") \
        .request_body(CreateMessageRequestBody.builder() \
            .receive_id(data.event.sender.sender_id.open_id) \
            .msg_type("text") \
            .content(json.dumps({"text": reply_text})) \
            .build()) \
        .build()
        
    resp = client.im.v1.message.create(request)
    if not resp.success():
        print(f"[ERROR] send failed: {resp.code}, {resp.msg}")

def main():
    print("Connecting to Lark WebSocket...")
    ws_client = lark_ws.Client(APP_ID, APP_SECRET, event_handler=do_p2p_message_handler, log_level=lark.LogLevel.DEBUG)
    ws_client.start()

if __name__ == "__main__":
    main()
