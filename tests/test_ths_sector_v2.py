
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta

def test_fetch_ths_sector_history_v2():
    sector_name = "半导体"
    sector_code = "881121"
    
    print(f"Fetching THS history for sector {sector_name}...")
    try:
        # Try with name
        df = ak.stock_board_industry_index_ths(symbol=sector_name, start_date="20240101", end_date="20240110")
        print("THS Sector History (by Name) Head:", df.head())
        return
    except Exception as e:
        print(f"THS Sector Error (Name): {e}")

    try:
        # Try with code if name fails
        df = ak.stock_board_industry_index_ths(symbol=sector_code, start_date="20240101", end_date="20240110")
        print("THS Sector History (by Code) Head:", df.head())
    except Exception as e:
        print(f"THS Sector Error (Code): {e}")

if __name__ == "__main__":
    test_fetch_ths_sector_history_v2()
