import akshare as ak
import pandas as pd

def check_structure():
    print("Checking 'stock_individual_fund_flow' columns for '600000'...")
    try:
        df = ak.stock_individual_fund_flow(stock="600000", market="sh")
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', 1000)
        
        print("\nAll Columns:")
        print(df.columns.tolist())
        
        print("\nFirst row data:")
        if not df.empty:
            print(df.iloc[0])
            
        # Check for keywords related to 'Count' / '笔数'
        count_keywords = ['笔数', 'count', 'num']
        found = [col for col in df.columns if any(k in col for k in count_keywords)]
        
        if found:
            print(f"\n[SUCCESS] Found columns related to counts: {found}")
        else:
            print("\n[INFO] No columns related to '笔数' (counts) found in stock_individual_fund_flow.")
            print("The available data is restricted to Net Amount (净额) and Net Ratio (净占比).")

    except Exception as e:
        print(f"Error: {e}")

def check_other_candidate():
    print("\nChecking 'stock_fund_flow_big_deal' (Real-time big deals)...")
    try:
        # This interface usually returns a streaming list of big deals for the market or stock
        # It does not provide daily summary counts directly.
        df_big = ak.stock_fund_flow_big_deal()
        print("Columns in stock_fund_flow_big_deal:")
        print(df_big.columns.tolist())
        print("Note: This returns individual transactions, not daily summaries.")
    except Exception as e:
        print(f"Error checking big deal: {e}")

if __name__ == "__main__":
    check_structure()
    check_other_candidate()
