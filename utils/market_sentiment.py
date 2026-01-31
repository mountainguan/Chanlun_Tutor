import pandas as pd
import requests
import datetime
import time
import urllib3
import os

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class MarketSentiment:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36 Edg/144.0.0.0"
        }
        self.data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
        self.cache_file = os.path.join(self.data_dir, 'market_sentiment_cache.csv')

    def load_cache(self):
        if os.path.exists(self.cache_file):
            try:
                df = pd.read_csv(self.cache_file)
                df['date'] = pd.to_datetime(df['date'])
                return df.set_index('date').sort_index()
            except Exception as e:
                print(f"Cache load failed: {e}")
        return None

    def save_cache(self, df):
        try:
            df.to_csv(self.cache_file)
        except Exception as e:
            print(f"Cache save failed: {e}")

    def get_sh_sz_turnover(self, beg="0"):
        """
        获取沪深两市成交额
        返回: pd.Series (index=Date, value=Amount in Trillions)
        """
        # 上证指数 1.000001
        # 深证成指 0.399001
        
        # 东方财富 K线接口
        # f51: 日期, f57: 成交额
        # 尝试多个备用域名
        self.kline_urls = [
            "https://push2his.eastmoney.com/api/qt/stock/kline/get",
            "http://push2his.eastmoney.com/api/qt/stock/kline/get",
            "https://push2.eastmoney.com/api/qt/stock/kline/get"
        ]
        
        def fetch_one(secid):
            params = {
                "secid": secid,
                "fields1": "f1",
                "fields2": "f51,f57",
                "klt": "101", # 日线
                "fqt": "1",
                "beg": beg,
                "end": "20500000",
                "lmt": "800" # 最近800天
            }
            # 更新 Headers 模拟浏览器
            headers = self.headers.copy()
            headers.update({
                "Referer": "https://quote.eastmoney.com/",
                "Accept": "*/*",
                "Host": "push2his.eastmoney.com"
            })
            
            for url in self.kline_urls:
                # 动态调整 Host
                if "push2.eastmoney.com" in url:
                    headers["Host"] = "push2.eastmoney.com"
                else:
                    headers["Host"] = "push2his.eastmoney.com"

                try:
                    # verify=False 避免 SSL 握手失败
                    r = requests.get(url, params=params, headers=headers, timeout=5, verify=False)
                    if r.status_code != 200:
                        continue
                        
                    data = r.json()
                    if data and data['data'] and data['data']['klines']:
                        klines = data['data']['klines']
                        rows = []
                        for line in klines:
                            dt_str, amt_str = line.split(',')
                            rows.append({'date': dt_str, 'amount': float(amt_str)})
                        df = pd.DataFrame(rows)
                        df['date'] = pd.to_datetime(df['date'])
                        return df.set_index('date')['amount']
                except Exception as e:
                    print(f"Error fetching {url} for {secid}: {e}")
            
            print(f"All URLs failed for {secid}")
            
            # --- Fallback to Sohu (Has Amount!) ---
            try:
                # Sohu code: SH="zs_000001", SZ="zs_399106" (Composite, not Component which is smaller)
                sohu_code = "zs_000001" if secid == "1.000001" else "zs_399106"
                
                # Sohu uses YYYYMMDD for start/end
                today_str = datetime.datetime.now().strftime("%Y%m%d")
                start_str = "20230101" 
                if beg and beg != "0":
                    start_str = beg
                
                url_sohu = "http://q.stock.sohu.com/hisHq"
                params_sohu = {
                    "code": sohu_code,
                    "start": start_str,
                    "end": today_str,
                    "stat": "1",
                    "order": "D",
                    "period": "d"
                }
                print(f"Trying Sohu fallback for {sohu_code}...")
                r = requests.get(url_sohu, params=params_sohu, headers=self.headers, timeout=5)
                # Response: [{"hq": [[date, open, close, ..., vol, amt(wan), ...]], "code":...}]
                data = r.json()
                
                if isinstance(data, list) and len(data) > 0 and 'hq' in data[0]:
                    hq = data[0]['hq']
                    rows = []
                    for item in hq:
                        # item format: [date, open, close, change, ratio, low, high, vol, amt, ...]
                        if len(item) < 9: continue
                        dt_str = item[0]
                        amt_wan = float(item[8])
                        # Wan Yuan to Yuan: * 10000
                        amt = amt_wan * 10000
                        rows.append({'date': dt_str, 'amount': amt})
                    
                    if rows:
                        df = pd.DataFrame(rows)
                        df['date'] = pd.to_datetime(df['date'])
                        print(f"Sohu fallback success for {sohu_code}")
                        return df.set_index('date')['amount']
            except Exception as e:
                 print(f"Sohu fallback failed for {secid}: {e}")

            # --- Fallback to Sina (Volume -> Estimated Turnover) ---
            try:
                # Sina symbol: SH="sh000001", SZ="sz399001"
                sina_symbol = "sh000001" if secid == "1.000001" else "sz399001"
                url_sina = "https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData"
                params_sina = {
                    "symbol": sina_symbol,
                    "scale": "240",
                    "ma": "no",
                    "datalen": "800"
                }
                print(f"Trying Sina fallback for {sina_symbol}...")
                r = requests.get(url_sina, params=params_sina, headers=self.headers, timeout=5)
                data = r.json()
                if isinstance(data, list) and len(data) > 0:
                     rows = []
                     for item in data:
                         # item: {'day': '2024-01-01', 'volume': '123456'}
                         # Approx: Turnover = Volume(Shares) * 12.0 (Avg Price)
                         vol = float(item['volume'])
                         amt = vol * 12.0
                         rows.append({'date': item['day'], 'amount': amt})
                     
                     df = pd.DataFrame(rows)
                     df['date'] = pd.to_datetime(df['date'])
                     print(f"Sina fallback success for {sina_symbol}")
                     return df.set_index('date')['amount']
            except Exception as e:
                print(f"Sina fallback failed: {e}")

            return None
            return None

        sh = fetch_one("1.000001")
        sz = fetch_one("0.399001")
        
        if sh is not None and sz is not None:
            # align
            total = sh + sz
            # 数据清洗，去除NaN
            total = total.dropna()
            # 转换为万亿 (原始单位通常是 元? 还是 万? 还是 亿?)
            # 东财 f57 通常是元。
            # 上证日成交3000亿 = 3*10^11. 万亿 = 10^12. -> 0.3
            return total / 1e12
        else:
            return None

    def get_margin_buy(self):
        """
        获取全市场融资买入额
        返回: pd.Series (index=Date, value=Margin Buy Amount in Trillions? No, formula needs amount. 
        Note: The formula uses '融资占比%'. 
        融资占比 = (融资买入额 / 总成交额) * 100
        So units must match. If turnover is in Yuan, Margin Buy must be in Yuan.
        """
        # 使用 Jin10 接口获取两融数据
        endpoints = {
            "SH": "https://cdn.jin10.com/data_center/reports/fs_1.json",
            "SZ": "https://cdn.jin10.com/data_center/reports/fs_2.json"
        }
        
        dfs = []

        for market, url in endpoints.items():
            try:
                r = requests.get(url, headers=self.headers, timeout=10)
                data = r.json()
                
                # Jin10 数据结构: 
                # "keys": [{"name": "融资买入额", ...}, ...]
                # "values": {"2023-01-01": [v1, v2...], ...}
                
                col_map = {item['name']: i for i, item in enumerate(data['keys'])}
                target_col = "融资买入额"
                
                if target_col not in col_map:
                    print(f"Column {target_col} not found in {market}")
                    continue
                    
                idx = col_map[target_col]
                
                records = []
                for date_str, values in data['values'].items():
                    if idx < len(values):
                        records.append({
                            "date": date_str,
                            target_col: float(values[idx])
                        })
                
                df = pd.DataFrame(records)
                if not df.empty:
                    df["date"] = pd.to_datetime(df["date"])
                    df = df.set_index("date")
                    dfs.append(df)
                
            except Exception as e:
                print(f"Error fetching {market}: {e}")

        if len(dfs) > 0:
            # 合并沪深两市数据 (sum)
            # 使用 add(fill_value=0) 处理日期不完全一致的情况 (虽然通常应该一致)
            total = dfs[0][[target_col]]
            if len(dfs) > 1:
                total = total.add(dfs[1][[target_col]], fill_value=0)
            
            # 过滤只保留最近三年的数据
            cutoff_date = pd.Timestamp.now() - pd.Timedelta(days=365*3)
            total = total[total.index >= cutoff_date]
            
            return total[target_col].sort_index()
        
        return None

    def get_temperature_data(self):
        # 1. Loading Cache
        cache = self.load_cache()
        today = datetime.datetime.now().date()
        
        latest_date = None
        need_fetch = True
        
        if cache is not None and not cache.empty:
            latest_date = cache.index[-1].date()
            # If we have data for today (or future), skip fetch
            if latest_date >= today:
                print(f"Cache up to date ({latest_date}), skipping API fetch.")
                need_fetch = False
        
        # 2. Fetch New Data if needed
        if need_fetch:
            print("Fetching new market data...")
            start_date_str = "0"
            if latest_date:
                # Fetch from next day
                start_date_str = (latest_date + datetime.timedelta(days=1)).strftime("%Y%m%d")
            
            turnover = self.get_sh_sz_turnover(beg=start_date_str)
            # Current margin API fetches all, we will filter later
            margin_buy = self.get_margin_buy()
            
            self.is_simulated = False
            
            if turnover is None:
                print("Turnover fetch failed.")
            
            # Combine new data
            if turnover is not None and margin_buy is not None:
                try:
                    df_new = pd.DataFrame({'turnover_trillion': turnover, 'margin_buy': margin_buy})
                    df_new = df_new.dropna()
                    
                    # Filter only new data
                    if latest_date:
                        df_new = df_new[df_new.index.date > latest_date]
                    
                    if not df_new.empty:
                        print(f"Got {len(df_new)} new records.")
                        if cache is not None:
                            df_final = pd.concat([cache, df_new])
                            # Remove duplicates
                            df_final = df_final[~df_final.index.duplicated(keep='last')]
                            df_final = df_final.sort_index()
                            cache = df_final
                        else:
                            cache = df_new
                        
                        # Update cache file
                        self.save_cache(cache)
                    else:
                        print("No new data to append.")
                except Exception as e:
                    print(f"Error merging new data: {e}")

        # 3. Use Cache for Calculation
        if cache is None or cache.empty:
            print("No data available. Simulation is disabled.")
            self.is_simulated = False
            return None
        
        df = cache.copy()
        
        try:
            # 融资占比% = (融资买入额 / 成交额) * 100
            turnover_yuan = df['turnover_trillion'] * 1e12
            df['margin_ratio_pct'] = (df['margin_buy'] / turnover_yuan) * 100
            
            # --- 恢复原公式 ---
            # 温度 = [(融资占比% - 4.5) × 7.5] + [(成交额万亿 - 0.65) × 17]
            
            base_score = (df['margin_ratio_pct'] - 4.5) * 7.5
            correction_score = (df['turnover_trillion'] - 0.65) * 17
            
            df['temperature'] = base_score + correction_score
            df = df.dropna(subset=['temperature'])

            return df
        except Exception as e:
            print(f"Error calculating temperature: {e}")
            return None

if __name__ == "__main__":
    ms = MarketSentiment()
    df = ms.get_temperature_data()
    if df is not None:
        print(df.tail())
    else:
        print("Failed to compute temperature.")
