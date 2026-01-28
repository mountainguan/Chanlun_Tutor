import requests
import pandas as pd
import json

def test_em_api(report_name):
    url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    params = {
        "reportName": report_name,
        "columns": "ALL",
        "source": "WEB",
        "client": "WEB",
        "sortColumns": "DATE",
        "sortTypes": "-1",
        "pageNumber": 1,
        "pageSize": 50,
        "filter": "" 
    }
    try:
        resp = requests.get(url, params=params, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('result') and data['result'].get('data'):
                print(f"[{report_name}] Success: Got {len(data['result']['data'])} rows")
                print(data['result']['data'][0])
                return True
            else:
                print(f"[{report_name}] Empty result or error: {data.get('message')}")
        else:
            print(f"[{report_name}] HTTP {resp.status_code}")
    except Exception as e:
        print(f"[{report_name}] Exception: {e}")
    return False

# Try probable report names for Industry Margin
candidates = [
    "RPTA_WEB_RZRQ_HY", # 行业融资融券
    "RPTA_RZRQ_HY",
    "RPT_RZRQ_HY",
    "RPT_WEB_RZRQ_BK",
    "RPTA_WEB_RZRQ_BK"
]

for c in candidates:
    test_em_api(c)
