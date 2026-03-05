import pandas as pd
import json
import random
import akshare as ak
import datetime
import requests
import time
from functools import lru_cache
import numpy as np
from utils.simulator_logic import calculate_macd, calculate_rsi, process_baohan, find_bi, calculate_bi_and_centers

_LOG_TS = {}

def _allow_log(key, cooldown_sec=180):
    now = time.time()
    last = _LOG_TS.get(key, 0)
    if (now - last) < cooldown_sec:
        return False
    _LOG_TS[key] = now
    return True

# Using a simple memory cache for the current session run
# This will be cleared when the server restarts, satisfying "not stored on server disk"
def _fetch_em_fund_flow_direct(code, limit=1000):
    for attempt in range(3):
        try:
            c_str = str(code).zfill(6)
            # Determine secid
            if c_str.startswith(('6', '9')):
                secid = f"1.{c_str}"
            else:
                secid = f"0.{c_str}"
                
            cb_val = f"jQuery{random.randint(1000000000000000000, 9999999999999999999)}_{int(time.time() * 1000)}"
            _val = int(time.time() * 1000)
                
            url = f"https://push2his.eastmoney.com/api/qt/stock/fflow/kline/get?cb={cb_val}&lmt={limit}&klt=101&secid={secid}&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65&ut=b2884a393a59ad64002292a3e90d46a5&_={_val}"
            headers = {
                "User-Agent": f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{random.randint(110, 122)}.0.0.0 Safari/537.36",
                "Referer": "https://quote.eastmoney.com/",
                "Accept": "*/*",
                "Connection": "close"
            }
            
            res = requests.get(url, headers=headers, timeout=5)
            if res.status_code != 200:
                time.sleep(1)
                continue
                
            text = res.text
            if "(" not in text or ")" not in text:
                time.sleep(1)
                continue
                
            json_str = text[text.find("(")+1 : text.rfind(")")]
            data = json.loads(json_str)
            
            if not (data and data.get('data') and data['data'].get('klines')):
                time.sleep(1)
                continue
                
            klines = data['data']['klines']
            rows = []
            for k in klines:
                parts = k.split(',')
                # f51: date, f52: main, f53: small, f54: mid, f55: large, f56: super large
                rows.append({
                    '日期': parts[0],
                    '主力净流入-净额': float(parts[1]),
                    '小单净流入-净额': float(parts[2]),
                    '中单净流入-净额': float(parts[3]),
                    '大单净流入-净额': float(parts[4]),
                    '超大单净流入-净额': float(parts[5]),
                })
            return pd.DataFrame(rows)
        except Exception as e:
            if attempt == 2:
                print(f"Direct EM Fund Flow fetch failed for {code}: {e}")
            else:
                time.sleep(random.uniform(0.5, 1.5))
    return None

@lru_cache(maxsize=100)
def _fetch_akshare_data(code, market):
    # 优先使用带抗反爬和降级的直连方式
    df = _fetch_em_fund_flow_direct(code)
    if df is not None and not df.empty:
        return df

    try:
        # Fallback
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

@lru_cache(maxsize=1)
def _fetch_code_name_map():
    try:
        df = ak.stock_info_a_code_name()
        if df is None or df.empty:
            return {}
        codes = df['code'].astype(str).str.zfill(6)
        names = df['name'].astype(str)
        return dict(zip(codes, names))
    except Exception as e:
        print(f"Fetch code-name map failed: {e}")
        return {}

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
    except TypeError:
        # Catch TypeError specifically (e.g. 'NoneType' object is not subscriptable)
        print(f"Fetch gdhs warning for {code}: No data returned (TypeError/NoneType).")
        return None
    except Exception as e:
        # Check if the error message matches the known 'NoneType' issue which usually means data not found or API change
        # Log it as a warning but don't crash or clutter with stack trace if it's just missing data
        if "NoneType" in str(e):
            print(f"Fetch gdhs warning for {code}: No data returned (NoneType).")
        else:
            print(f"Fetch gdhs failed for {code}: {e}")
        return None


