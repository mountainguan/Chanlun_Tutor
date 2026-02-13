"""
Shibor (上海银行间同业拆放利率) 数据获取与缓存模块
数据来源: 中国货币网 (chinamoney.com.cn)
API: POST https://www.chinamoney.com.cn/ags/ms/cm-u-bk-shibor/ShiborChrt?lang=CN
"""

import pandas as pd
import requests
import datetime
import os
from typing import Optional
from zoneinfo import ZoneInfo
import json
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Shibor 品种期限映射
SHIBOR_TERMS = {
    "O/N": "隔夜",
    "1W": "1周",
    "2W": "2周",
    "1M": "1个月",
    "3M": "3个月",
    "6M": "6个月",
    "9M": "9个月",
    "1Y": "1年",
}


class ShiborDataManager:
    """Shibor 利率数据管理器，支持获取、缓存和查询"""

    API_URL = "https://www.chinamoney.com.cn/ags/ms/cm-u-bk-shibor/ShiborChrt?lang=CN"

    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
            "Referer": "https://www.chinamoney.com.cn/chinese/bkshiborhischart/",
        }
        self.data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
        self.cache_file = os.path.join(self.data_dir, 'shibor_cache.csv')
        self.fetch_log_file = os.path.join(self.data_dir, 'market_fetch_log.json')

    # ── 缓存日志 ──────────────────────────────────────────────
    def _get_fetch_log_time(self):
        """获取上次 Shibor 数据拉取时间"""
        if os.path.exists(self.fetch_log_file):
            try:
                with open(self.fetch_log_file, 'r') as f:
                    log = json.load(f)
                    return log.get('last_shibor_fetch')
            except Exception:
                return None
        return None

    def _update_fetch_log_time(self):
        """记录本次拉取时间"""
        try:
            log = {}
            if os.path.exists(self.fetch_log_file):
                try:
                    with open(self.fetch_log_file, 'r') as f:
                        log = json.load(f)
                except Exception:
                    pass
            log['last_shibor_fetch'] = datetime.datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')
            with open(self.fetch_log_file, 'w') as f:
                json.dump(log, f)
        except Exception as e:
            print(f"[Shibor] Failed to update fetch log: {e}")

    # ── 本地缓存 ──────────────────────────────────────────────
    def load_cache(self) -> Optional[pd.DataFrame]:
        """从本地加载缓存数据"""
        if os.path.exists(self.cache_file):
            try:
                df = pd.read_csv(self.cache_file, parse_dates=['date'])
                df = df.sort_values('date').reset_index(drop=True)
                return df
            except Exception as e:
                print(f"[Shibor] Cache load failed: {e}")
        return None

    def save_cache(self, df: pd.DataFrame):
        """保存数据到本地缓存"""
        try:
            df.to_csv(self.cache_file, index=False)
        except Exception as e:
            print(f"[Shibor] Cache save failed: {e}")

    # ── 数据获取 ──────────────────────────────────────────────
    def fetch_from_api(self) -> Optional[pd.DataFrame]:
        """
        从中国货币网 API 获取 Shibor 历史数据
        返回 DataFrame，列: date, O/N, 1W, 2W, 1M, 3M, 6M, 9M, 1Y
        """
        try:
            r = requests.post(
                self.API_URL,
                headers=self.headers,
                timeout=15,
                verify=False,
            )
            r.raise_for_status()
            resp = r.json()

            csv_text = resp.get('data', {}).get('csv', '')
            columns = resp.get('data', {}).get('columns', [])

            if not csv_text or not columns:
                print("[Shibor] API returned empty data")
                return None

            # 解析 CSV 文本
            lines = [l.strip() for l in csv_text.split('\r\n') if l.strip()]
            if not lines:
                return None

            # columns: ['date','open','high','low','close','volume','O/N','1W','2W','1M','3M','6M','9M','1Y']
            rate_cols = [c for c in columns if c not in ('date', 'open', 'high', 'low', 'close', 'volume')]
            rows = []
            for line in lines:
                parts = line.split(',')
                if len(parts) < len(columns):
                    continue
                date_str = parts[0]
                # 利率数据从 index 6 开始 (跳过 date,open,high,low,close,volume)
                rate_values = {}
                for i, col_name in enumerate(rate_cols):
                    val_str = parts[6 + i] if (6 + i) < len(parts) else ''
                    try:
                        rate_values[col_name] = float(val_str) if val_str else None
                    except ValueError:
                        rate_values[col_name] = None
                row = {'date': date_str}
                row.update(rate_values)
                rows.append(row)

            df = pd.DataFrame(rows)
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
            df = df.dropna(subset=['date'])
            df = df.sort_values('date').reset_index(drop=True)

            print(f"[Shibor] Fetched {len(df)} records from API (from {df['date'].min().strftime('%Y-%m-%d')} to {df['date'].max().strftime('%Y-%m-%d')})")
            return df

        except Exception as e:
            print(f"[Shibor] API fetch failed: {e}")
            return None

    # ── 主入口 ────────────────────────────────────────────────
    def get_shibor_data(self, force_refresh=False) -> Optional[pd.DataFrame]:
        """
        获取 Shibor 数据（带缓存策略）
        - 默认每天最多从 API 拉取一次
        - force_refresh=True 强制刷新
        返回 DataFrame，列: date, O/N, 1W, 2W, 1M, 3M, 6M, 9M, 1Y
        """
        need_fetch = force_refresh

        if not need_fetch:
            last_fetch = self._get_fetch_log_time()
            if last_fetch:
                try:
                    last_dt = datetime.datetime.strptime(last_fetch, '%Y-%m-%d %H:%M:%S').replace(tzinfo=ZoneInfo('Asia/Shanghai'))
                    # 如果距上次拉取不足 6 小时，优先使用缓存
                    if (datetime.datetime.now(ZoneInfo('Asia/Shanghai')) - last_dt).total_seconds() < 6 * 3600:
                        cached = self.load_cache()
                        if cached is not None and not cached.empty:
                            return cached
                except Exception:
                    pass
            need_fetch = True

        if need_fetch:
            fresh = self.fetch_from_api()
            if fresh is not None and not fresh.empty:
                self.save_cache(fresh)
                self._update_fetch_log_time()
                return fresh

        # 兜底：返回缓存
        cached = self.load_cache()
        if cached is not None and not cached.empty:
            return cached

        return None

    def get_shibor_term(self, term: str = "O/N", force_refresh=False) -> Optional[pd.DataFrame]:
        """
        获取指定期限的 Shibor 利率时间序列
        term: "O/N", "1W", "2W", "1M", "3M", "6M", "9M", "1Y"
        返回 DataFrame，列: date, rate
        """
        df = self.get_shibor_data(force_refresh=force_refresh)
        if df is None or term not in df.columns:
            return None
        result = df[['date', term]].copy()
        result = result.rename(columns={term: 'rate'})
        result = result.dropna(subset=['rate'])
        return result
