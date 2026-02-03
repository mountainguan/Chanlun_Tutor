import akshare as ak
import pandas as pd

def check_individual_fund_flow():
    print("Checking stock_individual_fund_flow for '600519' (Kweichow Moutai)...")
    try:
        # stock="600519" is a good example
        df = ak.stock_individual_fund_flow(stock="600519", market="sh")
        print("Columns found:")
        for col in df.columns:
            print(f"- {col}")
        
        print("\nHead of data:")
        print(df.head(2))
        
        # Check for keywords
        keywords = ["笔数", "count", "num"]
        found_cols = [col for col in df.columns if any(k in col for k in keywords)]
        
        if found_cols:
            print(f"\nPotential 'count' columns found: {found_cols}")
        else:
            print("\nNo obvious 'count' (笔数) columns found in stock_individual_fund_flow.")
            
    except Exception as e:
        print(f"Error fetching stock_individual_fund_flow: {e}")

def check_stock_fund_flow_big_deal():
    print("\nChecking stock_fund_flow_big_deal...")
    try:
        df = ak.stock_fund_flow_big_deal(stock="600519") 
        print("Columns found:")
        for col in df.columns:
            print(f"- {col}")
        print(df.head(2))
    except Exception as e:
        print(f"Error fetching stock_fund_flow_big_deal: {e}")

def check_stock_fund_flow_individual():
    print("\nChecking stock_fund_flow_individual (alias?)...")
    try:
        df = ak.stock_fund_flow_individual(symbol="600519") # 'symbol' instead of 'stock'?
        print("Columns found:")
        for col in df.columns:
            print(f"- {col}")
    except Exception as e:
        print(f"Error fetching stock_fund_flow_individual: {e}")

def check_stock_fund_flow_big_deal_no_args():
    print("\nChecking stock_fund_flow_big_deal (no args)...")
    try:
        df = ak.stock_fund_flow_big_deal()
        print("Columns found:")
        for col in df.columns:
            print(f"- {col}")
        print(df.head(2))
    except Exception as e:
        print(f"Error fetching stock_fund_flow_big_deal: {e}")

if __name__ == "__main__":
    check_individual_fund_flow()
    check_stock_fund_flow_individual()
    check_stock_fund_flow_big_deal_no_args()