def _fetch_em_kline_direct(code, klt=101, limit=1000):
    for attempt in range(3):
        try:
            c_str = str(code)
            # Determine secid
            if c_str.startswith(('6', '9')):
                secid = f"1.{c_str}"
            elif c_str.startswith(('0', '3')):
                secid = f"0.{c_str}"
            elif c_str.startswith(('8', '4')):
                secid = f"0.{c_str}"
            else:
                secid = f"0.{c_str}"
                
            cb_val = f"jQuery{random.randint(1000000000000000000, 9999999999999999999)}_{int(time.time() * 1000)}"
            _val = int(time.time() * 1000)
            
            # User provided: ut=fa5fd1943c7b386f172d6893dbfba10b
            url = (
                f"https://push2his.eastmoney.com/api/qt/stock/kline/get?cb={cb_val}&secid={secid}"
                "&ut=fa5fd1943c7b386f172d6893dbfba10b"
                "&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
                f"&klt={klt}&fqt=1&end=20500101&lmt={limit}"
                f"&_={_val}"
            )
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Referer": "https://quote.eastmoney.com/",
                "Accept": "*/*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Connection": "close"
            }
            
            res = requests.get(url, headers=headers, timeout=5)
            if res.status_code != 200:
                time.sleep(1)
                continue
                
            text = res.text
            if "(" not in text or ")" not in text:
                time.sleep(1)
                continue
                
            json_str = text[text.find("(")+1 : text.rfind(")")]
            data = json.loads(json_str)
            
            if not (data and data.get('data') and data['data'].get('klines')):
                # Data payload is invalid or empty
                time.sleep(1)
                continue
                
            klines = data['data']['klines']
            rows = []
            for k in klines:
                parts = k.split(',')
                # f51: Date, f52: Open, f53: Close, f54: High, f55: Low, f56: Vol, f57: Amount
                rows.append({
                    '日期': parts[0],
                    '开盘': float(parts[1]),
                    '收盘': float(parts[2]),
                    '最高': float(parts[3]),
                    '最低': float(parts[4]),
                    '成交量': float(parts[5]),
                    '成交额': float(parts[6]),
                })
            return pd.DataFrame(rows)
        except Exception as e:
            if attempt == 2:
                print(f"Direct EM fetch failed for {code} klt={klt}: {e}")
            else:
                time.sleep(random.uniform(0.5, 1.5))
    return None

def _fetch_sina_kline_direct(code, scale=240, datalen=1000):
    try:
        symbol = f"{'sh' if str(code).startswith(('6', '9')) else 'sz'}{str(code).zfill(6)}"
        if str(code).startswith(('8', '4')):
            symbol = f"bj{str(code).zfill(6)}"
            
        api_url = (
            "https://quotes.sina.cn/cn/api/json_v2.php/"
            f"CN_MarketDataService.getKLineData?symbol={symbol}&scale={scale}&ma=no&datalen={datalen}"
        )
        headers = {
             "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        resp = requests.get(api_url, headers=headers, timeout=5)
        raw = resp.json()
        if raw:
            df = pd.DataFrame(raw)
            # Normalize Sina data to match EM/Akshare format
            # Sina: day, open, high, low, close, volume
            df.rename(columns={'day': '日期', 'open': '开盘', 'high': '最高', 'low': '最低', 'close': '收盘', 'volume': '成交量'}, inplace=True)
            # Ensure numeric types
            for col in ['开盘', '最高', '最低', '收盘', '成交量']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # Add '成交额' if missing (Sina doesn't return amount usually in kline, only volume)
            # We can approximate or leave it NaN?
            if '成交额' not in df.columns:
                 # Approximation: Amount = Volume * Close (Roughly)
                 # Or just leave it as None/0
                 df['成交额'] = df['成交量'] * df['收盘']
            
            return df
    except Exception as e:
        print(f"Sina direct fetch failed for {code}: {e}")
        return None

@lru_cache(maxsize=100)
def _fetch_daily_hist(code, start_date, end_date):
    # Try Sina Direct FIRST for Buy/Sell Assistant (better stability, less anti-scraping)
    df = _fetch_sina_kline_direct(code, scale=240)
    if df is not None and not df.empty:
        # Standardize date format to YYYYMMDD
        df['日期'] = df['日期'].str.replace('-', '')
        if start_date:
            df = df[df['日期'] >= start_date]
        if end_date:
            df = df[df['日期'] <= end_date]
        return df

    # Try Direct EM second
    df = _fetch_em_kline_direct(code, klt=101)
    if df is not None and not df.empty:
        df['日期'] = df['日期'].str.replace('-', '')
        if start_date:
            df = df[df['日期'] >= start_date]
        if end_date:
            df = df[df['日期'] <= end_date]
        return df

    try:
        df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start_date, end_date=end_date, adjust="qfq")
        return df
    except Exception as e:
        print(f"Fetch daily hist failed for {code}: {e}")
        return None

