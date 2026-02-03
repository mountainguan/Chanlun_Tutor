import pandas as pd
import akshare as ak
import datetime
from functools import lru_cache

# Using a simple memory cache for the current session run
# This will be cleared when the server restarts, satisfying "not stored on server disk"
@lru_cache(maxsize=100)
def _fetch_akshare_data(code, market):
    try:
        df = ak.stock_individual_fund_flow(stock=code, market=market)
        return df
    except Exception as e:
        print(f"Fetch failed for {code}: {e}")
        return None

import concurrent.futures

@lru_cache(maxsize=100)
def _fetch_stock_info(code):
    try:
        # Timeout wrapper is handled by caller
        df = ak.stock_individual_info_em(symbol=code)
        return df
    except Exception as e:
        print(f"Fetch info failed for {code}: {e}")
        return None

@lru_cache(maxsize=100)
def _fetch_gdhs(code):
    try:
        # User suggested stock_holder_number, mapped to stock_zh_a_gdhs_detail_em used as modern replacement
        # This is often more stable for single stock query
        if hasattr(ak, 'stock_zh_a_gdhs_detail_em'):
             df = ak.stock_zh_a_gdhs_detail_em(symbol=code)
             return df
        # Fallback
        df = ak.stock_zh_a_gdhs(symbol=code)
        return df
    except Exception as e:
        print(f"Fetch gdhs failed for {code}: {e}")
        return None


@lru_cache(maxsize=100)
def _fetch_daily_hist(code, start_date, end_date):
    try:
        # qfq: 前复权 (Forward Adjusted) is usually better for analyzing returns, 
        # but for absolute P_avg (VWAP), unadjusted 'None' or 'qfq' might matter if splits occurred.
        # Akshare hist usually provides '成交额' and '成交量'. 
        # For VWAP = Amount / Volume, splits don't affect Ratio much on same day, 
        # but price level matches the adjusted close?
        # Let's use 'qfq' to align with typical 'Close' analysis, though 'Amount' is nominal currency.
        # Actually for P_avg in formula $F_{net} / (P \times S)$, $F_{net}$ is nominal Yuan.
        # So $P$ should be nominal price (unadjusted) ideally? 
        # Or if $F_{net}$ is adjusted? No, standard flows are nominal.
        # So we should probably use Unadjusted price for P_avg if possible, OR
        # if input F_net is huge, P must be real price.
        # Let's use default (unadjusted) or check flow data nature. 
        # Standard flow is usually nominal capital.
        # Let's try 'qfq' first as it handles gaps better for visual trends, but strictly nominal is correct for Amount/Shares math.
        # However, Volume is in Hands.
        # Let's stick to adjusted="qfq" for consistency with charts, 
        # or "None" for strict math? 
        # Given "stock_zh_a_hist" default usually works. Let's try explicit adjust="qfq".
        df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start_date, end_date=end_date, adjust="qfq")
        return df
    except Exception as e:
        print(f"Fetch daily hist failed for {code}: {e}")
        return None

