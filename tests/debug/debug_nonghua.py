
import sys
import os
import pandas as pd
import akshare as ak
from utils.simulator_logic import calculate_macd

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.sector_analysis import SectorAnalyzer

def debug_nonghua():
    analyzer = SectorAnalyzer()
    sector_name = "农化制品"
    
    print(f"DEBUG: Analyzing sector '{sector_name}'")
    
    # 1. Check Mapping
    ths_name = analyzer._get_ths_name(sector_name)
    print(f"DEBUG: Mapped Name -> '{ths_name}'")
    
    # 2. Fetch Data (Force Update to ignore cache)
    print("DEBUG: Fetching data (Force Update)...")
    
    # Try extending end_date
    import datetime
    tomorrow = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime("%Y%m%d")
    print(f"DEBUG: Using end_date={tomorrow}")
    
    try:
        df = ak.stock_board_industry_index_ths(symbol=ths_name, start_date="20250101", end_date=tomorrow)
    except Exception as e:
        print(f"ERROR: API failed: {e}")
        return
    
    if df is None or df.empty:
        print("ERROR: No data fetched!")
        return
        
    # 3. Inspect Data
    print(f"DEBUG: Fetched {len(df)} rows.")
    print("DEBUG: Columns:", df.columns.tolist())
    print("DEBUG: Last 5 rows:")
    print(df.tail())
    
    # Try fetching Real-time Fund Flow (which might have price)
    print("\nDEBUG: Fetching Real-time Fund Flow...")
    try:
        # symbol="即时" is usually the default or for real-time
        flow_df = ak.stock_fund_flow_industry(symbol="即时")
        print("DEBUG: Flow Columns:", flow_df.columns.tolist())
        
        target = flow_df[flow_df['行业'] == sector_name]
        if not target.empty:
            print("DEBUG: Found target in Flow data:")
            print(target)
            # Check if we have price (usually '最新价' or '指数')
            current_price = target.iloc[0]['行业指数']
            print(f"DEBUG: Current Price: {current_price}")
            
            # Append to history
            import pandas as pd
            new_row = pd.DataFrame([{
                'date': datetime.datetime.now().strftime("%Y-%m-%d"),
                'close': current_price,
                'open': current_price,
                'high': current_price,
                'low': current_price
            }])
            
            # Ensure df has same columns
            # Map Chinese columns from history if needed?
            # No, we already renamed df to English.
            
            # Append
            df = pd.concat([df, new_row], ignore_index=True)
            print("DEBUG: Appended new row.")
            print(df.tail())
            
            # Recalculate MACD
            closes = df['close'].tolist()
            macd = calculate_macd(closes)
            
            print("\nDEBUG: Re-calculated MACD Analysis (Last 5 days):")
            for i in range(-5, 0):
                date = df.iloc[i]['date']
                c = closes[i]
                dif = macd['dif'][i]
                dea = macd['dea'][i]
                hist = macd['hist'][i]
                print(f"Date: {date} | Close: {c:.2f} | DIF: {dif:.3f} | DEA: {dea:.3f} | Hist: {hist:.3f}")
                
            last_dif = macd['dif'][-1]
            last_dea = macd['dea'][-1]
            if last_dif > last_dea:
                print("\nRESULT: GOLD CROSS (金叉) ✅")
            else:
                print("\nRESULT: DEATH CROSS (死叉) ❌")
            
        else:
            print("DEBUG: Target not found in Flow data.")
            
    except Exception as e:
        print(f"ERROR: Flow fetch failed: {e}")

    # Rename for calculation
    df = df.rename(columns={
        '日期': 'date',
        '开盘价': 'open',
        '最高价': 'high',
        '最低价': 'low',
        '收盘价': 'close',
    })
    
    # 4. Calculate MACD
    closes = df['close'].tolist()
    macd = calculate_macd(closes)
    
    print("\nDEBUG: MACD Analysis (Last 5 days):")
    for i in range(-5, 0):
        date = df.iloc[i]['date']
        c = closes[i]
        dif = macd['dif'][i]
        dea = macd['dea'][i]
        hist = macd['hist'][i]
        print(f"Date: {date} | Close: {c:.2f} | DIF: {dif:.3f} | DEA: {dea:.3f} | Hist: {hist:.3f}")
        
    # 5. Check Signal
    last_dif = macd['dif'][-1]
    last_dea = macd['dea'][-1]
    if last_dif > last_dea:
        print("\nRESULT: GOLD CROSS (金叉) ✅")
    else:
        print("\nRESULT: DEATH CROSS (死叉) ❌")

if __name__ == "__main__":
    debug_nonghua()
