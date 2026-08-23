"""
基金 / ETF 订阅跟踪数据层
==========================

数据源：Tushare Pro
    - pro.fund_basic      ：基金基础信息（含跟踪标的指数代码 index_code）
    - pro.fund_daily      ：基金日线行情（涨跌幅 / 净值）
    - pro.index_daily     ：指数日线行情（用于横向对比 4 大指数）

缓存策略：
    - 基金基础信息按交易日缓存（仅交易日更新，避免节假日的脏数据）
    - 基金日线行情缓存到 data/fund_tracker_cache/funds/ 目录
    - 指数日线行情缓存到 data/fund_tracker_cache/indexes/ 目录
    - 每次刷新只增量拉取最近 5 个交易日的数据

4 大指数 ts_code（固定）：
    - 上证指数   : 000001.SH
    - 深证成指   : 399001.SZ
    - 创业板指   : 399006.SZ
    - 科创50     : 000688.SH
"""

import os
import json
import re
import time
import datetime
import threading

import numpy as np
import pandas as pd
import requests
import tushare as ts


class FundTracker:
    """基金 / ETF 订阅跟踪数据层"""

    DATA_SOURCE = 'Tushare Pro'

    # ── 4 大指数固定映射 ─────────────────────────────────────
    # ts_code -> {name, short, bar, text}
    INDEX_DEFS = [
        {'ts_code': '000001.SH', 'name': '上证指数',   'short': '上证',   'bar': '#ef4444', 'text': 'text-rose-600'},
        {'ts_code': '399001.SZ', 'name': '深证成指',   'short': '深证',   'bar': '#f59e0b', 'text': 'text-amber-600'},
        {'ts_code': '399006.SZ', 'name': '创业板指数', 'short': '创业板', 'bar': '#10b981', 'text': 'text-emerald-600'},
        {'ts_code': '000688.SH', 'name': '科创50',     'short': '科创板', 'bar': '#3b82f6', 'text': 'text-blue-600'},
    ]
    INDEX_TS_CODE_MAP = {d['ts_code']: d for d in INDEX_DEFS}

    # ── 涨跌幅周期 ─────────────────────────────────────
    PERIOD_DEFS = [
        {'key': '1d',    'label': '当日',   'days': 1},
        {'key': '5d',    'label': '近5日',  'days': 5},
        {'key': '20d',   'label': '近20日', 'days': 20},
        {'key': '60d',   'label': '近60日', 'days': 60},
        {'key': 'ytd',   'label': '年内',   'days': None},  # 特殊处理
    ]

    CACHE_SCHEMA_VERSION = 1

    # ── Tushare Pro 限流：默认 190 req/min ─────────────────────
    _API_RPM_LIMIT = 190
    _api_lock = threading.Lock()
    _api_last_call_ts = 0.0
    _api_min_interval = 60.0 / _API_RPM_LIMIT  # ≈ 0.316s

    def __init__(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.data_dir = os.path.join(self.base_dir, 'data')
        self.cache_dir = os.path.join(self.data_dir, 'fund_tracker_cache')
        self.fund_cache_dir = os.path.join(self.cache_dir, 'funds')
        self.index_cache_dir = os.path.join(self.cache_dir, 'indexes')
        os.makedirs(self.fund_cache_dir, exist_ok=True)
        os.makedirs(self.index_cache_dir, exist_ok=True)

        self._pro = None
        self._fund_basic_cache = None  # 全市场基金基础信息 DataFrame

    # =================================================================
    # Tushare Pro 客户端
    # =================================================================

    def _get_pro(self):
        """获取 Tushare Pro 客户端。token 加载顺序：
        环境变量 TUSHARE_TOKEN > 项目根目录 tushare_token.txt > data/tushare_token.txt"""
        if self._pro is not None:
            return self._pro
        token = os.environ.get('TUSHARE_TOKEN', '').strip()
        if not token:
            candidates = [
                os.path.join(self.base_dir, 'tushare_token.txt'),
                os.path.join(self.data_dir, 'tushare_token.txt'),
            ]
            for path in candidates:
                if os.path.exists(path):
                    try:
                        with open(path, 'r', encoding='utf-8') as f:
                            token = f.read().strip()
                        if token:
                            break
                    except Exception as e:
                        print(f'[FundTracker] 读取 {path} 失败: {e}')
        if not token:
            raise RuntimeError(
                '未配置 TUSHARE_TOKEN。\n'
                '请通过以下任一方式配置：\n'
                '  1) 设置环境变量  TUSHARE_TOKEN=<你的token>\n'
                '  2) 在项目根目录或 data/ 下放置 tushare_token.txt（仅一行）\n'
                'token 在 https://tushare.pro 注册获取。'
            )
        ts.set_token(token)
        self._pro = ts.pro_api()
        return self._pro

    def _throttle(self):
        """全局节流：保证相邻两次 Tushare 调用间隔 ≥ _api_min_interval 秒。"""
        with self._api_lock:
            now = time.time()
            elapsed = now - self._api_last_call_ts
            if elapsed < self._api_min_interval:
                time.sleep(self._api_min_interval - elapsed)
            self._api_last_call_ts = time.time()

    # =================================================================
    # 基金基础信息
    # =================================================================

    def get_fund_basic(self, force_refresh: bool = False) -> pd.DataFrame:
        """获取全市场基金基础信息。
        字段：ts_code, name, management, custodian, fund_type, index_code, index_name,
              status, list_date
        """
        cache_file = os.path.join(self.cache_dir, 'fund_basic_cache.json')

        # 1) 缓存命中（仅当日有效）
        if not force_refresh and os.path.exists(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cache = json.load(f)
                if cache.get('date') == datetime.date.today().strftime('%Y-%m-%d'):
                    return pd.DataFrame(cache.get('records', []))
            except Exception as e:
                print(f'[FundTracker] fund_basic cache load error: {e}')

        # 2) 调 Tushare：分页拉取（fund_basic 没有分页，但 records 可能上千）
        pro = self._get_pro()
        all_records = []
        # 先取 ETF 类（lof + odii 涵盖场内 ETF 与场外 ETF）
        try:
            self._throttle()
            df_etf = pro.fund_basic(market='E', status='L',
                                    fields='ts_code,name,management,fund_type,index_code,index_name,status,list_date')
            if df_etf is not None and not df_etf.empty:
                all_records.append(df_etf)
        except Exception as e:
            print(f'[FundTracker] fund_basic(E) error: {e}')

        try:
            self._throttle()
            df_otc = pro.fund_basic(market='O', status='L',
                                    fields='ts_code,name,management,fund_type,index_code,index_name,status,list_date')
            if df_otc is not None and not df_otc.empty:
                all_records.append(df_otc)
        except Exception as e:
            print(f'[FundTracker] fund_basic(O) error: {e}')

        if not all_records:
            df = pd.DataFrame(columns=['ts_code', 'name', 'management', 'fund_type',
                                       'index_code', 'index_name', 'status', 'list_date'])
        else:
            df = pd.concat(all_records, ignore_index=True).drop_duplicates(subset=['ts_code'])

        # 3) 写缓存
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'date': datetime.date.today().strftime('%Y-%m-%d'),
                    'records': df.fillna('').to_dict(orient='records'),
                }, f, ensure_ascii=False)
        except Exception as e:
            print(f'[FundTracker] fund_basic cache save error: {e}')

        return df

    def search_funds(self, keyword: str, limit: int = 30) -> list:
        """按代码 / 名称 / 管理人模糊搜索基金。"""
        if not keyword:
            return []
        kw = keyword.strip().upper()
        df = self.get_fund_basic()
        if df.empty:
            return []
        # 名称去占位空格
        df = df.copy()
        df['name_clean'] = df['name'].astype(str).str.replace(r'\s+', '', regex=True)
        mask = (
            df['ts_code'].str.contains(kw, na=False, case=False) |
            df['name_clean'].str.contains(kw, na=False, case=False) |
            df['name'].str.contains(keyword.strip(), na=False, case=False) |
            df['management'].str.contains(keyword.strip(), na=False, case=False)
        )
        result = df[mask].head(limit)
        return result.fillna('').to_dict(orient='records')

    def get_fund_meta(self, ts_code: str) -> dict | None:
        """获取单只基金的完整基础信息（含 index_code / index_name）。"""
        df = self.get_fund_basic()
        if df.empty:
            return None
        row = df[df['ts_code'] == ts_code]
        if row.empty:
            return None
        rec = row.iloc[0].fillna('').to_dict()
        return rec

    # =================================================================
    # 基金日线行情
    # =================================================================

    def _fund_cache_path(self, ts_code: str) -> str:
        safe = ts_code.replace('.', '_')
        return os.path.join(self.fund_cache_dir, f'{safe}.csv')

    def _normalize_trade_date(self, df: pd.DataFrame) -> pd.DataFrame:
        """统一把 trade_date 列转成 datetime64（兼容 YYYYMMDD 字符串 / 时间戳 / 已是 datetime）。"""
        if df is None or df.empty or 'trade_date' not in df.columns:
            return df
        try:
            df['trade_date'] = pd.to_datetime(df['trade_date'], format='%Y%m%d', errors='coerce')
            df = df.dropna(subset=['trade_date'])
        except Exception:
            pass
        return df

    def load_fund_history(self, ts_code: str) -> pd.DataFrame:
        """加载本地缓存的基金日线历史（含 trade_date / close / pct_chg 等）。"""
        path = self._fund_cache_path(ts_code)
        if not os.path.exists(path):
            return pd.DataFrame()
        try:
            df = pd.read_csv(path)
            df = self._normalize_trade_date(df)
            df = df.sort_values('trade_date').reset_index(drop=True)
            return df
        except Exception as e:
            print(f'[FundTracker] load_fund_history({ts_code}) error: {e}')
            return pd.DataFrame()

    # 缓存最小窗口（日历日）：保证任何调用方切到「近 60 日」 / 「年内」时都有足够数据
    # 400 天 ≈ 280 交易日，覆盖近 60 日 + 年内（年初至今）
    _CACHE_MIN_DAYS = 400

    def _fetch_eastmoney_fund_history(self, fund_code: str) -> pd.DataFrame:
        """从天天基金（fund.eastmoney.com）拉取基金净值历史，返回标准化 df。

        fund_code: 6 位基金代号，如 '019889'（不含市场后缀）
        返回：trade_date / open / high / low / close / pct_chg / volume 等列
              （其中 open/high/low/volume 在场外基金无数据 → NaN；close = 单位净值）
        """
        if not fund_code or len(fund_code) != 6 or not fund_code.isdigit():
            return pd.DataFrame()
        url = f'http://fund.eastmoney.com/pingzhongdata/{fund_code}.js'
        try:
            res = requests.get(url, timeout=8,
                               headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'http://fund.eastmoney.com/'})
            text = res.text
        except Exception as e:
            print(f'[FundTracker] eastmoney fetch error: {e}')
            return pd.DataFrame()

        # 解析 Data_netWorthTrend = [{x: ms, y: unitNAV, equityReturn: pct, unitMoney: ''}, ...]
        import re
        m = re.search(r'Data_netWorthTrend\s*=\s*(\[.*?\]);', text, re.DOTALL)
        if not m:
            print(f'[FundTracker] eastmoney: netWorthTrend not found for {fund_code}')
            return pd.DataFrame()
        try:
            data = json.loads(m.group(1))
        except Exception as e:
            print(f'[FundTracker] eastmoney: parse netWorthTrend error: {e}')
            return pd.DataFrame()
        if not data:
            return pd.DataFrame()

        rows = []
        for entry in data:
            try:
                ts_ms = int(entry.get('x', 0))
                nav = float(entry.get('y', 0))
                pct = float(entry.get('equityReturn', 0) or 0)
                if ts_ms <= 0 or nav <= 0:
                    continue
                d = datetime.datetime.utcfromtimestamp(ts_ms / 1000.0).date()
                rows.append({
                    'trade_date': d.strftime('%Y%m%d'),
                    'close': nav,
                    'pct_chg': pct,
                })
            except Exception:
                continue
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        df = df.drop_duplicates(subset=['trade_date']).sort_values('trade_date').reset_index(drop=True)
        return df

    def _is_eastmoney_only(self, ts_code: str) -> bool:
        """判断该基金是否只能用天天基金（场外 OF，Tushare 无数据）。"""
        if not ts_code:
            return False
        return ts_code.endswith('.OF')

    def update_fund_history(self, ts_code: str, lookback_days: int = 5) -> pd.DataFrame:
        """增量更新单只基金日线（仅拉取最近 lookback_days 个交易日）。

        数据源策略：
          - 场内 ETF（.SH / .SZ） → 优先 Tushare fund_daily
          - 场外 OF → Tushare 不支持，自动走天天基金 pingzhongdata/{code}.js

        缓存策略：
          - 保留窗口固定为最近 _CACHE_MIN_DAYS 天，不会随 lookback_days 收缩
          - 当缓存最早一天晚于本次所需的 (today - lookback_days*4) 天时，
            强制从那一天补拉（避免切换周期后历史区间缺失）
        """
        cached = self.load_fund_history(ts_code)
        today = datetime.date.today()
        # 本次需要的日历日窗口（lookback_days*4 换算成日历日，留 60% 缓冲）
        needed_calendar_start = today - datetime.timedelta(days=max(lookback_days * 4, self._CACHE_MIN_DAYS))

        # ── 天天基金路径（场外 OF） ──
        if self._is_eastmoney_only(ts_code):
            fund_code = ts_code.split('.')[0]
            # 如果缓存已经覆盖到所需窗口起点，就跳过网络请求
            if not cached.empty and cached['trade_date'].min().date() <= needed_calendar_start:
                return cached
            df_new = self._fetch_eastmoney_fund_history(fund_code)
            if df_new is None or df_new.empty:
                return cached
            # 给 df_new 补齐 ts_code 列以保持一致
            df_new['ts_code'] = ts_code
            merged = pd.concat([cached, df_new], ignore_index=True)
            merged = self._normalize_trade_date(merged)
            merged = merged.drop_duplicates(subset=['trade_date']).sort_values('trade_date').reset_index(drop=True)
            if not merged.empty:
                cutoff = datetime.datetime.combine(today, datetime.time()) - datetime.timedelta(days=self._CACHE_MIN_DAYS)
                merged = merged[merged['trade_date'] >= cutoff]
            try:
                merged.to_csv(self._fund_cache_path(ts_code), index=False)
            except Exception as e:
                print(f'[FundTracker] save fund cache error: {e}')
            return merged

        # ── Tushare 路径（场内 ETF） ──
        pro = self._get_pro()

        start_date = ''
        force_backfill = False
        if not cached.empty:
            last_dt = cached['trade_date'].max()
            earliest_dt = cached['trade_date'].min()
            start_date = (last_dt + datetime.timedelta(days=1)).strftime('%Y%m%d')
            # 缓存最早一天比所需窗口还晚 → 需要从头补拉
            if earliest_dt.date() > needed_calendar_start:
                force_backfill = True
                start_date = needed_calendar_start.strftime('%Y%m%d')

        # 若 start_date 距今太远（> lookback_days × 3 个日历日），仍然只查近段
        if not start_date:
            start_date = needed_calendar_start.strftime('%Y%m%d')

        self._throttle()
        try:
            df_new = pro.fund_daily(ts_code=ts_code, start_date=start_date)
        except Exception as e:
            print(f'[FundTracker] fund_daily({ts_code}) error: {e}')
            df_new = pd.DataFrame()

        if df_new is None or df_new.empty:
            if force_backfill and not cached.empty:
                # 强制补拉却没拉到新数据 → 返回原缓存，不动
                return cached
            return cached

        # 合并（df_new 来自 Tushare，trade_date 是 'YYYYMMDD' 字符串，需统一转 datetime 才能比较）
        merged = pd.concat([cached, df_new], ignore_index=True)
        merged = self._normalize_trade_date(merged)
        merged = merged.drop_duplicates(subset=['trade_date']).sort_values('trade_date').reset_index(drop=True)

        # 仅保留 _CACHE_MIN_DAYS 天窗口，避免无界增长
        if not merged.empty:
            cutoff = datetime.datetime.combine(today, datetime.time()) - datetime.timedelta(days=self._CACHE_MIN_DAYS)
            merged = merged[merged['trade_date'] >= cutoff]

        try:
            merged.to_csv(self._fund_cache_path(ts_code), index=False)
        except Exception as e:
            print(f'[FundTracker] save fund cache error: {e}')
        return merged

    def fetch_fund_history(self, ts_code: str, lookback_days: int = 5) -> pd.DataFrame:
        """加载缓存 + 增量更新，保证返回的 df 是最新的。"""
        return self.update_fund_history(ts_code, lookback_days=lookback_days)

    # =================================================================
    # 指数日线行情
    # =================================================================

    def _index_cache_path(self, ts_code: str) -> str:
        safe = ts_code.replace('.', '_')
        return os.path.join(self.index_cache_dir, f'{safe}.csv')

    def load_index_history(self, ts_code: str) -> pd.DataFrame:
        path = self._index_cache_path(ts_code)
        if not os.path.exists(path):
            return pd.DataFrame()
        try:
            df = pd.read_csv(path)
            df = self._normalize_trade_date(df)
            df = df.sort_values('trade_date').reset_index(drop=True)
            return df
        except Exception as e:
            print(f'[FundTracker] load_index_history({ts_code}) error: {e}')
            return pd.DataFrame()

    def update_index_history(self, ts_code: str, lookback_days: int = 5) -> pd.DataFrame:
        cached = self.load_index_history(ts_code)
        pro = self._get_pro()

        today = datetime.date.today()
        needed_calendar_start = today - datetime.timedelta(days=max(lookback_days * 4, self._CACHE_MIN_DAYS))

        start_date = ''
        force_backfill = False
        if not cached.empty:
            last_dt = cached['trade_date'].max()
            earliest_dt = cached['trade_date'].min()
            start_date = (last_dt + datetime.timedelta(days=1)).strftime('%Y%m%d')
            if earliest_dt.date() > needed_calendar_start:
                force_backfill = True
                start_date = needed_calendar_start.strftime('%Y%m%d')
        if not start_date:
            start_date = needed_calendar_start.strftime('%Y%m%d')

        self._throttle()
        try:
            df_new = pro.index_daily(ts_code=ts_code, start_date=start_date)
        except Exception as e:
            print(f'[FundTracker] index_daily({ts_code}) error: {e}')
            df_new = pd.DataFrame()

        if df_new is None or df_new.empty:
            if force_backfill and not cached.empty:
                return cached
            return cached

        # 合并（df_new 来自 Tushare，trade_date 是 'YYYYMMDD' 字符串，需统一转 datetime 才能比较）
        merged = pd.concat([cached, df_new], ignore_index=True)
        merged = self._normalize_trade_date(merged)
        merged = merged.drop_duplicates(subset=['trade_date']).sort_values('trade_date').reset_index(drop=True)
        # 保留 _CACHE_MIN_DAYS 天窗口
        if not merged.empty:
            cutoff = datetime.datetime.combine(today, datetime.time()) - datetime.timedelta(days=self._CACHE_MIN_DAYS)
            merged = merged[merged['trade_date'] >= cutoff]
        try:
            merged.to_csv(self._index_cache_path(ts_code), index=False)
        except Exception as e:
            print(f'[FundTracker] save index cache error: {e}')
        return merged

    # =================================================================
    # 横向对比：4 大指数当日 / 多周期涨跌幅
    # =================================================================

    def get_indexes_compare(self) -> list:
        """获取 4 大指数的当日 + 多周期涨跌幅列表（dict）。"""
        results = []
        # 一次性拉够窗口，覆盖最长的「近 60 日」+ 「年内」两种周期
        for d in self.INDEX_DEFS:
            df = self.update_index_history(d['ts_code'], lookback_days=120)
            row = dict(d)  # ts_code, name, short, bar, text
            if df is None or df.empty:
                row.update({
                    'close': None,
                    'pct_1d': None,
                    'pct_5d': None,
                    'pct_20d': None,
                    'pct_60d': None,
                    'pct_ytd': None,
                    'last_date': None,
                })
                results.append(row)
                continue

            df = df.reset_index(drop=True)
            last = df.iloc[-1]
            row['close'] = float(last.get('close', 0)) if pd.notna(last.get('close')) else None
            row['last_date'] = last['trade_date'].strftime('%Y-%m-%d') if pd.notna(last.get('trade_date')) else None

            # pct_chg 字段是单日涨跌幅（百分比），需要我们自己算周期内累计涨跌幅
            close = df['close'].astype(float).reset_index(drop=True)
            n = len(close)

            def pct_n(n_days: int) -> float | None:
                if n_days <= 0 or n < n_days + 1:
                    return None
                c_now = close.iloc[-1]
                c_prev = close.iloc[-(n_days + 1)]
                if c_prev == 0 or pd.isna(c_prev) or pd.isna(c_now):
                    return None
                return float((c_now - c_prev) / c_prev * 100.0)

            row['pct_1d'] = pct_n(1)
            row['pct_5d'] = pct_n(5)
            row['pct_20d'] = pct_n(20)
            row['pct_60d'] = pct_n(60)

            # 年内涨跌幅：以今年首个交易日为基准
            try:
                df['year'] = df['trade_date'].dt.year
                this_year_df = df[df['year'] == datetime.date.today().year]
                if len(this_year_df) >= 2:
                    c_now = this_year_df['close'].iloc[-1]
                    c_ytd = this_year_df['close'].iloc[0]
                    if c_ytd and pd.notna(c_ytd) and pd.notna(c_now):
                        row['pct_ytd'] = float((c_now - c_ytd) / c_ytd * 100.0)
                    else:
                        row['pct_ytd'] = None
                else:
                    row['pct_ytd'] = None
            except Exception:
                row['pct_ytd'] = None

            results.append(row)
        return results

    # =================================================================
    # 订阅基金组合表现
    # =================================================================

    def get_subs_performance(self, subs: list, period_key: str = '1d', fund_overrides: dict | None = None) -> dict:
        """批量计算订阅基金列表在指定周期下的表现。

        subs: [{"ts_code": "510300.SH", "name": "沪深300ETF", "index_code": "000300.SH",
                "index_name": "沪深300", "benchmark_period": "1d"}, ...]

        fund_overrides: { ts_code: [{date: 'YYYYMMDD', close: float, pct_chg: float}, ...] }
                       —— 由浏览器 fetch 天天基金后回填；存在时优先使用，绕过服务端

        返回：
            {
                "as_of_date": "2026-08-21",
                "rows": [
                    {"fund_ts_code": ..., "fund_name": ..., "fund_pct": ..., "index_code": ...,
                     "index_name": ..., "index_pct": ..., "excess": ...},
                    ...
                ],
                "summary": {"avg_fund_pct": ..., "avg_index_pct": ..., "avg_excess": ...},
                "index_compare": [...4 大指数同周期数据...]
            }
        """
        fund_overrides = fund_overrides or {}

        def _override_to_df(rows_list):
            """把浏览器返回的 [{date, close, pct_chg}, ...] 转成标准 df。"""
            if not rows_list:
                return pd.DataFrame()
            try:
                df = pd.DataFrame(rows_list)
                if 'date' in df.columns:
                    df = df.rename(columns={'date': 'trade_date'})
                df['trade_date'] = pd.to_datetime(df['trade_date'], format='%Y%m%d', errors='coerce')
                df = df.dropna(subset=['trade_date'])
                df['close'] = pd.to_numeric(df['close'], errors='coerce')
                return df.sort_values('trade_date').reset_index(drop=True)
            except Exception:
                return pd.DataFrame()

        # 1) 4 大指数同周期数据（用于头部卡片）
        indexes_compare = self.get_indexes_compare()
        index_compare_by_period = []
        for row in indexes_compare:
            row2 = dict(row)
            row2['period_pct'] = row.get(f'pct_{period_key}', None)
            index_compare_by_period.append(row2)

        # 2) 订阅基金逐只计算
        period_days_map = {'1d': 1, '5d': 5, '20d': 20, '60d': 60}
        n_days = period_days_map.get(period_key, None)  # None 表示 ytd
        is_ytd = (period_key == 'ytd')
        # 拉取窗口：n_days 已知 → 用 n_days + 2；ytd → 需要覆盖本年初至今
        if is_ytd:
            fund_lookback = 120  # ≈ 240 交易日，覆盖年初至今
        else:
            fund_lookback = max(5, n_days + 2)

        rows = []
        fund_pcts = []
        idx_pcts = []
        excess_list = []

        # 用于记录所有需要的指数代码（订阅里指定的对标指数 + 4 大指数），做批量拉取
        needed_index_codes = set(self.INDEX_TS_CODE_MAP.keys())

        for sub in subs:
            fund_ts = sub.get('ts_code')
            if not fund_ts:
                continue
            # 浏览器预拉取数据 → 优先使用；服务端 eastmoney 仅作兜底
            override = fund_overrides.get(fund_ts)
            if override:
                fund_df = _override_to_df(override)
            else:
                fund_df = self.fetch_fund_history(fund_ts, lookback_days=fund_lookback)
            if is_ytd:
                fund_pct = _pct_ytd_from_df(fund_df)
            else:
                fund_pct = _pct_n_from_df(fund_df, n_days)
            if fund_pct is not None:
                fund_pcts.append(fund_pct)

            # 对标指数（用户指定，可能是 4 大指数之一，也可能是其它）
            user_index_code = sub.get('index_code', '') or ''
            index_pct = None
            index_name = sub.get('index_name', '') or ''

            if user_index_code:
                needed_index_codes.add(user_index_code)
                # 拉对标指数日线（复用 4 大指数缓存；自定义的指数另外缓存）
                idx_df = self._load_index_history_any(user_index_code)
                if idx_df is None or idx_df.empty:
                    idx_df = self._fetch_and_cache_index(user_index_code, lookback_days=fund_lookback)
                if is_ytd:
                    index_pct = _pct_ytd_from_df(idx_df)
                else:
                    index_pct = _pct_n_from_df(idx_df, n_days)
                # 若用户填了 code 但没填 name，则用元数据补
                if not index_name:
                    index_name = sub.get('index_code', '')

            row = {
                'fund_ts_code': fund_ts,
                'fund_name': sub.get('name', ''),
                'fund_pct': fund_pct,
                'index_code': user_index_code,
                'index_name': index_name,
                'index_pct': index_pct,
                'excess': (fund_pct - index_pct) if (fund_pct is not None and index_pct is not None) else None,
            }
            rows.append(row)
            if index_pct is not None:
                idx_pcts.append(index_pct)
            if row['excess'] is not None:
                excess_list.append(row['excess'])

        summary = {
            'avg_fund_pct': float(np.mean(fund_pcts)) if fund_pcts else None,
            'avg_index_pct': float(np.mean(idx_pcts)) if idx_pcts else None,
            'avg_excess': float(np.mean(excess_list)) if excess_list else None,
            'count': len(rows),
            'valid_count': len(fund_pcts),
        }

        # as_of_date: 优先用 override 的最新日期；其次服务端缓存
        as_of = None
        for r in rows:
            if r['fund_pct'] is not None:
                ts_code = r['fund_ts_code']
                if ts_code in fund_overrides and fund_overrides[ts_code]:
                    try:
                        last_raw = fund_overrides[ts_code][-1].get('date')
                        if last_raw:
                            as_of = f"{last_raw[:4]}-{last_raw[4:6]}-{last_raw[6:8]}"
                            break
                    except Exception:
                        pass
                d = self.load_fund_history(ts_code)
                if not d.empty:
                    as_of = d['trade_date'].max().strftime('%Y-%m-%d')
                    break
        if as_of is None:
            for ic in indexes_compare:
                if ic.get('last_date'):
                    as_of = ic['last_date']
                    break
        if as_of is None:
            as_of = datetime.date.today().strftime('%Y-%m-%d')

        return {
            'as_of_date': as_of,
            'period_key': period_key,
            'rows': rows,
            'summary': summary,
            'index_compare': index_compare_by_period,
        }

    # =================================================================
    # 内部辅助：自定义指数代码的缓存管理（不限于 4 大指数）
    # =================================================================

    def _index_cache_path_any(self, ts_code: str) -> str:
        """4 大指数走 indexes/，其它走 custom_indexes/"""
        if ts_code in self.INDEX_TS_CODE_MAP:
            return self._index_cache_path(ts_code)
        custom_dir = os.path.join(self.cache_dir, 'custom_indexes')
        os.makedirs(custom_dir, exist_ok=True)
        safe = ts_code.replace('.', '_')
        return os.path.join(custom_dir, f'{safe}.csv')

    def _load_index_history_any(self, ts_code: str) -> pd.DataFrame:
        path = self._index_cache_path_any(ts_code)
        if not os.path.exists(path):
            return pd.DataFrame()
        try:
            df = pd.read_csv(path)
            df = self._normalize_trade_date(df)
            df = df.sort_values('trade_date').reset_index(drop=True)
            return df
        except Exception:
            return pd.DataFrame()

    def _fetch_and_cache_index(self, ts_code: str, lookback_days: int = 5) -> pd.DataFrame:
        """拉取任意指数代码的日线并写入对应缓存（4 大指数走专用路径，其它走 custom）。"""
        cached = self._load_index_history_any(ts_code)
        pro = self._get_pro()
        today = datetime.date.today()
        needed_calendar_start = today - datetime.timedelta(days=max(lookback_days * 4, self._CACHE_MIN_DAYS))

        start_date = ''
        force_backfill = False
        if not cached.empty:
            last_dt = cached['trade_date'].max()
            earliest_dt = cached['trade_date'].min()
            start_date = (last_dt + datetime.timedelta(days=1)).strftime('%Y%m%d')
            if earliest_dt.date() > needed_calendar_start:
                force_backfill = True
                start_date = needed_calendar_start.strftime('%Y%m%d')
        if not start_date:
            start_date = needed_calendar_start.strftime('%Y%m%d')

        self._throttle()
        try:
            df_new = pro.index_daily(ts_code=ts_code, start_date=start_date)
        except Exception as e:
            print(f'[FundTracker] custom index_daily({ts_code}) error: {e}')
            df_new = pd.DataFrame()

        if df_new is None or df_new.empty:
            if force_backfill and not cached.empty:
                return cached
            return cached

        # 合并（df_new 来自 Tushare，trade_date 是 'YYYYMMDD' 字符串，需统一转 datetime 才能后续比较）
        merged = pd.concat([cached, df_new], ignore_index=True)
        merged = self._normalize_trade_date(merged)
        merged = merged.drop_duplicates(subset=['trade_date']).sort_values('trade_date').reset_index(drop=True)
        # 保留 _CACHE_MIN_DAYS 天窗口
        if not merged.empty:
            cutoff = datetime.datetime.combine(today, datetime.time()) - datetime.timedelta(days=self._CACHE_MIN_DAYS)
            merged = merged[merged['trade_date'] >= cutoff]
        try:
            merged.to_csv(self._index_cache_path_any(ts_code), index=False)
        except Exception as e:
            print(f'[FundTracker] save custom index cache error: {e}')
        return merged


