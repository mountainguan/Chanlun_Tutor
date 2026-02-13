import pandas as pd
import requests
import datetime
import time
import urllib3
import os
import json
from zoneinfo import ZoneInfo

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
        self.fetch_log_file = os.path.join(self.data_dir, 'market_fetch_log.json')
    
    def _get_fetch_log_time(self):
        if os.path.exists(self.fetch_log_file):
            try:
                with open(self.fetch_log_file, 'r') as f:
                    log = json.load(f)
                    return log.get('last_market_sentiment_fetch')
            except:
                return None
        return None

    def _update_fetch_log_time(self):
        try:
            log = {}
            if os.path.exists(self.fetch_log_file):
                try:
                     with open(self.fetch_log_file, 'r') as f:
                        log = json.load(f)
                except:
                    pass
            
            log['last_market_sentiment_fetch'] = datetime.datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')
            
            with open(self.fetch_log_file, 'w') as f:
                json.dump(log, f)
        except Exception as e:
            print(f"Failed to update market fetch log: {e}")

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

    def fetch_sina_live(self, code):
        """
        获取新浪实时交易数据，主要用于补全当天的成交额
        code: sh000001, sz399001
        """
        url = f"http://hq.sinajs.cn/list={code}"
        headers = {"Referer": "https://finance.sina.com.cn/"}
        try:
            r = requests.get(url, headers=headers, timeout=5)
            if r.status_code == 200:
                text = r.text
                if code in text and '"' in text:
                    content = text.split('"')[1]
                    parts = content.split(',')
                    if len(parts) > 30:
                        date_str = parts[30]
                        # time_str = parts[31]
                        # Index 9 is amount in Yuan
                        amt = float(parts[9])
                        
                        df = pd.DataFrame({'date': [date_str], 'amount': [amt]})
                        df['date'] = pd.to_datetime(df['date'])
                        return df.set_index('date')['amount']
        except Exception as e:
            print(f"Fetch Sina Live failed for {code}: {e}")
        return None

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
                today_str = datetime.datetime.now(ZoneInfo('Asia/Shanghai')).strftime("%Y%m%d")
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
                        
                        # Check if we need to append today's data from Sina Live
                        # Sohu usually updates after close, but sometimes delays.
                        # Always try to fetch live data for today if Sohu doesn't have it (or even if it does, live might be fresher)
                        
                        try:
                            # Map secid to sina code
                            sina_live_code = "sh000001" if secid == "1.000001" else "sz399001"
                            live_df = self.fetch_sina_live(sina_live_code)
                            
                            if live_df is not None and not live_df.empty:
                                live_date = live_df.index[0]
                                if live_date not in df['date'].values:
                                    print(f"Appending Sina Live data for {sina_live_code}: {live_date.date()}")
                                    # live_df index is date, value is amount. Reset to match df format
                                    live_row = pd.DataFrame({'date': [live_date], 'amount': [live_df.iloc[0]]})
                                    df = pd.concat([df, live_row], ignore_index=True)
                                else:
                                    # Update today's data if exists (realtime is better than hisHq history if same day)
                                    print(f"Updating today's data from Sina Live for {sina_live_code}")
                                    df.loc[df['date'] == live_date, 'amount'] = live_df.iloc[0]
                        except Exception as e_live:
                            print(f"Error fetching live data: {e_live}")

                        return df.set_index('date')['amount']
            except Exception as e:
                 print(f"Sohu fallback failed for {secid}: {e}")

            # --- Fallback to Sina (Volume -> Estimated Turnover) ---
            # Try Sina Live FIRST if historical Sina fails or as a supplement?
            # If Sohu failed, we have NO historical data. 
            # We can at least return Today's data from Sina Live to keep the app running for today.
            
            sina_symbol = "sh000001" if secid == "1.000001" else "sz399001"
            
            # 1. Try Sina Live for at least TODAY's data
            live_df = self.fetch_sina_live(sina_symbol)
            if live_df is not None:
                print(f"Sina Live success for {sina_symbol} (Single Day)")
                # If we only have today, that's better than nothing.
                # But if user requested historical (datalen=800), we still lack history.
                # We can try to fetch history from Sina KLine (estimated) and overwrite today with Live.
            
            try:
                # Sina symbol: SH="sh000001", SZ="sz399001"
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
                     
                     # MERGE LIVE DATA
                     if live_df is not None:
                         live_date = live_df.index[0]
                         mask = df['date'] == live_date
                         if mask.any():
                             df.loc[mask, 'amount'] = live_df.iloc[0]
                             print(f"Overwrote Sina estimated data with Live data for {live_date.date()}")
                         else:
                             live_row = pd.DataFrame({'date': [live_date], 'amount': [live_df.iloc[0]]})
                             df = pd.concat([df, live_row], ignore_index=True)
                     
                     return df.set_index('date')['amount']
            except Exception as e:
                print(f"Sina fallback failed: {e}")

            if live_df is not None:
                 print(f"Returning Sina Live data only for {sina_symbol}")
                 return live_df

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
            # 必须严格确保两个市场都有数据，否则会导致总额只有一半，进而导致温度骤降
            if len(dfs) > 1:
                # 使用 inner join，只有两个市场都有数据的日期才会被保留
                # 这样如果某天只有一个市场更新了，这天会被丢弃，然后在 get_temperature_data 中触发“缺失数据估算”逻辑
                aligned = dfs[0][[target_col]].join(dfs[1][[target_col]], lsuffix='_sh', rsuffix='_sz', how='inner')
                total = pd.DataFrame(index=aligned.index)
                total[target_col] = aligned[f'{target_col}_sh'] + aligned[f'{target_col}_sz']
            else:
                # 只有一种情况会进入这里：由于网络或者接口原因只获取到了一个市场的数据列表dfs长度为1
                # 这种情况下为了安全起见，我们只能假设这就是总额(虽然可能不准)，或者也可以选择返回空
                # 但根据现有逻辑，如果 endpoints 循环里一个失败了被 try-catch 捕获，dfs 长度就是1
                total = dfs[0][[target_col]]
            
            # 过滤只保留最近三年的数据
            cutoff_date = (pd.Timestamp.now(tz='Asia/Shanghai') - pd.Timedelta(days=365*3)).tz_convert(None)
            total = total[total.index >= cutoff_date]
            
            return total[target_col].sort_index()
        
        return None

    def get_temperature_data(self, force_refresh=False):
        # 1. Loading Cache
        cache = self.load_cache()
        today = datetime.datetime.now(ZoneInfo('Asia/Shanghai')).date()
        
        latest_date = None
        need_fetch = True
        
        if cache is not None and not cache.empty:
            # Check if the last record is a simulated value from the past (yesterday or older)
            if 'is_simulated' in cache.columns:
                try:
                    is_sim = str(cache.iloc[-1]['is_simulated']).lower() in ('true', '1')
                    last_dt = cache.index[-1].date()
                    if is_sim and last_dt < today:
                        print(f"Removing simulated data from {last_dt} to fetch actual data.")
                        cache = cache.iloc[:-1]
                        self.save_cache(cache)
                except Exception as e:
                    print(f"Error checking simulated status: {e}")

            if not cache.empty:
                latest_date = cache.index[-1].date()
            else:
                latest_date = None

            # If we have data for today (or future), skip fetch
            if latest_date and latest_date >= today:
                if force_refresh:
                    print(f"Force refresh requested. Deleting today's data from cache.")
                    # 显式从缓存中删除今天及以后的数据，确保重新获取时能够覆盖
                    cache = cache[cache.index.date < today]
                    # 立即保存清理后的缓存到文件，确保文件状态同步
                    self.save_cache(cache)
                    
                    if not cache.empty:
                        latest_date = cache.index[-1].date()
                    else:
                        latest_date = None
                    # 强制需要fetch
                    need_fetch = True
                else:
                    print(f"Cache up to date ({latest_date}), skipping API fetch.")
                    need_fetch = False
            else:
                # Latest date is OLDER than today.
                # However, we should also check if we recently tried fetching (Fetch Throttling)
                last_fetch_str = self._get_fetch_log_time()
                current_time = datetime.datetime.now(ZoneInfo('Asia/Shanghai'))
                checkpoint_morning = current_time.replace(hour=9, minute=10, second=0, microsecond=0)
                checkpoint_midday = current_time.replace(hour=11, minute=30, second=0, microsecond=0)
                checkpoint_close = current_time.replace(hour=15, minute=30, second=0, microsecond=0)
                
                # Default: Fetch if we haven't fetched at all
                # If force_refresh is True, always fetch
                need_fetch = True if force_refresh else True
                
                if last_fetch_str and not force_refresh:
                    try:
                        last_fetch = datetime.datetime.strptime(last_fetch_str, '%Y-%m-%d %H:%M:%S').replace(tzinfo=ZoneInfo('Asia/Shanghai'))
                        
                        # Logic:
                        # If last fetch was TODAY
                        if last_fetch.date() == current_time.date():
                            
                            target_time = None
                            if current_time > checkpoint_close:
                                target_time = checkpoint_close
                            elif current_time > checkpoint_morning: # Covers trading day
                                target_time = checkpoint_morning
                            
                            # If we fetched AFTER the latest target time, we are good.
                            # Exception: If we are in trading hours (9:30 - 15:00), maybe we want more frequent updates?
                            # User said: "Unless ... 9:10am ... 3:30pm" implies ONLY those times or new day.
                            # So even if trading, we don't spam fetch unless we hit those marks?
                            # Actually, "新的一天打开" implies first open today.
                            
                            # Let's simplify:
                            # If we have fetched today...
                            
                            # Case 1: Before 9:10
                            if current_time < checkpoint_morning:
                                # Data unlikely to change from yesterday close, wait.
                                if last_fetch >= current_time.replace(hour=0, minute=0):
                                    need_fetch = False
                                    
                            # Case 2: After 9:10 but before 15:30
                            elif current_time < checkpoint_close:
                                # We want at least one fetch after 9:10
                                if last_fetch >= checkpoint_morning:
                                    need_fetch = False
                                    
                            # Case 3: After 15:30
                            else:
                                # We want at least one fetch after 15:30
                                if last_fetch >= checkpoint_close:
                                    need_fetch = False
                        
                        else:
                            # Last fetch was NOT today -> Must fetch
                            need_fetch = True
                            
                    except Exception as e:
                        print(f"Date parse error in strategies, defaulting to fetch: {e}")
                        need_fetch = True
                
                if not need_fetch:
                     print(f"Skipping market data fetch. Last attempt ({last_fetch_str}) is sufficient for now.")

        
        # 2. Fetch New Data if needed
        if need_fetch:
            print("Fetching new market data...")
            self._update_fetch_log_time()
            
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
                    df_new['is_simulated'] = False # Default Flag

                    # Filter only new data
                    if latest_date:
                        df_new = df_new[df_new.index.date > latest_date]
                    
                    # 尝试修复当天的融资数据缺失（如果成交额存在但融资数据缺失）
                    if not df_new.empty:
                        last_idx = df_new.index[-1]
                        # 检查最后一行是否只有成交额而没有融资买入数据
                        # 增加时间判断：只有下午3点收盘后才允许估算
                        # 这样盘中刷新时，如果真实数据未出，则不显示当天数据；盘后刷新则显示估算数据
                        # 使用 UTC+8 (北京时间) 进行判断
                        utc_now = datetime.datetime.now(datetime.timezone.utc)
                        cst_now = utc_now + datetime.timedelta(hours=8)
                        
                        # 只有当今天已经是收盘后，或者要估算的数据日期实际上是过去（比如假期时看前一个交易日），才允许估算
                        is_past_date = last_idx.date() < cst_now.date()
                        is_after_close_today = (last_idx.date() == cst_now.date()) and (cst_now.hour >= 15)
                        allow_estimation = is_past_date or is_after_close_today
                        
                        if pd.notna(df_new.at[last_idx, 'turnover_trillion']) and pd.isna(df_new.at[last_idx, 'margin_buy']) and allow_estimation:
                            print(f"Detected missing margin data for {last_idx.date()}, attempting estimation (After close CST {cst_now.strftime('%H:%M')})...")
                            prev_ratio = 8.5 # 默认兜底值
                            
                            # 获取前一天的融资占比
                            prev_valid_row = None
                            if len(df_new) > 1:
                                prev_valid_row = df_new.iloc[-2]
                            elif cache is not None and not cache.empty:
                                prev_valid_row = cache.iloc[-1]
                                
                            if prev_valid_row is not None:
                                try:
                                    p_to = prev_valid_row['turnover_trillion']
                                    p_mb = prev_valid_row['margin_buy']
                                    if p_to > 0:
                                        prev_ratio = (p_mb / (p_to * 1e12)) * 100
                                except Exception:
                                    pass
                            
                            # 使用前一天的比例估算今天的融资买入额
                            est_margin_buy = (prev_ratio / 100) * (df_new.at[last_idx, 'turnover_trillion'] * 1e12)
                            df_new.at[last_idx, 'margin_buy'] = est_margin_buy
                            # 标记为估算数据，以便前端展示警告
                            df_new.at[last_idx, 'is_simulated'] = True
                            self.is_simulated = True 
                            print(f"Estimated margin buy for {last_idx.date()} using ratio {prev_ratio:.2f}%: {est_margin_buy/1e8:.2f} 亿")

                    # Drop NaN if margin buy is still missing for non-estimated rows
                    df_new = df_new.dropna(subset=['turnover_trillion', 'margin_buy'])
                    
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

            # Restore simulation flag from cache if available
            if 'is_simulated' in df.columns and not df.empty:
                last_row_simulated = df.iloc[-1]['is_simulated']
                # Check for boolean True or string 'True' or 1
                if str(last_row_simulated).lower() in ('true', '1'):
                    self.is_simulated = True
                else:
                    self.is_simulated = False
            elif not hasattr(self, 'is_simulated'):
                self.is_simulated = False

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
