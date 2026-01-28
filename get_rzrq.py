
import requests
import pandas as pd

def get_margin_data():
    print("Fetching RZRQ data from Jin10 (Source mirrored from Exchanges)...")
    # 融资买入额 is usually index 0, but we map by name
    urls = {
        "SH": "https://cdn.jin10.com/data_center/reports/fs_1.json",
        "SZ": "https://cdn.jin10.com/data_center/reports/fs_2.json"
    }
    
    dfs = []
    for market, url in urls.items():
        try:
            r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
            if r.status_code != 200:
                print(f"Failed to fetch {market}")
                continue
                
            data = r.json()
            # structure: {"keys": [{"name": "融资买入额", ...}, ...], "values": {"2022-01-01": [v1, v2...], ...}}
            
            # Extract column names
            cols = [item['name'] for item in data['keys']]
            
            # Extract values
            # data['values'] is a dict with date keys
            records = []
            for date_str, values in data['values'].items():
                record = {'date': date_str}
                for i, val in enumerate(values):
                    if i < len(cols):
                        record[cols[i]] = val
                records.append(record)
                
            df = pd.DataFrame(records)
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date').sort_index()
            print(f"{market} data fetched. Records: {len(df)}. Range: {df.index.min().date()} to {df.index.max().date()}")
            dfs.append(df)
            
        except Exception as e:
            print(f"Error processing {market}: {e}")

    if len(dfs) == 2:
        sh = dfs[0]
        sz = dfs[1]
        
        # Align and sum
        # Only keep common columns that are numeric
        common_cols = [c for c in sh.columns if c in sz.columns]
        
        total = sh[common_cols].add(sz[common_cols], fill_value=0)
        
        target_col = '融资买入额'
        if target_col in total.columns:
            print(f"\n--- Combined {target_col} (Last 5 days) ---")
            print(total[target_col].tail())
            
            # Verify units (Usually Yuan)
            latest_val = total[target_col].iloc[-1]
            print(f"Latest Value: {latest_val:,.0f} Yuan")
            return total
    else:
        print("Could not fetch both markets.")
    return None

if __name__ == "__main__":
    get_margin_data()
