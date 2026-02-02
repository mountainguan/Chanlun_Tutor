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
        Fetch Market (SH+SZ) data using MarketSentiment class to ensure consistency and include estimations.
        Returns DataFrame aligned by date columns: 'market_vol', 'market_margin_buy'
        """
        import sys
        
        # Ensure project root is in sys.path so 'utils' package can be resolved
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

        try:
            from utils.market_sentiment import MarketSentiment
        except ImportError:
            # Fallback: if running inside utils folder directly
            try:
                from market_sentiment import MarketSentiment
            except ImportError as e:
                print(f"Import Error: {e}")
                return None

        try:
            ms = MarketSentiment()
            # force_refresh=False to use existing cache (which might contain estimated data from today)
            # But if cache is old, MS logic will fetch new.
            df_ms = ms.get_temperature_data()
            
            if df_ms is None or df_ms.empty:
                print("MarketSentiment returned no data.")
                return None
            
            # Map columns
            # MarketSentiment: 'turnover_trillion' (Trillion), 'margin_buy' (Yuan)
            # SectorSentiment logic expects:
            # market_vol (Yuan) -> to match 'amount' from TDX which is usually Yuan (or needs checking)
            # TDX amount is usually unit=1 (Yuan).
            
            df_market = pd.DataFrame(index=df_ms.index)
            df_market['market_vol'] = df_ms['turnover_trillion'] * 1e12 
            df_market['market_margin_buy'] = df_ms['margin_buy']
            
            # Carry over the simulation flag if needed, though we check it per-row usually or just valid/invalid.
            # But SectorSentiment needs to know if market is simulated? 
            # Actually, if market_margin_buy is estimated in MS, it is just a number here.
            # We can trust that number for calculation.
            
            return df_market
            
        except Exception as e:
            print(f"Error fetching market history via MarketSentiment: {e}")
            return None

    def update_data(self):
        """
        更新板块情绪数据，支持历史回溯和预估
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
        
        if not self.api or not self.api.client: 
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
            
            # 兼容性检查：如果旧格式（值为dict且没有history字段），则清空
            # 我们尽量复用，但如果结构变了，最好重新生成
            # 只要是 dict，我们可以把旧的作为 latest，新建 history 为空
            results = {} # Start fresh to clean up old keys or formats

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
            
            for i, sector in enumerate(sectors):
                name = sector['name']
                code = sector['code']
                
                print(f"[{i+1}/{len(sectors)}] Fetching {name} ({code})...")
                
                # 1. 尝试真实获取
                df = self.fetch_sector_history_raw(code, name)
                
                if df is None or df.empty:
                    print(f"Failed to fetch {name}, skipping...")
                    continue
                    
                try:
                    if len(df) < 60: 
                        continue
                        
                    # Align with Market Data
                    # Use inner join to find common dates, but ensure we don't lose today if market has it
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
                         # Left merge to keep validation logic later
                         company_df = pd.merge(company_df, df_sector_margin[['sector_margin_buy']], left_index=True, right_index=True, how='left')
                    else:
                        company_df['sector_margin_buy'] = np.nan

                    # --- Estimation Logic for Sector Margin ---
                    # Check the last row. If Sector Margin is NaN but we have Volume and Market Data
                    last_idx = company_df.index[-1]
                    is_simulated = False
                    
                    if pd.isna(company_df.at[last_idx, 'sector_margin_buy']):
                        # Try to estimate using previous day's ratio
                        # Find the last valid margin data point
                        valid_margin_df = company_df.dropna(subset=['sector_margin_buy'])
                        if not valid_margin_df.empty:
                            last_valid = valid_margin_df.iloc[-1]
                            # Use ratio: sector_margin_buy / amount
                            if last_valid['amount'] > 0:
                                prev_ratio = last_valid['sector_margin_buy'] / last_valid['amount']
                                # Estimate: today_amount * prev_ratio
                                est_val = company_df.at[last_idx, 'amount'] * prev_ratio
                                # Update DataFrame
                                company_df.at[last_idx, 'sector_margin_buy'] = est_val
                                is_simulated = True
                                # print(f"  Estimated margin for {name} on {last_idx.date()}")
                        
                    # Fill remaining NaNs with 0 (should not happen often if history is good)
                    company_df['sector_margin_buy'] = company_df['sector_margin_buy'].fillna(0.0)

                    # --- Calculation ---
                    
                    # 1. Volume Part
                    company_df['sector_vol_ma20'] = company_df['amount'].rolling(window=20).mean()
                    company_df['sector_vol_ratio'] = company_df['amount'] / company_df['sector_vol_ma20']
                    
                    company_df['market_vol_ma20'] = company_df['market_vol'].rolling(window=20).mean()
                    company_df['market_vol_ratio'] = company_df['market_vol'] / company_df['market_vol_ma20']
                    
                    company_df['rel_vol_ratio'] = company_df['sector_vol_ratio'] / company_df['market_vol_ratio']
                    company_df['score_vol'] = (company_df['rel_vol_ratio'] - 1) * 100
                    
                    # 2. Margin Part
                    company_df['sector_margin_pct'] = company_df['sector_margin_buy'] / company_df['amount']
                    company_df['market_margin_pct'] = company_df['market_margin_buy'] / company_df['market_vol']
                    
                    company_df['margin_spread'] = company_df['sector_margin_pct'] - company_df['market_margin_pct']
                    company_df['margin_spread_ma60'] = company_df['margin_spread'].rolling(window=60).mean()
                    company_df['score_margin'] = (company_df['margin_spread'] - company_df['margin_spread_ma60']) * 2000
                    
                    # 3. Final Temperature
                    has_margin = company_df['sector_margin_buy'].sum() > 1000
                    if not has_margin:
                        company_df['score_margin'] = 0
                        
                    company_df['temperature'] = company_df['score_vol'] + company_df['score_margin']
                    
                    # Prepare Output Structure
                    # Save last 180 days history
                    hist_df = company_df.tail(180).copy()
                    history_list = []
                    
                    for date_idx, row in hist_df.iterrows():
                        # Determine if this specific row was simulated (only the last one could be)
                        row_sim = is_simulated and (date_idx == last_idx)
                        
                        history_list.append({
                            'date': date_idx.strftime('%Y-%m-%d'),
                            'temperature': round(row['temperature'], 2) if pd.notna(row['temperature']) else 0,
                            'turnover': float(row['amount']),
                            'score_vol': round(row['score_vol'], 2) if pd.notna(row['score_vol']) else 0,
                            'score_margin': round(row['score_margin'], 2) if pd.notna(row['score_margin']) else 0,
                            'is_mock': row_sim
                        })
                    
                    # Latest entry
                    latest_entry = history_list[-1]
                    
                    results[name] = {
                        'latest': latest_entry,
                        'history': history_list
                    }
                    
                    updated_count += 1
                    
                    if updated_count % 5 == 0:
                         with open(self.cache_file, 'w', encoding='utf-8') as f:
                            json.dump(results, f, ensure_ascii=False, indent=4)

                except Exception as e:
                    print(f"Error processing {name}: {e}")
                
                time.sleep(0.02)

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
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # Backward compatibility check: if data structure is old (no 'history'), wrap it
            # Assuming old structure: { "Name": { "temperature": ..., "date": ... } }
            # New structure: { "Name": { "latest": {...}, "history": [...] } }
            fixed_data = {}
            for k, v in data.items():
                if 'latest' not in v and 'temperature' in v:
                    # Old format, convert on the fly for display
                    fixed_data[k] = {
                        'latest': v,
                        'history': [v] # Fake history
                    }
                else:
                    fixed_data[k] = v
                    
            return fixed_data
        except Exception as e:
            print(f"Error loading cache: {e}")
            return None

    def get_daily_stats(self, target_date=None):
        """
        从缓存中读取指定日期的板块数据，按照温度分组返回统计信息。
        target_date: 'YYYY-MM-DD' 或 None (Latest)
        """
        data = self.get_display_data()
        if not data:
            return None

        overheat = []
        overcold = []
        cold = []
        
        display_date = target_date

        # If no target date, find the max date available in data (usually today/yesterday)
        if not display_date:
            dates = set()
            for v in data.values():
                if 'latest' in v:
                     dates.add(v['latest']['date'])
            if dates:
                display_date = max(dates)
            else:
                return None

        # Iterate all sectors
        for name, rec in data.items():
            entry = None
            if 'history' in rec:
                # Find the entry for target_date
                # History is sorted by date ascending usually
                # Linear search backwards is faster for recent dates
                for h in reversed(rec['history']):
                    if h['date'] == display_date:
                         entry = h
                         break
            elif 'latest' in rec:
                 if rec['latest']['date'] == display_date:
                     entry = rec['latest']
            
            if entry:
                try:
                    temp = float(entry.get('temperature', 0))
                except: temp = 0
                
                if temp > 100:
                    overheat.append(name)
                elif temp < -50:
                    overcold.append(name)
                elif temp <= -20 and temp >= -50:
                    cold.append(name)

        return {
            'date': display_date,
            'counts': {
                'overheat': len(overheat),
                'cold': len(cold),
                'overcold': len(overcold)
            },
            'overheat': sorted(overheat),
            'cold': sorted(cold),
            'overcold': sorted(overcold)
        }

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
