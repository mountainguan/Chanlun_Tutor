
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
import time

def test_fetch_stock_history():
    symbol = "600519"
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=10)).strftime("%Y%m%d")
    
    print(f"Fetching history for stock {symbol}...")
    try:
        df = ak.stock_zh_a_hist(symbol=symbol, start_date=start_date, end_date=end_date)
        print("Stock History Head:", df.head())
    except Exception as e:
        print(f"Stock Error: {e}")

def test_fetch_sector_history_retry():
    sector = "半导体"
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=10)).strftime("%Y%m%d")
    
    print(f"Fetching history for sector {sector}...")
    for i in range(3):
        try:
            df = ak.stock_board_industry_hist_em(symbol=sector, start_date=start_date, end_date=end_date)
            print("Sector History Head:", df.head())
            return
        except Exception as e:
            print(f"Sector Error (Attempt {i+1}): {e}")
            time.sleep(2)

if __name__ == "__main__":
    test_fetch_stock_history()
    print("-" * 20)
    test_fetch_sector_history_retry()
