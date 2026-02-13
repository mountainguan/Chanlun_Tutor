import akshare as ak
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo

print("Checking akshare interfaces...\n")

# 1. Check stock_zh_a_gdhs (Shareholder Count)
print("-" * 50)
print("1. Checking ak.stock_zh_a_gdhs(symbol='600000')...")
try:
    gdhs_df = ak.stock_zh_a_gdhs(symbol="600000")
    print("\nColumns:", gdhs_df.columns.tolist())
    print("\nFirst 5 rows:")
    print(gdhs_df.head())
except Exception as e:
    print(f"Error calling stock_zh_a_gdhs: {e}")


# 2. Check stock_zh_a_hist (Daily Market Data)
print("-" * 50)
print("2. Checking ak.stock_zh_a_hist(symbol='600000', period='daily')...")
try:
    start_date = "20230101"
    end_date = datetime.now(ZoneInfo('Asia/Shanghai')).strftime("%Y%m%d")
    hist_df = ak.stock_zh_a_hist(symbol="600000", period="daily", start_date=start_date, end_date=end_date)
    
    print("\nColumns:", hist_df.columns.tolist())
    
    required_cols = ['成交额', '成交量']
    missing_cols = [col for col in required_cols if col not in hist_df.columns]
    
    if missing_cols:
         print(f"WARNING: Missing columns: {missing_cols}")
    else:
         print("Confirmed: '成交额' and '成交量' are present.")
         
    print("\nFirst 5 rows:")
    print(hist_df.head())
except Exception as e:
    print(f"Error calling stock_zh_a_hist: {e}")

# 3. Check stock_individual_fund_flow (Individual Fund Flow)
print("-" * 50)
print("3. Checking ak.stock_individual_fund_flow(stock='600000', market='sh')...")
try:
    flow_df = ak.stock_individual_fund_flow(stock="600000", market="sh")
    print("\nColumns:", flow_df.columns.tolist())
    print("\nFirst 5 rows:")
    print(flow_df.head())
except Exception as e:
    print(f"Error calling stock_individual_fund_flow: {e}")

print("-" * 50)
print("Done.")
