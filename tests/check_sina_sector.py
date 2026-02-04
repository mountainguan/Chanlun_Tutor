
import akshare as ak
import pandas as pd

def check_sina():
    print("Testing Sina Sector Data...")
    try:
        # stock_sector_spot indicator="新浪行业"
        # Note: akshare interface names change. Let's try known ones.
        df = ak.stock_sector_spot(indicator="新浪行业")
        print("Sina Columns:", df.columns)
        print(df.head(3))
    except Exception as e:
        print(f"Sina Error: {e}")

if __name__ == "__main__":
    check_sina()
