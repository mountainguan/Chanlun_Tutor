
import pandas as pd
import akshare as ak
import datetime
import os
import json
import time

class FundRadar:
    """
    Simplified FundRadar Manager.
    Philosophy: 
    - Cache First: Always prefer cache.
    - Explicit Update: Only update if cache is missing or explicitly requested by background task.
    - No "Force Refresh" via UI unless button clicked.
    """
    
    # Class-level Global Throttle (shared across all instances)
    _fetch_log = {} 
    
    # Retry Scheduling for Background Tasks
    _next_retry_time = {} # Key: date_str, Value: timestamp

    def __init__(self):
        self.data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
        self.cache_dir = os.path.join(self.data_dir, 'fund_radar_cache')
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)
            
    def _get_china_now(self):
        utc_now = datetime.datetime.now(datetime.timezone.utc)
        cn_now = utc_now + datetime.timedelta(hours=8)
        return cn_now

    def _get_cache_path(self, date_str):
        return os.path.join(self.cache_dir, f"sector_sina_{date_str}.json")

    def is_trading_time(self, cn_now=None):
        if cn_now is None:
            cn_now = self._get_china_now()
        
        # Weekends
        if cn_now.weekday() >= 5: return False
        
        t = cn_now.time()
        # 09:30 - 11:30, 13:00 - 15:00
        # Add slight buffer unique to data availability
        # Morning: 9:25 to 11:35
        if datetime.time(9, 25) <= t <= datetime.time(11, 35): return True
        # Afternoon: 12:55 to 15:05
        if datetime.time(12, 55) <= t <= datetime.time(15, 5): return True
        return False

    def load_from_cache(self, date_str):
        """
        Purely load data from cache file. No fetching side effects.
        Returns: (data_dict, file_exists, file_mtime)
        """
        path = self._get_cache_path(date_str)
        if not os.path.exists(path):
            return None, False, 0
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content: return None, True, 0 # File exists but empty
                
                data = json.loads(content)
                # Normalize legacy list format to dict
                if isinstance(data, list):
                    data = {"sina_sectors": data, "ths_sectors": [], "market": None, "update_time": "00:00:00"}
                
                return data, True, os.path.getmtime(path)
        except Exception as e:
            print(f"[FundRadar] Cache read error {path}: {e}")
            return None, True, 0 # Treat as exists-but-corrupt

    def fetch_and_save(self, date_str):
        """
        Execute the actual network fetch and save to disk.
        Returns: (data, success_bool)
        """
        print(f"[FundRadar] Executing NETWORK FETCH for {date_str}...")
        
        try:
            # 1. Fetch Data
            df_sina = self._fetch_sina_sector()
            df_ths = self._fetch_ths_sector()
            market_snap = self.get_market_snapshot()
            
            # Check for critical data failure (at least Sina or THS should exist)
            if df_sina.empty and df_ths.empty:
                print("[FundRadar] Both Sina and THS data fetch failed (empty).")
                return None, False

            # 2. Prepare Data Structure
            now_str = self._get_china_now().strftime('%H:%M:%S')
            
            data = {
                "sina_sectors": df_sina.to_dict(orient='records') if not df_sina.empty else [],
                "ths_sectors": df_ths.to_dict(orient='records') if not df_ths.empty else [],
                "market": market_snap,
                "update_time": now_str
            }
            
            # If market snap fetched, ensure it has timestamp
            if market_snap: 
                data['market']['update_time'] = now_str
                data['update_time'] = now_str # Root level update time

            # 3. Save to Disk (Atomic-ish)
            path = self._get_cache_path(date_str)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            return data, True
            
        except Exception as e:
            print(f"[FundRadar] Fetch/Save failed: {e}")
            return None, False

    def get_data(self, date_str, mode='READ_CACHE'):
        """
        Main Entry Point.
        Modes:
        - 'READ_CACHE': Try cache. If missing, fetch. 
        - 'FORCE_UPDATE': Ignore cache logic, force fetch.
        - 'BACKGROUND_AUTO': Logic for background task - checks interval & failure policy.
        """
        cn_now = self._get_china_now()
        today_str = cn_now.strftime('%Y-%m-%d')
        is_today = (date_str == today_str)

        # 1. Load Cache
        cache_data, cache_exists, cache_mtime = self.load_from_cache(date_str)
        
        # 2. Determine Action
        should_fetch = False
        
        if mode == 'FORCE_UPDATE':
            if is_today:
                print(f"[FundRadar] Force update requested for {date_str}")
                should_fetch = True
            else:
                print(f"[FundRadar] Cannot force update past date {date_str}")
                
        elif not cache_exists:
            # If cache missing completely -> Must Fetch (if Today)
            if is_today:
                print(f"[FundRadar] Cache missing for {date_str}, fetching...")
                should_fetch = True
            else:
                print(f"[FundRadar] History missing for {date_str}, nothing to fetch.")
                
        elif mode == 'BACKGROUND_AUTO':
            if is_today:
                # A. Check Retry Throttle
                retry_ts = FundRadar._next_retry_time.get(date_str, 0)
                if time.time() < retry_ts:
                    # Still in cooldown
                    pass 
                else:
                    # B. Check Stale Cache
                    is_stale = False
                    if cache_data:
                        last_update_str = cache_data.get('update_time', '00:00:00')
                        try:
                            # Construct DT from time string and today's date
                            # Use simple seconds comparison for robustness
                            now_time_obj = datetime.datetime.strptime(cn_now.strftime('%H:%M:%S'), "%H:%M:%S")
                            last_time_obj = datetime.datetime.strptime(last_update_str, "%H:%M:%S")
                            
                            age_seconds = (now_time_obj - last_time_obj).total_seconds()
                            if age_seconds < 0: age_seconds += 86400 # wrap around
                            
                            if age_seconds > 1800: # 30 mins
                                print(f"[FundRadar] Background: Cache is old ({age_seconds/60:.1f} min).")
                                is_stale = True
                        except:
                            is_stale = True
                    else:
                        is_stale = True # Exists but None/Empty -> Stale

                    if is_stale:
                        # User requirement: "30分钟机制只在中国A股，股市开始过程才进行加载"
                        if self.is_trading_time(cn_now):
                            print(f"[FundRadar] Background: Triggering update (Trading Time + Stale).")
                            should_fetch = True
            
        elif mode == 'READ_CACHE':
            # Default UI Mode
            # Just return cache if exists.
            pass
            
        # 3. Execution (with Global Throttle)
        if should_fetch:
            throttle_key = f"global_fetch_{date_str}"
            # Check global throttle (prevent burst)
            if self._check_throttle(throttle_key, cooldown=10): 
                new_data, success = self.fetch_and_save(date_str)
                if success: 
                     cache_data = new_data
                     # Clear retry time on success
                     if date_str in FundRadar._next_retry_time:
                         del FundRadar._next_retry_time[date_str]
                else:
                    print(f"[FundRadar] Fetch failed.")
                    # If this was a background attempt, schedule retry
                    if mode == 'BACKGROUND_AUTO':
                        print(f"[FundRadar] Background: Scheduling retry in 5 mins.")
                        FundRadar._next_retry_time[date_str] = time.time() + 300
            else:
                 print(f"[FundRadar] Fetch suppressed by global throttle (10s).")

        # 4. Return Formatted Data
        if not cache_data:
            return pd.DataFrame(), pd.DataFrame(), None

        df_sina = pd.DataFrame(cache_data.get('sina_sectors', []))
        df_ths = pd.DataFrame(cache_data.get('ths_sectors', []))
        market = cache_data.get('market')
        
        return df_sina, df_ths, market

    def _check_throttle(self, key, cooldown=60):
        now = time.time()
        last = FundRadar._fetch_log.get(key, 0)
        if now - last > cooldown:
            FundRadar._fetch_log[key] = now
            return True
        return False

    # --- Fetch Implementations (Keep existing logic) ---
    def _fetch_sina_sector(self):
        try:
            df = ak.stock_sector_spot(indicator="新浪行业")
            if df is not None and not df.empty:
                res = pd.DataFrame()
                res['名称'] = df['板块']
                res['涨跌幅'] = pd.to_numeric(df['涨跌幅'], errors='coerce')
                res['成交额'] = pd.to_numeric(df['总成交额'], errors='coerce')
                return res
        except: return pd.DataFrame()

    def _fetch_ths_sector(self):
        try:
            df = ak.stock_board_industry_summary_ths()
            if df is not None and not df.empty:
                res = pd.DataFrame()
                res['名称'] = df['板块']
                res['涨跌幅'] = pd.to_numeric(df['涨跌幅'], errors='coerce')
                res['净流入'] = pd.to_numeric(df['净流入'], errors='coerce')
                res['总成交额'] = pd.to_numeric(df['总成交额'], errors='coerce')
                return res
        except: return pd.DataFrame()

    def get_market_snapshot(self):
        try:
            df = ak.stock_zh_index_spot_sina()
            if df is not None and not df.empty:
                row = df[df['代码'] == 'sh000001']
                if not row.empty:
                    return {
                        'change_pct': float(row.iloc[0]['涨跌幅']),
                        'amount': float(row.iloc[0]['成交额']), 
                        'price': float(row.iloc[0]['最新价']),
                        'name': '上证指数'
                    }
        except: pass
        return None

    def get_offensive_defensive_list(self):
        # Keep existing list
        offensive = ["半导体", "分立器件", "电子元件", "电子器件", "电子信息", "光学光电子", "电子化学品", "软件开发", "互联网服务", "计算机设备", "IT服务", "通信设备", "通信服务", "消费电子", "游戏", "文化传媒", "传媒娱乐", "互联网视频", "互联网广告", "航天航空", "飞机制造", "卫星互联网", "商业航天", "机器人", "减速器", "工业母机", "通用设备", "专用设备", "仪器仪表", "发电设备", "光伏设备", "风电设备", "储能", "氢能", "电池", "能源金属", "动力电池", "固态电池", "汽车整车", "汽车制造", "汽车零部件", "摩托车", "新能源汽车", "生物制药", "生物制品", "创新药", "医疗器械", "医疗服务", "次新股", "旅游酒店", "餐饮", "教育", "玻璃玻纤"]
        defensive = ["银行", "保险", "证券", "多元金融", "金融行业", "电力行业", "煤炭行业", "石油行业", "石油加工", "采掘行业", "燃气", "供水供气", "公路铁路", "公路桥梁", "交通运输", "港口航运", "码头", "机场", "跨境物流", "仓储物流", "建筑建材", "建筑装饰", "水泥行业", "钢铁行业", "工程建设", "食品饮料", "食品行业", "饮料制造", "酿酒行业", "农牧饲渔", "农林牧渔", "种植业", "林业", "渔业", "饲料", "家电行业", "白色家电", "厨卫电器", "中药", "医药商业", "医药制造", "化学制药", "房地产开发", "房地产服务", "零售", "百货商超", "环保行业", "水务", "园林绿化", "纺织服装", "服装家纺", "轻工制造", "造纸印刷", "装修装饰", "化纤行业", "化学制品"]
        return offensive, defensive
