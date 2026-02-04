
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
            tuple: (DataFrame (Sectors), dict (Market Snapshot or None))
        """
        today_str = datetime.datetime.now().strftime('%Y-%m-%d')
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
                    df = pd.DataFrame()

                    # Handle new structure vs old structure
                    if isinstance(data, dict) and 'sectors' in data:
                        # New structure: {'sectors': [], 'market': {}}
                        df = pd.DataFrame(data['sectors'])
                        market_snap = data.get('market')
                    elif isinstance(data, list):
                        # Old structure: List of sectors
                        df = pd.DataFrame(data)
                        market_snap = None # No market data in old cache
                        
                    return df, market_snap
            except Exception as e:
                print(f"Error reading cache {cache_path}: {e}")
        
        # 3. If no cache, check if we can fetch
        # We can ONLY fetch if date requested is TODAY. 
        if date_str == today_str:
            print(f"Fetching fresh data for {date_str}...")
            df = self._fetch_sina_sector()
            market_snap = self.get_market_snapshot()
            
            if not df.empty:
                # Save to cache with market data
                try:
                    # Convert to list of dicts for JSON
                    cache_data = {
                        "sectors": df.to_dict(orient='records'),
                        "market": market_snap
                    }
                    with open(cache_path, 'w', encoding='utf-8') as f:
                        json.dump(cache_data, f, ensure_ascii=False, indent=2)
                    return df, market_snap
                except Exception as e:
                    print(f"Failed to save cache: {e}")
                    return df, market_snap
            else:
                return pd.DataFrame(), None
        
        # If date is in the past and no cache, we can't get it.
        return pd.DataFrame(), None

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
        # Based on user input, expanded for better coverage (Includes both EM and Sina names)
        offensive = [
            # Eastmoney Names
            "半导体", "电子元件", "互联网服务", "软件开发", "通信设备", "计算机设备", 
            "消费电子", "游戏", "汽车整车", "光伏设备", "电池", "能源金属", "航天航空",
            "光学光电子", "电子化学品",
            # Sina Names
            "电子器件", "电子信息", "传媒娱乐", "飞机制造", "电器行业", "仪器仪表", 
            "汽车制造", "生物制药", "发电设备", "次新股"
        ] 
        defensive = [
            # Eastmoney Names
            "银行", "电力行业", "煤炭行业", "公路铁路", "港口航运", "农牧饲渔", 
            "食品饮料", "石油行业", "中药", "医药商业", "保险", "证券", 
            "家电行业", "酿酒行业", "工程建设",
            # Sina Names
            "公路桥梁", "供水供气", "金融行业", "农林牧渔", "食品行业", 
            "交通运输", "建筑建材", "水泥行业", "钢铁行业"
        ] 
        return offensive, defensive
