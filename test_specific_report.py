import requests
import json

def test_specific():
    url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    report = "RPTA_WEB_BKJYMX"
    filter_val = '(BOARD_CODE="478")'
    
    print(f"Verifying {report}...")
    params = {
        "reportName": report,
        "columns": "ALL",
        "pageSize": 5,
        "pageNumber": 1,
        "sortColumns": "TRADE_DATE",
        "sortTypes": "-1",
        "source": "WEB",
        "client": "WEB",
        "filter": filter_val
    }
    
    r = requests.get(url, params=params, timeout=5)
    data = r.json()
    first_item = data["result"]["data"][0]
    print(f"Keys: {list(first_item.keys())}")
    print(f"Sample: {json.dumps(first_item, ensure_ascii=False)}")

if __name__ == "__main__":
    test_specific()
