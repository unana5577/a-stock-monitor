import akshare as ak
try:
    print("stock:", ak.stock_zh_a_hist_min_em(symbol="sz399001", period='1').tail(1))
except Exception as e:
    print("stock error:", e)
try:
    print("index:", ak.index_zh_a_hist_min_em(symbol="sz399001", period='1').tail(1))
except Exception as e:
    print("index error:", e)
