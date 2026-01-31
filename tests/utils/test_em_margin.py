import requests
import pandas as pd
import json

def fetch_list():
    url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    params = {
        "reportName": "RPTA_WEB_BKJYMXN",
        "columns": "ALL",
        "source": "WEB",
        "client": "WEB",
        "sortColumns": "FIN_BALANCE",
        "sortTypes": "-1",
        "pageNumber": 1,
        "pageSize": 1000,
        "filter": "" 
    }
    try:
        resp = requests.get(url, params=params, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('result') and data['result'].get('data'):
                print(f"Success: Got {len(data['result']['data'])} rows")
                # Find '有色'
                found_code = None
                for row in data['result']['data']:
                    if '有色' in row['BOARD_NAME']:
                        print("Found:", row['BOARD_NAME'], row['BOARD_CODE'])
                        found_code = row['BOARD_CODE']
                
                return found_code if found_code else data['result']['data'][0]['BOARD_CODE']
    except Exception as e:
        print(f"List Exception: {e}")
    return None

def fetch_history(board_code):
    pass
    try:
        resp = requests.get(url, params=params, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('result') and data['result'].get('data'):
                print(f"History Success: Got {len(data['result']['data'])} rows")
                print(data['result']['data'][0])
                print(data['result']['data'][-1])
                return
            else:
                print("History: Empty result (maybe this report doesn't support history)")
                
    except Exception as e:
        print(f"History Exception: {e}")

df = fetch_list()
if df:
    # Pick first code
    code = df
    fetch_history(code)
