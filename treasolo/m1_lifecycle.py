import json
import os
import pandas as pd
from pathlib import Path
from datetime import datetime
import sys
import importlib.util

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

# 将 scripts/legacy 加入 sys.path，解决 config 等模块引用问题
sys.path.append(str(PROJECT_ROOT / "scripts" / "legacy"))

# 动态加载根目录下的 sector_lifecycle_module（已移至 scripts/legacy/sector_lifecycle.py）
try:
    spec = importlib.util.spec_from_file_location("sector_lifecycle_module", str(PROJECT_ROOT / "scripts/legacy/sector_lifecycle.py"))
    sector_lifecycle_module = importlib.util.module_from_spec(spec)
    sys.modules["sector_lifecycle_module"] = sector_lifecycle_module
    spec.loader.exec_module(sector_lifecycle_module)
except Exception as e:
    print(f"Error loading sector_lifecycle_module: {e}")
    sys.exit(1)

analyze_sector = sector_lifecycle_module.analyze_sector
select_dynamic_benchmark = sector_lifecycle_module.select_dynamic_benchmark

SYMBOL_TO_NAME = {
    "sh000001": "上证指数",
    "sz399001": "深证成指",
    "sz399006": "创业板指",
    "sh000688": "科创50",
    "sh000300": "沪深300",
    "sh000852": "中证1000",
    "sh511130": "30年国债ETF",
    "sh511260": "10年国债ETF",
    "sh512400": "有色金属ETF",  
    "sh512480": "半导体ETF",
    "sh515120": "创新药ETF",
    "sh515880": "通信ETF",
    "sh516010": "游戏ETF",
    "sh516160": "新能源ETF",
    "sh516510": "云计算ETF",
    "sh562500": "机器人ETF",
    "sh563530": "商业航天ETF"   # 修正：之前写成了数字经济，实际为商业航天
}

def build_lifecycle():
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 正在执行 M1-Lifecycle: 基于 Warmup 数据进行业务分析")
    
    # 1. 读取 warmup 数据
    warmup_file = PROJECT_ROOT / "data/warmup/warmup-60.json"
    if not warmup_file.exists():
        print("❌ warmup 文件不存在，请先运行 m1_warmup.py")
        return 1
        
    with open(warmup_file, "r", encoding="utf-8") as f:
        warmup_data = json.load(f)
        
    history = warmup_data.get("history", {})
    day = warmup_data.get("day", "")
    
    # 将 history 转换为 DataFrame
    df_map = {}
    for symbol, records in history.items():
        if not records: continue
        # 补齐缺失的列
        for r in records:
            if "amount" not in r: r["amount"] = 0
            if "volume" not in r: r["volume"] = 0
            if "close" not in r: r["close"] = r.get("price", 0)
        df = pd.DataFrame(records)
        df_map[symbol] = df
        
    # 2. 准备 benchmark_map (6大宽基指数)
    benchmark_symbols = ["sh000001", "sz399001", "sz399006", "sh000688", "sh000300", "sh000852"]
    benchmark_map = {}
    for sym in benchmark_symbols:
        if sym in df_map:
            name = SYMBOL_TO_NAME.get(sym, sym)
            benchmark_map[name] = df_map[sym]
            
    # 3. 准备 market_amount_df
    # 读取 daily.jsonl, 取每天最后一条记录
    market_amount_file = PROJECT_ROOT / "data/market/daily/amount/daily.jsonl"
    market_daily = {}
    if market_amount_file.exists():
        with open(market_amount_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip(): continue
                try:
                    obj = json.loads(line)
                    date = obj.get("date")
                    # 使用 etf_amount 而不是 market_amount
                    amt = obj.get("etf_amount")
                    if date and amt:
                        market_daily[date] = amt
                except:
                    pass
                    
    market_amount_records = [{"date": k, "amount": v} for k, v in market_daily.items()]
    market_amount_df = pd.DataFrame(market_amount_records) if market_amount_records else None
    if market_amount_df is not None and not market_amount_df.empty:
        market_amount_df = market_amount_df.sort_values("date").reset_index(drop=True)
        
    # 4. 分析每个 ETF 和指数
    results = []
    
    for symbol, df in df_map.items():
        sector_name = SYMBOL_TO_NAME.get(symbol, symbol)
        
        # 动态寻找相关性最高的 benchmark
        # 对于指数自身，benchmark 可以设为上证或深证，也可以设为自身（相关性=1）
        # 这里统一让系统去找
        best_bench_name, best_corr = select_dynamic_benchmark(df, benchmark_map, days=60)
        
        # 如果是指数自己，可能最好用它自己，或者不分析
        # 但为了让所有标的都有生命周期状态，全部扔进 analyze_sector
        try:
            analysis = analyze_sector(
                sector_df=df,
                benchmark_df=benchmark_map.get(best_bench_name) if best_bench_name else None,
                sector_name=sector_name,
                benchmark_name=best_bench_name,
                benchmark_corr=best_corr,
                market_amount_df=market_amount_df,
                history_df=df # 将当前 60 天数据也作为 history_df 传进去用于算分位
            )
            # 添加额外的 symbol 标识供前端绑定
            analysis["symbol"] = symbol
            results.append(analysis)
        except Exception as e:
            print(f"  ⚠️ 分析 {symbol} 失败: {e}")
            
    # 按 _score 降序排序
    results.sort(key=lambda x: x.get("_score", 0), reverse=True)
    
    # 5. 输出保存与打印操作说明
    print("\n--- 操作说明 ---")
    for r in results:
        # 只打印 ETF 的操作说明
        if "ETF" in r.get("ETF名称", ""):
            print(f"[{r.get('ETF名称')}] 阶段: {r.get('阶段信号')} | 动能: {r.get('动能')} | 行为: {r.get('资金行为')} | 建议: {r.get('操作建议')}")
    
    output = {
        "day": day,
        "count": len(results),
        "data": results
    }
    
    out_dir = PROJECT_ROOT / "data/lifecycle"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # 带有日期的文件，方便追溯
    out_file = out_dir / f"lifecycle-{day}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
        
    # 固定名称的文件，方便前端请求
    fixed_file = out_dir / "lifecycle.json"
    with open(fixed_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
        
    print(f"✅ M1-Lifecycle 成功！分析了 {len(results)} 个标的, 已保存至 {out_file.relative_to(PROJECT_ROOT)}")
    return 0

if __name__ == "__main__":
    exit(build_lifecycle())
