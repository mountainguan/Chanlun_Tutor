import requests
import pandas as pd
import numpy as np
import os
import datetime
import json
import time
import random

# 通达信 行业板块代码映射表（由用户提供）
tdx_industry_map = {
    "881070": "有色", "881006": "石油", "881001": "煤炭",
    "881090": "建材", "881061": "钢铁", "881150": "纺织服饰",
    "881015": "化工", "881337": "通信", "881417": "房地产",
    "881105": "农林牧渔", "881318": "电子", "881405": "建筑",
    "881469": "环保", "881458": "公共事业", "881393": "非银金融",
    "881199": "商贸", "881441": "交通运输", "881166": "轻工制造",
    "881129": "食品饮料", "881385": "银行", "881260": "电力设备",
    "881351": "计算机", "881292": "机械设备", "881211": "汽车",
    "881426": "社会服务", "881368": "传媒", "881183": "家电",
    "881230": "医药医疗", "881286": "国防军工", "881477": "综合",
}
class SectorSentiment:
    def __init__(self):
        self.data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
        self.cache_file = os.path.join(self.data_dir, 'sector_sentiment_cache.json')
        self.if_sector_list_cache = os.path.join(self.data_dir, 'sector_list.json')
        self.api = None
        self.em_sector_map = None # Cache for EM mapping

    def _get_em_sector_map(self):
        """
        Fetch EastMoney sector list and build a mapping name->code
        """
        if self.em_sector_map is not None:
            return self.em_sector_map
            
        url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
        params = {
            "reportName": "RPTA_WEB_BKJYMXN",
            "columns": "BOARD_CODE,BOARD_NAME",
            "source": "WEB",
            "client": "WEB",
            "pageNumber": 1,
            "pageSize": 1000,
            "filter": "" 
        }
        try:
            resp = requests.get(url, params=params, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('result') and data['result'].get('data'):
                    mapping = {}
                    for item in data['result']['data']:
                        mapping[item['BOARD_NAME']] = item['BOARD_CODE']
                    self.em_sector_map = mapping
                    print(f"Loaded {len(mapping)} sectors from EastMoney")
                    return mapping
        except Exception as e:
            print(f"Failed to load EM sector map: {e}")
        return {}
    
    def _find_em_code(self, tdx_name):
        mapping = self._get_em_sector_map()
        if not mapping:
            return None
            
        # 1. Exact match
        if tdx_name in mapping:
            return mapping[tdx_name]
        
        # 2. Suffix match (EM often has "行业" or "概念")
        # e.g. TDX "有色" -> EM "有色金属"
        for em_name, code in mapping.items():
            if tdx_name in em_name:
                # print(f"Mapped {tdx_name} -> {em_name}")
                return code
                
        return None

    def _fetch_em_margin_history(self, em_code):
        if not em_code:
            return None
        url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
        params = {
            "reportName": "RPTA_WEB_BKJYMX",
            "columns": "TRADE_DATE,FIN_BUY_AMT",
            "pageSize": 500,
            "pageNumber": 1,
            "sortColumns": "TRADE_DATE",
            "sortTypes": "-1", # Descending
            "source": "WEB",
            "client": "WEB",
            "filter": f'(BOARD_CODE="{em_code}")'
        }
        try:
            resp = requests.get(url, params=params, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('result') and data['result'].get('data'):
                    df = pd.DataFrame(data['result']['data'])
                    df['TRADE_DATE'] = pd.to_datetime(df['TRADE_DATE'])
                    df['FIN_BUY_AMT'] = pd.to_numeric(df['FIN_BUY_AMT'], errors='coerce')
                    df = df.set_index('TRADE_DATE').sort_index()
                    return df
        except Exception as e:
            print(f"Failed to fetch EM history for {em_code}: {e}")
        return None

    def _connect_tdx(self):
        try:
            from pytdx.hq import TdxHq_API
            self.api = TdxHq_API()
            # Prioritize known good IPs
            ips = [
                ('60.191.117.167', 7709), # Stable
                ('124.71.187.100', 7709),
                ('218.75.126.9', 7709),
                ('119.147.212.81', 7709),
                ('115.238.56.198', 7709)
            ]
            
            # Disable shuffle to try the best ones first
            # random.shuffle(ips) 
            
            for ip, port in ips:
                # Re-instantiate API for each attempt to ensure clean state
                if self.api:
                    try: self.api.disconnect()
                    except: pass
                self.api = TdxHq_API()

                try:
                    print(f"Connecting to {ip}:{port}...")
                    if self.api.connect(ip, port, time_out=20):
                        print(f"Connected to TDX server: {ip}:{port}")
                        return True
                    else:
                        print(f"Connection failed for {ip}:{port}")
                except Exception as ex:
                    print(f"Connection error for {ip}:{port}: {ex}")
                    pass
            
            print("Failed to connect to any TDX server")
            return False
        except Exception as e:
            print(f"TDX init error: {e}")
            if "No module named 'pytdx'" in str(e):
                print("Missing dependency: Please run 'pip install pytdx'")
            return False

    def _disconnect_tdx(self):
        if self.api:
            try:
                self.api.disconnect()
            except:
                pass
            self.api = None

    def get_sector_list(self):
        """获取A股行业板块列表，返回 [{name, code}]"""
        # 如果存在通达信测试结果文件，则优先根据测试通过的映射构建板块列表并缓存（覆盖旧缓存）
        test_file = os.path.join(self.data_dir, 'tdx_industry_test_results.json')
        try:
            if os.path.exists(test_file):
                with open(test_file, 'r', encoding='utf-8') as f:
                    test_results = json.load(f)
                sectors = []
                for code, info in test_results.items():
                    if info.get('ok'):
                        sectors.append({'name': info.get('name', tdx_industry_map.get(code, '')), 'code': code})
                if sectors:
                    with open(self.if_sector_list_cache, 'w', encoding='utf-8') as f:
                        json.dump({'date': datetime.datetime.now().isoformat(), 'sectors': sectors}, f, ensure_ascii=False)
                    return sectors
        except Exception:
            pass

        # 优先读取已有缓存（如果没有 tdx 测试映射）
        if os.path.exists(self.if_sector_list_cache):
            try:
                with open(self.if_sector_list_cache, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if (datetime.datetime.now() - datetime.datetime.fromisoformat(data['date'])).days < 30:
                        sectors = data['sectors']
                        # 验证缓存格式是否为新版 [{name, code}]
                        if sectors and isinstance(sectors[0], dict) and 'code' in sectors[0]:
                            return sectors
            except:
                pass

        # 如果存在通达信测试结果文件，则优先根据测试通过的映射构建板块列表并缓存
        test_file = os.path.join(self.data_dir, 'tdx_industry_test_results.json')
        try:
            if os.path.exists(test_file):
                with open(test_file, 'r', encoding='utf-8') as f:
                    test_results = json.load(f)
                sectors = []
                for code, info in test_results.items():
                    if info.get('ok'):
                        sectors.append({'name': info.get('name', tdx_industry_map.get(code, '')), 'code': code})
                if sectors:
                    with open(self.if_sector_list_cache, 'w', encoding='utf-8') as f:
                        json.dump({'date': datetime.datetime.now().isoformat(), 'sectors': sectors}, f, ensure_ascii=False)
                    return sectors
        except Exception:
            pass

        # 不再使用 AkShare 或 东方财富；仅使用用户提供的 tdx 映射表
        try:
            sectors = []
            for code, name in tdx_industry_map.items():
                sectors.append({'name': name, 'code': code})
            with open(self.if_sector_list_cache, 'w', encoding='utf-8') as f:
                json.dump({'date': datetime.datetime.now().isoformat(), 'sectors': sectors}, f, ensure_ascii=False)
            return sectors
        except Exception as e:
            print(f"Failed to build sector list from tdx_industry_map: {e}")
            return []

    def fetch_sector_history_raw(self, sector_code, sector_name):
        """
        获取板块历史数据，优先使用 AkShare，失败则尝试直接请求
        """
        # If sector_code looks like a TDX index (880xxx or 881xxx), try pytdx first
        if isinstance(sector_code, str) and sector_code.isdigit() and sector_code.startswith(('880', '881')):
            df_tdx = self._fetch_sector_from_tdx(sector_code)
            if df_tdx is not None and not df_tdx.empty:
                return df_tdx
        # 如果通达信也无法获取，则返回 None
        return None

    def _fetch_sector_from_tdx(self, code, count=500):
        """使用 pytdx 获取板块（880xxx）历史日线成交额"""
        if not self.api:
             return None

        # 尝试不同的 market 参数（某些通达信节点/版本对 market 的处理可能不同）
        # 测试脚本中使用的是 market=1，通常指数在 market=1
        markets = [1, 0]

        for market in markets:
            try:
                # Use get_index_bars for index codes (starts with 88)
                data = self.api.get_index_bars(9, market, code, 0, count)
                
                if not data:
                    continue

                records = []
                for item in data:
                    try:
                        # pytdx bar dict may contain year/month/day or datetime
                        if isinstance(item, dict) and 'year' in item and item.get('month') is not None and item.get('day') is not None:
                            y = int(item.get('year'))
                            m = int(item.get('month'))
                            d = int(item.get('day'))
                            date_str = f"{y:04d}-{m:02d}-{d:02d}"
                        else:
                            date_str = str(item.get('datetime', ''))[:10] if isinstance(item, dict) else ''
                        
                        amt = float(item.get('amount', 0)) if isinstance(item, dict) else 0.0
                        records.append({'date': date_str, 'amount': amt})
                    except Exception:
                        continue
                
                if records:
                    df = pd.DataFrame(records)
                    df['date'] = pd.to_datetime(df['date'], errors='coerce')
                    df = df.dropna(subset=['date'])
                    # Verify data quality: Filter out future dates or extremely old dates if needed
                    # But for now, trust the data if get_index_bars works
                    df = df.set_index('date').sort_index()
                    return df

            except Exception as e:
                # If get_index_bars fails (e.g. not supported by server), fallback might be needed
                # But for 881xxx, get_security_bars usually returns garbage, so we stick to this.
                print(f"TDX fetch error code={code} market={market}: {e}")
                pass

        return None
    # Removed _generate_mock_history as it is no longer used/desired


    def _fetch_market_history(self):
        """
        Fetch Market (SH+SZ) data for Volume and Margin
        Returns DataFrame aligned by date columns: 'market_vol', 'market_margin_buy'
        """
        # 1. Volume: SH (999999) + SZ (399001) from TDX
        if not self.api: return None
        
        try:
             # SH Index
            df_sh = self._fetch_sector_from_tdx('999999')
            # SZ Index
            df_sz = self._fetch_sector_from_tdx('399001')
            
            if df_sh is None or df_sz is None:
                print("Failed to fetch SH/SZ index for market volume")
                return None
                
            df_vol = pd.merge(df_sh[['amount']], df_sz[['amount']], on='date', suffixes=('_sh', '_sz'), how='inner')
            df_vol['market_vol'] = df_vol['amount_sh'] + df_vol['amount_sz']
            df_vol = df_vol[['market_vol']]
            
            # 2. Margin: Jin10
            urls = {
                "SH": "https://cdn.jin10.com/data_center/reports/fs_1.json",
                "SZ": "https://cdn.jin10.com/data_center/reports/fs_2.json"
            }
            dfs_m = []
            for market, url in urls.items():
                try:
                    r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
                    if r.status_code == 200:
                        data = r.json()
                        cols = [item['name'] for item in data['keys']]
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
                        # Find '融资买入额'
                        buy_col = next((c for c in df.columns if '融资买入额' in c), None)
                        if buy_col:
                            df = df[[buy_col]].rename(columns={buy_col: 'margin_buy'})
                            # Convert to float
                            df['margin_buy'] = pd.to_numeric(df['margin_buy'], errors='coerce')
                            dfs_m.append(df)
                except Exception as e:
                    print(f"Jin10 fetch error {market}: {e}")
            
            df_margin = None
            if len(dfs_m) == 2:
                df_margin = pd.merge(dfs_m[0], dfs_m[1], on='date', suffixes=('_sh', '_sz'), how='inner')
                df_margin['market_margin_buy'] = df_margin['margin_buy_sh'] + df_margin['margin_buy_sz']
                df_margin = df_margin[['market_margin_buy']]
            
            # 3. Merge
            if df_margin is not None:
                # Use inner join to ensure we only use dates where both Volume and Margin are available
                # (Typically T-1, as Margin data is delayed by 1 day)
                df_market = pd.merge(df_vol, df_margin, on='date', how='inner')
                return df_market
            else:
                print("Warning: Market Margin data missing")
                return None

        except Exception as e:
            print(f"Error fetching market history: {e}")
            return None

    def update_data(self):
        """
        更新板块情绪数据
        """
        try:
           sectors = self.get_sector_list() # list of dicts {name, code}
        except:
           sectors = []
           
        if not sectors:
            print("No sector list available.")
            return {}

        # Connect to TDX (Retry logic)
        for attempt in range(3):
            if self._connect_tdx():
                break
            print(f"Retrying connection ({attempt+1}/3)...")
            time.sleep(2)
        
        if not self.api or not self.api.client: # Check if connected
             error_msg = "无法连接到通达信服务器，请检查网络 (All retries failed)"
             print(error_msg)
             raise Exception(error_msg)

        try:
            # Load existing cache
            cache_data = {}
            if os.path.exists(self.cache_file):
                try:
                    with open(self.cache_file, 'r', encoding='utf-8') as f:
                        cache_data = json.load(f)
                except:
                    pass
            
            today_str = datetime.datetime.now().strftime('%Y-%m-%d')
            results = cache_data.copy()
            
            # 0. Get Market Data (Global)
            print("Fetching Market Data (Volume & Margin)...")
            df_market = self._fetch_market_history()
            if df_market is None or df_market.empty:
                error_msg = "获取大盘基准数据失败 (TDX或Jin10数据缺失)"
                print(error_msg)
                raise Exception(error_msg)

            print(f"Market Data loaded: {len(df_market)} records.")

            print(f"Updating data for {len(sectors)} sectors...")
            
            updated_count = 0
            
            # 只需要简单的计数，不再因为失败而完全停止，而是转为 Mock
            for i, sector in enumerate(sectors):
                name = sector['name']
                code = sector['code']
                
                # Note: We need to RE-CALCULATE even if 'date' is today because the formula changed?
                # Or just skip if already done today?
                # Ideally, if user asks to "correct logic", we should force update.
                # But 'update_data' might be called automatically.
                # Let's assume we force update for now or skip. The user just asked for logic fix.
                # If I want to reflect changes immediately, I should remove the skip check.
                # But 'cache_data' checks name and date. If I change logic, I should invalidate cache.
                # I'll Comment out the skip logic for now to force refresh.
                # if name in cache_data and cache_data[name].get('date') == today_str:
                #    continue
                
                print(f"[{i+1}/{len(sectors)}] Fetching {name} ({code})...")
                
                # 1. 尝试真实获取
                df = self.fetch_sector_history_raw(code, name)
                
                is_mock = False
                # 2. 如果失败，跳过，不使用 Mock
                if df is None or df.empty:
                    print(f"Failed to fetch {name}, skipping...")
                    continue
                    
                try:
                    # Process data
                    if len(df) < 60: # 至少需要一定的数据量 (60 for MA)
                        continue
                        
                    # Align with Market Data
                    company_df = pd.merge(df, df_market, left_index=True, right_index=True, how='inner')
                    if len(company_df) < 20: continue
                    
                    # Get Margin Data for Sector
                    df_sector_margin = None
                    try:
                        em_code = self._find_em_code(name)
                        if em_code:
                            df_sector_margin = self._fetch_em_margin_history(em_code)
                    except: pass
                    
                    if df_sector_margin is not None and not df_sector_margin.empty:
                         df_sector_margin = df_sector_margin.rename(columns={'FIN_BUY_AMT': 'sector_margin_buy'})
                         # Use left merge to keep latest date from price/volume df
                         company_df = pd.merge(company_df, df_sector_margin[['sector_margin_buy']], left_index=True, right_index=True, how='left')
                         # Forward fill sector margin (as it's usually T-1)
                         company_df['sector_margin_buy'] = company_df['sector_margin_buy'].ffill()
                    else:
                        company_df['sector_margin_buy'] = 0.0

                    # --- New Formula Calculation ---
                    
                    # 1. Volume Part
                    company_df['sector_vol_ma20'] = company_df['amount'].rolling(window=20).mean()
                    company_df['sector_vol_ratio'] = company_df['amount'] / company_df['sector_vol_ma20']
                    
                    company_df['market_vol_ma20'] = company_df['market_vol'].rolling(window=20).mean()
                    company_df['market_vol_ratio'] = company_df['market_vol'] / company_df['market_vol_ma20']
                    
                    # Relative Vol Ratio
                    # Use a small epsilon for division safety? Or usually volumes are large.
                    company_df['rel_vol_ratio'] = company_df['sector_vol_ratio'] / company_df['market_vol_ratio']
                    
                    # Volume Score = (Relative Vol Ratio - 1) * 100
                    company_df['score_vol'] = (company_df['rel_vol_ratio'] - 1) * 100
                    
                    # 2. Margin Part
                    # Sector Margin % = sector_margin_buy / amount (Vol)
                    company_df['sector_margin_pct'] = company_df['sector_margin_buy'] / company_df['amount']
                    
                    # Market Margin %
                    company_df['market_margin_pct'] = company_df['market_margin_buy'] / company_df['market_vol']
                    
                    # Spread
                    company_df['margin_spread'] = company_df['sector_margin_pct'] - company_df['market_margin_pct']
                    
                    # Historical Spread MA 60
                    company_df['margin_spread_ma60'] = company_df['margin_spread'].rolling(window=60).mean()
                    
                    # Margin Score = (Spread - MA60) * 2000
                    company_df['score_margin'] = (company_df['margin_spread'] - company_df['margin_spread_ma60']) * 2000
                    
                    # Latest value
                    latest = company_df.iloc[-1]
                    last_date = latest.name.strftime('%Y-%m-%d')
                    
                    s_vol = latest['score_vol']
                    if pd.isna(s_vol): s_vol = 0
                    
                    s_margin = latest['score_margin']
                    if pd.isna(s_margin): s_margin = 0 
                    
                    # If sector has very little margin trading (sum close to 0), ignore margin part
                    has_margin = company_df['sector_margin_buy'].sum() > 1000 # minimal threshold
                    if not has_margin:
                        s_margin = 0
                    
                    final_temp = s_vol + s_margin
                    
                    results[name] = {
                        'date': last_date,
                        'temperature': round(final_temp, 2),
                        'turnover': float(latest['amount']),
                        'score_vol': round(float(s_vol), 2),
                        'score_margin': round(float(s_margin), 2),
                        'is_mock': is_mock 
                    }
                    updated_count += 1
                    
                    if updated_count % 5 == 0:
                         with open(self.cache_file, 'w', encoding='utf-8') as f:
                            json.dump(results, f, ensure_ascii=False, indent=4)

                except Exception as e:
                    print(f"Error processing {name}: {e}")
                
                # Sleep only if not mock to save time
                if not is_mock:
                    time.sleep(0.05)

            # Final Save
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=4)
            print(f"Update finished. Updated {updated_count} sectors.")
            return results
        finally:
            self._disconnect_tdx()

    def get_display_data(self):
        if not os.path.exists(self.cache_file):
            return None
        with open(self.cache_file, 'r', encoding='utf-8') as f:
            return json.load(f)

if __name__ == "__main__":
    import urllib3
    import sys
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    print(f"Running data update... Python: {sys.executable}")
    ss = SectorSentiment()
    # Explicitly connect first (like debug script) to ensure connectivity before heavy lifting
    print("Testing connection...")
    if not ss._connect_tdx():
        print("Initial connection check failed, but will let update_data retry.")
    
    data = ss.update_data()
    print("Done")
