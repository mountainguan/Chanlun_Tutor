
import os
import json
import time
import datetime
import pandas as pd
import akshare as ak
import numpy as np
from utils.simulator_logic import calculate_macd, calculate_rsi, process_baohan, find_bi, calculate_bollinger_bands, calculate_bi_and_centers
from utils.fund_radar import FundRadar

class SectorAnalyzer:
    CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'sector_history_cache')
    
    # EM Sector Name to THS Sector Name Mapping (Partial)
    # Most names match, but some need manual mapping
    EM_TO_THS_MAP = {
        '贸易行业': '贸易',
        '有色金属': '工业金属',
        '食品饮料': '食品加工制造',
        '农牧饲渔': '养殖业',
        '医药制造': '化学制药',
        '电子元件': '元件',
        '通信行业': '通信设备',
        '家电行业': '白色家电',
        '纺织服装': '纺织制造',
        '旅游酒店': '旅游及酒店',
        '医疗行业': '医疗服务',
        '公用事业': '电力',
        '酿酒行业': '白酒',
        '石油行业': '石油加工贸易',
        '化工行业': '化学制品',
        '工程建设': '建筑装饰',
        '交运设备': '轨交设备',
        '贵金属': '贵金属',
        '钢铁行业': '钢铁',
        '煤炭行业': '煤炭开采加工',
        '玻璃玻纤': '建筑材料',
        '化肥行业': '农化制品',
        '船舶制造': '军工装备',
        '航天航空': '军工装备',
        '文化传媒': '文化传媒',
        '互联网服务': 'IT服务',
        '软件开发': '软件开发',
        '游戏': '游戏',
        '计算机设备': '计算机设备',
        '半导体': '半导体',
        '消费电子': '消费电子',
        '光学光电子': '光学光电子',
        '电池': '电池',
        '光伏设备': '光伏设备',
        '风电设备': '风电设备',
        '电网设备': '电网设备'
    }

    def __init__(self):
        if not os.path.exists(self.CACHE_DIR):
            os.makedirs(self.CACHE_DIR)
        self.ths_names = None
        # Cache for real-time flow data to avoid hammering API per sector
        self._flow_cache = None
        self._flow_cache_time = 0
        self._flow_cache_ttl = 60 # 60 seconds

    def _get_realtime_flow_df(self):
        """Fetch real-time fund flow data with caching and fallback."""
        now = time.time()
        if self._flow_cache is not None and (now - self._flow_cache_time) < self._flow_cache_ttl:
            return self._flow_cache
            
        # 1. Try EM Fund Flow (Preferred for Index Value)
        try:
            # Use FundRadar's robust rate-limited caller to handle anti-crawl
            # symbol="即时" is usually the default
            df = FundRadar._rate_limited_call(
                ak.stock_fund_flow_industry, 
                symbol="即时", 
                _label="SectorAnalyzer_Realtime"
            )
            
            if df is not None and not df.empty:
                self._flow_cache = df
                self._flow_cache_time = now
                return df
        except Exception as e:
            print(f"[SectorAnalyzer] EM Real-time flow fetch failed: {e}")
            
        # 2. Fallback to THS Industry Summary (For Change % only)
        # Only use this if EM failed.
        print("[SectorAnalyzer] Falling back to THS Industry Summary...")
        try:
            df_fallback = FundRadar._rate_limited_call(
                ak.stock_board_industry_summary_ths,
                _label="SectorAnalyzer_Fallback"
            )
            if df_fallback is not None and not df_fallback.empty:
                # Mark as fallback data to handle differently
                df_fallback['_is_fallback_ths'] = True
                self._flow_cache = df_fallback
                self._flow_cache_time = now
                return df_fallback
        except Exception as e:
             print(f"[SectorAnalyzer] THS Fallback fetch failed: {e}")

        return None

    def _get_ths_name(self, em_name):
        """Map EM name to THS name."""
        name = str(em_name).strip()
        # 1. Direct Map
        if name in self.EM_TO_THS_MAP:
            return self.EM_TO_THS_MAP[name]
        
        # 2. Suffix removal
        for suffix in ['行业', '概念', '板块']:
            if name.endswith(suffix):
                norm = name[:-len(suffix)]
                if norm in self.EM_TO_THS_MAP:
                    return self.EM_TO_THS_MAP[norm]
        
        # 3. Return original (hope it works)
        return name

    def fetch_history(self, sector_name, days=180, force_update=False):
        """
        Fetch sector history (Daily K-Line) from THS via Akshare.
        Cache results for 24 hours.
        """
        ths_name = self._get_ths_name(sector_name)
        cache_file = os.path.join(self.CACHE_DIR, f"{ths_name}.json")
        
        # Check cache
        if not force_update and os.path.exists(cache_file):
            try:
                mtime = os.path.getmtime(cache_file)
                if (time.time() - mtime) < 24 * 3600: # 24h cache
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        return pd.DataFrame(data)
            except Exception as e:
                print(f"[SectorAnalyzer] Cache read error: {e}")

        # Fetch from API
        try:
            end_date = datetime.datetime.now().strftime("%Y%m%d")
            start_date = (datetime.datetime.now() - datetime.timedelta(days=days)).strftime("%Y%m%d")
            
            # Using THS Index API
            df = ak.stock_board_industry_index_ths(symbol=ths_name, start_date=start_date, end_date=end_date)
            
            if df is not None and not df.empty:
                # Normalize columns
                # THS returns: 日期, 开盘价, 最高价, 最低价, 收盘价, ...
                df = df.rename(columns={
                    '日期': 'date',
                    '开盘价': 'open',
                    '最高价': 'high',
                    '最低价': 'low',
                    '收盘价': 'close',
                    '成交量': 'volume',
                    '成交额': 'amount'
                })
                
                # Convert to list of dicts for JSON serialization
                # Ensure date is string
                if 'date' in df.columns:
                    df['date'] = df['date'].astype(str)
                
                records = df.to_dict('records')
                with open(cache_file, 'w', encoding='utf-8') as f:
                    json.dump(records, f, ensure_ascii=False)
                
                return df
        except Exception as e:
            print(f"[SectorAnalyzer] Fetch error for {sector_name} ({ths_name}): {e}")
            return None

    def analyze(self, sector_name):
        """
        Perform technical analysis on the sector.
        Returns a dict with indicators and judgment.
        """
        df = self.fetch_history(sector_name)
        
        # Check if we need to append or update real-time data
        # If df last date is not today, try to fetch spot. 
        # If it IS today, it might be delayed/stale (THS API issue), so we update it with EM spot.
        if df is not None and not df.empty:
            last_date_str = str(df.iloc[-1]['date'])
            # Normalize date string (e.g., 2026-02-24 or 20260224)
            last_date_str = last_date_str.replace('-', '')
            
            today_str = datetime.datetime.now().strftime("%Y%m%d")
            
            # Try to get spot data to Ensure Freshness
            flow_df = self._get_realtime_flow_df()
            if flow_df is not None:
                ths_name = self._get_ths_name(sector_name)
                current_price = None
                
                # Check source type
                is_fallback = flow_df.attrs.get('is_fallback_ths', False) or '_is_fallback_ths' in flow_df.columns
                
                if is_fallback:
                    # THS Fallback Logic: Use Change % to estimate price
                    # THS Summary columns: ['板块', '涨跌幅', ...]
                    target = flow_df[flow_df['板块'] == ths_name]
                    if not target.empty:
                        try:
                            pct_change = float(target.iloc[0]['涨跌幅'])
                            # Get yesterday's close from history df
                            # If today is already in df (stale), use yesterday (index -2) or just use current close if it's actually yesterday's data?
                            # last_date_str is df.iloc[-1]['date']
                            
                            # If last_date_str IS today, then df[-1] is potentially STALE today data or initialized data.
                            # We should use df[-2] if available, or just trust df[-1] is "yesterday" if date mismatch?
                            
                            # Actually, if we are in this block, we want to UPDATE df[-1] or APPEND new row.
                            # So we need a base price.
                            
                            if last_date_str == today_str:
                                # df[-1] is today (stale/partial). We need yesterday's close.
                                if len(df) > 1:
                                    last_close = df.iloc[-2]['close']
                                else:
                                    last_close = df.iloc[-1]['open'] # Fallback
                            else:
                                # df[-1] is yesterday.
                                last_close = df.iloc[-1]['close']
                                
                            current_price = last_close * (1 + pct_change / 100)
                        except Exception as e:
                            print(f"[SectorAnalyzer] Fallback calculation failed for {sector_name}: {e}")
                else:
                    # EM Standard Logic: Use Direct Index Value
                    # flow_df['行业'] contains EM names.
                    target = pd.DataFrame()
                    
                    # 1. Direct match (EM name == THS name)
                    if ths_name in flow_df['行业'].values:
                        target = flow_df[flow_df['行业'] == ths_name]
                    else:
                        # 2. Reverse Map lookup
                        found_em_name = None
                        for em_k, ths_v in self.EM_TO_THS_MAP.items():
                            if ths_v == ths_name:
                                found_em_name = em_k
                                break
                        if found_em_name and found_em_name in flow_df['行业'].values:
                            target = flow_df[flow_df['行业'] == found_em_name]
                            
                    if not target.empty:
                        try:
                            current_price = float(target.iloc[0]['行业指数'])
                        except:
                            pass

                if current_price is not None:
                    try:
                        if last_date_str == today_str:
                            # Update existing Today row
                            idx = df.index[-1]
                            df.at[idx, 'close'] = current_price
                            # Update High/Low
                            current_high = df.at[idx, 'high']
                            current_low = df.at[idx, 'low']
                            
                            if pd.isna(current_high): df.at[idx, 'high'] = current_price
                            else: df.at[idx, 'high'] = max(current_high, current_price)
                                
                            if pd.isna(current_low): df.at[idx, 'low'] = current_price
                            else: df.at[idx, 'low'] = min(current_low, current_price)
                                
                            if pd.isna(df.at[idx, 'open']):
                                df.at[idx, 'open'] = current_price
                        else:
                            # Append new row
                            new_row = pd.DataFrame([{
                                'date': datetime.datetime.now().strftime("%Y-%m-%d"),
                                'close': current_price,
                                'open': current_price,
                                'high': current_price,
                                'low': current_price,
                                'volume': 0,
                                'amount': 0
                            }])
                            df = pd.concat([df, new_row], ignore_index=True)
                            
                    except Exception as e:
                        print(f"[SectorAnalyzer] Failed to update/append spot for {sector_name}: {e}")

        if df is None or df.empty:
            return {
                "status": "No Data",
                "color": "gray",
                "summary": "无法获取历史数据",
                "details": "无法获取历史数据",
                "macd_signal": 0,
                "rsi_val": 50,
                "macd": None,
                "rsi": None,
                "last_rsi": 50,
                "bi_points": [],
                "short_term": {"status": "-", "color": "text-gray-400", "signal": "-"},
                "mid_long_term": {"status": "-", "color": "text-gray-400", "signal": "-"}
            }
            
        # Ensure numeric types
        for col in ['open', 'high', 'low', 'close']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        closes = df['close'].tolist()
        
        # 1. Indicators
        macd = calculate_macd(closes)
        rsi = calculate_rsi(closes)
        last_rsi = rsi[-1] if rsi else 50
        boll = calculate_bollinger_bands(closes)
        
        # MA Calculation
        series_close = pd.Series(closes)
        ma5 = series_close.rolling(window=5).mean().fillna(0).tolist()
        ma10 = series_close.rolling(window=10).mean().fillna(0).tolist()
        ma20 = series_close.rolling(window=20).mean().fillna(0).tolist()
        ma60 = series_close.rolling(window=60).mean().fillna(0).tolist()
        
        # 2. Chan Lun Bi
        # Convert df to list of dicts for process_baohan
        klines = df.to_dict('records')
        processed_klines = process_baohan(klines)
        bi_points = find_bi(processed_klines)
        
        # 3. Calculate Centers (Pivot Boxes)
        # Using processed klines for consistency
        _, centers = calculate_bi_and_centers(processed_klines)
        
        # 4. Analysis & Judgment
        status = "震荡"
        color = "text-gray-500"
        details = []
        
        # New Structured Fields
        macd_info = {"text": "-", "color": "text-gray-400"}
        boll_info = {"text": "-", "color": "text-gray-400"}
        breakout_info = {"text": "-", "color": "text-gray-400"}
        chan_info = {"text": "-", "color": "text-gray-400"}
        
        # Short & Mid-Long Term Structures
        short_term = {"status": "观望", "color": "text-gray-400", "signal": "无明显信号"}
        mid_long_term = {"status": "震荡", "color": "text-gray-400", "signal": "趋势不明"}
        
        macd_signal = 0 # -1 Bear, 0 Neutral, 1 Bull
        
        # MACD Analysis
        if macd['dif'] and macd['dea']:
            last_dif = macd['dif'][-1]
            last_dea = macd['dea'][-1]
            prev_dif = macd['dif'][-2]
            prev_dea = macd['dea'][-2]
            
            macd_desc = []
            
            # Basic Crossover
            if last_dif > last_dea:
                macd_desc.append("金叉")
                macd_signal = 1
                macd_info["color"] = "text-red-500"
                if prev_dif <= prev_dea:
                    details.append("刚金叉")
            else:
                macd_desc.append("死叉")
                macd_signal = -1
                macd_info["color"] = "text-green-500"
                if prev_dif >= prev_dea:
                    details.append("刚死叉")
            
            # Zero Line & Bullish Arrangement
            if last_dif > 0 and last_dea > 0:
                macd_desc.append("零轴上")
                if last_dif > last_dea and last_dif > prev_dif: # Simple bullish trend check
                    macd_desc.append("多头")
                    details.append("MACD多头")
            elif last_dif < 0 and last_dea < 0:
                macd_desc.append("零轴下")
            
            macd_info["text"] = " ".join(macd_desc)
        
        # Bollinger Analysis
        if boll['upper']:
            last_close = closes[-1]
            last_upper = boll['upper'][-1]
            last_lower = boll['lower'][-1]
            last_mid = boll['middle'][-1]
            
            if last_close > last_upper:
                boll_info["text"] = "突破上轨"
                boll_info["color"] = "text-purple-500 font-bold"
                details.append("突破布林上轨")
                status = "强势突破"
                color = "text-purple-500"
            elif last_close < last_lower:
                boll_info["text"] = "跌破下轨"
                boll_info["color"] = "text-green-600 font-bold"
                details.append("跌破布林下轨")
                status = "超卖弱势"
                color = "text-green-600"
            elif last_close > last_mid:
                boll_info["text"] = "中轨上方"
                boll_info["color"] = "text-red-400 font-bold"
            else:
                boll_info["text"] = "中轨下方"
                boll_info["color"] = "text-green-400 font-bold"
        
        # RSI Analysis
        if last_rsi > 70:
            details.append("RSI超买")
            if "强势突破" not in status: # Don't override strong breakout
                status = "顶部风险"
                color = "text-red-500"
        elif last_rsi < 30:
            details.append("RSI超卖")
            status = "底部机会"
            color = "text-green-500"
            
        # Chan Lun Bi & Breakout Analysis
        last_bi_type = None
        last_bi_price = 0
        
        if bi_points:
            last_bi = bi_points[-1]
            last_bi_type = last_bi['type']
            last_bi_price = last_bi['price']
            
            # Default text and color based on last Bi type (Current Stroke Direction)
            if last_bi['type'] == 'bottom':
                 # Last was Bottom -> Current is Rising
                 chan_info["text"] = "↗ 上涨中"
                 chan_info["color"] = "text-red-500" 
            else:
                 # Last was Top -> Current is Falling
                 chan_info["text"] = "↘ 下跌中"
                 chan_info["color"] = "text-green-500"
            
            # Check Breakout (Break last Top Bi)
            # Find last Top Bi
            last_top_bi = None
            for bi in reversed(bi_points):
                if bi['type'] == 'top':
                    last_top_bi = bi
                    break
            
            if last_top_bi and closes[-1] > last_top_bi['price']:
                 breakout_info["text"] = f"突破前高"
                 breakout_info["color"] = "text-red-600 font-bold"
                 details.append(f"突破前高({last_top_bi['price']})")
                 status = "向上突破"
                 color = "text-red-600" # Strong Red

            # Trend Confirmation / Strength Check
            if len(bi_points) >= 2:
                prev_bi = bi_points[-2]
                
                # Case 1: Rising from Bottom
                if last_bi['type'] == 'bottom':
                    # Check strength
                    if closes[-1] > last_bi['price']:
                         # Confirmed rise
                         chan_info["text"] = "🚀 强力拉升" if closes[-1] > last_bi['price'] * 1.03 else "↗ 上涨中"
                         chan_info["color"] = "text-red-600 font-bold"
                         details.append("向上笔延续")
                         
                         if macd_signal == 1:
                             status = "上涨加速"
                             color = "text-red-500"
                    else:
                         # Price dipped below bottom? (Unlikely if last_bi is valid, but possible if new low forming)
                         chan_info["text"] = "🔄 底部震荡"
                         chan_info["color"] = "text-red-300"
                
                # Case 2: Falling from Top
                elif last_bi['type'] == 'top':
                     if closes[-1] < last_bi['price']:
                         # Confirmed fall
                         chan_info["text"] = "📉 加速下跌" if closes[-1] < last_bi['price'] * 0.97 else "↘ 下跌中"
                         chan_info["color"] = "text-green-600 font-bold"
                         details.append("向下笔延续")
                         
                         if macd_signal == -1:
                             status = "下跌中"
                             color = "text-green-500"
                     else:
                         # Price went above top?
                         chan_info["text"] = "🔄 顶部震荡"
                         chan_info["color"] = "text-green-300"

        # --- Short Term Analysis (Logic Enhancement) ---
        # Focus: Last Bi direction + MACD Cross + MA5
        st_score = 0
        st_signals = []
        
        # 1. Bi Direction
        if last_bi_type == 'bottom':
            st_score += 1
            st_signals.append("向上笔")
        elif last_bi_type == 'top':
            st_score -= 1
            st_signals.append("向下笔")
            
        # 2. MACD Short Term
        if macd_signal == 1: # Gold Cross
            st_score += 1
            st_signals.append("金叉")
        elif macd_signal == -1: # Death Cross
            st_score -= 1
            st_signals.append("死叉")
            
        # 3. MA5 Relation
        if closes[-1] > ma5[-1]:
            st_score += 1
        else:
            st_score -= 1
            
        # Short Term Judgment
        if st_score >= 2:
            short_term["status"] = "买入机会"
            short_term["color"] = "text-red-600 font-bold"
            short_term["signal"] = " | ".join(st_signals)
        elif st_score == 1:
            short_term["status"] = "偏多震荡"
            short_term["color"] = "text-red-400"
            short_term["signal"] = " | ".join(st_signals)
        elif st_score == -1:
            short_term["status"] = "偏空震荡"
            short_term["color"] = "text-green-400"
            short_term["signal"] = " | ".join(st_signals)
        elif st_score <= -2:
            short_term["status"] = "卖出风险"
            short_term["color"] = "text-green-600 font-bold"
            short_term["signal"] = " | ".join(st_signals)
        else:
            short_term["status"] = "盘整观望"
            short_term["color"] = "text-gray-500"
            short_term["signal"] = "多空平衡"

        # --- Medium Term Analysis (Nuanced Bull Market Logic) ---
        # Focus: MA20 Trend (Primary) + MA60 (Support) + Momentum (MACD)
        # Goal: Differentiate Acceleration, Trending, Pullback, Consolidation, Weakness
        
        medium_term = {"status": "震荡整理", "color": "text-gray-500", "signal": "趋势不明"}
        mt_signals = []
        
        # 1. Primary Trend (MA20 Slope & Direction)
        ma20_slope = 0
        if len(ma20) > 5:
            ma20_slope = (ma20[-1] - ma20[-5]) / ma20[-5] * 100 # % change over 5 days
            
        is_ma20_up = ma20_slope > 0.5 # Strong Up
        is_ma20_flat = -0.5 <= ma20_slope <= 0.5
        is_ma20_down = ma20_slope < -0.5
        
        # 2. Price Position relative to MA20
        price_vs_ma20 = (closes[-1] - ma20[-1]) / ma20[-1] * 100
        
        # 3. MACD Momentum
        macd_momentum = "neutral"
        if macd['hist']:
            if macd['hist'][-1] > 0 and macd['hist'][-1] > macd['hist'][-2]:
                macd_momentum = "strong"
            elif macd['hist'][-1] > 0 and macd['hist'][-1] < macd['hist'][-2]:
                macd_momentum = "weakening"
            elif macd['hist'][-1] < 0:
                macd_momentum = "negative"

        # Logic Tree
        if is_ma20_up:
            # Bullish Context
            if price_vs_ma20 > 5: # Far above MA20
                if macd_momentum == "strong":
                    medium_term["status"] = "加速主升" # Accelerating
                    medium_term["color"] = "text-red-600 font-black"
                    mt_signals.append("均线发散 | 动能增强")
                else:
                    medium_term["status"] = "高位钝化" # High but momentum slowing
                    medium_term["color"] = "text-orange-500 font-bold"
                    mt_signals.append("乖离过大 | 动能减弱")
            elif 0 <= price_vs_ma20 <= 5: # Near MA20 (Above)
                if macd_momentum == "weakening" or macd_momentum == "negative":
                    medium_term["status"] = "回踩支撑" # Pullback to support
                    medium_term["color"] = "text-indigo-500 font-bold" # Opportunity color?
                    mt_signals.append("缩量回调 | 关注支撑")
                else:
                    medium_term["status"] = "稳健上行" # Steady trend
                    medium_term["color"] = "text-red-500 font-bold"
                    mt_signals.append("依托均线 | 趋势健康")
            else: # Below MA20 but MA20 is Up
                medium_term["status"] = "破位警示" # Broken trend line?
                medium_term["color"] = "text-green-600 font-bold"
                mt_signals.append("跌破20日线 | 短期调整")
                
        elif is_ma20_flat:
            # Consolidation Context
            if price_vs_ma20 > 0:
                medium_term["status"] = "蓄势待发" # Consolidation (Bullish bias)
                medium_term["color"] = "text-red-400 font-bold"
                mt_signals.append("均线粘合 | 多头蓄势")
            else:
                medium_term["status"] = "弱势震荡" # Consolidation (Bearish bias)
                medium_term["color"] = "text-gray-500"
                mt_signals.append("均线走平 | 缺乏方向")
                
        else: # MA20 Down
            # Bearish Context
            if price_vs_ma20 > 0:
                medium_term["status"] = "超跌反弹" # Rebound
                medium_term["color"] = "text-orange-400"
                mt_signals.append("乖离修复 | 谨防回落")
            else:
                medium_term["status"] = "空头趋势" # Downtrend
                medium_term["color"] = "text-green-600 font-bold"
                mt_signals.append("均线压制 | 阴跌不止")

        # Special Case: MA60 Check (Long Term Filter)
        if closes[-1] < ma60[-1]:
             # Downgrade status if below Bull/Bear line
             if "主升" in medium_term["status"] or "上行" in medium_term["status"]:
                 medium_term["status"] = "反弹受阻"
                 medium_term["color"] = "text-orange-500"
                 mt_signals.append("受制60日线")

        medium_term["signal"] = " | ".join(mt_signals)
        
        # Combine Status
        if not details:
            details.append("无明显趋势")
            
        summary = f"{status} | " + " ".join(details)
        
        # Calculate Market Data
        market_data = {
            "close": closes[-1],
            "change": (closes[-1] - closes[-2]) / closes[-2] * 100 if len(closes) > 1 else 0.0,
            "volume": df['volume'].iloc[-1] if 'volume' in df.columns else 0,
            "amount": df['amount'].iloc[-1] if 'amount' in df.columns else 0,
            "date": df['date'].iloc[-1]
        }
        
        # Re-calculate MA alignment for return data structure
        ma_alignment_bull = (ma5[-1] > ma10[-1] > ma20[-1] > ma60[-1])
        ma_alignment_bear = (ma5[-1] < ma10[-1] < ma20[-1] < ma60[-1])
        
        return {
            "status": status,
            "color": color,
            "summary": summary,
            "macd_info": macd_info,
            "boll_info": boll_info,
            "breakout_info": breakout_info,
            "chan_info": chan_info,
            "short_term": short_term,
            "mid_long_term": medium_term, # Use new logic variable
            "macd": macd,
            "rsi": rsi,
            "last_rsi": round(last_rsi, 1),
            "bi_points": bi_points,
            "centers": centers,
            "ma_data": {
                "ma5": ma5[-1],
                "ma10": ma10[-1],
                "ma20": ma20[-1],
                "ma60": ma60[-1],
                "alignment": "bull" if ma_alignment_bull else ("bear" if ma_alignment_bear else "none")
            },
            "market_data": market_data,
            "chart_data": {
                "dates": df['date'].tolist(),
                "open": df['open'].tolist(),
                "close": df['close'].tolist(),
                "high": df['high'].tolist(),
                "low": df['low'].tolist(),
                "ma5": ma5,
                "ma10": ma10,
                "ma20": ma20,
                "ma60": ma60
            },
            "bollinger_bands": {
                "upper": boll['upper'][-1],
                "middle": boll['middle'][-1],
                "lower": boll['lower'][-1]
            }
        }

# Global Instance
sector_analyzer = SectorAnalyzer()
