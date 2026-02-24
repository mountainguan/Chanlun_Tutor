import akshare as ak
import pandas as pd
import datetime

print("Testing akshare for Central Huijin data...")

try:
    # Attempt 1: stock_report_fund_hold with '中央汇金'
    print("Attempt 1: stock_report_fund_hold(symbol='中央汇金')")
    df = ak.stock_report_fund_hold(symbol='中央汇金', date='20240930') # Try 20240930 first as 2025 might be future/not ready
    if not df.empty:
        print("Success!")
        print(df.head())
    else:
        print("Empty DataFrame")
except Exception as e:
    print(f"Failed: {e}")

try:
    # Attempt 2: stock_report_fund_hold with '国家队'
    print("\nAttempt 2: stock_report_fund_hold(symbol='国家队')")
    df = ak.stock_report_fund_hold(symbol='国家队', date='20240930')
    if not df.empty:
        print("Success!")
        print(df.head())
    else:
        print("Empty DataFrame")
except Exception as e:
    print(f"Failed: {e}")

# If specific symbols fail, we might need to iterate over stocks and check shareholders.
# Let's check if we can get shareholders for one stock to see the format.
try:
    print("\nCheck shareholders for 600036 (China Merchants Bank)")
    df = ak.stock_gdfx_free_top_10_em(symbol='600036', date='20240930')
    print(df)
except Exception as e:
    print(f"Failed to get shareholders: {e}")
