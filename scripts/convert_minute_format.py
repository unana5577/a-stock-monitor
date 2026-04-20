import json
import os
import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--old-file", required=True, help="旧的分钟线文件，如 minute-20260417-sse.jsonl")
    parser.add_argument("--symbol", required=True, help="目标代码，如 sh000001")
    parser.add_argument("--day", required=True, help="日期，如 2026-04-17")
    parser.add_argument("--pre-close", type=float, required=True, help="昨收价")
    args = parser.parse_args()

    base_dir = "/Users/una5577/Documents/trae_projects/a-stock-monitor"
    old_file = os.path.join(base_dir, "data", args.old_file)
    
    # 决定输出目录（指数放 index/minute，ETF放 etf/minute）
    if args.symbol.startswith("sh0") or args.symbol.startswith("sz399"):
        out_dir = os.path.join(base_dir, f"data/index/minute/{args.symbol}")
    else:
        out_dir = os.path.join(base_dir, f"data/etf/minute/{args.symbol}")
        
    new_file = os.path.join(out_dir, f"{args.day}.jsonl")

    os.makedirs(out_dir, exist_ok=True)

    count = 0
    with open(old_file, 'r', encoding='utf-8') as f_in, \
         open(new_file, 'w', encoding='utf-8') as f_out:
        
        for line in f_in:
            line = line.strip()
            if not line:
                continue
                
            try:
                # 解析 ["2026-04-17 09:30", 4043.38, 4043.38]
                data = json.loads(line)
                time_str = data[0]
                as_of = time_str.split(" ")[1]
                
                # [2] 是该分钟的收盘价/末端价
                price = float(data[2])
                
                pct = round((price - args.pre_close) / args.pre_close * 100, 2)
                
                # M1 的指数分时其实只需要 {"time": iso, "asOf": HH:MM, "price": num}
                # 但这里我们为了兼容性，把全字段（包括 pct, pre_close）都带上
                new_obj = {
                    "time": f"{args.day}T{as_of}:00.000000",
                    "asOf": as_of,
                    "price": price,
                    "pct": pct,
                    "amount": 0,
                    "vol": 0,
                    "open": float(data[1]), 
                    "high": price,
                    "low": price,
                    "pre_close": args.pre_close
                }
                
                f_out.write(json.dumps(new_obj) + "\n")
                count += 1
                
            except Exception as e:
                print(f"解析错误: {e}")

    print(f"转换完成! 从 {args.old_file} -> {new_file}")
    print(f"共写入 {count} 行，昨收基准: {args.pre_close}")

if __name__ == "__main__":
    main()