class MoneyFlow:
    """
    Refactored MoneyFlow to have NO server-side persistence (no JSON, no CSV).
    Subscription list should be handled by the UI (storage.user or client local storage).
    Data caching is done in-memory only.
    """
    def __init__(self):
        pass
    
    def get_stock_info(self, code):
        df = _fetch_stock_info(code)
        info = {}
        if df is not None and not df.empty:
            # item, value columns
            try:
                # Convert to dict
                records = df.to_dict('records')
                for row in records:
                    info[row['item']] = row['value']
            except:
                pass
        return info

    def guess_market(self, code):
        if code.startswith('6'):
            return 'sh'
        elif code.startswith('9'):
            return 'sh'
        elif code.startswith('0') or code.startswith('3'):
            return 'sz'
        elif code.startswith('8') or code.startswith('4'):
            return 'bj'
        return 'sh' # default

    def get_flow_data(self, code, force_update=False):
        market = self.guess_market(code)
        
        if force_update:
            _fetch_akshare_data.cache_clear() 
            _fetch_stock_info.cache_clear()
            _fetch_gdhs.cache_clear()
            _fetch_daily_hist.cache_clear()
        
        # --- Parallel Fetching ---
        # We fetch flow (essential), then others (optional/supporting)
        # To speed up, we run them in parallel.
        
        # 1. Start fetching essential data
        # We can't easily parallelize _fetch_akshare_data with others if others depend on flow date range?
        # Actually, hist data depends on flow dates to optimize range. 
        # But grabbing last 365 days of hist is safe enough usually.
        # Let's fetch Flow first (it's fast usually), then fetch others in parallel.
        
        df = _fetch_akshare_data(code, market)

        if df is None or df.empty:
            return None
            
        # Process Flow DF Base
        df = df.copy()
        if '日期' in df.columns:
            df['date'] = pd.to_datetime(df['日期'])
            df.set_index('date', inplace=True)
            df.drop(columns=['日期'], inplace=True)
        elif 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
            
        if '中单净流入-净额' in df.columns and '小单净流入-净额' in df.columns:
             df['散户净流入-净额'] = df['中单净流入-净额'] + df['小单净流入-净额']

        # 2. Parallel fetch for supporting data
        # info (Float Shares), gdhs (Holders), hist (Daily P_avg)
        
        # Determine date range for hist using flow data
        dates = df.index.sort_values()
        if not dates.empty:
            start_date_str = dates[0].strftime("%Y%m%d")
            end_date_str = dates[-1].strftime("%Y%m%d")
        else:
            # Fallback
            end_dt = datetime.date.today()
            start_dt = end_dt - datetime.timedelta(days=180)
            start_date_str = start_dt.strftime("%Y%m%d")
            end_date_str = end_dt.strftime("%Y%m%d")

        hist_df = None
        info = {}
        gdhs_df = None

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            future_info = executor.submit(_fetch_stock_info, code)
            # gdhs can be slow, we might timeout inside usages if needed, or rely on logic below
            future_gdhs = executor.submit(_fetch_gdhs, code)
            future_hist = executor.submit(_fetch_daily_hist, code, start_date_str, end_date_str)
            
            # Wait for results with optional timeout for the slower ones?
            # We wait for all, but simple try-except on result()
            
            try:
                info_df = future_info.result(timeout=5)
                if info_df is not None and not info_df.empty:
                    try:
                        records = info_df.to_dict('records')
                        for row in records:
                            info[row['item']] = row['value']
                    except: pass
            except Exception as e:
                print(f"Parallel fetch info failed: {e}")

            try:
                hist_df = future_hist.result(timeout=8)
            except Exception as e:
                print(f"Parallel fetch hist failed: {e}")

            try:
                # GDHS is the problematic one. Give it 3 seconds max.
                gdhs_df = future_gdhs.result(timeout=3)
            except concurrent.futures.TimeoutError:
                print(f"Parallel fetch gdhs TIMEOUT for {code}")
                gdhs_df = None # Will fallback to default
            except Exception as e:
                print(f"Parallel fetch gdhs failed: {e}")
        
        # --- Calculate Estimated Retail Count (New Formula) ---
        # Formula: N_t = N_{t-1} - F_net / (P_avg * S_per)
        
        try:
            # B. History P_avg processing
            p_avg_series = None

            
            p_avg_series = None
            if hist_df is not None and not hist_df.empty:
                hist_df['date'] = pd.to_datetime(hist_df['日期'])
                hist_df.set_index('date', inplace=True)
                
                # Check for duplicate indices in hist_df which can cause errors
                hist_df = hist_df[~hist_df.index.duplicated(keep='first')]

                # P_avg = Amount (Yuan) / (Volume (Hands) * 100)
                common_indices = df.index.intersection(hist_df.index)
                if not common_indices.empty:
                    hist_sub = hist_df.loc[common_indices]
                    vol = hist_sub['成交量'] * 100
                    amt = hist_sub['成交额']
                    vwap = amt / vol.replace(0, 1) 
                    p_avg_series = vwap
            
            # Fallback P_avg
            if p_avg_series is None:
                if '收盘价' in df.columns:
                    p_avg_series = df['收盘价']
                else: 
                     # Should rarely happen
                     import numpy as np
                     p_avg_series = pd.Series(10.0, index=df.index)

            # C. Initial Value (N_0) and S_per preparation
            
            # Defaults
            N_prev = 50000.0 
            S_per = 1000.0 
            
            float_shares = info.get('流通股')
            if float_shares and isinstance(float_shares, (str, float, int)):
                 try: float_shares = float(float_shares) 
                 except: float_shares = None
            
            # Estimation Strategy if GDHS missing
            # If no GDHS, assume S_per based on rough market avg (e.g. 15w CNY per holder?)
            # N_0 = FloatMarketCap / AvgHoldingVal.
            # But simpler: N_0 = 50000 default is fine for relative trend.
            # However, S_per is critical for MAGNITUDE of change.
            # DeltaN = F_net / (P * S_per)
            # F_net / P = Shares Moved.
            # DeltaN = SharesMoved / S_per. 
            # So S_per is "Avg Shares Per Holder".
            # If we guess S_per wrong, the curve is just scaled up/down vertically. 
            # S_per approx = FloatShares / N.
            if gdhs_df is not None and not gdhs_df.empty:
                # Find appropriate initial N_prev and S_per
                # Column mapping for different interfaces
                date_cols_to_check = ['股东户数统计截止日', '截止日期', '公告日期', '股东户数公告日期']
                date_col = next((col for col in date_cols_to_check if col in gdhs_df.columns), None)
                
                if date_col:
                    gdhs_df['date'] = pd.to_datetime(gdhs_df[date_col], errors='coerce')
                    gdhs_df = gdhs_df.dropna(subset=['date']).sort_values('date')
                    
                    if not dates.empty:
                        first_flow_date = dates[0]
                        prior = gdhs_df[gdhs_df['date'] <= first_flow_date]
                        
                        target_record = None
                        if not prior.empty:
                            target_record = prior.iloc[-1]
                        else:
                            target_record = gdhs_df.iloc[0]
                        
                        if target_record is not None:
                             if '股东户数-本次' in target_record:
                                val = target_record['股东户数-本次']
                                if val: N_prev = float(val)

                             if '户均持股数量' in target_record:
                                  val = target_record['户均持股数量']
                                  if val: S_per = float(val)
                             elif float_shares:
                                  S_per = float(float_shares) / N_prev
            else:
                # GDHS missing (Timeout or Empty)
                # Try to use Info to estimate S_per
                if float_shares:
                    # Assume typical 50000 holders if unknown
                    # Or better: Assume Avg Holding Value ~ 100,000 CNY?
                    # S_per * Price = 100,000. => S_per = 100,000 / Price.
                    # We can update S_per dynamically? No formula assumes constant S_per roughly or updated quarterly.
                    # Let's fallback to S_per = FloatShares / 50000 if FloatShares known
                    S_per = float_shares / 50000.0
                else:
                    S_per = 5000.0 # Blind guess
                
                # N_prev default 50000 is used.


            # D. Iterative Calculation
            # Logic Update (User Request): 
            # Implemented a variation of "Retail Score" based on user's code snippet.
            # User Formula Concept: Score = (BuyLargeCount - SellLargeCount) / FloatShares * 10000
            # Since AkShare/EastMoney FREE API does not provide "Order Counts" (BiShu), 
            # we adapt the formula to use "Net Inflow Amount" which is the closest proxy available.
            # Adaptation: Score = (MainForceNetInflowAmount / AvgPrice) / FloatShares * 10000
            # Explanation: Amount/Price = Approx Shares Volume. 
            # NetShares / FloatShares = Chips Change Ratio.
            
            # Note: The user's snippet calculates a "Score" (-100 to 100).
            # We will visualize this score as a Histogram or Curve.
            # But the existing UI expects "Retail Count Index" (Curve). 
            # We can convert the Score to a Cumulative Curve to show "Retail Count Trend".
            # Score > 0 => Main Force Buy => Retail Count Down.
            # Score < 0 => Main Force Sell => Retail Count Up.
            
            # Let's map calculate the score and then derive N_t.
            
            main_col = '主力净流入-净额'
            
            if main_col in df.columns:
                retail_counts = []
                current_N = N_prev
                
                if N_prev <= 0: N_prev = 50000.0
                
                # Float Shares in Wan (10000)
                if not float_shares:
                     float_shares = N_prev * S_per
                
                float_shares_wan = float_shares / 10000.0
                if float_shares_wan <= 0: float_shares_wan = 1000.0

                sorted_dates = df.index.sort_values()
                
                retail_scores = []
                
                for date in sorted_dates:
                    # P_avg
                    if date in p_avg_series.index:
                        p = float(p_avg_series.loc[date])
                    elif '收盘价' in df.columns:
                        p = float(df.loc[date, '收盘价'])
                    else:
                        p = 10.0
                    
                    if p <= 0.1: p = 0.1
                    
                    # Main Force Net Inflow (Yuan)
                    # "Main Force" in AkShare = Super Large + Large Orders
                    # This maps to "Buy Large - Sell Large" in money terms.
                    f_net = float(df.loc[date, main_col])
                    
                    # Convert to "Shares" (Proxy for Count difference)
                    # User's logic: Count Diff / Float * 10000
                    # We use: (NetAmount / Price) / Float * Scaling
                    # NetShares = f_net / p
                    # Score = (NetShares / 10000) / float_shares_wan * Factor
                    
                    # Why divide by 10000? To match float_shares_wan units.
                    net_shares_wan = (f_net / p) / 10000.0
                    
                    # Factor 10000 from user script
                    # User script: (CountDiff / FloatWan) * 10000
                    # Here we use ShareDiff. ShareDiff is proportional to CountDiff * AvgSharesPerOrder.
                    # Assuming AvgSharesPerOrder is constant-ish, the shape is same.
                    # We use a factor to make the score readable (e.g. around -50 to 50)
                    
                    # For a stock with 10B cap, MainInflow 100M. 1%.
                    # NetSharesWan / FloatSharesWan = 1%. 
                    # 0.01 * 10000 = 100.
                    # This matches the user's scale perfectly.
                    score = (net_shares_wan / float_shares_wan) * 10000
                    
                    # Interpretation:
                    # Score > 0: Main Buy -> Retail Sell -> Retail Count DOWN.
                    # Score < 0: Main Sell -> Retail Buy -> Retail Count UP.
                    
                    # Refinement (User Request): "Looks too much like Money Flow".
                    # We try to use weighted Small/Medium orders to better approximate "Count" behavior.
                    # Small orders (San Hu) imply more head count change than Medium orders.
                    
                    small_col = '小单净流入-净额'
                    mid_col = '中单净流入-净额'
                    
                    final_score_val = score # Default base
                    
                    if small_col in df.columns and mid_col in df.columns:
                        small_net = float(df.loc[date, small_col])
                        mid_net = float(df.loc[date, mid_col])
                        
                        # Weighting Strategy:
                        # Small orders are purely retail => Weight 1.0
                        # Medium orders are mixed/larger retail => Weight 0.2 (Assume 5x ticket size means 1/5 impact on count)
                        # Note: 'retail_money' used before was (Small + Mid).
                        # Main Force Score ~ -(Small + Mid).
                        # New weighted proxy:
                        weighted_retail_money = (small_net * 1.0) + (mid_net * 0.2)
                        
                        # Calc equivalent score from Retail Perspective
                        retail_proxy_shares_wan = (weighted_retail_money / p) / 10000.0
                        retail_proxy_score = (retail_proxy_shares_wan / float_shares_wan) * 20000 
                        
                        # Use this proxy instead of the Main Force derived one
                        # Retail Proxy > 0 => Count UP.
                        # Matches target sign.
                        final_score_val = -1 * retail_proxy_score # We need to maintain the "Main Force Score" sign convention for the delta_N logic below which expects Main Force sign?
                        # Actually let's rewrite the delta logic to be clearer.
                        
                        # Direct Retail Score (Positive = Count Up)
                        display_score = retail_proxy_score
                        
                        # Delta N logic: Display Score > 0 => Count Up.
                        change_pct = display_score / 10000.0
                        delta_N = current_N * change_pct
                    else:
                        # Fallback
                        display_score = -1 * score # Invert Main Force Score
                        change_pct = score / 10000.0
                        delta_N = -1 * current_N * change_pct

                    retail_scores.append(display_score)
                    
                    current_N = current_N + delta_N
                    retail_counts.append(current_N)

                # Store the user's score 
                rc_series = pd.Series(retail_counts, index=sorted_dates)
                df['retail_count_index'] = rc_series
                
                # Direct Score for Bar Chart
                df['retail_score'] = pd.Series(retail_scores, index=sorted_dates)

        except Exception as e:
            print(f"Retail count calc failed (New Formula): {e}")
            import traceback
            traceback.print_exc()
        
        return df
