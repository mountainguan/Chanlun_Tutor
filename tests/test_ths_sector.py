
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
import time

def test_fetch_ths_sector_history():
    sector = "半导体及元件"  # THS name might be different
    print(f"Fetching THS history for sector {sector}...")
    try:
        # THS history might need specific params
        df = ak.stock_board_industry_index_ths(symbol=sector, start_date="20240101", end_date="20240110")
        print("THS Sector History Head:", df.head())
    except Exception as e:
        print(f"THS Sector Error: {e}")
        
    # Try getting list of THS industries first
    try:
        df_list = ak.stock_board_industry_name_ths()
        print("THS Industry List Head:", df_list.head())
        # Check if '半导体' is in it
        print("Contains '半导体':", df_list[df_list['name'].str.contains('半导体')])
    except Exception as e:
        print(f"THS List Error: {e}")

if __name__ == "__main__":
    test_fetch_ths_sector_history()