@lru_cache(maxsize=300)
def _fetch_kline_hist(code, period, start_date, end_date):
    # Fallback to Sina Direct FIRST
    scale_map = {
        '5m': 5,
        '15m': 15,
        '30m': 30,
        '60m': 60,
        '120m': 60,
        'day': 240,
        'week': 240,
    }
    if period in scale_map:
        df = _fetch_sina_kline_direct(code, scale=scale_map[period])
        if df is not None and not df.empty:
            return df
            
    # Try Direct EM second
    klt_map = {
        'day': 101,
        'week': 102,
        'month': 103,
        '5m': 5,
        '15m': 15,
        '30m': 30,
        '60m': 60,
        '120m': 60,
    }
    
    if period in klt_map:
        df = _fetch_em_kline_direct(code, klt=klt_map[period])
        if df is not None and not df.empty:
             return df

    try:
        period_map = {
            'day': 'daily',
            'week': 'weekly',
        }
        if period in period_map:
            return ak.stock_zh_a_hist(
                symbol=code,
                period=period_map[period],
                start_date=start_date,
                end_date=end_date,
                adjust="qfq"
            )
        minute_map = {
            '5m': '5',
            '15m': '15',
            '30m': '30',
            '60m': '60',
            '120m': '60',
        }
        if period in minute_map:
            return ak.stock_zh_a_hist_min_em(
                symbol=code,
                period=minute_map[period],
                adjust="qfq"
            )
        return None
    except Exception as e:
        print(f"Fetch kline failed for {code} {period}: {e}")
        return None

