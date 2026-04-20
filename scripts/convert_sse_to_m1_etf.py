import json
import os

# 配置路径
base_dir = "/Users/una5577/Documents/trae_projects/a-stock-monitor"
old_sse_file = os.path.join(base_dir, "data/minute-20260417-sse.jsonl")
# 我们把它伪装成半导体ETF sh512480 放到 M1 目录下测试
new_etf_file = os.path.join(base_dir, "data/etf/minute/sh512480/2026-04-17.jsonl")

# 确保目录存在
os.makedirs(os.path.dirname(new_etf_file), exist_ok=True)

# 刚才查出来的 4月16日 上证收盘价，作为 4月17日的 pre_close
pre_close = 4055.55

with open(old_sse_file, 'r', encoding='utf-8') as f_in, \
     open(new_etf_file, 'w', encoding='utf-8') as f_out:
    
    for line in f_in:
        line = line.strip()
        if not line:
            continue
            
        try:
            # 解析旧的数组结构 ["2026-04-17 09:30", 4043.38, 4043.38]
            data = json.loads(line)
            time_str = data[0]
            # 提取 HH:MM
            as_of = time_str.split(" ")[1]
            
            # 使用末端价/当前价（数组的第2个元素）作为 price
            price = data[2]
            
            # 计算伪造的涨跌幅
            pct = round((price - pre_close) / pre_close * 100, 2)
            
            # 组装 M1 期望的 ETF 分时 Object 结构
            # time 给一个假的 ISO 时间，amount 和 vol 暂时给 0
            new_obj = {
                "time": f"2026-04-17T{as_of}:00.000000",
                "asOf": as_of,
                "price": price,
                "pct": pct,
                "amount": 0,
                "vol": 0,
                "open": 4043.38, # 09:30 的开盘价
                "high": price,   # 简化处理
                "low": price,    # 简化处理
                "pre_close": pre_close
            }
            
            f_out.write(json.dumps(new_obj) + "\n")
            
        except Exception as e:
            print(f"解析错误: {e}")

print(f"转换完成，已生成测试文件: {new_etf_file}")
