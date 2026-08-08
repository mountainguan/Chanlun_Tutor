"""
成交集中度拥挤度（Trading Concentration Crowding）
==================================================

定义：板块（行业 / 指数）内按成交量（成交额）排序的【前 5% 个股】合计
占板块总量的比例，用于衡量交易的拥挤程度。

数据源（Tushare Pro，token 从环境变量 TUSHARE_TOKEN 或
项目根目录 / data 目录下的 tushare_token.txt 读取）：
    - pro.daily      : 全市场日行情
        vol 成交量（手）/ amount 成交额（千元）
    - pro.stock_basic: 行业分类（兜底；优先本地 data/stock_industry_cache.json）
    - pro.trade_cal  : 交易日历

计算口径：
    - 行业集中度 = 行业内成交量(成交额)前 5% 个股合计 ÷ 行业总量 × 100%
    - 指数集中度 = 指数成分股内成交量(成交额)前 5% 个股合计 ÷ 指数总量 × 100%
    - 前 5% 数量   = max(1, ceil(个股数 × 5%))
    - 集中度 > 45% 标记为拥挤（成交量维度与成交额维度分别统计）

历史数据：按交易日增量拉取，缓存于 data/trading_crowding/ 目录：
    - trading_crowding_history.csv        行业维度
    - trading_crowding_index_history.csv  指数维度
支持断点续跑（resume）。
"""

import os
import json
import math
import time
import datetime

import numpy as np
import pandas as pd
import tushare as ts

from utils.sector_crowding import SectorCrowding


