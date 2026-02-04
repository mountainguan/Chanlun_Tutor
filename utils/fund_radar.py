
import pandas as pd
import akshare as ak
import datetime
import os
import json
import time
import requests
import math

class FundRadar:
    def __init__(self):
        self.data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
        self.cache_dir = os.path.join(self.data_dir, 'fund_radar_cache')
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)
    
    def _get_cache_path(self, name):
        return os.path.join(self.cache_dir, f"{name}_{datetime.datetime.now().strftime('%Y%m%d')}.json")

    def get_sector_flow_ranking(self, days=0):
        """
        Get sector fund flow ranking.
        days: 0 for today, 3, 5, 10 for cumulative.
        """
        indicator_map = {0: "今日", 3: "3日", 5: "5日", 10: "10日"}
        indicator = indicator_map.get(days, "今日")
        
        # 1. Try Akshare First (Detailed Fund Flow)
        try:
            df = ak.stock_sector_fund_flow_rank(indicator=indicator, sector_type="行业资金流")
            if df is not None and not df.empty:
                if indicator == "今日":
                     df.rename(columns={"今日主力净流入-净额": "主力净流入-净额", "今日涨跌幅": "涨跌幅"}, inplace=True)
                elif indicator == "5日":
                     df.rename(columns={"5日主力净流入-净额": "主力净流入-净额", "5日涨跌幅": "涨跌幅"}, inplace=True)
                elif indicator == "10日":
                     df.rename(columns={"10日主力净流入-净额": "主力净流入-净额", "10日涨跌幅": "涨跌幅"}, inplace=True)
                return df
        except Exception as e:
            print(f"Akshare fetch failed ({indicator}): {e}")

        # 2. Try Direct EastMoney API (Fallback for all periods)
        try:
            print(f"Attempting direct API fetch for {indicator}...")
            df_direct = self._fetch_eastmoney_direct(indicator)
            if not df_direct.empty:
                return df_direct
        except Exception as e:
            print(f"Direct API fetch also failed: {e}")
            
        # 3. Fallback to Sina (General Sector Data, No Net Inflow, just Turnover)
        # This works if days=0 (Today) because Sina is real-time spot
        if days == 0:
            try:
                print("Attempting Sina Finance fallback...")
                return self._fetch_sina_sector()
            except Exception as e:
                print(f"Sina fallback failed: {e}")

        return pd.DataFrame() # Empty on error

    def _fetch_sina_sector(self):
        """
        Fetch sector data from Sina Finance.
        Returns cols: 名称, 涨跌幅, 成交额 (instead of Net Inflow)
        """
        try:
            df = ak.stock_sector_spot(indicator="新浪行业")
            if df is not None and not df.empty:
                # Sina columns: label, 板块, 公司家数, 平均价格, 涨跌额, 涨跌幅, 总成交量, 总成交额...
                # Map to our standard
                res = pd.DataFrame()
                res['名称'] = df['板块']
                res['涨跌幅'] = pd.to_numeric(df['涨跌幅'], errors='coerce')
                res['成交额'] = pd.to_numeric(df['总成交额'], errors='coerce')
                
                return res
        except Exception as e:
            print(f"Sina fetch error: {e}")
            return pd.DataFrame()

    def _fetch_eastmoney_direct(self, indicator):
        # Implementation adapted from akshare source code logic
        sector_type_map = {"行业资金流": "2", "概念资金流": "3", "地域资金流": "1"}
        sector_type = "行业资金流" # Fixed
        
        # Mapping from akshare source
        indicator_map = {
            "今日": ["f62", "1", "f12,f14,f2,f3,f62,184,f66,f69,f72,f75,f78,f81,f84,f87,f204,f205,f124"],
            "5日": ["f164", "5", "f12,f14,f2,f109,f164,f165,f166,f167,f168,f169,f170,f171,f172,f173,f257,f258,f124"],
            "10日": ["f174", "10", "f12,f14,f2,f160,f174,f175,f176,f177,f178,f179,f180,f181,f182,f183,f260,f261,f124"],
        }
        
        # 3日 is not in standard akshare supported list for that function
        if indicator == "3日":
             print("3-day flow not fully supported by standard API mapping, logic skipped fallback.")
             return pd.DataFrame()

        if indicator not in indicator_map:
             print(f"Indicator {indicator} not supported in direct fetch fallback.")
             return pd.DataFrame()

        url = "https://push2.eastmoney.com/api/qt/clist/get"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.138 Safari/537.36",
        }
        
        params = {
            "pn": "1",
            "pz": "100",
            "po": "1",
            "np": "1",
            "ut": "b2884a393a59ad64002292a3e90d46a5",
            "fltt": "2",
            "invt": "2",
            "fid": indicator_map[indicator][0],
            "fs": f"m:90 t:{sector_type_map[sector_type]}",
            "stat": indicator_map[indicator][1],
            "fields": indicator_map[indicator][2],
            "rt": "52975239",
            "_": int(time.time() * 1000),
        }

        # Multi-page handling? Akshare does it. We do simple 2 pages (200 sectors usually enough)
        all_diff = []
        for page in range(1, 4): # Max 300 sectors
            params['pn'] = page
            # Try plain http if https fails?
            try:
                r = requests.get(url, params=params, headers=headers, timeout=6)
            except:
                # Try http
                r = requests.get(url.replace("https://", "http://"), params=params, headers=headers, timeout=6)
                
            data_json = r.json()
            if not data_json["data"] or not data_json["data"]["diff"]:
                break
            all_diff.extend(data_json["data"]["diff"])
        
        if not all_diff:
            return pd.DataFrame()
            
        temp_df = pd.DataFrame(all_diff)
        
        res = pd.DataFrame()
        res['名称'] = temp_df['f14']
        
        if indicator == "今日":
            res['主力净流入-净额'] = pd.to_numeric(temp_df['f62'], errors='coerce')
            res['涨跌幅'] = temp_df['f3']
        elif indicator == "5日":
            res['主力净流入-净额'] = pd.to_numeric(temp_df['f164'], errors='coerce')
            res['涨跌幅'] = temp_df['f109']
        elif indicator == "10日":
            res['主力净流入-净额'] = pd.to_numeric(temp_df['f174'], errors='coerce')
            res['涨跌幅'] = temp_df['f160'] 
            
        return res

    def get_market_index(self):
        """Fetch SH Index (000001)"""
        try:
            start_date = (datetime.datetime.now() - datetime.timedelta(days=365)).strftime("%Y%m%d")
            end_date = datetime.datetime.now().strftime("%Y%m%d")
            df = ak.stock_zh_index_daily(symbol="sh000001")
            # Filter ranges? No, keep all for calculation
            return df
        except Exception as e:
            print(f"Error fetching SH Index: {e}")
            return None

    def get_sector_index(self, sector_name):
        """Fetch Sector Index History"""
        try:
            start_date = (datetime.datetime.now() - datetime.timedelta(days=365)).strftime("%Y%m%d")
            end_date = datetime.datetime.now().strftime("%Y%m%d")
            df = ak.stock_board_industry_hist_em(symbol=sector_name, start_date=start_date, end_date=end_date, adjust="qfq")
            return df
        except Exception as e:
            print(f"Error fetching Sector Index ({sector_name}): {e}")
            return None

    def calculate_rs(self, sector_df, market_df):
        """
        Calculate Relative Strength (RS) = Sector Close / Market Close
        Returns a Series or DataFrame with RS.
        """
        if sector_df is None or market_df is None or sector_df.empty or market_df.empty:
            return None
            
        # Merge on date. Ensure datetime types
        s_df = sector_df.copy()
        m_df = market_df.copy()
        
        # Standardize date columns
        if '日期' in s_df.columns:
            s_df['date'] = pd.to_datetime(s_df['日期'])
        if 'date' in m_df.columns:
            m_df['date'] = pd.to_datetime(m_df['date'])
        
        # Set index
        s_df.set_index('date', inplace=True)
        m_df.set_index('date', inplace=True)
        
        # Join
        merged = s_df[['收盘']].join(m_df[['close']], lsuffix='_sector', rsuffix='_market', how='inner')
        
        # RS
        merged['rs'] = merged['收盘'] / merged['close']
        
        # Normalize to start at 1 or similar? Not strictly needed for shape analysis
        return merged

    def get_offensive_defensive_list(self):
        # Based on user input
        offensive = ["半导体", "电子元件", "互联网服务", "软件开发", "通信设备", "计算机设备", "消费电子", "游戏", "汽车整车"] # AI, Robot, Chips
        defensive = ["银行", "电力行业", "煤炭行业", "公路铁路", "港口航运", "农牧饲渔", "食品饮料", "石油行业"] # High yield, stability
        return offensive, defensive

    def analyze_market_status(self, sh_index_df, flow_df):
        """
        Analyze if it's Rotation (调仓) or Escape (撤退).
        """
        # Logic: 
        # Escape: SH Index weak/dropping + High Volume Drop OR Low Volume. 
        #         Defensive sectors UP.
        # Rotation: SH Index oscillating. Money out of High, into Low.
        
        # This is qualitative. We return a dict of indicators.
        status = {
            "index_trend": "Unknown",
            "volume_trend": "Unknown",
            "market_stage": "Unknown"
        }
        
        if sh_index_df is not None and not sh_index_df.empty:
            latest = sh_index_df.iloc[-1]
            prev = sh_index_df.iloc[-2]
            
            # Simple trend
            if latest['close'] > prev['close']:
                status['index_trend'] = "Up"
            else:
                status['index_trend'] = "Down"
                
            # Volume check (user says: escape if volume shrinks heavily or high volume drop)
            vol_ma5 = sh_index_df['volume'].rolling(5).mean().iloc[-1]
            if latest['volume'] < vol_ma5 * 0.8:
                status['volume_trend'] = "Shrinking"
            elif latest['volume'] > vol_ma5 * 1.2:
                status['volume_trend'] = "Expanding"
            else:
                status['volume_trend'] = "Normal"

        return status