def _pct_n_from_df(df: pd.DataFrame, n_days: int) -> float | None:
    """从日线 df 计算最近 n_days 的累计涨跌幅（%）。"""
    if df is None or df.empty or 'close' not in df.columns:
        return None
    df = df.sort_values('trade_date').reset_index(drop=True)
    if len(df) < n_days + 1 or n_days <= 0:
        return None
    try:
        c_now = float(df['close'].iloc[-1])
        c_prev = float(df['close'].iloc[-(n_days + 1)])
        if c_prev == 0:
            return None
        return (c_now - c_prev) / c_prev * 100.0
    except Exception:
        return None


def _pct_ytd_from_df(df: pd.DataFrame, today: datetime.date | None = None) -> float | None:
    """从日线 df 计算年内累计涨跌幅（今年首个交易日到最新一天）。"""
    if df is None or df.empty or 'close' not in df.columns:
        return None
    if today is None:
        today = datetime.date.today()
    try:
        df = df.copy()
        # trade_date 可能是 datetime / Timestamp，取年份
        years = df['trade_date'].dt.year
        ytd_df = df[years == today.year]
        if len(ytd_df) < 2:
            return None
        c_now = float(ytd_df['close'].iloc[-1])
        c_ytd = float(ytd_df['close'].iloc[0])
        if c_ytd == 0 or pd.isna(c_ytd) or pd.isna(c_now):
            return None
        return (c_now - c_ytd) / c_ytd * 100.0
    except Exception:
        return None