class TradingCrowding:
    """成交集中度拥挤度数据层：拉取、聚合、缓存、查询。"""

    DATA_SOURCE = 'Tushare Pro'
    SCHEMA_VERSION = 1
    HISTORY_YEARS = 3
    # 前 5% 个股占比（成交量 / 成交额分别按各自排序取前 5%）
    TOP_PCT = 0.05
    # 集中度高于该值（%）标记为拥挤
    THRESHOLD = 45.0

    CSV_COLUMNS = [
        'trade_date', 'industry', 'stock_count',
        'total_vol', 'top5_vol', 'vol_concentration_pct',
        'total_amount', 'top5_amount', 'amount_concentration_pct',
    ]
    INDEX_CSV_COLUMNS = [
        'trade_date', 'index_code', 'index_name', 'stock_count', 'coverage',
        'total_vol', 'top5_vol', 'vol_concentration_pct',
        'total_amount', 'top5_amount', 'amount_concentration_pct',
    ]

    def __init__(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.data_dir = os.path.join(self.base_dir, 'data')
        self.cache_dir = os.path.join(self.data_dir, 'trading_crowding')
        os.makedirs(self.cache_dir, exist_ok=True)
        self.history_file = os.path.join(self.cache_dir, 'trading_crowding_history.csv')
        self.index_history_file = os.path.join(
            self.cache_dir, 'trading_crowding_index_history.csv')
        self.meta_file = os.path.join(self.cache_dir, 'meta.json')
        self._pro = None
        self._industry_map = None
        self._index_groups = None

    # ==================== Tushare Pro 客户端 ====================

    def _get_pro(self):
        """获取 Tushare Pro 客户端。
        token 加载顺序：环境变量 TUSHARE_TOKEN > 项目根目录 tushare_token.txt
        > data/tushare_token.txt"""
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
                        print(f'[TradingCrowding] 读取 {path} 失败: {e}')
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

    # ==================== 映射与成分股 ====================

    def _get_industry_map(self):
        """ts_code -> 证监会行业。
        优先 Tushare stock_basic 全市场分类（与两融维度口径一致，
        避免本地缓存仅覆盖部分股票导致行业样本严重缩水）；
        接口失败时兜底本地 data/stock_industry_cache.json。"""
        if self._industry_map is not None:
            return self._industry_map
        ts_to_ind = {}
        try:
            pro = self._get_pro()
            df = pro.stock_basic(list_status='L', fields='ts_code,industry')
            if df is not None and not df.empty:
                ts_to_ind = dict(zip(df['ts_code'], df['industry']))
        except Exception as e:
            print(f'[TradingCrowding] 拉取全市场行业分类失败，回退本地缓存: {e}')
        if not ts_to_ind:
            path = os.path.join(self.data_dir, 'stock_industry_cache.json')
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    si = json.load(f)
                for code, info in si.items():
                    if isinstance(info, dict):
                        ind = info.get('industry')
                        if not ind:
                            continue
                        ind = SectorCrowding._normalize(ind)
                        if not ind:
                            continue
                        cstr = str(code).strip()
                        if cstr.startswith(('6', '9', '5', '8', '4')):
                            ts_to_ind[f'{cstr}.SH'] = ind
                        else:
                            ts_to_ind[f'{cstr}.SZ'] = ind
            except Exception as e:
                print(f'[TradingCrowding] 读取行业缓存失败: {e}')
        self._industry_map = ts_to_ind
        return ts_to_ind

    def _get_index_groups(self):
        """返回 [(指数代码, 指数名, [成分股 ts_code])]，口径与 SectorCrowding 一致。"""
        if self._index_groups is not None:
            return self._index_groups
        sc = SectorCrowding()
        groups = []
        for code, name, scope in SectorCrowding.INDEX_LIST:
            if scope is None and code in SectorCrowding.INDEX_LIST_SCOPE_MAP:
                scope = SectorCrowding.INDEX_LIST_SCOPE_MAP[code]
            cache_path = os.path.join(
                self.data_dir, 'index_constituents_cache', f'index_cons_{code}.json'
            )
            if scope and not os.path.exists(cache_path):
                idx_name = SectorCrowding._SCOPE_NAMES.get(scope, code)
                codes = sc._load_all_a_share_codes(scope)
            elif os.path.exists(cache_path):
                idx_name, codes = sc._load_index_constituents(code)
            else:
                if scope:
                    idx_name = SectorCrowding._SCOPE_NAMES.get(scope, code)
                    codes = sc._load_all_a_share_codes(scope)
                else:
                    idx_name, codes = sc._load_index_constituents(code)
            if codes:
                groups.append((code, idx_name or name, codes))
        self._index_groups = groups
        return groups

    # ==================== 单日聚合 ====================

    @staticmethod
    def _concentration(d, group_col):
        """纯函数（便于测试）：按 group_col 分组，计算成交量/成交额前 5% 集中度。
        入参 d 需含 ts_code / vol / amount / group_col，返回按组聚合的 DataFrame。

        成交量维度：按 vol 降序取前 5% 个股，其 vol 合计 / 组内总 vol；
        成交额维度：按 amount 降序取前 5% 个股，其 amount 合计 / 组内总 amount。
        （两个维度各自独立排序、独立统计。）"""
        if d is None or d.empty:
            return pd.DataFrame()
        df = d[['ts_code', 'vol', 'amount', group_col]].copy()
        df = df.dropna(subset=[group_col])
        for col in ('vol', 'amount'):
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df = df.dropna(subset=['vol', 'amount'])
        df = df[df['vol'] > 0]
        if df.empty:
            return pd.DataFrame()

        # 组内前 5% 个股数 = max(1, ceil(n × 5%))，两个维度一致
        sizes = df.groupby(group_col, sort=False).size().rename('stock_count')
        ks = sizes.apply(lambda n: max(1, int(math.ceil(n * TradingCrowding.TOP_PCT))))

        parts = []
        for metric in ('vol', 'amount'):
            tmp = df.sort_values([group_col, metric], ascending=[True, False])
            g = tmp.groupby(group_col, sort=False)
            tmp['_rank'] = tmp.groupby(group_col).cumcount()
            tmp['_k'] = tmp[group_col].map(ks)
            top = tmp[tmp['_rank'] < tmp['_k']]
            top_sum = top.groupby(group_col)[metric].sum().rename(f'top5_{metric}')
            total_sum = g[metric].sum().rename(f'total_{metric}')
            part = pd.DataFrame({f'top5_{metric}': top_sum,
                                 f'total_{metric}': total_sum})
            part[f'{metric}_concentration_pct'] = np.where(
                part[f'total_{metric}'] > 0,
                part[f'top5_{metric}'] / part[f'total_{metric}'] * 100.0,
                np.nan,
            )
            parts.append(part)

        out = pd.concat([sizes] + parts, axis=1)
        out = out.reset_index()
        out['stock_count'] = out['stock_count'].astype(int)
        return out

    @staticmethod
    def aggregate_industries(daily_df, industry_map):
        """纯聚合函数（便于测试）：
        daily_df 为 Tushare pro.daily 原始结果（需含 ts_code/vol/amount），
        industry_map 为 ts_code -> 行业。返回按行业聚合后的 DataFrame。"""
        if daily_df is None or daily_df.empty:
            return pd.DataFrame(columns=TradingCrowding.CSV_COLUMNS[1:])
        d = daily_df[['ts_code', 'vol', 'amount']].copy()
        d['industry'] = d['ts_code'].map(industry_map)
        out = TradingCrowding._concentration(d, 'industry')
        if out.empty:
            return pd.DataFrame(columns=TradingCrowding.CSV_COLUMNS[1:])
        return out

    @staticmethod
    def aggregate_indices(daily_df, index_groups):
        """纯聚合函数（便于测试）：
        index_groups 为 [(指数代码, 指数名, [成分股 ts_code])]。"""
        if daily_df is None or daily_df.empty:
            return pd.DataFrame(columns=TradingCrowding.INDEX_CSV_COLUMNS[1:])
        rows = []
        for code, name, codes in index_groups:
            sub = daily_df[daily_df['ts_code'].isin(codes)]
            if sub.empty:
                continue
            sub = sub.copy()
            sub['group'] = code
            agg = TradingCrowding._concentration(sub, 'group')
            if agg.empty:
                continue
            r = agg.iloc[0]
            total = len(codes)
            rows.append({
                'index_code': code,
                'index_name': name or code,
                'stock_count': int(r['stock_count']),
                'coverage': round(float(r['stock_count']) / total * 100.0, 1)
                if total else 0.0,
                'total_vol': float(r['total_vol']),
                'top5_vol': float(r['top5_vol']),
                'vol_concentration_pct': (
                    None if pd.isna(r['vol_concentration_pct'])
                    else float(r['vol_concentration_pct'])),
                'total_amount': float(r['total_amount']),
                'top5_amount': float(r['top5_amount']),
                'amount_concentration_pct': (
                    None if pd.isna(r['amount_concentration_pct'])
                    else float(r['amount_concentration_pct'])),
            })
        return pd.DataFrame(rows, columns=TradingCrowding.INDEX_CSV_COLUMNS[1:])

    @staticmethod
    def aggregate_market(daily_df, industry_map):
        """全A市场集中度：全部已上市 A 股（有行业分类，即 stock_basic 全市场）
        前 5% 个股的成交量/成交额占全市场比例。
        返回单行 DataFrame（index_code='ALL'，index_name='全A'）。"""
        if daily_df is None or daily_df.empty:
            return pd.DataFrame(columns=TradingCrowding.INDEX_CSV_COLUMNS[1:])
        d = daily_df[['ts_code', 'vol', 'amount']].copy()
        if industry_map:
            d = d[d['ts_code'].isin(industry_map)]
        if d.empty:
            return pd.DataFrame(columns=TradingCrowding.INDEX_CSV_COLUMNS[1:])
        d['group'] = 'ALL'
        agg = TradingCrowding._concentration(d, 'group')
        if agg.empty:
            return pd.DataFrame(columns=TradingCrowding.INDEX_CSV_COLUMNS[1:])
        r = agg.iloc[0]
        return pd.DataFrame([{
            'index_code': 'ALL',
            'index_name': '全A',
            'stock_count': int(r['stock_count']),
            'coverage': 100.0,
            'total_vol': float(r['total_vol']),
            'top5_vol': float(r['top5_vol']),
            'vol_concentration_pct': (
                None if pd.isna(r['vol_concentration_pct'])
                else float(r['vol_concentration_pct'])),
            'total_amount': float(r['total_amount']),
            'top5_amount': float(r['top5_amount']),
            'amount_concentration_pct': (
                None if pd.isna(r['amount_concentration_pct'])
                else float(r['amount_concentration_pct'])),
        }], columns=TradingCrowding.INDEX_CSV_COLUMNS[1:])

    def fetch_day(self, trade_date, max_retries=3, retry_delay=2.0):
        """拉取并聚合单个交易日的成交集中度数据。
        trade_date: 'YYYYMMDD'。返回 (行业 DataFrame, 指数 DataFrame)，
        指数 DataFrame 含 10 个大指数 + 1 行「全A」市场维度。"""
        pro = self._get_pro()
        industry_map = self._get_industry_map()
        index_groups = self._get_index_groups()
        empty = (pd.DataFrame(columns=self.CSV_COLUMNS),
                 pd.DataFrame(columns=self.INDEX_CSV_COLUMNS))
        last_err = None
        for attempt in range(max_retries):
            try:
                daily_df = pro.daily(trade_date=trade_date)
                if daily_df is None or daily_df.empty:
                    return empty
                ind_df = self.aggregate_industries(daily_df, industry_map)
                idx_df = self.aggregate_indices(daily_df, index_groups)
                market_df = self.aggregate_market(daily_df, industry_map)
                if not market_df.empty:
                    idx_df = (pd.concat([idx_df, market_df], ignore_index=True)
                              if not idx_df.empty else market_df)
                return ind_df, idx_df
            except Exception as e:
                last_err = e
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))
        print(f'[TradingCrowding] {trade_date} 拉取失败: {last_err}')
        return empty

    def fetch_market(self, trade_date, max_retries=3, retry_delay=2.0):
        """仅拉取单个交易日的全A市场集中度行（用于历史回填）。"""
        pro = self._get_pro()
        industry_map = self._get_industry_map()
        last_err = None
        for attempt in range(max_retries):
            try:
                daily_df = pro.daily(trade_date=trade_date)
                if daily_df is None or daily_df.empty:
                    return pd.DataFrame(columns=self.INDEX_CSV_COLUMNS)
                return self.aggregate_market(daily_df, industry_map)
            except Exception as e:
                last_err = e
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))
        print(f'[TradingCrowding] {trade_date} 全A拉取失败: {last_err}')
        return pd.DataFrame(columns=self.INDEX_CSV_COLUMNS)

    # ==================== 历史缓存 ====================

    def load_history(self, force=False):
        """行业维度历史（进程级缓存，mtime 命中直接返回）。"""
        return SectorCrowding._load_history_shared(
            self.history_file, self.CSV_COLUMNS, force=force)

    def load_index_history(self, force=False):
        """指数维度历史（进程级缓存，mtime 命中直接返回）。"""
        return SectorCrowding._load_history_shared(
            self.index_history_file, self.INDEX_CSV_COLUMNS, force=force)

    def invalidate_history_cache(self):
        SectorCrowding._PROCESS_HISTORY_CACHE.clear()

    def _append_rows(self, rows, file_path, columns):
        if not rows:
            return
        df = pd.DataFrame(rows, columns=columns)
        df['trade_date'] = df['trade_date'].astype(str)
        file_exists = os.path.exists(file_path) and os.path.getsize(file_path) > 0
        if file_exists:
            df.to_csv(file_path, mode='a', header=False, index=False,
                      encoding='utf-8-sig')
        else:
            df.to_csv(file_path, mode='w', header=True, index=False,
                      encoding='utf-8-sig')
        self.invalidate_history_cache()

    def _save_meta(self, start_date, end_date, latest_date, total_days):
        meta = {
            '_meta': {
                'last_updated': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'version': '1.0',
                'ttl_seconds': 86400,
            },
            'schema_version': self.SCHEMA_VERSION,
            'data_source': self.DATA_SOURCE,
            'start_date': start_date,
            'end_date': end_date,
            'latest_date': latest_date,
            'total_days': total_days,
        }
        tmp_file = self.meta_file + '.tmp'
        with open(tmp_file, 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        os.replace(tmp_file, self.meta_file)

    def build_history(self, start_date=None, end_date=None, max_days=None,
                      resume=True, call_delay=0.35, flush_every=20,
                      progress_cb=None, max_retries=3, retry_delay=2.0):
        """按交易日逐日拉取并构建三年成交集中度历史。
        返回：本次实际新增的交易日数量。"""
        pro = self._get_pro()
        today = datetime.date.today().strftime('%Y%m%d')
        if end_date is None:
            end_date = today
        if start_date is None:
            start_date = (datetime.date.today()
                          - datetime.timedelta(days=365 * self.HISTORY_YEARS)
                          ).strftime('%Y%m%d')

        # 交易日历：网络/DNS 瞬时故障时重试，避免一次抖动导致整段重建失败
        cal = None
        last_err = None
        for attempt in range(max_retries):
            try:
                cal = pro.trade_cal(exchange='SSE', start_date=start_date,
                                    end_date=end_date, is_open='1')
                if cal is not None and not cal.empty:
                    break
            except Exception as e:
                last_err = e
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))
        if cal is None or cal.empty:
            if last_err:
                print(f'[TradingCrowding] 交易日历拉取失败: {last_err}')
            print('[TradingCrowding] 交易日历为空，请检查日期范围')
            return 0
        dates = sorted(cal['cal_date'].astype(str).tolist())

        if resume and os.path.exists(self.history_file) \
                and os.path.getsize(self.history_file) > 0:
            existing = self.load_history()
            if not existing.empty:
                last = existing['trade_date'].max().strftime('%Y%m%d')
                dates = [d for d in dates if d > last]

        if max_days is not None:
            dates = dates[:max_days]
        if not dates:
            print('[TradingCrowding] 没有需要更新的交易日（数据已最新）')
            return 0

        print(f'[TradingCrowding] 开始构建历史：{dates[0]} ~ {dates[-1]}，'
              f'共 {len(dates)} 个交易日')
        ind_rows, idx_rows = [], []
        done = 0
        latest = None
        for d in dates:
            ind_df, idx_df = self.fetch_day(d)
            if not ind_df.empty:
                ind_df['trade_date'] = d
                ind_rows.extend(ind_df.to_dict('records'))
            if not idx_df.empty:
                idx_df['trade_date'] = d
                idx_rows.extend(idx_df.to_dict('records'))
            if not ind_df.empty or not idx_df.empty:
                latest = d
            done += 1
            if progress_cb:
                progress_cb(done, len(dates), d, latest)
            if len(ind_rows) >= flush_every:
                self._append_rows(ind_rows, self.history_file, self.CSV_COLUMNS)
                ind_rows = []
            if len(idx_rows) >= flush_every:
                self._append_rows(idx_rows, self.index_history_file,
                                  self.INDEX_CSV_COLUMNS)
                idx_rows = []
            if done % 20 == 0:
                print(f'[TradingCrowding] 进度 {done}/{len(dates)}，'
                      f'最新成功日期 {latest}')
            time.sleep(call_delay)

        if ind_rows:
            self._append_rows(ind_rows, self.history_file, self.CSV_COLUMNS)
        if idx_rows:
            self._append_rows(idx_rows, self.index_history_file,
                              self.INDEX_CSV_COLUMNS)

        meta_latest = self.load_history(force=True)['trade_date'].max()
        self._save_meta(
            start_date=dates[0],
            end_date=dates[-1],
            latest_date=(meta_latest.strftime('%Y%m%d')
                         if meta_latest is not None and not pd.isna(meta_latest)
                         else latest),
            total_days=len(dates),
        )
        print(f'[TradingCrowding] 完成，本次新增 {len(dates)} 个交易日')
        return len(dates)

    # ==================== 查询接口 ====================

    def precompute(self):
        """一次性构造行业维度面板渲染所需数据。"""
        df = self.load_history()
        if df.empty:
            return {
                'df': df,
                'dates': [],
                'latest_date': None,
                'prev_date': None,
                'latest_df': pd.DataFrame(),
                'prev_df': pd.DataFrame(),
                'by_industry': {},
            }
        dates = sorted(df['trade_date'].unique())
        latest_date = dates[-1]
        prev_date = dates[-22] if len(dates) > 22 else dates[0]
        latest_df = df[df['trade_date'] == latest_date].copy()
        prev_df = df[df['trade_date'] == prev_date].set_index('industry')[
            ['vol_concentration_pct', 'amount_concentration_pct']
        ]
        by_industry = {
            ind: g.sort_values('trade_date')[
                ['trade_date', 'vol_concentration_pct', 'amount_concentration_pct']
            ].reset_index(drop=True)
            for ind, g in df.groupby('industry', sort=False)
        }
        return {
            'df': df,
            'dates': dates,
            'latest_date': latest_date,
            'prev_date': prev_date,
            'latest_df': latest_df,
            'prev_df': prev_df,
            'by_industry': by_industry,
        }

    def precompute_indices(self):
        """返回 dict[指数代码 -> (指数名, 时间序列 DataFrame)]。"""
        df = self.load_index_history()
        out = {}
        if df.empty:
            return out
        for code, g in df.groupby('index_code', sort=False):
            g = g.sort_values('trade_date').reset_index(drop=True)
            name = g.iloc[0]['index_name']
            out[code] = (
                name,
                g[['trade_date', 'vol_concentration_pct',
                   'amount_concentration_pct', 'stock_count', 'coverage']],
            )
        return out

    def get_latest(self, date_str=None):
        """返回最新交易日（或指定日期）的行业集中度表，按成交额集中度降序。"""
        df = self.load_history()
        if df.empty:
            return pd.DataFrame()
        if date_str is not None:
            target = pd.to_datetime(date_str)
            latest_date = df[df['trade_date'] <= target]['trade_date'].max()
            if latest_date is None:
                return pd.DataFrame()
        else:
            latest_date = df['trade_date'].max()
        day = df[df['trade_date'] == latest_date].copy()
        day['amount_concentration_pct'] = pd.to_numeric(
            day['amount_concentration_pct'], errors='coerce')
        day = day.sort_values('amount_concentration_pct',
                              ascending=False).reset_index(drop=True)
        return day

    def get_all_industries(self):
        """返回历史数据中出现过的行业列表。"""
        latest = self.get_latest()
        if latest.empty:
            return []
        return latest['industry'].tolist()


if __name__ == '__main__':
    tc = TradingCrowding()
    print('行业数:', len(tc.get_all_industries()))
