import urllib.request
import json
import sys

def get_gtimg():
    url = "https://qt.gtimg.cn/q=sz399006,sh000688"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        res = urllib.request.urlopen(req).read().decode('gbk')
        print(res)
    except Exception as e:
        print(e)

get_gtimg()
