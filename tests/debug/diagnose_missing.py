
import sys
import os
import pandas as pd
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from utils.national_team import NationalTeamSelector

def diagnose():
    print("Starting diagnosis...")
    selector = NationalTeamSelector()
    
    # Force update to ensure we hit the API
    # Use 'social_security' as default, maybe 'pension' if user switched? 
    # The user screenshot shows "养老金" (Pension) selected in the tab if I could see it, but let's try both or just one.
    # Actually, let's try 'pension' since the user might be looking at that.
    # Or I can check both.
    
    for fund_type in ['social_security', 'pension']:
        print(f"\nChecking {fund_type}...")
        try:
            df, meta = selector.get_selection(fund_type=fund_type, force_update=False) # Use cache first to see what user sees
            
            if df.empty:
                print(f"No data for {fund_type}")
                continue
                
            missing_industry = df[df['同花顺行业'] == '']
            missing_price = df[df['最新价'].isna() | (df['最新价'] == '')]
            
            print(f"Total: {len(df)}")
            print(f"Missing Industry: {len(missing_industry)}")
            if not missing_industry.empty:
                print(missing_industry[['股票代码', '股票简称', '同花顺行业']].head(10))
                
            print(f"Missing Price: {len(missing_price)}")
            if not missing_price.empty:
                print(missing_price[['股票代码', '股票简称', '最新价']].head(10))
                
        except Exception as e:
            print(f"Error checking {fund_type}: {e}")

if __name__ == "__main__":
    diagnose()
