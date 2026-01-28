import requests
import pandas as pd

def get_sector_margin_data():
    """
    Fetches EastMoney Sector/Industry Margin Trading Data.
    Report Name: RPTA_WEB_BKJYMXN
    """
    url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    params = {
        'reportName': 'RPTA_WEB_BKJYMXN',
        'columns': 'ALL',
        'source': 'WEB',
        'pageNumber': 1,
        'pageSize': 500, 
        'sortTypes': '-1',
        'sortColumns': 'FIN_BALANCE', # Sort by Financing Balance descending
    }
    
    try:
        resp = requests.get(url, params=params)
        data = resp.json()
        
        if data.get('result') and data['result'].get('data'):
            df = pd.DataFrame(data['result']['data'])
            
            # Map column names for clarity
            column_map = {
                'BOARD_CODE': '板块代码',
                'BOARD_NAME': '板块名称',
                'TRADE_DATE': '交易日期',
                'FIN_BALANCE': '融资余额',
                'FIN_BUY_AMT': '融资买入额',
                'FIN_REPAY_AMT': '融资偿还额',
                'FIN_NETBUY_AMT': '融资净买入',
                'LOAN_BALANCE': '融券余额',
                'LOAN_SELL_VOL': '融券卖出量',
                'LOAN_REPAY_VOL': '融券偿还量',
                'LOAN_NETSELL_AMT': '融券净卖出',
                'BOARD_TYPE': '板块类型'
            }
            
            # Select and rename interesting columns
            cols = [c for c in column_map.keys() if c in df.columns]
            df = df[cols].rename(columns=column_map)
            
            return df
        else:
            print("No data found or API format changed.")
            return None
            
    except Exception as e:
        print(f"Error fetching data: {e}")
        return None

if __name__ == "__main__":
    df = get_sector_margin_data()
    if df is not None:
        print(f"Fetched {len(df)} sector records.")
        # Filter for Industries (005) if mostly relevant, but show top 10 general first
        print(df[['板块名称', '板块类型', '融资余额', '融资买入额']].head(10).to_string())
        
        # Save to CSV for user inspection
        df.to_csv("eastmoney_sector_rzrq.csv", index=False, encoding='utf-8-sig')
        print("Saved to eastmoney_sector_rzrq.csv")
