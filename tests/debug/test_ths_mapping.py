
import akshare as ak
import pandas as pd
import time

def test_ths_cons():
    print("Testing THS sector constituents...")
    try:
        # 获取同花顺行业列表
        df_summary = ak.stock_board_industry_summary_ths()
        print(f"Total THS Sectors: {len(df_summary)}")
        print("First 5 sectors:", df_summary['板块'].head().tolist())
        
        # 尝试获取第一个行业的成分股
        first_sector = df_summary['板块'].iloc[0]
        print(f"Fetching constituents for {first_sector}...")
        df_cons = ak.stock_board_industry_cons_ths(symbol=first_sector)
        print(f"Constituents count: {len(df_cons)}")
        print("Head:", df_cons.head(2).to_dict('records'))
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_ths_cons()
