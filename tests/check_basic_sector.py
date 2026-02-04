
import akshare as ak
import pandas as pd

try:
    print("Testing ak.stock_board_industry_name_em()...")
    df = ak.stock_board_industry_name_em()
    print("Columns:", df.columns)
    print("First row:", df.iloc[0].to_dict())
    
    if '主力净流入' in df.columns:
        print("FOUND Main Force Inflow in basic list!")
    else:
        print("NO Main Force Inflow in basic list.")

except Exception as e:
    print(f"Error: {e}")