def _fetch_sina_quote(symbol):
    try:
        url = f"http://hq.sinajs.cn/list={symbol}"
        headers = {'Referer': 'http://finance.sina.com.cn'}
        r = requests.get(url, headers=headers, timeout=1.2)
        if r.status_code != 200:
            return None
        parts = r.text.split('=', 1)
        if len(parts) < 2:
            return None
        val = parts[1].strip().strip('";')
        if not val:
            return None
        q = val.split(',')
        if len(q) < 10:
            return None
        now = datetime.datetime.now()
        return {
            'date': pd.to_datetime(now.date()),
            'open': float(q[1]),
            'close': float(q[3]),
            'high': float(q[4]),
            'low': float(q[5]),
            'volume': float(q[8]),
            'amount': float(q[9]),
        }
    except Exception:
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

    def get_stock_name(self, code):
        code = str(code).strip().zfill(6)

        try:
            prefix = 'sh' if code.startswith('6') or code.startswith('9') else 'sz'
            if code.startswith('8') or code.startswith('4'): 
                prefix = 'bj'

            url = f"http://hq.sinajs.cn/list={prefix}{code}"
            headers = {'Referer': 'http://finance.sina.com.cn'}
            r = requests.get(url, headers=headers, timeout=1.2)
            if r.status_code == 200:
                parts = r.text.split('=', 1)
                if len(parts) < 2:
                    return None
                val = parts[1].strip().strip('";')
                if val:
                    quote_parts = val.split(',')
                    if len(quote_parts) > 1 and quote_parts[0]:
                        return quote_parts[0]
        except Exception as e:
            print(f"Sina name fetch failed: {e}")

        name_map = _fetch_code_name_map()
        name = name_map.get(code)
        if name:
            return name

        info = self.get_stock_info(code)
        name = info.get('股票简称')
        if name:
            return name

        return None

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

    def _normalize_kline_df(self, df):
        if df is None or df.empty:
            return pd.DataFrame()
        col_map = {
            '日期': 'date',
            '时间': 'date',
            'day': 'date',
            '开盘': 'open',
            '开盘价': 'open',
            '收盘': 'close',
            '收盘价': 'close',
            '最高': 'high',
            '最高价': 'high',
            '最低': 'low',
            '最低价': 'low',
            '成交量': 'volume',
            '成交额': 'amount',
        }
        out = df.copy()
        out = out.rename(columns={k: v for k, v in col_map.items() if k in out.columns})
        # Remove duplicate columns if any (e.g. if source has both 'amount' and '成交额' mapping to 'amount')
        out = out.loc[:, ~out.columns.duplicated()]
        
        if 'date' not in out.columns:
            return pd.DataFrame()
        out['date'] = pd.to_datetime(out['date'], errors='coerce')
        out = out.dropna(subset=['date'])
        for col in ['open', 'close', 'high', 'low', 'volume', 'amount']:
            if col in out.columns:
                out[col] = pd.to_numeric(out[col], errors='coerce')
            else:
                out[col] = np.nan
        out = out.dropna(subset=['open', 'close', 'high', 'low'])
        out = out.sort_values('date')
        out = out.drop_duplicates(subset=['date'], keep='last')
        out.set_index('date', inplace=True)
        return out[['open', 'high', 'low', 'close', 'volume', 'amount']]

    def _to_120m(self, df):
        if df is None or df.empty:
            return pd.DataFrame()
        if not isinstance(df.index, pd.DatetimeIndex):
            return pd.DataFrame()
        agg = df.resample('120min', label='right', closed='right').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum',
            'amount': 'sum',
        })
        return agg.dropna(subset=['open', 'close', 'high', 'low'])

    def _tdx_sma(self, series, n, m=1):
        clean = pd.to_numeric(series, errors='coerce').fillna(0.0)
        if clean.empty:
            return clean
        result = []
        prev = float(clean.iloc[0])
        for val in clean:
            prev = (m * float(val) + (n - m) * prev) / n
            result.append(prev)
        return pd.Series(result, index=clean.index)

    def get_kline_data(self, code, period='day', force_update=False):
        if force_update:
            _fetch_kline_hist.cache_clear()
        end_dt = datetime.datetime.now()
        if period in ['day', 'week']:
            start_dt = end_dt - datetime.timedelta(days=900)
            raw_df = _fetch_kline_hist(code, period, start_dt.strftime('%Y%m%d'), end_dt.strftime('%Y%m%d'))
        else:
            raw_df = _fetch_kline_hist(code, period, '', '')
        df = self._normalize_kline_df(raw_df)
        if period == 'day':
            try:
                start_recent = (end_dt - datetime.timedelta(days=10)).strftime('%Y%m%d')
                end_recent = end_dt.strftime('%Y%m%d')
                recent_ak = ak.stock_zh_a_hist(symbol=code, period='daily', start_date=start_recent, end_date=end_recent, adjust='qfq')
                recent_df = self._normalize_kline_df(recent_ak)
                if not recent_df.empty:
                    df = pd.concat([df, recent_df]).sort_index()
                    df = df[~df.index.duplicated(keep='last')]
            except Exception as e:
                if _allow_log(f"recent_daily_fallback_{code}", cooldown_sec=300):
                    print(f"Fetch recent daily fallback failed for {code}: {e}")

            symbol = f"{'sh' if str(code).startswith(('6', '9')) else 'sz'}{str(code).zfill(6)}"
            if str(code).startswith(('8', '4')):
                symbol = f"bj{str(code).zfill(6)}"
            quote_row = _fetch_sina_quote(symbol)
            if quote_row and quote_row['close'] > 0:
                qd = quote_row['date']
                if qd not in df.index or abs(float(df.loc[qd, 'close']) - quote_row['close']) > 1e-8:
                    df.loc[qd, ['open', 'high', 'low', 'close', 'volume', 'amount']] = [
                        quote_row['open'], quote_row['high'], quote_row['low'], quote_row['close'], quote_row['volume'], quote_row['amount']
                    ]
                df = df.sort_index()

        if period == '120m':
            df = self._to_120m(df)
        elif period == 'week' and not df.empty:
            df = df.resample('W-FRI').agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum',
                'amount': 'sum',
            }).dropna(subset=['open', 'high', 'low', 'close'])
        return df

    def build_buy_sell_assistant(self, kline_df):
        if kline_df is None or kline_df.empty:
            return {'kline': pd.DataFrame(), 'analysis': {}}
        df = kline_df.copy()
        close = df['close']
        high = df['high']
        low = df['low']
        volume = df['volume'].fillna(0).copy()
        
        # Optimization: Intraday Volume Projection
        # If the last bar is today and market is open/mid-day, volume is partial.
        # We project it to avoid false negatives in VUP check.
        try:
            last_idx = df.index[-1]
            last_dt = pd.to_datetime(last_idx) if isinstance(last_idx, (str, datetime.date, datetime.datetime)) else pd.to_datetime(df.iloc[-1]['date'])
            now = datetime.datetime.now()
            
            # Check if last bar is today
            if last_dt.date() == now.date():
                morning_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
                morning_close = now.replace(hour=11, minute=30, second=0, microsecond=0)
                afternoon_open = now.replace(hour=13, minute=0, second=0, microsecond=0)
                afternoon_close = now.replace(hour=15, minute=0, second=0, microsecond=0)
                
                elapsed_minutes = 0
                if now > morning_open and now < afternoon_close:
                    if now <= morning_close:
                        elapsed_minutes = (now - morning_open).total_seconds() / 60
                    elif now <= afternoon_open:
                        elapsed_minutes = 120 # Full morning
                    else:
                        elapsed_minutes = 120 + (now - afternoon_open).total_seconds() / 60
                    
                    if elapsed_minutes > 10: # Avoid noise at open
                        factor = 240.0 / elapsed_minutes
                        # Apply reasonable cap to factor (e.g. max 5x)
                        factor = min(factor, 5.0)
                        # Only adjust for logic calculation, not for display
                        volume.iloc[-1] = volume.iloc[-1] * factor
        except Exception as e:
            # print(f"Volume projection failed: {e}")
            pass

        ma60 = close.rolling(60, min_periods=1).mean()
        qsup = ma60 > ma60.shift(1)
        qsx = close.ewm(span=13, adjust=False).mean()
        vup = volume > (volume.rolling(20, min_periods=1).mean() * 1.5)
        tpm = (close > qsx) & (close.shift(1) <= qsx.shift(1)) & vup
        llv9 = low.rolling(9, min_periods=1).min()
        hhv9 = high.rolling(9, min_periods=1).max()
        rsv1 = ((close - llv9) / (hhv9 - llv9).replace(0, pd.NA) * 100).fillna(0)
        k1 = self._tdx_sma(rsv1, 3, 1)
        d1 = self._tdx_sma(k1, 3, 1)
        j1 = 3 * k1 - 2 * d1
        cdm = (j1.shift(1) < 0) & (j1 > j1.shift(1)) & qsup
        ma10 = close.rolling(10, min_periods=1).mean()
        gll = ((close - ma10) / ma10.replace(0, pd.NA) * 100).fillna(0)
        avggl = (((close - ma10).abs() / ma10.replace(0, pd.NA) * 100).fillna(0)).rolling(60, min_periods=1).mean()
        glv = avggl * 2.5
        glm = (gll < -glv) & (close > low)
        zhm = (tpm | cdm | glm).fillna(False)
        pdm = (qsx > close) & (qsx.shift(1) <= close.shift(1))
        cbm = (j1.shift(1) > 100) & (j1 < j1.shift(1)) & (~qsup)
        gls = (gll > glv) & (close < high)
        zhs = (pdm | cbm | gls).fillna(False)
        ph = pd.concat([(high - low), close * 0.005], axis=1).max(axis=1).fillna(0)
        buy_y = low - ph * 0.6
        sell_y = high + ph * 0.6
        wave_pct = ((close - qsx) / qsx.replace(0, pd.NA) * 100).fillna(0)
        ma5 = close.rolling(5, min_periods=1).mean()
        ma10_line = close.rolling(10, min_periods=1).mean()
        ma20 = close.rolling(20, min_periods=1).mean()
        ma30 = close.rolling(30, min_periods=1).mean()
        ma60_line = close.rolling(60, min_periods=1).mean()
        macd = calculate_macd(close.ffill().bfill().tolist())
        dif = pd.Series(macd.get('dif', []), index=df.index[-len(macd.get('dif', [])):]) if macd.get('dif') else pd.Series(0.0, index=df.index)
        dea = pd.Series(macd.get('dea', []), index=df.index[-len(macd.get('dea', [])):]) if macd.get('dea') else pd.Series(0.0, index=df.index)
        hist = pd.Series(macd.get('hist', []), index=df.index[-len(macd.get('hist', [])):]) if macd.get('hist') else pd.Series(0.0, index=df.index)
        dif = dif.reindex(df.index).fillna(0.0)
        dea = dea.reindex(df.index).fillna(0.0)
        hist = hist.reindex(df.index).fillna(0.0)
        golden_cross = (dif > dea) & (dif.shift(1) <= dea.shift(1))
        dead_cross = (dif < dea) & (dif.shift(1) >= dea.shift(1))
        out = df.copy()
        out['qsx'] = qsx
        out['buy_signal'] = zhm
        out['sell_signal'] = zhs
        out['buy_y'] = buy_y
        out['sell_y'] = sell_y
        out['wave_pct'] = wave_pct
        out['ma5'] = ma5
        out['ma10'] = ma10_line
        out['ma20'] = ma20
        out['ma30'] = ma30
        out['ma60'] = ma60_line
        out['dif'] = dif
        out['dea'] = dea
        out['macd_hist'] = hist
        out['golden_cross'] = golden_cross.fillna(False)
        out['dead_cross'] = dead_cross.fillna(False)
        analysis = self.build_chanlun_assistant(df, zhm, zhs, wave_pct)
        return {'kline': out, 'analysis': analysis}

    def build_chanlun_assistant(self, df, buy_signal=None, sell_signal=None, wave_pct=None):
        if df is None or df.empty:
            return {
                'structure': '数据缺失',
                'short_term': '无信号',
                'mid_term': '无信号',
                'macd': '-',
                'rsi': 50.0,
                'last_signal': '暂无',
                'summary': '暂无可用K线',
                'ma_alignment': '未知',
                'support_price': None,
                'pressure_price': None,
                'buy_zone': '-',
                'sell_zone': '-',
                'risk_line': '-',
                'action_plan': [],
                'bi_points': []
            }
        closes = pd.to_numeric(df['close'], errors='coerce').ffill().bfill().tolist()
        macd = calculate_macd(closes)
        rsi = calculate_rsi(closes)
        rsi_last = float(rsi[-1]) if rsi else 50.0
        records = df.reset_index().rename(columns={'index': 'date'}).to_dict('records')
        processed = process_baohan(records)
        bi_points = find_bi(processed)
        _, centers = calculate_bi_and_centers(processed)
        series_close = pd.Series(closes)
        ma5 = series_close.rolling(5, min_periods=1).mean()
        ma10 = series_close.rolling(10, min_periods=1).mean()
        ma20 = pd.Series(closes).rolling(20, min_periods=1).mean()
        ma60 = pd.Series(closes).rolling(60, min_periods=1).mean()
        trend_up = closes[-1] > ma20.iloc[-1] > ma60.iloc[-1]
        trend_down = closes[-1] < ma20.iloc[-1] < ma60.iloc[-1]
        if trend_up:
            mid_term = '多头趋势'
        elif trend_down:
            mid_term = '空头趋势'
        else:
            mid_term = '震荡整理'
        short_term = '观望'
        if macd.get('dif') and macd.get('dea'):
            if macd['dif'][-1] > macd['dea'][-1]:
                short_term = '短线偏多'
            else:
                short_term = '短线偏空'
        structure = f'笔{len(bi_points)} / 中枢{len(centers)}'
        if len(bi_points) >= 2:
            tail = bi_points[-1]['type']
            structure = f'{structure} · 最近{ "底分型" if tail == "bottom" else "顶分型"}'
        if ma5.iloc[-1] > ma10.iloc[-1] > ma20.iloc[-1] > ma60.iloc[-1]:
            ma_alignment = '多头排列'
        elif ma5.iloc[-1] < ma10.iloc[-1] < ma20.iloc[-1] < ma60.iloc[-1]:
            ma_alignment = '空头排列'
        else:
            ma_alignment = '均线缠绕'
        last_signal = '暂无'
        if buy_signal is not None and sell_signal is not None and len(df) > 0:
            buy_idx = list(df.index[buy_signal]) if hasattr(buy_signal, '__iter__') else []
            sell_idx = list(df.index[sell_signal]) if hasattr(sell_signal, '__iter__') else []
            if buy_idx or sell_idx:
                last_buy = buy_idx[-1] if buy_idx else pd.Timestamp.min
                last_sell = sell_idx[-1] if sell_idx else pd.Timestamp.min
                last_signal = f'最近信号：{"买" if last_buy > last_sell else "卖"}'
        support_price = float(ma20.iloc[-1])
        risk_price = float(ma60.iloc[-1])
        pressure_price = float(pd.to_numeric(df['high'], errors='coerce').tail(30).max())
        buy_low = support_price * 0.992
        buy_high = support_price * 1.012
        sell_low = pressure_price * 0.988
        sell_high = pressure_price * 1.012
        action_plan = [
            f"回踩{buy_low:.2f}~{buy_high:.2f}分批关注，跌破{risk_price:.2f}降低仓位",
            f"反弹至{sell_low:.2f}~{sell_high:.2f}可分批止盈，突破后看量能决定是否续持",
            f"当前为{ma_alignment}，建议单次仓位不超过3成并按信号逐步加减"
        ]
        wave_val = float(wave_pct.iloc[-1]) if wave_pct is not None and not wave_pct.empty else 0.0
        summary = f'{mid_term}，{short_term}，{ma_alignment}，波段值{wave_val:+.2f}%'
        bi_render = []
        for p in bi_points[-50:]: # Increase to last 50 points to be safe
            date_val = p.get('date')
            # Preserve full datetime string for matching
            bi_render.append({
                'type': p.get('type', ''),
                'price': float(p.get('price', 0)),
                'date': str(date_val)
            })
        return {
            'structure': structure,
            'short_term': short_term,
            'mid_term': mid_term,
            'macd': '金叉' if macd.get('dif') and macd.get('dea') and macd['dif'][-1] > macd['dea'][-1] else '死叉',
            'rsi': round(rsi_last, 1),
            'last_signal': last_signal,
            'summary': summary,
            'ma_alignment': ma_alignment,
            'support_price': round(support_price, 2),
            'pressure_price': round(pressure_price, 2),
            'buy_zone': f'{buy_low:.2f} ~ {buy_high:.2f}',
            'sell_zone': f'{sell_low:.2f} ~ {sell_high:.2f}',
            'risk_line': f'{risk_price:.2f}',
            'action_plan': action_plan,
            'bi_points': bi_render
        }

    def get_flow_data(self, code, force_update=False):
        market = self.guess_market(code)
        
        if force_update:
            _fetch_akshare_data.cache_clear() 
            _fetch_stock_info.cache_clear()
            _fetch_code_name_map.cache_clear()
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
                for col in ['开盘', '收盘', '最高', '最低', '成交量', '成交额']:
                    if col in hist_df.columns:
                        hist_df[col] = pd.to_numeric(hist_df[col], errors='coerce')

                # P_avg = Amount (Yuan) / (Volume (Hands) * 100)
                common_indices = df.index.intersection(hist_df.index)
                if not common_indices.empty:
                    hist_sub = hist_df.loc[common_indices]
                    vol = hist_sub['成交量'] * 100
                    amt = hist_sub['成交额']
                    vwap = amt / vol.replace(0, 1) 
                    p_avg_series = vwap
                    kline_col_map = {
                        '开盘': 'open',
                        '收盘': 'close',
                        '最高': 'high',
                        '最低': 'low',
                        '成交量': 'volume',
                    }
                    for src, dst in kline_col_map.items():
                        if src in hist_sub.columns:
                            df.loc[common_indices, dst] = hist_sub[src].values
            
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
                        weighted_retail_money = (small_net * 1.0) 
                        
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
                rc_series = pd.Series(retail_counts, index=sorted_dates).round(2)
                df['retail_count_index'] = rc_series
                
                # Direct Score for Bar Chart
                df['retail_score'] = pd.Series(retail_scores, index=sorted_dates).round(2)

        except Exception as e:
            print(f"Retail count calc failed (New Formula): {e}")
            import traceback
            traceback.print_exc()
        
        return df
