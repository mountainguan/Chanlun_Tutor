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
    def __init__(self, industry_level=1):
        self.data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
        self.industry_level = int(industry_level) # Ensure int
        self.set_level(self.industry_level)
        self.api = None
        self.em_sector_map = None # Cache for EM mapping
        self.manual_mapping = {
            # TDX -> EM (Manual Mapping optimized for Margin Data availability)
            "IT设备": "计算机设备", "一般零售": "商业百货", "专业工程": "工程建设", 
            "专业服务": "多元金融", "专业连锁": "商业百货", "交通运输": "物流行业",
            "产业互联网": "互联网服务", "休闲食品": "食品饮料", "传媒": "文化传媒",
            "体育": "体育产业", "元器件": "电子元件", "光学广电": "光学光电子",
            "全国性银行": "银行", "公共事业": "电力行业", "公路铁路": "铁路基建",
            "其他发电设备": "电源设备", "其他电子": "电子元件", "养殖业": "农牧饲渔",
            "军工电子": "军工", "农产品加工": "农牧饲渔", "农林牧渔": "农牧饲渔",
            "农用化工": "化肥行业", "冶钢原料": "钢铁行业", "出版社": "文化传媒",
            "动物保健": "生物制品", "包装印刷": "综合行业", "化工": "化学原料",
            "医药医疗": "医药商业", "厨卫电器": "家电行业", "商业物业经营": "房地产开发",
            "商用车": "汽车整车", "商贸": "贸易行业", "国防军工": "军工",
            "地方性银行": "银行", "地面兵装": "军工", "基础建设": "工程建设",
            "塑料": "塑料制品", "家居用品": "家电行业", "家电零部件": "家电行业",
            "小家电": "家电行业", "工业金属": "有色金属", "工程咨询服务": "工程建设",
            "广告营销": "文化传媒", "广播电视": "广电", "建材": "水泥建材",
            "建筑": "工程建设", "影视院线": "影视概念", "房产服务": "房地产开发",
            "房地产": "房地产开发", "房屋建设": "工程建设", "摩托车及其他": "交运设备",
            "教育培训": "职业教育", "数字媒体": "数字经济", "文娱用品": "文化传媒",
            "旅游": "旅游酒店", "日用化工": "化学制品", "普钢": "钢铁行业",
            "有色": "有色金属", "服装家纺": "纺织服装", "机械设备": "工程机械",
            "林业": "农牧饲渔", "橡胶": "橡胶制品", "水务": "环保行业",
            "水泥": "水泥建材", "汽车": "汽车整车", "汽车服务": "汽车整车",
            "油服工程": "采掘行业", "油气开采": "石油行业", "渔业": "水产养殖",
            "焦炭加工": "煤炭行业", "煤炭开采": "煤炭行业", "燃气": "天然气",
            "特钢": "钢铁行业", "环保设备": "环保行业", "环境治理": "环保行业",
            "环境监测": "环保行业", "玻璃纤维": "玻璃玻纤", "电信服务": "通信服务",
            "电力设备": "电网设备", "电子": "电子元件", "电子商务": "电商概念",
            "电机制造": "电机", "白色家电": "家电行业", "石油化工": "石油行业",
            "社会服务": "旅游酒店", "种植业": "农业种植", "稀有金属": "有色金属",
            "纺织制造": "纺织服装", "纺织服饰": "纺织服装", "综合类": "综合行业",
            "自动化设备": "专用设备", "航天装备": "航天航空", "航海设备": "船舶制造",
            "航空装备": "航天航空", "装修装饰": "工程建设", "装饰建材": "工程建设",
            "计算机": "计算机设备", "调味品": "调味品概念", "轨交设备": "交运设备",
            "软件服务": "软件开发", "轻工制造": "综合行业", "通信": "通信设备",
            "通信工程": "通信服务", "造纸": "综合行业", "酒店餐饮": "旅游酒店",
            "金属新材料": "有色金属", "非银金融": "证券", "食品加工": "食品饮料",
            "饮料乳品": "食品饮料", "饰品": "美容护理", "饲料": "农牧饲渔",
            "黑色家电": "家电行业", "乘用车": "汽车整车", "云服务": "互联网服务",
            "生物制品": "生物制品", "医疗器械": "医疗器械", "中药": "中药"
        }

    def set_level(self, level):
        self.industry_level = int(level)
        if self.industry_level == 2:
            self.cache_file = os.path.join(self.data_dir, 'sector_sentiment_cache_erji.json')
            # Level 2 list comes from CSV, we might not need to cache the list itself separately like list.json
            self.if_sector_list_cache = None
        else:
            self.cache_file = os.path.join(self.data_dir, 'sector_sentiment_cache.json')
            self.if_sector_list_cache = os.path.join(self.data_dir, 'sector_list.json')

    def _get_em_sector_map(self):
        """
        Fetch EastMoney sector list and build a mapping name->code
        """
        if self.em_sector_map is not None:
            return self.em_sector_map
            
        mapping = {}
        
        # 0. Try loading from local CSV (eastmoney_sector_rzrq.csv)
        try:
            root_dir = os.path.dirname(self.data_dir) # data_dir is root/data
            csv_path = os.path.join(root_dir, 'eastmoney_sector_rzrq.csv')
            if os.path.exists(csv_path):
                try:
                    df = pd.read_csv(csv_path, encoding='utf-8')
                except:
                    df = pd.read_csv(csv_path, encoding='gbk')
                    
                if '板块名称' in df.columns and '板块代码' in df.columns:
                    for _, row in df.iterrows():
                        mapping[str(row['板块名称'])] = str(row['板块代码'])
                    print(f"Loaded {len(mapping)} sectors from local CSV")
        except Exception as e:
            print(f"Error loading local EM CSV: {e}")

        # If we got a good mapping from CSV, we can use it, or merge with API.
        # But API is fresher. Let's try API and merge.
        
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
                    # mapping = {} # Don't clear, just update/overwrite
                    for item in data['result']['data']:
                        mapping[item['BOARD_NAME']] = item['BOARD_CODE']
                    self.em_sector_map = mapping
                    print(f"Loaded {len(mapping)} sectors from EastMoney (CSV + API)")
                    return mapping
        except Exception as e:
            print(f"Failed to load EM sector map from Web: {e}")
            
        if mapping:
            self.em_sector_map = mapping
            return mapping
            
        return {}
    
    def _find_em_code(self, tdx_name):
        mapping = self._get_em_sector_map()
        if not mapping:
            return None
            
        # 0. Check Manual Mapping first
        if tdx_name in self.manual_mapping:
            target_name = self.manual_mapping[tdx_name]
            if target_name in mapping:
                return mapping[target_name]
            # Try appending "行业" or similar if manual mapping target is not exact code key
            # But usually manual_mapping values are EM names.
        
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
        if self.industry_level == 2:
            csv_path = os.path.join(self.data_dir, 'tdx_industry_erji.csv')
            if os.path.exists(csv_path):
                try:
                    try:
                        df = pd.read_csv(csv_path, encoding='utf-8')
                    except UnicodeDecodeError:
                        df = pd.read_csv(csv_path, encoding='gbk')

                    # Determine code column name (compatible with '板块编码' or '二级板块编码')
                    code_col = '二级板块编码' if '二级板块编码' in df.columns else '板块编码'

                    if '二级板块名称' in df.columns and code_col in df.columns:
                        sectors = []
                        for _, row in df.iterrows():
                            item = {'name': str(row['二级板块名称']), 'code': str(row[code_col])}
                            if '一级板块名称' in row and pd.notna(row['一级板块名称']):
                                item['group'] = str(row['一级板块名称'])
                            sectors.append(item)
                        print(f"Loaded {len(sectors)} Level 2 sectors from CSV")
                        return sectors
                except Exception as e:
                    print(f"Error reading Level 2 sector CSV: {e}")
            return []

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
                
                progress = (i + 1) / len(sectors) * 100
                print(f"[{i+1}/{len(sectors)} {progress:5.1f}%] 正在获取 {name:10} ({code})...", end='', flush=True)
                
                # 1. 尝试真实获取
                df = self.fetch_sector_history_raw(code, name)
                
                if df is None or df.empty:
                    print(" 失败 (跳过)")
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
                    company_df['score_margin'] = (company_df['margin_spread'] - company_df['margin_spread_ma60']) * 1000
                    company_df['score_margin'] = company_df['score_margin'].clip(lower=-50, upper=50)
                    
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
                    print(f" 完成 (温度: {latest_entry['temperature']:>6.2f})")

                    # Preserve group info in the results
                    item_data = {
                        'latest': latest_entry,
                        'history': history_list
                    }
                    if 'group' in sector:
                        item_data['group'] = sector['group']
                    
                    results[name] = item_data
                    
                    updated_count += 1
                    
                    if updated_count % 5 == 0:
                         with open(self.cache_file, 'w', encoding='utf-8') as f:
                            json.dump(results, f, ensure_ascii=False, indent=4)

                except Exception as e:
                    print(f" 出错: {e}")
                
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
    import argparse
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    parser = argparse.ArgumentParser(description='Update Sector Sentiment')
    parser.add_argument('--level', type=int, default=1, choices=[1, 2], help='Industry Level (1: Level 1, 2: Level 2)')
    # Allow unknown args passing
    args, unknown = parser.parse_known_args()

    print(f"Running data update Level {args.level}... Python: {sys.executable}")
    ss = SectorSentiment(industry_level=args.level)
    # Explicitly connect first (like debug script) to ensure connectivity before heavy lifting
    print("Testing connection...")
    if not ss._connect_tdx():
        print("Initial connection check failed, but will let update_data retry.")
    
    data = ss.update_data()
    print("Done")
