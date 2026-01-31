import requests
import json
import pandas as pd

def get_sector_margin_history(sector_code="478"):
    """
    Fetches historical margin data for a specific sector from EastMoney.
    
    Api found:
    ReportName: RPTA_WEB_BKJYMX
    Filter: (BOARD_CODE="{code}")
    """
    url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    
    # "478" is "有色金属"
    # Note: RPTA_WEB_BKJYMXN (with N) is the daily snapshot
    #       RPTA_WEB_BKJYMX (without N) is the history
    
    params = {
        "reportName": "RPTA_WEB_BKJYMX",
        "columns": "ALL",
        "pageSize": 500, # Get more records for history
        "pageNumber": 1,
        "sortColumns": "TRADE_DATE",
        "sortTypes": "-1",
        "source": "WEB",
        "client": "WEB",
        "filter": f'(BOARD_CODE="{sector_code}")'
    }
    
    print(f"Fetching history for Sector Code: {sector_code}...")
    
    try:
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success") and data.get("result") and data["result"].get("data"):
                items = data["result"]["data"]
                df = pd.DataFrame(items)
                print(f"Successfully fetched {len(df)} records.")
                print("Columns found:", df.columns.tolist())
                print("First 3 records:")
                print(df[["TRADE_DATE", "BOARD_NAME", "FIN_BALANCE", "FIN_BUY_AMT"]].head(3))
                return df
            else:
                print("No data found or API error.")
        else:
            print(f"HTTP Error: {response.status_code}")
            
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    get_sector_margin_history("478")
