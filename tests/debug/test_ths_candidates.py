
import akshare as ak
import pandas as pd

def test_func(name, func, **kwargs):
    print(f"\n--- Testing {name} ---")
    try:
        res = func(**kwargs)
        if isinstance(res, pd.DataFrame):
            print(f"Columns: {res.columns.tolist()}")
            print(res.head(2))
        else:
            print(f"Result type: {type(res)}")
            print(res)
    except Exception as e:
        print(f"Error: {e}")

print("Testing available THS functions...")

# 1. stock_board_industry_name_ths
test_func("stock_board_industry_name_ths", ak.stock_board_industry_name_ths)

# 2. stock_board_industry_info_ths
# Likely needs a symbol/code. Let's try to find a valid code from name_ths or summary_ths
summary = ak.stock_board_industry_summary_ths()
if not summary.empty:
    first_sector = summary.iloc[0]['板块']
    print(f"\nUsing sector: {first_sector}")
    
    test_func(f"stock_board_industry_info_ths('{first_sector}')", 
              ak.stock_board_industry_info_ths, symbol=first_sector)

    # Some old versions used different params, but let's try standard 'symbol'
    
    # Check if index_ths returns constituents
    test_func(f"stock_board_industry_index_ths('{first_sector}')", 
              ak.stock_board_industry_index_ths, symbol=first_sector)

