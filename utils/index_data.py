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
        self.fetch_log_file = os.path.join(self.data_dir, 'index_fetch_log.json')
        
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

    def _get_fetch_log(self):
        if os.path.exists(self.fetch_log_file):
            try:
                with open(self.fetch_log_file, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def _update_fetch_log_time(self, code):
        """Record the fetch time for specific index code"""
        try:
            log = self._get_fetch_log()
            log[code] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            with open(self.fetch_log_file, 'w') as f:
                json.dump(log, f)
        except Exception as e:
            print(f"Failed to update fetch log: {e}")

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
        need_fetch = False
        
        # 1. Check if we have data for 'today' (or at least recent) in raw cache
        # If cache is empty for this code, we definitely need fetch
        if curr_cache.empty:
            need_fetch = True
        else:
            # 2. Advanced Cache Strategy
            # Requirement: Read cache if available. Don't refresh unless:
            #   - New Day (First access today)
            #   - Time is > 09:10 (Morning update)
            #   - Time is > 15:30 (Close update)
            
            try:
                log = self._get_fetch_log()
                last_fetch_str = log.get(code)
                now = datetime.datetime.now()
                
                if not last_fetch_str:
                    # Never fetched this code recorded -> Fetch
                    need_fetch = True
                else:
                    last_fetch = datetime.datetime.strptime(last_fetch_str, '%Y-%m-%d %H:%M:%S')
                    
                    # Define Checkpoints for Today
                    checkpoint_new_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
                    checkpoint_morning = now.replace(hour=9, minute=10, second=0, microsecond=0)
                    checkpoint_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
                    
                    # Determine key target time based on current time
                    target_time = checkpoint_new_day # Default: must have fetched today
                    
                    if now > checkpoint_close:
                        target_time = checkpoint_close
                    elif now > checkpoint_morning:
                        target_time = checkpoint_morning
                        
                    # If our last fetch was before the target checkpoint -> REFRESH
                    if last_fetch < target_time:
                        need_fetch = True
                        print(f"Index fetch trigger for {index_name}: Now={now.strftime('%H:%M')}, Last={last_fetch.strftime('%H:%M')}, Target={target_time.strftime('%H:%M')}")
                    else:
                        need_fetch = False
                        
            except Exception as e:
                print(f"Cache check logic failed: {e}, forcing fetch.")
                need_fetch = True

        
        if need_fetch or force_refresh:
            print(f"Fetching index data for {index_name} ({code})...")
            new_df = self.fetch_sina_kline(code, datalen=days)
            if new_df is not None and not new_df.empty:
                # Update Fetch Log Logic
                self._update_fetch_log_time(code)

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
