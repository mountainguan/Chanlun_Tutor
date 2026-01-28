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

    def _connect_tdx(self):
        try:
            from pytdx.hq import TdxHq_API
            self.api = TdxHq_API()
            ips = [
                ('218.75.126.9', 7709),
                ('115.238.56.198', 7709),
                ('60.191.117.167', 7709),
                ('119.147.212.81', 7709),
                ('119.147.212.80', 7709),
                ('124.71.187.100', 7709)
            ]
            for ip, port in ips:
                try:
                    if self.api.connect(ip, port, time_out=8):
                        print(f"Connected to TDX server: {ip}:{port}")
                        return True
                except:
                    pass
            print("Failed to connect to any TDX server")
            return False
        except Exception as e:
            print(f"TDX init error: {e}")
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

        # Connect to TDX once
        if not self._connect_tdx():
            print("Warning: Could not connect to TDX, fetching might fail.")

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
            
            print(f"Updating data for {len(sectors)} sectors...")
            
            updated_count = 0
            
            # 只需要简单的计数，不再因为失败而完全停止，而是转为 Mock
            for i, sector in enumerate(sectors):
                name = sector['name']
                code = sector['code']
                
                # Skip if already updated today
                if name in cache_data and cache_data[name].get('date') == today_str:
                    continue
                
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
                    if len(df) < 20: # 至少需要一定的数据量
                        continue
                        
                    turnover_values = df['amount'].dropna().values
                    if len(turnover_values) == 0: continue
                    
                    current_turnover = turnover_values[-1]
                    last_date = df.index[-1].strftime('%Y-%m-%d')
                    
                    # 如果是 Mock 数据，稍微调整下日期到今天
                    if is_mock:
                        last_date = today_str

                    margin_values = turnover_values 
                    current_margin = current_turnover
                    
                    # Quantiles
                    q_percents = np.linspace(0, 100, 201)
                    turnover_quantiles = np.percentile(turnover_values, q_percents).tolist()
                    
                    # Rank
                    from scipy.stats import percentileofscore
                    rank_turnover = percentileofscore(turnover_values, current_turnover)
                    rank_margin = percentileofscore(margin_values, current_margin)
                    
                    # Formula
                    score = (rank_margin * 0.2) + (rank_turnover * 1.0)
                    final_temp = (score / 120) * 100
                    
                    results[name] = {
                        'date': last_date,
                        'temperature': round(final_temp, 2),
                        'turnover': float(current_turnover),
                        'rank_turnover': float(rank_turnover),
                        'rank_margin': float(rank_margin),
                        'turnover_quantiles': [float(x) for x in turnover_quantiles],
                        'is_mock': is_mock # 标记该条数据是否为模拟
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
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    ss = SectorSentiment()
    data = ss.update_data()
    print("Done")
