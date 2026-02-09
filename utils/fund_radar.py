
import pandas as pd
import akshare as ak
import datetime
import os
import json
import time
import threading
import random
from concurrent.futures import ThreadPoolExecutor, as_completed

class FundRadar:
    """
    Simplified FundRadar Manager.
    Philosophy: 
    - Cache First: Always prefer cache.
    - Explicit Update: Only update if cache is missing or explicitly requested by background task.
    - No "Force Refresh" via UI unless button clicked.
    """
    
    # ── A股节假日休市日历 (工作日但休市的日期) ──
    # 仅需维护非周末的休市日，周末自动排除
    # 格式: {(month, day), ...}
    HOLIDAYS_2026 = {
        (1, 1), (1, 2),                                          # 元旦
        (2, 16), (2, 17), (2, 18), (2, 19), (2, 20), (2, 23),   # 春节
        (4, 6),                                                  # 清明
        (5, 1), (5, 4), (5, 5),                                  # 劳动节
        (6, 19),                                                 # 端午
        (9, 25),                                                 # 中秋
        (10, 1), (10, 2), (10, 5), (10, 6), (10, 7),            # 国庆
    }

    # Class-level Global Throttle (shared across all instances)
    _fetch_log = {} 
    
    # Retry Scheduling for Background Tasks
    _next_retry_time = {} # Key: date_str, Value: timestamp
    
    # Class-level cache for multi-day direct THS data
    _multi_day_cache = {}  # Key: f"{days}_{date_str}", Value: (timestamp, DataFrame)
    
    # ── Anti-Crawl Rate Limiter (shared across all threads) ──
    _api_lock = threading.Lock()
    _api_last_call_ts = 0            # timestamp of last API call
    _api_min_interval = 1.5          # min seconds between any two API calls (THS needs ≥1s)
    _api_error_count = 0             # consecutive error counter
    _api_backoff_until = 0           # global pause timestamp (adaptive backoff)
    _API_MAX_WORKERS = 2             # max parallel threads (conservative for THS)
    _API_JITTER_RANGE = (0.3, 1.0)   # random jitter added per request (seconds)
    _ths_flow_cache = {}             # short-lived cache for stock_fund_flow_industry results
    _ths_flow_cache_lock = threading.Lock()
    _ths_flow_blocked_until = 0      # timestamp: skip fund_flow_industry calls until this time

    def __init__(self):
        self.data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
        self.cache_dir = os.path.join(self.data_dir, 'fund_radar_cache')
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)
        # Auto-cleanup: remove stale batch cache files and legacy sector_history folder
        self._cleanup_stale_cache()

    # ── Anti-Crawl: Rate-Limited API Wrapper ──────────────────────

    @classmethod
    def _rate_limited_call(cls, api_func, *args, _retry_max=3, _label="API", **kwargs):
        """
        Thread-safe, rate-limited wrapper for any akshare API call.
        Features:
          - Global lock ensures min interval between ANY two outgoing requests
          - Random jitter to avoid fingerprinting
          - Adaptive backoff: if consecutive errors spike, pause all threads
          - Retry with exponential backoff on failure
        Returns: result or None on total failure.
        """
        for attempt in range(1, _retry_max + 1):
            # 1. Check global adaptive backoff
            now = time.time()
            if now < cls._api_backoff_until:
                wait = cls._api_backoff_until - now
                print(f"[RateLimit] Global backoff active, sleeping {wait:.1f}s...")
                time.sleep(wait)

            # 2. Acquire lock → enforce min interval + add jitter
            with cls._api_lock:
                elapsed = time.time() - cls._api_last_call_ts
                if elapsed < cls._api_min_interval:
                    time.sleep(cls._api_min_interval - elapsed)
                # Add random jitter
                jitter = random.uniform(*cls._API_JITTER_RANGE)
                time.sleep(jitter)
                cls._api_last_call_ts = time.time()

            # 3. Execute
            try:
                result = api_func(*args, **kwargs)
                # Success → reset error counter
                with cls._api_lock:
                    cls._api_error_count = max(0, cls._api_error_count - 1)
                return result
            except Exception as e:
                err_msg = str(e).lower()
                # NoneType parsing error = THS anti-crawl blocked the response
                # (server returns a CAPTCHA/empty page instead of data)
                is_anticrawl_parse = "'nonetype' object has no attribute 'text'" in err_msg
                is_rate_limit = is_anticrawl_parse or any(kw in err_msg for kw in [
                    '403', '429', 'too many', 'rate limit', 'frequent',
                    'banned', 'block', 'access denied', 'timeout',
                    'timed out', 'connection', 'reset by peer'
                ])
                if is_anticrawl_parse:
                    print(f"[AntiCrawl] {_label} blocked by THS (NoneType parse error), attempt {attempt}/{_retry_max}")
                
                with cls._api_lock:
                    cls._api_error_count += 1
                    ec = cls._api_error_count
                
                if is_rate_limit or ec >= 5:
                    # Anti-crawl backoff: longer base delay (5s minimum) with exponential growth
                    base = 5 if is_anticrawl_parse else 2
                    backoff = min(base * (2 ** min(attempt - 1, 4)), 120)  # 5→10→20→40→80 or 2→4→8→16→32
                    backoff += random.uniform(1, 3)  # extra jitter
                    print(f"[RateLimit] {_label} attempt {attempt} failed (errors={ec}): {e}")
                    print(f"[RateLimit] Triggering adaptive backoff: {backoff:.0f}s")
                    with cls._api_lock:
                        cls._api_backoff_until = time.time() + backoff
                    time.sleep(backoff)
                else:
                    # Normal error → small delay before retry
                    delay = attempt * 2.0 + random.uniform(1.0, 3.0)
                    if attempt < _retry_max:
                        print(f"[RateLimit] {_label} attempt {attempt} error: {e}, retrying in {delay:.1f}s")
                        time.sleep(delay)
                    else:
                        print(f"[RateLimit] {_label} FAILED after {_retry_max} attempts: {e}")
        
        return None  # All retries exhausted

    # ── Sector History Batch Disk Cache ──────────────────────
    # One JSON file per (start_date, end_date, max_days) containing ALL sectors.
    # e.g. hist_batch_20260125_20260209_5.json → {"半导体": {"turnover": ..., "pct": ...}, ...}
    # This keeps the cache folder clean: ~1 file per period instead of 90.

    def _get_batch_cache_path(self, date_key):
        """Single file path for an entire batch of sector history data."""
        return os.path.join(self.cache_dir, f"hist_batch_{date_key}.json")

    def _load_batch_cache(self, date_key):
        """Load the full batch cache. Returns dict {sector_name: {turnover, pct}} or None."""
        path = self._get_batch_cache_path(date_key)
        if not os.path.exists(path):
            return None
        try:
            mtime = os.path.getmtime(path)
            cache_age_hours = (time.time() - mtime) / 3600
            if cache_age_hours > 16:  # Stale after 16h (next trading day)
                return None
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return None

    def _save_batch_cache(self, date_key, all_sectors_dict):
        """Save the full batch of sector history to one file."""
        path = self._get_batch_cache_path(date_key)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(all_sectors_dict, f, ensure_ascii=False)
        except Exception as e:
            print(f"[FundRadar] Batch cache write error: {e}")

    def _cleanup_stale_cache(self):
        """Remove expired batch cache files (>24h) and legacy sector_history folder."""
        try:
            # Remove legacy per-sector folder if it exists
            legacy_dir = os.path.join(self.cache_dir, 'sector_history')
            if os.path.exists(legacy_dir):
                import shutil
                shutil.rmtree(legacy_dir, ignore_errors=True)
                print(f"[FundRadar] Cleaned up legacy sector_history folder")

            # Remove stale hist_batch_*.json files (>24 hours old)
            now = time.time()
            for f in os.listdir(self.cache_dir):
                if f.startswith('hist_batch_') and f.endswith('.json'):
                    fpath = os.path.join(self.cache_dir, f)
                    age_hours = (now - os.path.getmtime(fpath)) / 3600
                    if age_hours > 24:
                        os.remove(fpath)
        except Exception as e:
            print(f"[FundRadar] Cache cleanup error: {e}")
            
    def _get_china_now(self):
        utc_now = datetime.datetime.now(datetime.timezone.utc)
        cn_now = utc_now + datetime.timedelta(hours=8)
        return cn_now

    def _get_cache_path(self, date_str):
        return os.path.join(self.cache_dir, f"sector_sina_{date_str}.json")

    @classmethod
    def is_holiday(cls, dt):
        """判断指定日期是否为A股节假日休市（仅判断非周末的特殊休市日）"""
        if isinstance(dt, datetime.datetime):
            dt = dt.date() if hasattr(dt, 'date') else dt
        return (dt.month, dt.day) in cls.HOLIDAYS_2026

    @classmethod
    def is_trading_day(cls, cn_now=None):
        """
        判断是否为A股交易日（非周末 且 非节假日）。
        传入中国时间 datetime，或默认取当前中国时间。
        """
        if cn_now is None:
            utc_now = datetime.datetime.now(datetime.timezone.utc)
            cn_now = utc_now + datetime.timedelta(hours=8)
        # Weekend
        if cn_now.weekday() >= 5:
            return False
        # Holiday
        if cls.is_holiday(cn_now):
            return False
        return True

    def is_trading_time(self, cn_now=None):
        """判断当前是否在A股盘中时段（交易日 + 开盘时间段）"""
        if cn_now is None:
            cn_now = self._get_china_now()
        
        # 非交易日直接返回 False
        if not self.is_trading_day(cn_now):
            return False
        
        t = cn_now.time()
        # 09:30 - 11:30, 13:00 - 15:00
        # Add slight buffer for data availability
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
            # df_sina = self._fetch_sina_sector() # Deprecated by user request to unify on THS
            df_ths = self._fetch_ths_sector()
            market_snap = self.get_market_snapshot()
            
            # Check for critical data failure (at least THS should exist)
            if df_ths.empty:
                print("[FundRadar] THS data fetch failed (empty). check akshare.")
                return None, False

            # Prepare 'sina_sectors' slot with THS data for UI compatibility
            # This ensures 'df_flow' in UI matches 'df_ths' exactly (same industry list)
            df_sina = df_ths.copy()
            if not df_sina.empty:
                 if '总成交额' in df_sina.columns:
                     df_sina['成交额'] = df_sina['总成交额'] # Alias for UI
            
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
        
        # --- Normalize Units to "亿" (100 Million Yuan) ---
        def normalize_df(df, cols):
            if df.empty: return df
            for col in cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
                    # Heuristic: Akshare returns Yuan for these interfaces. 
                    # If max value is large (>1e5), it's definitely Yuan.
                    if df[col].abs().max() > 100000:
                        df[col] = df[col] / 100000000.0
            return df

        df_sina = normalize_df(df_sina, ['成交额', '成交额(元)', '总成交额'])
        df_ths = normalize_df(df_ths, ['净流入', '总成交额', '成交额'])

        return df_sina, df_ths, market

    def _check_throttle(self, key, cooldown=60):
        now = time.time()
        last = FundRadar._fetch_log.get(key, 0)
        if now - last > cooldown:
            FundRadar._fetch_log[key] = now
            return True
        return False

    def get_available_cache_dates(self):
        """
        Return sorted list of date strings (YYYY-MM-DD) available in cache.
        """
        if not os.path.exists(self.cache_dir):
            return []
        files = os.listdir(self.cache_dir)
        dates = []
        for f in files:
            if f.startswith('sector_sina_') and f.endswith('.json'):
                d_str = f[12:-5]
                # Simple validation of format YYYY-MM-DD
                if len(d_str) == 10 and d_str[4] == '-' and d_str[7] == '-':
                    dates.append(d_str)
        dates.sort()
        return dates

    def get_multi_day_data(self, end_date_str, days, cache_only=False):
        """
        Aggregate multi-day data. Now uses DIRECT THS API for 3/5/10/20 day periods,
        no daily cache accumulation needed.
        Falls back to cache aggregation only when direct API fails.
        
        cache_only: If True, only use local cache (no online fetching).
                    Used when viewing historical dates to avoid unnecessary API calls.
        Returns: (DataFrame, list_of_dates_used_or_period_label)
        """
        # If cache_only, skip all online APIs and go straight to local cache
        if cache_only:
            print(f"[FundRadar] Multi-day {days}d: cache_only mode, using local cache for {end_date_str}")
            return self._get_multi_day_from_cache(end_date_str, days)

        # Map days to THS multi-day ranking API periods
        ths_period_map = {3: '3日排行', 5: '5日排行', 10: '10日排行', 20: '20日排行'}
        
        # Try direct THS API first for supported periods
        if days in ths_period_map:
            df_direct = self._fetch_multi_day_ths_direct(days, end_date_str)
            if df_direct is not None and not df_direct.empty:
                return df_direct, [f"THS {days}日直取"]
        
        # Fallback 2: summary + history combo (when fund_flow_industry is blocked)
        df_summary = self._fetch_multi_day_via_summary(days, end_date_str)
        if df_summary is not None and not df_summary.empty:
            return df_summary, [f"THS {days}日(概览+历史)"]
        
        # Fallback 3: For unsupported periods (e.g. 60 days) or API failure, 
        # try direct history fetch for arbitrary period
        df_hist = self._fetch_multi_day_history_direct(days, end_date_str)
        if df_hist is not None and not df_hist.empty:
            return df_hist, [f"THS {days}日历史"]

        # Final fallback: legacy cache aggregation
        return self._get_multi_day_from_cache(end_date_str, days)

    def _get_ths_flow_cached(self, symbol):
        """
        Fetch stock_fund_flow_industry with short-lived in-memory cache (10 min).
        Avoids hammering THS when multiple periods are requested simultaneously.
        Failed results are cached for 2 min (to avoid immediate re-hammering).
        If the endpoint is known to be blocked, skip entirely for 10 min.
        Returns DataFrame or None.
        """
        # Fast-skip if endpoint is known to be blocked
        now = time.time()
        if now < FundRadar._ths_flow_blocked_until:
            remaining = (FundRadar._ths_flow_blocked_until - now) / 60
            print(f"[FundRadar] stock_fund_flow_industry({symbol}): SKIPPED (endpoint blocked, retry in {remaining:.0f}m)")
            return None

        cache_key = symbol
        with FundRadar._ths_flow_cache_lock:
            cached = FundRadar._ths_flow_cache.get(cache_key)
            if cached:
                ts, df, success = cached
                ttl = 600 if success else 120  # 10 min for success, 2 min for failure
                if time.time() - ts < ttl:
                    status = "cache hit" if success else "cached failure"
                    print(f"[FundRadar] stock_fund_flow_industry({symbol}): {status} ({(time.time()-ts)/60:.0f}m old)")
                    return df.copy() if df is not None else None

        # Not cached or expired → fetch with rate limiting
        df = self._rate_limited_call(
            ak.stock_fund_flow_industry, symbol=symbol,
            _retry_max=3, _label=f"fund_flow_industry({symbol})"
        )
        success = df is not None and not df.empty
        with FundRadar._ths_flow_cache_lock:
            FundRadar._ths_flow_cache[cache_key] = (time.time(), df, success)
        
        # If failed, mark this endpoint as blocked for 10 minutes
        # to prevent wasting time on retries for other period queries
        if not success:
            FundRadar._ths_flow_blocked_until = time.time() + 600
            print(f"[FundRadar] stock_fund_flow_industry blocked → skipping all calls for 10 min")
        
        return df

    def _fetch_multi_day_ths_direct(self, days, date_str):
        """
        Fetch multi-day aggregated data directly from THS APIs.
        Combines:
          1. stock_fund_flow_industry("N日排行") → 阶段涨跌幅, 流入, 流出, 净额
          2. stock_board_industry_index_ths() per sector (parallel) → 累计成交额
        Result: Full multi-day DF with both 净流入 and 总成交额.
        """
        ths_period_map = {3: '3日排行', 5: '5日排行', 10: '10日排行', 20: '20日排行'}
        period_label = ths_period_map.get(days)
        if not period_label:
            return None
        
        # Check class-level cache (valid for 30 minutes)
        cache_key = f"{days}_{date_str}"
        cached = FundRadar._multi_day_cache.get(cache_key)
        if cached:
            ts, df_cached = cached
            if time.time() - ts < 1800:  # 30 min cache
                print(f"[FundRadar] Multi-day {days}d: Using memory cache ({(time.time()-ts)/60:.0f}m old)")
                return df_cached
        
        print(f"[FundRadar] Multi-day {days}d: Fetching from THS directly...")
        
        try:
            # Step 1: Fetch multi-day fund flow ranking (with short-lived cache)
            df_flow = self._get_ths_flow_cached(period_label)
            if df_flow is None or df_flow.empty:
                print(f"[FundRadar] stock_fund_flow_industry({period_label}) returned empty")
                return None
            
            # Step 2: Fetch cumulative turnover via parallel history calls (rate-limited)
            end_dt = datetime.datetime.strptime(date_str, '%Y-%m-%d')
            start_dt = end_dt - datetime.timedelta(days=days + 10)  # Extra buffer for weekends/holidays
            start_str = start_dt.strftime('%Y%m%d')
            end_str = end_dt.strftime('%Y%m%d')
            
            sector_names = df_flow['行业'].tolist()
            hist_map = self._parallel_fetch_sector_history(sector_names, start_str, end_str, days)
            
            # Step 3: Merge into unified DataFrame
            rows = []
            for _, row in df_flow.iterrows():
                name = row['行业']
                try: 
                    net_flow = float(row.get('净额', 0))
                except (ValueError, TypeError): 
                    net_flow = 0.0
                
                try:
                    inflow = float(row.get('流入资金', 0))
                except (ValueError, TypeError):
                    inflow = 0.0
                    
                try:
                    outflow = float(row.get('流出资金', 0))
                except (ValueError, TypeError):
                    outflow = 0.0
                
                try:
                    pct_str = str(row.get('阶段涨跌幅', '0'))
                    pct = float(pct_str.replace('%', ''))
                except (ValueError, TypeError):
                    pct = 0.0
                
                # Get turnover from parallel fetch (already in 亿)
                hist_info = hist_map.get(name, {})
                turnover_yi = hist_info.get('turnover', 0.0)
                
                # Normalize net flow to 亿 if needed
                if abs(net_flow) > 100000:
                    net_flow /= 100000000.0
                if abs(inflow) > 100000:
                    inflow /= 100000000.0
                if abs(outflow) > 100000:
                    outflow /= 100000000.0
                
                rows.append({
                    '名称': name,
                    '净流入': net_flow,
                    '流入资金': inflow,
                    '流出资金': outflow,
                    '总成交额': turnover_yi,
                    '活跃天数': days,
                    '涨跌幅': pct,
                    '日均趋势': []  # Not available from ranking API
                })
            
            df_result = pd.DataFrame(rows)
            
            # Save to class-level cache
            FundRadar._multi_day_cache[cache_key] = (time.time(), df_result)
            print(f"[FundRadar] Multi-day {days}d: Fetched {len(df_result)} sectors successfully")
            return df_result
            
        except Exception as e:
            print(f"[FundRadar] Multi-day {days}d direct fetch failed: {e}")
            return None

    def _fetch_multi_day_via_summary(self, days, date_str):
        """
        Fallback: When stock_fund_flow_industry is blocked by anti-crawl,
        use stock_board_industry_summary_ths (today's snapshot with 净流入) 
        + stock_board_industry_index_ths (history) to construct multi-day data.
        
        Limitation: 净流入 is today-only (not N-day cumulative), but combined with
        history-derived 涨跌幅 and 总成交额, it still provides useful ranking data.
        """
        cache_key = f"summary_{days}_{date_str}"
        cached = FundRadar._multi_day_cache.get(cache_key)
        if cached:
            ts, df_cached = cached
            if time.time() - ts < 1800:
                print(f"[FundRadar] Multi-day {days}d (summary fallback): Using memory cache")
                return df_cached

        print(f"[FundRadar] Multi-day {days}d: Trying summary+history fallback...")
        
        try:
            # Step 1: Get sector list + today's net flow from summary API
            df_summary = self._rate_limited_call(
                ak.stock_board_industry_summary_ths,
                _retry_max=3, _label="ths_summary_fallback"
            )
            if df_summary is None or df_summary.empty:
                print(f"[FundRadar] Summary fallback also failed")
                return None
            
            # Step 2: Parallel fetch N-day history for turnover + pct
            end_dt = datetime.datetime.strptime(date_str, '%Y-%m-%d')
            start_dt = end_dt - datetime.timedelta(days=days + 15)
            start_str = start_dt.strftime('%Y%m%d')
            end_str = end_dt.strftime('%Y%m%d')
            
            sector_names = df_summary['板块'].tolist()
            hist_map = self._parallel_fetch_sector_history(sector_names, start_str, end_str, days)
            
            # Step 3: Merge
            rows = []
            for _, row in df_summary.iterrows():
                name = row['板块']
                try:
                    # 净流入 from summary (today only, unit varies)
                    net_flow = float(row.get('净流入', 0))
                except (ValueError, TypeError):
                    net_flow = 0.0
                
                hist_info = hist_map.get(name, {})
                turnover_yi = hist_info.get('turnover', 0.0)
                pct = hist_info.get('pct', 0.0)
                
                # Normalize net flow to 亿 if needed
                if abs(net_flow) > 100000:
                    net_flow /= 100000000.0
                
                rows.append({
                    '名称': name,
                    '净流入': net_flow,
                    '总成交额': turnover_yi,
                    '活跃天数': days,
                    '涨跌幅': pct,
                    '日均趋势': []
                })
            
            df_result = pd.DataFrame(rows)
            FundRadar._multi_day_cache[cache_key] = (time.time(), df_result)
            print(f"[FundRadar] Multi-day {days}d (summary fallback): Got {len(df_result)} sectors")
            return df_result
            
        except Exception as e:
            print(f"[FundRadar] Multi-day {days}d summary fallback failed: {e}")
            return None

    def _fetch_multi_day_history_direct(self, days, date_str):
        """
        For arbitrary periods (e.g. 60 days) not covered by THS ranking API.
        Uses stock_fund_flow_industry("20日排行") for net flow proxy +
        single parallel batch for both turnover AND pct from history.
        """
        cache_key = f"hist_{days}_{date_str}"
        cached = FundRadar._multi_day_cache.get(cache_key)
        if cached:
            ts, df_cached = cached
            if time.time() - ts < 1800:
                return df_cached
        
        print(f"[FundRadar] Multi-day {days}d (history): Fetching from THS...")
        
        try:
            # Rate-limited call for the ranking API (with short-lived cache)
            df_flow_20 = self._get_ths_flow_cached('20日排行')
            if df_flow_20 is None or df_flow_20.empty:
                return None
            
            end_dt = datetime.datetime.strptime(date_str, '%Y-%m-%d')
            start_dt = end_dt - datetime.timedelta(days=days + 15)
            start_str = start_dt.strftime('%Y%m%d')
            end_str = end_dt.strftime('%Y%m%d')
            
            sector_names = df_flow_20['行业'].tolist()
            # Single combined parallel fetch (turnover + pct in one pass)
            hist_map = self._parallel_fetch_sector_history(sector_names, start_str, end_str, days)
            
            rows = []
            for _, row in df_flow_20.iterrows():
                name = row['行业']
                try: net_flow = float(row.get('净额', 0))
                except: net_flow = 0.0
                if abs(net_flow) > 100000:
                    net_flow /= 100000000.0
                
                hist_info = hist_map.get(name, {})
                turnover_yi = hist_info.get('turnover', 0.0)
                pct = hist_info.get('pct', 0.0)
                
                rows.append({
                    '名称': name,
                    '净流入': net_flow,
                    '总成交额': turnover_yi,
                    '活跃天数': days,
                    '涨跌幅': pct,
                    '日均趋势': []
                })
            
            df_result = pd.DataFrame(rows)
            FundRadar._multi_day_cache[cache_key] = (time.time(), df_result)
            print(f"[FundRadar] Multi-day {days}d (history): Fetched {len(df_result)} sectors")
            return df_result
            
        except Exception as e:
            print(f"[FundRadar] Multi-day {days}d history fetch failed: {e}")
            return None


    def _parallel_fetch_sector_history(self, sector_names, start_str, end_str, max_days):
        """
        Rate-limited parallel fetch of sector history data.
        Returns BOTH turnover and pct_change in a single pass per sector.
        Uses a single batch cache file per (start, end, days) to keep disk clean.
        
        Returns: dict {name: {'turnover': float_yi, 'pct': float_pct}}
        """
        date_key = f"{start_str}_{end_str}_{max_days}"
        
        # Phase 1: Try to load entire batch from one disk file
        batch_cached = self._load_batch_cache(date_key)
        if batch_cached:
            # Verify it has enough sectors (in case the list changed)
            missing = [n for n in sector_names if n not in batch_cached]
            if not missing:
                print(f"[FundRadar] Sector history: All {len(sector_names)} from batch cache")
                return batch_cached
            else:
                # Partial hit: reuse cached, only fetch missing
                results = dict(batch_cached)
                to_fetch = missing
                print(f"[FundRadar] Sector history: {len(sector_names)-len(missing)} cached, {len(missing)} to fetch")
        else:
            results = {}
            to_fetch = list(sector_names)
            print(f"[FundRadar] Sector history: 0 cached, {len(to_fetch)} to fetch")
        
        if to_fetch:
            # Phase 2: Rate-limited parallel fetch for uncached sectors
            fetch_errors = []
            
            def fetch_one(name):
                df = self._rate_limited_call(
                    ak.stock_board_industry_index_ths,
                    symbol=name, start_date=start_str, end_date=end_str,
                    _retry_max=2, _label=f"hist({name})"
                )
                if df is not None and not df.empty:
                    df = df.sort_values('日期').tail(max_days)
                    turnover = df['成交额'].sum() / 1e8  # → 亿
                    pct = 0.0
                    if len(df) >= 2:
                        first_close = float(df.iloc[0]['收盘价'])
                        last_close = float(df.iloc[-1]['收盘价'])
                        if first_close > 0:
                            pct = ((last_close - first_close) / first_close) * 100
                    return name, {'turnover': turnover, 'pct': pct}, True
                return name, {'turnover': 0.0, 'pct': 0.0}, False
            
            with ThreadPoolExecutor(max_workers=self._API_MAX_WORKERS) as executor:
                futures = {executor.submit(fetch_one, s): s for s in to_fetch}
                done_count = 0
                for future in as_completed(futures):
                    name, data, success = future.result()
                    results[name] = data
                    done_count += 1
                    if not success:
                        fetch_errors.append(name)
                    if done_count % 20 == 0:
                        print(f"[FundRadar] Sector history progress: {done_count}/{len(to_fetch)}")
            
            # Phase 3: Save entire batch as ONE file
            self._save_batch_cache(date_key, results)
            
            if fetch_errors:
                print(f"[FundRadar] Sector history: {len(fetch_errors)} failed: {fetch_errors[:5]}{'...' if len(fetch_errors)>5 else ''}")
        
        return results

    def _get_multi_day_from_cache(self, end_date_str, days):
        """
        Legacy: Aggregate data from daily cache files.
        Fallback when direct THS API is unavailable.
        """
        all_dates = self.get_available_cache_dates()
        
        try:
            idx = all_dates.index(end_date_str)
        except ValueError:
            return pd.DataFrame(), []

        start_idx = max(0, idx - days + 1)
        target_dates = all_dates[start_idx : idx + 1]
        
        aggregated_stats = {} 
        
        for d_str in target_dates:
             data, _, _ = self.load_from_cache(d_str)
             if not data: continue
             
             ths_list = data.get('ths_sectors', [])
             for item in ths_list:
                 name = item.get('名称')
                 if not name: continue
                 
                 try: flow = float(item.get('净流入', 0))
                 except (ValueError, TypeError): flow = 0.0
                 if abs(flow) > 100000: flow /= 100000000.0
                     
                 try: turnover = float(item.get('总成交额', 0)) 
                 except (ValueError, TypeError): turnover = 0.0
                 if turnover > 100000: turnover /= 100000000.0

                 try: pct = float(item.get('涨跌幅', 0))
                 except (ValueError, TypeError): pct = 0.0
                 
                 if name not in aggregated_stats:
                     aggregated_stats[name] = {
                         'net_inflow': 0.0, 'turnover': 0.0, 'count': 0, 
                         'flows': [], 'turnovers': [], 'pcts': [], 'dates': []
                     }
                 
                 stats = aggregated_stats[name]
                 stats['net_inflow'] += flow
                 stats['turnover'] += turnover
                 stats['count'] += 1
                 stats['flows'].append(flow)
                 stats['turnovers'].append(turnover)
                 stats['pcts'].append(pct)
                 stats['dates'].append(d_str)
                 
        rows = []
        for name, stats in aggregated_stats.items():
            if stats['count'] > 0:
                avg_pct = sum(stats['pcts']) / stats['count']
                rows.append({
                    '名称': name,
                    '净流入': stats['net_inflow'],     
                    '总成交额': stats['turnover'],    
                    '活跃天数': stats['count'],
                    '涨跌幅': avg_pct,
                    '日均趋势': stats['flows'] 
                })
                
        df = pd.DataFrame(rows)
        return df, target_dates

    # --- Fetch Implementations (Rate-Limited) ---
    def _fetch_sina_sector(self):
        try:
            df = self._rate_limited_call(
                ak.stock_sector_spot, indicator="新浪行业",
                _label="sina_sector"
            )
            if df is not None and not df.empty:
                res = pd.DataFrame()
                res['名称'] = df['板块']
                res['涨跌幅'] = pd.to_numeric(df['涨跌幅'], errors='coerce')
                res['成交额'] = pd.to_numeric(df['总成交额'], errors='coerce')
                return res
        except: pass
        return pd.DataFrame()

    def _fetch_ths_sector(self):
        """
        Original THS fetcher via Akshare. 
        Now using ak.stock_board_industry_summary_ths() which provides Snapshot with Turnover.
        """
        try:
            df = self._rate_limited_call(
                ak.stock_board_industry_summary_ths,
                _label="ths_summary"
            )
            if df is None or df.empty:
                return pd.DataFrame()
            
            # Rename columns to match system expectations
            df = df.rename(columns={
                '板块': '名称',
            })
            
            # Ensure required columns exist
            required = ['名称', '涨跌幅', '总成交额', '净流入']
            for col in required:
                if col not in df.columns:
                    df[col] = 0.0
            
            return df[required]
        except Exception as e:
            print(f"[FundRadar] THS Akshare Fetch Error: {e}")
            return pd.DataFrame()

    def _fetch_ths_hyzjl_new(self):
        """
        Legacy scraper. Now Deprecated in favor of generic summary.
        """
        return pd.DataFrame()

    def _parse_ths_html_rows(self, text):
        import re
        rows_data = []
        trs = re.findall(r'<tr[^>]*>(.*?)</tr>', text, re.DOTALL)
        for tr in trs:
            tds = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.DOTALL)
            if len(tds) >= 8:
                clean_tds = [re.sub(r'<[^>]+>', '', td).strip() for td in tds]
                rows_data.append(clean_tds)
        return rows_data

    def get_market_snapshot(self):
        try:
            df = self._rate_limited_call(
                ak.stock_zh_index_spot_sina,
                _label="market_snapshot"
            )
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
