import pandas as pd
import requests
import datetime
import os
import json

class IndexDataManager:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.75 Safari/537.36"
        }
        self.data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
        self.cache_file = os.path.join(self.data_dir, 'index_history_cache.csv')
        
        # 核心指数代码映射 (Sina 格式)
        self.index_map = {
            "上证指数": "sh000001",
            "深证成指": "sz399001",
            "创业板指": "sz399006",
            "上证50": "sh000016",
            "沪深300": "sh000300",
            "中证500": "sh000905"
        }

    def load_cache(self):
        if os.path.exists(self.cache_file):
            try:
                df = pd.read_csv(self.cache_file)
                df['date'] = pd.to_datetime(df['date'])
                return df
            except Exception as e:
                print(f"Index cache load failed: {e}")
        return pd.DataFrame(columns=['date', 'code', 'close', 'open', 'high', 'low'])

    def save_cache(self, df):
        try:
            df.to_csv(self.cache_file, index=False)
        except Exception as e:
            print(f"Index cache save failed: {e}")

    def fetch_sina_kline(self, code, scale=240, datalen=1200):
        """
        仿 Ashare 方式获取新浪行情
        scale: 240=日线, 60=60分钟
        """
        api_url = f"https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData?symbol={code}&scale={scale}&ma=no&datalen={datalen}"
        try:
            res = requests.get(api_url, headers=self.headers, timeout=5)
            data = res.json()
            if not data:
                return None
            
            # Data format: [{'day': '2023-01-01', 'open': ..., 'high': ..., 'low': ..., 'close': ..., 'volume': ...}]
            df = pd.DataFrame(data)
            df.rename(columns={'day': 'date'}, inplace=True)
            df['date'] = pd.to_datetime(df['date'])
            cols = ['date', 'open', 'high', 'low', 'close', 'volume']
            df = df[cols].copy()
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].astype(float)
            
            df['code'] = code
            return df
        except Exception as e:
            print(f"Fetch index {code} failed: {e}")
            return None

    def get_index_data(self, index_name, days=1200, force_refresh=False):
        """
        获取指定指数的历史数据
        """
        code = self.index_map.get(index_name)
        if not code:
            print(f"Index {index_name} not found in map.")
            return None

        # 1. Load Cache
        cache = self.load_cache()
        curr_cache = pd.DataFrame()
        
        if not cache.empty:
            curr_cache = cache[cache['code'] == code].copy()
            curr_cache = curr_cache.sort_values('date')
        
        today = datetime.datetime.now().date()
        latest_date = None
        
        if not curr_cache.empty:
            latest_date = curr_cache.iloc[-1]['date'].date()
            
        # Determine if we need to fetch
        need_fetch = True
        
        # 如果缓存是最新的，且没强制刷新，就不取
        if latest_date:
            if latest_date >= today:
                 # Check close time? Normally daily data updates after close. 
                 # But if we have 'today' in cache, we assume it's good unless force_refresh
                 if force_refresh:
                     pass
                 else:
                     need_fetch = False
        
        if need_fetch or force_refresh:
            print(f"Fetching index data for {index_name} ({code})...")
            new_df = self.fetch_sina_kline(code, datalen=days)
            if new_df is not None and not new_df.empty:
                # Merge logic
                if not curr_cache.empty:
                    # Filter new data that is NOT in cache or just replace overlap?
                    # Easiest is to overwrite overlapping dates logic or simply concate and drop duplicates
                    # But since new_df is 'datalen' long, it might be shorter or longer.
                    # Best: Append new dates, update last date if changed.
                    
                    # Actually, for simplicity with limited history window, we can merge
                    # Remove old records of this code from main cache, then append merged
                    other_cache = cache[cache['code'] != code]
                    
                    # Combine old curr_cache and new_df
                    combined = pd.concat([curr_cache, new_df])
                    combined = combined.drop_duplicates(subset=['date'], keep='last')
                    combined = combined.sort_values('date')
                    
                    # Reconstruct global cache
                    cache = pd.concat([other_cache, combined])
                    self.save_cache(cache)
                    
                    curr_cache = combined
                else:
                    # No cache for this code yet
                    cache = pd.concat([cache, new_df])
                    self.save_cache(cache)
                    curr_cache = new_df

        return curr_cache

if __name__ == '__main__':
    im = IndexDataManager()
    df = im.get_index_data("上证指数")
    print(df.tail())
