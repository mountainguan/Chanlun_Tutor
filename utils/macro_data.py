import pandas as pd
import requests
import os
import time
from io import StringIO

# Base path setup
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_FILE = os.path.join(BASE_DIR, 'data', 'macro_rmb_deposit_cache.csv')
RATIO_CACHE_FILE = os.path.join(BASE_DIR, 'data', 'macro_deposit_ratio_cache.csv')

URL = "https://data.10jqka.com.cn/macro/rmb/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36 Edg/144.0.0.0"
}

def fetch_rmb_deposit_data(force_update=False):
    """
    Fetches RMB deposit macro data from 10jqka and caches it.
    Returns a DataFrame.
    
    Data is cached in: d:\缠论小应用\data\macro_rmb_deposit_cache.csv
    Cache validity: Tuned for monthly updates.
    """
    
    # Check cache freshness
    if not force_update and os.path.exists(CACHE_FILE):
        mtime = os.path.getmtime(CACHE_FILE)
        # If file is less than 1 day old, use cache (simple logic for now)
        if time.time() - mtime < 24 * 3600:
            try:
                print(f"Loading data from cache: {CACHE_FILE}")
                return pd.read_csv(CACHE_FILE)
            except Exception as e:
                print(f"Error reading cache, refetching: {e}")

    try:
        print(f"Fetching data from {URL}...")
        response = requests.get(URL, headers=HEADERS)
        response.encoding = 'gbk'

        if response.status_code != 200:
            print(f"Failed to fetch data: {response.status_code}")
            return None
        
        # Use StringIO to avoid FutureWarning
        html_io = StringIO(response.text)
        dfs = pd.read_html(html_io)
        
        if not dfs:
            print("No tables found in response.")
            return None
            
        # Find the correct table
        target_df = None
        for df in dfs:
            cols_str = str(df.columns)
            if "新增存款" in cols_str:
                target_df = df
                break
        
        if target_df is None:
            target_df = dfs[0]

        # Flatten columns if MultiIndex
        if isinstance(target_df.columns, pd.MultiIndex):
            new_cols = []
            for col in target_df.columns:
                # col is a tuple ('月份', '月份') or ('新增存款(亿元)', '数量')
                c0 = col[0]
                c1 = col[1]
                if '月份' in c0:
                    new_cols.append('月份')
                else:
                    # Combine, e.g., "新增存款(亿元)_数量"
                    new_cols.append(f"{c0}_{c1}")
            target_df.columns = new_cols

        # Clean "月份" column if needed (sometimes it has spaces)
        if '月份' in target_df.columns:
             target_df['月份'] = target_df['月份'].astype(str).str.strip()

        # Save to cache
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        target_df.to_csv(CACHE_FILE, index=False, encoding='utf-8-sig')
        print(f"Data saved to {CACHE_FILE}")
        
        return target_df

    except Exception as e:
        print(f"Error fetching RMB deposit data: {e}")
        # Try to read legacy cache if fetch fails
        if os.path.exists(CACHE_FILE):
             print("Falling back to existing cache.")
             return pd.read_csv(CACHE_FILE)
        return None

def get_savings_mv_ratio_data(force_update=False):
    """
    Calculates the ratio between Deposits (Household, Corporate, Total) and A-share Total Market Value.
    Anchor: 2026-02-03 Shanghai Index 4067.7, Total A-share MV ~92.29 Trillion RMB.
    """
    # Check cache
    if not force_update and os.path.exists(RATIO_CACHE_FILE):
        try:
            return pd.read_csv(RATIO_CACHE_FILE)
        except Exception as e:
            print(f"Error reading ratio cache: {e}")

    deposit_df = fetch_rmb_deposit_data(force_update=force_update)
    if deposit_df is None or deposit_df.empty:
        return None
    
    # Load Index Data
    index_cache_path = os.path.join(BASE_DIR, 'data', 'index_history_cache.csv')
    if not os.path.exists(index_cache_path):
        return None
        
    try:
        index_df = pd.read_csv(index_cache_path)
        index_df['date'] = pd.to_datetime(index_df['date'])
        # Filter for Shanghai Index
        sh_index = index_df[index_df['code'] == 'sh000001'].copy()
        if sh_index.empty:
            return None
        sh_index = sh_index.sort_values('date')
        
        # Savings Data Month-End Dates
        results = []
        
        # Anchor point (2026-02-03)
        ANCHOR_MV = 922898.29 # 亿元
        ANCHOR_INDEX = 4067.738
        SCALE_FACTOR = ANCHOR_MV / ANCHOR_INDEX
        
        for _, row in deposit_df.iterrows():
            month_str = str(row['月份'])
            try:
                month_dt = pd.to_datetime(month_str)
                month_indices = sh_index[(sh_index['date'].dt.year == month_dt.year) & 
                                         (sh_index['date'].dt.month == month_dt.month)]
                
                if month_indices.empty:
                    continue
                
                last_day = month_indices.iloc[-1]
                close_price = last_day['close']
                trade_date = last_day['date'].strftime('%Y-%m-%d')
                
                est_mv = close_price * SCALE_FACTOR
                
                # Ratios
                total_dep = float(row['新增存款(亿元)_数量'])
                corp_dep = float(row['新增企业存款(亿元)_数量'])
                sav_dep = float(row['新增储蓄存款(亿元)_数量'])
                
                results.append({
                    '月份': month_str,
                    '交易日期': trade_date,
                    '总存款(亿)': round(total_dep, 2),
                    '企业存款(亿)': round(corp_dep, 2),
                    '储蓄存款(亿)': round(sav_dep, 2),
                    'A股总市值(亿)': round(est_mv, 2),
                    '总存款/市值': round(total_dep / est_mv, 2) if est_mv != 0 else 0,
                    '企业存款/市值': round(corp_dep / est_mv, 2) if est_mv != 0 else 0,
                    '储蓄存款/市值': round(sav_dep / est_mv, 2) if est_mv != 0 else 0
                })
            except:
                continue
        
        res_df = pd.DataFrame(results)
        if not res_df.empty:
            res_df.to_csv(RATIO_CACHE_FILE, index=False, encoding='utf-8-sig')
            
        return res_df
    except Exception as e:
        print(f"Error calculating ratio: {e}")
        return None

if __name__ == "__main__":
    df = fetch_rmb_deposit_data(force_update=True)
    if df is not None:
        print("Data fetched successfully. Rows:", len(df))
        print("Columns:", df.columns.tolist())
        print(df.head(2))
    else:
        print("Failed to fetch data.")
