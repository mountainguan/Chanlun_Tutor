
import pandas as pd
import akshare as ak
import datetime
import os
import json
import time

class FundRadar:
    def __init__(self):
        self.data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
        self.cache_dir = os.path.join(self.data_dir, 'fund_radar_cache')
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)
            
    def _get_cache_file_path(self, date_str):
        """
        Get the path for a specific date's cache file.
        Format: sector_sina_YYYY-MM-DD.json
        """
        return os.path.join(self.cache_dir, f"sector_sina_{date_str}.json")

    def get_sector_data_by_date(self, date_str, force_refresh=False):
        """
        Get sector data for a specific date. 
        Auto-fetches if date is today and no cache exists.
        
        Args:
            date_str (str): "YYYY-MM-DD"
            force_refresh (bool): If True, delete existing cache and re-fetch (only works if date is Today).
            
        Returns:
            tuple: (DataFrame (Sina Sectors), DataFrame (THS Sectors), dict (Market Snapshot or None))
        """
        # Ensure Today is based on China Time (UTC+8)
        utc_now = datetime.datetime.now(datetime.timezone.utc)
        cn_now = utc_now + datetime.timedelta(hours=8)
        today_str = cn_now.strftime('%Y-%m-%d')
        
        cache_path = self._get_cache_file_path(date_str)
        
        # 1. Handle Force Refresh
        if force_refresh and date_str == today_str:
            if os.path.exists(cache_path):
                try:
                    os.remove(cache_path)
                    print(f"Cache cleared for {date_str}")
                except Exception as e:
                    print(f"Failed to clear cache: {e}")
        
        # 2. Try Loading from Cache
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    market_snap = None
                    df_sina = pd.DataFrame()
                    df_ths = pd.DataFrame()
                    needs_update = False

                    # Handle new structure vs old structure
                    if isinstance(data, dict):
                        market_snap = data.get('market')
                        
                        # Compatible with new structure (sina_sectors) and old (sectors)
                        if 'sina_sectors' in data:
                            df_sina = pd.DataFrame(data['sina_sectors'])
                        elif 'sectors' in data:
                            df_sina = pd.DataFrame(data['sectors'])
                        
                        # --- Backfill Logic ---
                        if 'ths_sectors' in data:
                            df_ths = pd.DataFrame(data['ths_sectors'])
                        elif date_str == today_str:
                            # Cache exists but missing THS (e.g. created by old version). 
                            # Update it now for convenience.
                            print(f"Backfilling THS data to cache for {date_str}...")
                            df_ths = self._fetch_ths_sector()
                            if not df_ths.empty:
                                data['ths_sectors'] = df_ths.to_dict(orient='records')
                                needs_update = True
                        
                        if market_snap is None and date_str == today_str:
                            market_snap = self.get_market_snapshot()
                            data['market'] = market_snap
                            needs_update = True
                        
                        # Return update_time if present
                        market_snap = market_snap or {}
                        if 'update_time' in data:
                            market_snap['update_time'] = data['update_time']
                            
                    elif isinstance(data, list):
                        # Very old structure: List of sectors
                        df_sina = pd.DataFrame(data)
                        # Migration to dict structure
                        if date_str == today_str:
                            print(f"Migrating cache for {date_str} to new dictionary format...")
                            df_ths = self._fetch_ths_sector()
                            market_snap = self.get_market_snapshot()
                            # Use China Time (UTC+8)
                            utc_now = datetime.datetime.now(datetime.timezone.utc)
                            cn_now = utc_now + datetime.timedelta(hours=8)
                            now_time = cn_now.strftime('%H:%M:%S')
                            
                            data = {
                                "sina_sectors": data,
                                "ths_sectors": df_ths.to_dict(orient='records') if not df_ths.empty else [],
                                "market": market_snap,
                                "update_time": now_time
                            }
                            if market_snap: market_snap['update_time'] = now_time
                            needs_update = True
                    
                    # Persist backfill changes
                    if needs_update:
                        try:
                            # Ensure we have update_time on save
                            if 'update_time' not in data and date_str == today_str:
                                # Use China Time (UTC+8)
                                utc_now = datetime.datetime.now(datetime.timezone.utc)
                                cn_now = utc_now + datetime.timedelta(hours=8)
                                data['update_time'] = cn_now.strftime('%H:%M:%S')

                            with open(cache_path, 'w', encoding='utf-8') as f:
                                json.dump(data, f, ensure_ascii=False, indent=2)
                        except Exception as e:
                            print(f"Failed to update existing cache: {e}")
                        
                    return df_sina, df_ths, market_snap
            except Exception as e:
                print(f"Error reading cache {cache_path}: {e}")
        
        # 3. If no cache, check if we can fetch
        if date_str == today_str:
            print(f"Fetching fresh data for {date_str}...")
            df_sina = self._fetch_sina_sector()
            df_ths = self._fetch_ths_sector()
            market_snap = self.get_market_snapshot()
            
            # Use China Time (UTC+8)
            utc_now = datetime.datetime.now(datetime.timezone.utc)
            cn_now = utc_now + datetime.timedelta(hours=8)
            now_time = cn_now.strftime('%H:%M:%S')
            
            # Save to cache with market data
            try:
                cache_data = {
                    "sina_sectors": df_sina.to_dict(orient='records') if not df_sina.empty else [],
                    "ths_sectors": df_ths.to_dict(orient='records') if not df_ths.empty else [],
                    "market": market_snap,
                    "update_time": now_time
                }
                
                if market_snap:
                    market_snap['update_time'] = now_time
                
                # Validation: Only save if we got at least something
                if not df_sina.empty or not df_ths.empty:
                    with open(cache_path, 'w', encoding='utf-8') as f:
                        json.dump(cache_data, f, ensure_ascii=False, indent=2)
                        
                return df_sina, df_ths, market_snap
            except Exception as e:
                print(f"Failed to save cache: {e}")
                return df_sina, df_ths, market_snap
        
        # If date is in the past and no cache, we can't get it.
        return pd.DataFrame(), pd.DataFrame(), None

    def _fetch_sina_sector(self):
        """
        Fetch sector data from Sina Finance (Spot Data).
        Returns cols: 名称, 涨跌幅, 成交额
        """
        try:
            # Using stock_sector_spot for real-time sector data
            df = ak.stock_sector_spot(indicator="新浪行业")
            if df is not None and not df.empty:
                res = pd.DataFrame()
                res['名称'] = df['板块']
                res['涨跌幅'] = pd.to_numeric(df['涨跌幅'], errors='coerce')
                res['成交额'] = pd.to_numeric(df['总成交额'], errors='coerce')
                return res
        except Exception as e:
            print(f"Sina fetch error: {e}")
            return pd.DataFrame()
            
    def _fetch_ths_sector(self):
        """
        Fetch sector data from Tonghuashun (THS).
        Useful for Net Inflow (Main Force) data which Sina lacks.
        Returns cols: 名称, 涨跌幅, 净流入, 总成交额, 领涨股, 代码
        """
        try:
            df = ak.stock_board_industry_summary_ths()
            if df is not None and not df.empty:
                res = pd.DataFrame()
                res['名称'] = df['板块']
                res['涨跌幅'] = pd.to_numeric(df['涨跌幅'], errors='coerce')
                res['净流入'] = pd.to_numeric(df['净流入'], errors='coerce')
                res['总成交额'] = pd.to_numeric(df['总成交额'], errors='coerce')
                # Add extra columns for future convenience
                res['领涨股'] = df['领涨股'] if '领涨股' in df.columns else ""
                res['代码'] = df['代码'] if '代码' in df.columns else ""
                return res
        except Exception as e:
            print(f"THS fetch error: {e}")
            return pd.DataFrame()

    def get_market_snapshot(self):
        """Fetch real-time snapshot for SH Index"""
        try:
            df = ak.stock_zh_index_spot_sina()
            if df is not None and not df.empty:
                sh_row = df[df['代码'] == 'sh000001']
                if not sh_row.empty:
                    return {
                        'change_pct': float(sh_row.iloc[0]['涨跌幅']),
                        'amount': float(sh_row.iloc[0]['成交额']), 
                        'price': float(sh_row.iloc[0]['最新价']),
                        'name': '上证指数'
                    }
        except Exception as e:
            print(f"Error fetching market snapshot: {e}")
        return None

    def get_offensive_defensive_list(self):
        """
        Returns categorized sector names for Offense (Growth/Tech) vs Defense (Value/Utilities).
        Merged names from multiple sources (Sina, THS, EM) to ensure match coverage.
        """
        offensive = [
            # TMT & Tech
            "半导体", "分立器件", "电子元件", "电子器件", "电子信息", "光学光电子", "电子化学品",
            "软件开发", "互联网服务", "计算机设备", "IT服务", "通信设备", "通信服务", "消费电子",
            # Media & Entertainment
            "游戏", "文化传媒", "传媒娱乐", "互联网视频", "互联网广告", 
            # High-end Manufacturing
            "航天航空", "飞机制造", "卫星互联网", "商业航天", "机器人", "减速器", "工业母机", 
            "通用设备", "专用设备", "仪器仪表", "发电设备", 
            # New Energy & Vehicles
            "光伏设备", "风电设备", "储能", "氢能", "电池", "能源金属", "动力电池", "固态电池",
            "汽车整车", "汽车制造", "汽车零部件", "摩托车", "新能源汽车",
            # Healthcare (Growth part)
            "生物制药", "生物制品", "创新药", "医疗器械", "医疗服务",
            # Hot Themes & Other Growth
            "次新股", "旅游酒店", "餐饮", "教育", "玻璃玻纤"
        ] 
        defensive = [
            # Financials
            "银行", "保险", "证券", "多元金融", "金融行业",
            # Utilities & Energy
            "电力行业", "煤炭行业", "石油行业", "石油加工", "采掘行业", "燃气", "供水供气",
            # Infrastructure & Transportation
            "公路铁路", "公路桥梁", "交通运输", "港口航运", "码头", "机场", "跨境物流", "仓储物流",
            "建筑建材", "建筑装饰", "水泥行业", "钢铁行业", "工程建设",
            # Consumer Staples
            "食品饮料", "食品行业", "饮料制造", "酿酒行业", "农牧饲渔", "农林牧渔", "种植业", 
            "林业", "渔业", "饲料", "家电行业", "白色家电", "厨卫电器",
            # Traditional Health & Value
            "中药", "医药商业", "医药制造", "化学制药",
            # Others
            "房地产开发", "房地产服务", "零售", "百货商超", "环保行业", "水务", "园林绿化",
            "纺织服装", "服装家纺", "轻工制造", "造纸印刷", "装修装饰", "化纤行业", "化学制品"
        ] 
        return offensive, defensive
