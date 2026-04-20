import json
import os
import sys
from datetime import datetime
import time

def get_beijing_time():
    os.environ['TZ'] = 'Asia/Shanghai'
    if hasattr(time, 'tzset'):
        time.tzset()
    return datetime.now()

def is_trading_session():
    now = get_beijing_time()
    current_time = now.strftime('%H:%M')
    
    holidays_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'holidays.json')
    try:
        with open(holidays_file, 'r') as f:
            holidays = json.load(f)
            if now.strftime('%Y-%m-%d') in holidays:
                return False
    except Exception:
        pass
        
    if now.weekday() >= 5:
        return False
        
    if ('09:15' <= current_time <= '11:30') or ('13:00' <= current_time <= '15:05'):
        return True
    return False

def append_jsonl(filepath, record):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            lines = f.readlines()
            for line in lines[-10:]:
                if not line.strip(): continue
                try:
                    obj = json.loads(line)
                    if obj.get('asOf') == record['asOf']:
                        return
                except:
                    pass
    with open(filepath, 'a') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')

def fetch_sectors():
    try:
        import akshare as ak
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"import_failed: {e}"}))
        return
        
    try:
        df = ak.stock_zh_index_spot_sina()
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"fetch_failed: {e}"}))
        return
        
    sectors = [
        {'symbol': 'sz399986', 'name': '中证银行', 'dir': 'bank'},
        {'symbol': 'sz399975', 'name': '证券公司', 'dir': 'broker'},
        {'symbol': 'sz399809', 'name': '保险主题', 'dir': 'insure'}
    ]
    
    now = get_beijing_time()
    day_str = now.strftime('%Y-%m-%d')
    asOf_str = now.strftime('%H:%M')
    
    wrote_list = []
    
    for s in sectors:
        try:
            row = df[df["代码"] == s['symbol']]
            if row.empty: continue
            
            row = row.iloc[0]
            price = float(row["最新价"])
            pct = float(row["涨跌幅"])
            pre_close = float(row["昨收"])
            vol = int(row["成交量"])
            amount = float(row["成交额"])
            
            record = {
                "time": now.strftime('%Y-%m-%d %H:%M:%S'),
                "asOf": asOf_str,
                "price": price,
                "pct": pct,
                "vol": vol,
                "amount": amount,
                "pre_close": pre_close
            }
            
            filepath = os.path.join(os.path.dirname(os.path.dirname(__file__)), f"data/sector/minute/{s['dir']}/{day_str}.jsonl")
            append_jsonl(filepath, record)
            wrote_list.append(s['dir'])
        except Exception as e:
            print(f"Error processing {s['symbol']}: {e}")
            
    print(json.dumps({"ok": True, "day": day_str, "asOf": asOf_str, "wrote": wrote_list}))

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--force':
        fetch_sectors()
    elif is_trading_session():
        fetch_sectors()
    else:
        print(json.dumps({"ok": False, "msg": "Not in trading session"}))
