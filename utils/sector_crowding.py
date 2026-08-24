"""
板块拥挤度（Sector Crowding）
============================

定义：行业拥挤度 = 行业两融余额 / 行业总市值 × 100%

数据源（优先 Tushare Pro，token 从环境变量 TUSHARE_TOKEN 或
项目根目录/ data 目录下的 tushare_token.txt 读取）：
    - pro.margin_detail : 个股融资融券明细（T+1 发布）
        rzye 融资余额 / rqye 融券余额 / rzrqye 融资融券余额
    - pro.daily_basic   : 个股每日指标
        total_mv 总市值（单位：万元）
    - pro.stock_basic   : 个股行业分类（industry，证监会行业）

计算口径：
    - 行业总市值   = 该行业全部 A 股 total_mv 之和（含非两融标的）
    - 行业两融余额 = 该行业两融标的 rzrqye 之和
    - 拥挤度       = 行业两融余额 / 行业总市值 × 100%
    - 同时输出融资余额占比、融券余额占比、样本数等
    - 行业归属使用当前 stock_basic 分类（历史行业变动不追溯调整）

历史数据：按交易日增量拉取，缓存于 data/sector_crowding/ 目录，
支持断点续跑（resume）。
"""

import os
import json
import time
import datetime
import pandas as pd
import numpy as np

import tushare as ts


class SectorCrowding:
    """板块拥挤度数据层：拉取、聚合、缓存、查询。"""

    DATA_SOURCE = 'Tushare Pro'
    SCHEMA_VERSION = 1
    HISTORY_YEARS = 3
    # 两融涨跌速度模块的观察窗口（交易日数），默认 10 个交易日 ≈ 近两周。
    SPEED_WINDOWS = (3, 5, 10, 15, 20)
    # 派生缓存（precompute / precompute_all_indices 的结果）格式版本。
    # 当缓存结构变化（如新增字段）时 +1，旧缓存会自动失效并重建。
    DERIVED_SCHEMA_VERSION = 4

    CSV_COLUMNS = [
        'trade_date', 'industry', 'stock_count', 'margin_stock_count',
        'total_mv', 'rzye', 'rqye', 'rzrqye',
        'crowding_pct', 'financing_pct', 'short_pct',
    ]

    def __init__(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.data_dir = os.path.join(self.base_dir, 'data')
        self.cache_dir = os.path.join(self.data_dir, 'sector_crowding')
        os.makedirs(self.cache_dir, exist_ok=True)
        self.history_file = os.path.join(self.cache_dir, 'sector_crowding_history.csv')
        self.meta_file = os.path.join(self.cache_dir, 'meta.json')
        self.derived_file = os.path.join(self.cache_dir, 'sector_crowding_derived.pkl')
        self._pro = None
        self._stock_basic = None
        self._history_cache = None
        self._history_mtime = None

    # ==================== 进程级缓存 ====================
    # SectorCrowding 历史 CSV 在三年口径下可达 11MB。
    # 同一进程里通常会创建多个 SectorCrowding()（拥挤度面板每次重建都会新建一个），
    # 旧实现中 _history_cache 仅限实例内，切换 tab 时仍会重新读盘 + 重新解析，
    # 是「点击 tab 后等很久」的根因。
    # 这里加一个模块级缓存，键为文件 mtime，跨实例共享同一份已解析 DataFrame。
    _PROCESS_HISTORY_CACHE = {}  # mtime -> DataFrame
    # 进程级派生缓存：键为 (history mtime_ns, size, 派生格式版本)。
    # 拥挤度面板每次挂载都会新建 SectorCrowding() 并调用 precompute() 系列方法，
    # 这里保证同一进程内只算一次，其余全部命中内存缓存。
    _PROCESS_DERIVED_CACHE = {}  # key -> {'pre': ..., 'pre_idx': ...}

    @classmethod
    def _load_history_shared(cls, history_file, csv_columns, force=False):
        """进程级历史缓存：(文件路径, mtime) 命中即直接返回，避免重复 IO/解析。
        键包含文件路径：多个历史文件可能共享同一 mtime（如同一批写入），
        仅用 mtime 会把别的文件的内容错还给当前调用方。"""
        try:
            mtime = os.path.getmtime(history_file)
        except OSError:
            mtime = None
        cache_key = (history_file, mtime)
        if not force and mtime is not None \
                and cls._PROCESS_HISTORY_CACHE.get(cache_key) is not None:
            return cls._PROCESS_HISTORY_CACHE[cache_key]
        if not os.path.exists(history_file):
            df = pd.DataFrame(columns=csv_columns)
        else:
            df = pd.read_csv(history_file, dtype={'trade_date': str})
            for col in csv_columns:
                if col not in df.columns:
                    df[col] = None
            df = df[csv_columns]
            df['trade_date'] = pd.to_datetime(df['trade_date'], errors='coerce')
            df = df.dropna(subset=['trade_date'])
        # 写入进程级缓存，淘汰旧 mtime
        if len(cls._PROCESS_HISTORY_CACHE) > 4:
            cls._PROCESS_HISTORY_CACHE.clear()
        if mtime is not None:
            cls._PROCESS_HISTORY_CACHE[cache_key] = df
        return df

    def invalidate_history_cache(self):
        """主动失效（写入新数据后调用）。"""
        self._history_cache = None
        self._history_mtime = None
        SectorCrowding._PROCESS_HISTORY_CACHE.clear()
        SectorCrowding._PROCESS_DERIVED_CACHE.clear()

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
                        print(f'[SectorCrowding] 读取 {path} 失败: {e}')
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

    def _get_stock_basic(self):
        """拉取全市场股票基础信息（含行业分类），实例内缓存。"""
        if self._stock_basic is not None:
            return self._stock_basic
        pro = self._get_pro()
        df = pro.stock_basic(list_status='L', fields='ts_code,name,industry')
        if df is None:
            df = pd.DataFrame(columns=['ts_code', 'name', 'industry'])
        self._stock_basic = df
        return df

    # ==================== 单日聚合 ====================

    @staticmethod
    def aggregate_day(margin_df, daily_basic_df, industry_map):
        """纯聚合函数（便于测试）：
        margin_df / daily_basic_df 为 Tushare 原始 DataFrame，
        industry_map 为 ts_code -> 行业 的映射。
        返回按行业聚合后的 DataFrame，列同 CSV_COLUMNS。
        """
        if margin_df is None or daily_basic_df is None:
            return pd.DataFrame(columns=SectorCrowding.CSV_COLUMNS)
        if margin_df.empty or daily_basic_df.empty:
            return pd.DataFrame(columns=SectorCrowding.CSV_COLUMNS)

        db = daily_basic_df[['ts_code', 'total_mv']].copy()
        db['industry'] = db['ts_code'].map(industry_map)
        db = db.dropna(subset=['industry'])
        db['total_mv'] = pd.to_numeric(db['total_mv'], errors='coerce')
        db = db.dropna(subset=['total_mv'])
        # total_mv 单位是万元，统一换算为元（与两融余额单位一致）
        db['total_mv'] = db['total_mv'] * 1e4
        if db.empty:
            return pd.DataFrame(columns=SectorCrowding.CSV_COLUMNS)

        mv = db.groupby('industry')['total_mv'].sum()
        stock_count = db.groupby('industry')['ts_code'].size().rename('stock_count')

        md = margin_df[['ts_code', 'rzye', 'rqye', 'rzrqye']].copy()
        md['industry'] = md['ts_code'].map(industry_map)
        md = md.dropna(subset=['industry'])
        for col in ('rzye', 'rqye', 'rzrqye'):
            md[col] = pd.to_numeric(md[col], errors='coerce').fillna(0.0)

        margin = md.groupby('industry')[['rzye', 'rqye', 'rzrqye']].sum()
        margin_stock_count = md.groupby('industry')['ts_code'].size().rename('margin_stock_count')

        merged = pd.concat([mv, stock_count, margin, margin_stock_count],
                           axis=1, join='outer')
        merged.columns = ['total_mv', 'stock_count', 'rzye', 'rqye', 'rzrqye',
                          'margin_stock_count']
        merged = merged.fillna({'total_mv': 0.0, 'stock_count': 0,
                                'rzye': 0.0, 'rqye': 0.0, 'rzrqye': 0.0,
                                'margin_stock_count': 0})
        merged = merged[merged['total_mv'] > 0]

        merged['crowding_pct'] = merged['rzrqye'] / merged['total_mv'] * 100.0
        merged['financing_pct'] = merged['rzye'] / merged['total_mv'] * 100.0
        merged['short_pct'] = merged['rqye'] / merged['total_mv'] * 100.0
        merged = merged.reset_index()

        for col in ('stock_count', 'margin_stock_count'):
            merged[col] = merged[col].astype(int)
        day_columns = [c for c in SectorCrowding.CSV_COLUMNS if c != 'trade_date']
        return merged[day_columns]

    def fetch_day(self, trade_date, max_retries=3, retry_delay=2.0):
        """拉取并聚合单个交易日的板块拥挤度数据。
        trade_date: 'YYYYMMDD'。数据不可用（如当天两融尚未发布）时返回空 DataFrame。"""
        pro = self._get_pro()
        industry_map = self._get_stock_basic().set_index('ts_code')['industry']
        last_err = None
        for attempt in range(max_retries):
            try:
                margin_df = pro.margin_detail(trade_date=trade_date)
                daily_basic_df = pro.daily_basic(
                    trade_date=trade_date, fields='ts_code,close,total_mv,circ_mv')
                if margin_df is None or margin_df.empty or daily_basic_df is None or daily_basic_df.empty:
                    return pd.DataFrame(columns=self.CSV_COLUMNS)
                return self.aggregate_day(margin_df, daily_basic_df, industry_map)
            except Exception as e:
                last_err = e
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))
        print(f'[SectorCrowding] {trade_date} 拉取失败: {last_err}')
        return pd.DataFrame(columns=self.CSV_COLUMNS)

    # ==================== 历史构建 ====================

    def _load_history(self, force=False):
        """读取历史缓存 CSV（进程级 + 实例级二级缓存）。"""
        try:
            mtime = os.path.getmtime(self.history_file)
        except OSError:
            mtime = None
        if (not force and self._history_cache is not None
                and self._history_mtime == mtime):
            return self._history_cache
        df = SectorCrowding._load_history_shared(
            self.history_file, self.CSV_COLUMNS, force=force,
        )
        self._history_cache = df
        self._history_mtime = mtime
        return df

    def load_history(self, force=False):
        """对外读取历史数据。

        注意：不再每次返回 .copy()，调用方若需修改应显式调用 .copy()。
        进程级缓存保证多次调用在同一进程内零 IO / 零重复解析。"""
        return self._load_history(force=force)

    # ==================== 两融涨跌速度（板块升温/降温） ====================

    def compute_margin_speed(self, windows=None, df=None):
        """计算各行业近 N 个交易日（N ∈ 3/5/10/15/20）的两融/市值变化。

        口径（对每个行业取最新交易日 T 与 T-N 个交易日）：
            - 两融变化额 = rzrqye_T - rzrqye_{T-N}（元）
            - 市值变化额 = total_mv_T - total_mv_{T-N}（元）
            - 两融增速 % = (rzrqye_T - rzrqye_{T-N}) / rzrqye_{T-N} × 100%
            - 市值增速 % = (total_mv_T - total_mv_{T-N}) / total_mv_{T-N} × 100%
            - 增量比      = 两融变化额 / 市值变化额（核心指标，
              衡量每增加 1 元市值伴随的两融增量；市值变化为 0 时为 ±inf/NaN）
            - 拥挤度变化  = 拥挤度_T - 拥挤度_{T-N}（pp，用于升温/降温判定）

        返回值：dict[window -> DataFrame]，DataFrame 按 industry 索引，列为：
            trade_date / prev_date（最新日与 N 个交易日前）
            rzrqye_now / rzrqye_prev / rzrqye_chg（元）
            total_mv_now / total_mv_prev / total_mv_chg（元）
            rzrqye_pct / total_mv_pct（%）
            delta_ratio（增量比，无量纲）
            crowding_pct / crowding_prev / crowding_chg（% / pp）

        实现为向量化 groupby.shift（纯 pandas C 路径），
        结果随 precompute() 一并落入派生缓存。
        """
        if windows is None:
            windows = self.SPEED_WINDOWS
        out = {w: pd.DataFrame() for w in windows}
        if df is None:
            df = self.load_history()
        if df.empty:
            return out

        d = df.sort_values(['industry', 'trade_date']).copy()
        g = d.groupby('industry', sort=False)
        rzrqye_now = d['rzrqye'].values
        mv_now = d['total_mv'].values
        crowding = d['crowding_pct'].values
        trade_date = d['trade_date'].values

        cols = [
            'trade_date', 'prev_date',
            'rzrqye_now', 'rzrqye_prev', 'rzrqye_chg',
            'total_mv_now', 'total_mv_prev', 'total_mv_chg',
            'rzrqye_pct', 'total_mv_pct', 'delta_ratio',
            'crowding_pct', 'crowding_prev', 'crowding_chg',
        ]
        for w in windows:
            tmp = pd.DataFrame({
                'industry': d['industry'].values,
                'trade_date': trade_date,
                'prev_date': g['trade_date'].shift(w).values,
                'rzrqye_now': rzrqye_now,
                'rzrqye_prev': g['rzrqye'].shift(w).values,
                'total_mv_now': mv_now,
                'total_mv_prev': g['total_mv'].shift(w).values,
                'crowding_pct': crowding,
                'crowding_prev': g['crowding_pct'].shift(w).values,
            })
            tmp = tmp.dropna(subset=['prev_date', 'rzrqye_prev', 'total_mv_prev'])
            if tmp.empty:
                out[w] = pd.DataFrame(columns=cols)
                continue
            last = tmp.groupby('industry', sort=False).tail(1).set_index('industry')
            last['rzrqye_chg'] = last['rzrqye_now'] - last['rzrqye_prev']
            last['total_mv_chg'] = last['total_mv_now'] - last['total_mv_prev']
            last['rzrqye_pct'] = last['rzrqye_chg'] / last['rzrqye_prev'] * 100.0
            last['total_mv_pct'] = last['total_mv_chg'] / last['total_mv_prev'] * 100.0
            # 核心指标：增量比 = 两融变化额 / 市值变化额（市值未变时为 ±inf/NaN）
            with np.errstate(divide='ignore', invalid='ignore'):
                last['delta_ratio'] = last['rzrqye_chg'] / last['total_mv_chg']
            last['crowding_chg'] = last['crowding_pct'] - last['crowding_prev']
            out[w] = last[cols]
        return out

    # ==================== 派生缓存（计算好的结果落盘） ====================
    # 拥挤度面板每次挂载都会调用 precompute() + precompute_all_indices()，
    # 对 ~110 行业 × ~750 交易日的 DataFrame 做 groupby / isin 切片 / 加权聚合。
    # 单次 ~100ms（本地）~ 数秒（线上小规格服务器），且每个新进程都要重来一遍。
    # 这里把计算结果序列化到 data/sector_crowding/sector_crowding_derived.pkl，
    # 用历史 CSV 的 (mtime_ns, size) 作为键：CSV 没变就直接加载落盘结果，
    # 彻底跳过重复计算；CSV 更新后键变化自动重建。

    def _derived_cache_key(self):
        """派生缓存键：(历史 CSV mtime_ns, 大小, 派生格式版本, 指数清单)。"""
        try:
            st = os.stat(self.history_file)
            key = (st.st_mtime_ns, st.st_size, self.DERIVED_SCHEMA_VERSION,
                   tuple(self.INDEX_LIST))
        except OSError:
            key = (None, 0, self.DERIVED_SCHEMA_VERSION, tuple(self.INDEX_LIST))
        return key

    def _pre_to_payload(self, pre, pre_idx):
        """把 precompute / precompute_all_indices 的结果打包为可落盘的 dict。
        直接 pickle DataFrame，保证类型/NaN 与计算路径完全一致；
        同时带上完整 df，冷启动时连 11MB CSV 解析都可以跳过。"""
        payload = {
            'pre': pre,
            'pre_idx': {
                code: {'name': name, 'series': s}
                for code, (name, s) in pre_idx.items()
            },
        }
        return payload

    def _payload_to_pre(self, payload):
        """把落盘 payload 还原成 precompute / precompute_all_indices 的形状。"""
        pre = payload['pre']
        pre_idx = {
            code: (entry.get('name', code), entry['series'])
            for code, entry in payload.get('pre_idx', {}).items()
        }
        return pre, pre_idx

    def _load_derived(self):
        """进程级 + 磁盘级加载派生缓存；未命中或损坏返回 None。"""
        key = self._derived_cache_key()
        if key in SectorCrowding._PROCESS_DERIVED_CACHE:
            return SectorCrowding._PROCESS_DERIVED_CACHE[key]
        if key[0] is None or not os.path.exists(self.derived_file):
            return None
        try:
            import pickle
            with open(self.derived_file, 'rb') as f:
                payload = pickle.load(f)
            if payload.get('key') != key:
                return None
            pre, pre_idx = self._payload_to_pre(payload)
            cached = {'pre': pre, 'pre_idx': pre_idx}
            if len(SectorCrowding._PROCESS_DERIVED_CACHE) > 2:
                SectorCrowding._PROCESS_DERIVED_CACHE.clear()
            SectorCrowding._PROCESS_DERIVED_CACHE[key] = cached
            return cached
        except Exception as e:
            print(f'[SectorCrowding] 派生缓存读取失败（将重新计算）: {e}')
            return None

    def _save_derived(self, pre, pre_idx):
        """把派生结果落盘（原子写 tmp + os.replace）。"""
        if pre.get('df', pd.DataFrame()).empty:
            return
        try:
            import pickle
            payload = self._pre_to_payload(pre, pre_idx)
            payload['key'] = self._derived_cache_key()
            tmp_file = self.derived_file + '.tmp'
            with open(tmp_file, 'wb') as f:
                pickle.dump(payload, f, protocol=4)
            os.replace(tmp_file, self.derived_file)
        except Exception as e:
            print(f'[SectorCrowding] 派生缓存写入失败: {e}')

    def precompute(self, use_cache=True):
        """一次性计算面板渲染所需的全部派生数据，避免同一份逻辑被反复调用。

        返回 dict：
          - df          : 完整历史
          - dates       : 排序后的交易日 ndarray（升序）
          - latest_date : 最新交易日 Timestamp
          - prev_date   : 1 月前 / 上一交易日
          - latest_df   : 最新交易日行业表
          - prev_df     : 上一个交易日行业表（按 industry 索引的 crowding_pct Series）
          - by_industry : dict[industry -> 该行业完整序列 DataFrame]
                         （用于 build_display 中按行业 percentile_rank，
                          避免对 df 做 N 次 boolean filter 的 O(N²) 行为）
          - margin_speed : dict[window -> 行业两融/市值增速 DataFrame]
                           （两融涨跌速度模块，见 compute_margin_speed）

        面板每次挂载调用一次即可，多个渲染函数共享同一份缓存。
        """
        if use_cache:
            cached = self._load_derived()
            if cached is not None:
                return cached['pre']
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
                'margin_speed': {w: pd.DataFrame() for w in self.SPEED_WINDOWS},
            }
        dates = sorted(df['trade_date'].unique())
        latest_date = dates[-1]
        prev_date = dates[-22] if len(dates) > 22 else dates[0]
        latest_df = df[df['trade_date'] == latest_date].copy()
        prev_df = df[df['trade_date'] == prev_date].set_index('industry')[
            ['crowding_pct']
        ]
        by_industry = {
            ind: g.sort_values('trade_date')[['trade_date', 'crowding_pct',
                                              'financing_pct']].reset_index(drop=True)
            for ind, g in df.groupby('industry', sort=False)
        }
        margin_speed = self.compute_margin_speed(df=df)
        pre = {
            'df': df,
            'dates': dates,
            'latest_date': latest_date,
            'prev_date': prev_date,
            'latest_df': latest_df,
            'prev_df': prev_df,
            'by_industry': by_industry,
            'margin_speed': margin_speed,
        }
        if use_cache:
            pre_idx = self.precompute_all_indices(use_cache=False)
            self._save_derived(pre, pre_idx)
            key = self._derived_cache_key()
            SectorCrowding._PROCESS_DERIVED_CACHE[key] = {'pre': pre, 'pre_idx': pre_idx}
        return pre

    def _append_rows(self, rows):
        """追加一批聚合行到历史 CSV。"""
        if not rows:
            return
        df = pd.DataFrame(rows, columns=self.CSV_COLUMNS)
        df['trade_date'] = df['trade_date'].astype(str)
        file_exists = os.path.exists(self.history_file) and os.path.getsize(self.history_file) > 0
        if file_exists:
            df.to_csv(self.history_file, mode='a', header=False, index=False,
                      encoding='utf-8-sig')
        else:
            df.to_csv(self.history_file, mode='w', header=True, index=False,
                      encoding='utf-8-sig')
        self.invalidate_history_cache()

    def _dedup_history_csv(self):
        """对历史 CSV 按 (trade_date, industry) 去重，保留最后一行。

        当 build_history 把"最近 N 天既存在又要重拉"也纳入拉取范围时，
        旧实现只追加不替换，会产生 (trade_date, industry) 重复行，
        进而导致后续 groupby / shift / percentile_rank 计算重复计数。
        在所有 flush 完成后调用一次，把 CSV 落盘为最新一份（最新一次拉取胜出）。
        """
        if not os.path.exists(self.history_file) \
                or os.path.getsize(self.history_file) == 0:
            return
        try:
            raw = pd.read_csv(self.history_file, dtype={'trade_date': str})
        except Exception as e:
            print(f'[SectorCrowding] 历史去重读取失败（跳过）: {e}')
            return
        if raw.empty or 'trade_date' not in raw.columns \
                or 'industry' not in raw.columns:
            return
        before = len(raw)
        raw = raw.drop_duplicates(subset=['trade_date', 'industry'],
                                  keep='last')
        after = len(raw)
        if after < before:
            print(f'[SectorCrowding] 去重历史: {before} -> {after} 行 '
                  f'（{(before - after)} 行重复，已丢弃旧值）')
            try:
                tmp_file = self.history_file + '.tmp'
                raw.to_csv(tmp_file, index=False, encoding='utf-8-sig')
                os.replace(tmp_file, self.history_file)
            except Exception as e:
                print(f'[SectorCrowding] 去重历史写回失败: {e}')
                return
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
                      progress_cb=None, max_retries=3, retry_delay=2.0,
                      refetch_recent_days=2):
        """按交易日逐日拉取并构建三年板块拥挤度历史。

        参数：
            start_date         : 'YYYYMMDD'，默认当前日期往前 HISTORY_YEARS 年
            end_date           : 'YYYYMMDD'，默认今天
            max_days           : 本次最多拉取多少天（调试用）
            resume             : 从历史缓存最后一个日期之后继续（默认 True）
            call_delay         : 每次接口调用间隔秒数，防止触发限频
            flush_every        : 攒多少天写一次缓存
            progress_cb        : 进度回调 f(done, total, current_date)
            refetch_recent_days: 除新增外，额外覆盖已有最新 N 个交易日（默认 2）。
                Tushare 两融明细在 T+1 仍可能修订/回填（如昨日收盘后公布融资融券新口径），
                仅按"严格大于"已有最新日期拉取会漏掉修正。
                在 resume=True 且已有历史时，把 already-existing 的最近 N 天也重新拉取，
                并在末尾按 (trade_date, industry) 去重（最后一行 = 最新一次拉取），
                实现"可覆盖"语义（详见 _dedup_history_csv）。
        返回：本次实际新增的交易日数量。
        """
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
                print(f'[SectorCrowding] 交易日历拉取失败: {last_err}')
            print('[SectorCrowding] 交易日历为空，请检查日期范围')
            return 0
        dates = sorted(cal['cal_date'].astype(str).tolist())

        # resume：除新增外，还要把已存在的最近 N 天拉一遍以覆盖可能的修正。
        # bisect_right 找到"已有最新日期 last"在交易日历里的"之后"插入点 pos，
        # [start_idx, pos) 即包含 last 在内的最后 2N 个交易日；
        # 再裁剪到 "包含 last 的最后 N 个交易日"，与严格新增日期合并拉取。
        # max_days 仍作为最后一道闸门，避免日期过多触发 Tushare 限频。
        refetch_pool = []
        if resume and os.path.exists(self.history_file) and os.path.getsize(self.history_file) > 0:
            existing = self.load_history()
            if not existing.empty:
                last = existing['trade_date'].max().strftime('%Y%m%d')
                try:
                    import bisect as _bisect
                    pos = _bisect.bisect_right(dates, last)
                except Exception:
                    pos = len(dates)
                # 先取包含 last 在内的 2N 个交易日作为候选缓冲
                start_idx = max(0, pos - refetch_recent_days * 2)
                refetch_pool = dates[start_idx:pos]
                # 收紧到包含 last 在内的最近 N 个交易日
                if len(refetch_pool) > refetch_recent_days:
                    refetch_pool = refetch_pool[-refetch_recent_days:]
                new_dates = [d for d in dates if d > last]
                dates = sorted(set(new_dates) | set(refetch_pool))

        if max_days is not None:
            dates = dates[:max_days]
        if not dates:
            print('[SectorCrowding] 没有需要更新的交易日（数据已最新）')
            return 0

        print(f'[SectorCrowding] 开始构建历史：{dates[0]} ~ {dates[-1]}，'
              f'共 {len(dates)} 个交易日'
              f'（含回填修正 {len(refetch_pool)} 天）')
        rows = []
        done = 0
        latest = None
        for d in dates:
            day_df = self.fetch_day(d)
            if not day_df.empty:
                day_df['trade_date'] = d
                rows.extend(day_df.to_dict('records'))
                latest = d
            done += 1
            if progress_cb:
                progress_cb(done, len(dates), d, latest)
            if len(rows) >= flush_every:
                self._append_rows(rows)
                rows = []
            if done % 20 == 0:
                print(f'[SectorCrowding] 进度 {done}/{len(dates)}，最新成功日期 {latest}')
            time.sleep(call_delay)

        if rows:
            self._append_rows(rows)

        # 末尾按 (trade_date, industry) 去重：若最近 N 天被回填修正，
        # 旧行已经在 CSV 里了，新追加的行需要把它替换掉。
        self._dedup_history_csv()

        meta_latest = self.load_history(force=True)['trade_date'].max()
        self._save_meta(
            start_date=dates[0],
            end_date=dates[-1],
            latest_date=(meta_latest.strftime('%Y%m%d')
                         if meta_latest is not None and not pd.isna(meta_latest)
                         else latest),
            total_days=len(dates),
        )
        print(f'[SectorCrowding] 完成，本次新增 {len(dates)} 个交易日')
        return len(dates)

    # ==================== 查询接口 ====================

    def get_latest(self, date_str=None):
        """返回最新交易日（或指定日期）的行业拥挤度表，按拥挤度降序。
        date_str: 'YYYY-MM-DD' 或 'YYYYMMDD'。"""
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
        day['crowding_pct'] = pd.to_numeric(day['crowding_pct'], errors='coerce')
        day = day.sort_values('crowding_pct', ascending=False).reset_index(drop=True)
        return day

    def get_industry_series(self, industry):
        """返回单个行业按日期排序的拥挤度序列。"""
        df = self.load_history()
        if df.empty:
            return pd.DataFrame()
        ser = df[df['industry'] == industry].sort_values('trade_date').copy()
        return ser

    @staticmethod
    def percentile_rank(values, value):
        """计算 value 在 values 序列中的历史分位（0-100）。
        分位 = 小于等于 value 的样本占比 × 100。"""
        vals = pd.Series(values, dtype=float).dropna()
        if len(vals) < 5 or pd.isna(value):
            return None
        return float((vals <= value).mean() * 100)

    def get_all_industries(self):
        """返回历史数据中出现过的行业列表（按最新拥挤度降序）。"""
        latest = self.get_latest()
        if latest.empty:
            return []
        return latest['industry'].tolist()

    # ============ 指数板块拥挤度（用成分股聚合） ============

    # 缓存目录中所有可用的指数
    # ('指数代码', '指数名', 'scope')
    #   - scope='SH': 沪市全市场 A 股（无 .json 缓存时用全市场）
    #   - scope='SZ': 深市全市场 A 股
    #   - scope='STAR': 科创板（688 开头）
    #   - scope='GEM': 创业板（300 开头）
    # 如果 index_cons_<code>.json 存在，优先用 .json 缓存的成分股；
    # 否则 fallback 到 scope 范围。
    INDEX_LIST = [
        ('000001', '上证指数', 'SH'),
        ('399001', '深证成指', 'SZ'),
        ('000300', '沪深300', None),
        ('000016', '上证50', None),
        ('399006', '创业板指', None),  # 优先用 .json 成分股
        ('000688', '科创50', None),
        ('STAR', '科创板', 'STAR'),  # 全科创板（无 .json，强制用 scope）
        ('000905', '中证500', None),
        ('000852', '中证1000', None),
        ('399330', '深证100', None),
    ]

    # 指数代码 -> scope 的快速查找
    INDEX_LIST_SCOPE_MAP = {}
    for code, _, scope in INDEX_LIST:
        INDEX_LIST_SCOPE_MAP[code] = scope
    # scope -> 中文名（fallback 时用）
    _SCOPE_NAMES = {
        'SH': '上证指数',
        'SZ': '深证成指',
        'STAR': '科创板',
        'GEM': '创业板',
    }

    def _load_index_constituents(self, index_code, scope=None):
        """读取指数成分股代码列表（已带 .SZ/.SH 后缀）。
        scope: 范围筛选后缀（仅对 .json 缓存生效）。
        """
        cache_path = os.path.join(
            self.data_dir, 'index_constituents_cache', f'index_cons_{index_code}.json'
        )
        if not os.path.exists(cache_path):
            return None, None
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            codes_raw = data.get('codes', [])
            codes_ts = []
            for c in codes_raw:
                c = str(c).strip()
                if not c:
                    continue
                if c.startswith(('6', '9', '5', '8', '4')):
                    codes_ts.append(f'{c}.SH')
                else:
                    codes_ts.append(f'{c}.SZ')
            return data.get('index_name', index_code), codes_ts
        except Exception as e:
            print(f'SectorCrowding: 读取指数 {index_code} 成分股失败: {e}')
            return None, None

    def _load_all_a_share_codes(self, scope=None):
        """从 stock_industry_cache.json 加载所有 A 股代码（按 scope 过滤）。
        scope:
            - 'SH'   : 沪市（6/9 开头）
            - 'SZ'   : 深市（0/2/3 开头）
            - 'STAR' : 科创板（688 开头）
            - 'GEM'  : 创业板（300 开头）
            - None   : 全部
        """
        path = os.path.join(self.data_dir, 'stock_industry_cache.json')
        if not os.path.exists(path):
            return []
        try:
            with open(path, 'r', encoding='utf-8') as f:
                si = json.load(f)
        except Exception:
            return []
        codes = []
        for k in si.keys():
            c = str(k).strip()
            if not c:
                continue
            # 加后缀
            if c.startswith(('6', '9', '5', '8', '4')):
                ts = f'{c}.SH'
            else:
                ts = f'{c}.SZ'
            # scope 过滤
            if scope == 'SH' and not ts.startswith(('6', '9')):
                continue
            if scope == 'SZ' and ts.startswith(('6', '9')):
                continue
            if scope == 'STAR' and not c.startswith('688'):
                continue
            if scope == 'GEM' and not c.startswith('300'):
                continue
            codes.append(ts)
        return codes

    def get_index_crowding_series(self, index_code, scope=None, df=None):
        """计算给定指数（成分股聚合）的拥挤度时间序列。

        index_code: 指数代码 或 scope 标识
        scope: 'SH'/'SZ'/'STAR'/'GEM' 表示全市场范围
              例如 '000001'/'SH' -> 沪市全市场
                    '399001'/'SZ' -> 深市全市场
                    'STAR'      -> 科创板（688 开头）
                    'GEM'       -> 创业板（300 开头）
        df: 预加载的历史 DataFrame（可选）。同一面板内多次调用时复用，
            避免对同一份历史做重复 isin 切片。

        计算口径：指数拥挤度 = 范围股票的两融余额之和 / 总市值之和 × 100%
        实现：先按证监会行业聚合，再用"范围内行业成分股数"加权。
        """
        # 1) 决定成分股列表
        #    - 如果 INDEX_LIST 里给了非空 scope（且 .json 不存在），用 scope 范围
        #    - 如果 .json 存在，用 .json 成分股
        if scope is None and index_code in self.INDEX_LIST_SCOPE_MAP:
            scope = self.INDEX_LIST_SCOPE_MAP[index_code]

        cache_path = os.path.join(
            self.data_dir, 'index_constituents_cache', f'index_cons_{index_code}.json'
        )
        if scope and not os.path.exists(cache_path):
            # 强制走 scope
            index_name = self._SCOPE_NAMES.get(scope, index_code)
            codes = self._load_all_a_share_codes(scope)
        elif os.path.exists(cache_path):
            index_name, codes = self._load_index_constituents(index_code)
        else:
            # 兜底：尝试 scope
            if scope:
                index_name = self._SCOPE_NAMES.get(scope, index_code)
                codes = self._load_all_a_share_codes(scope)
            else:
                index_name, codes = self._load_index_constituents(index_code)
        if not codes:
            return None, None

        # 1) 加载历史（全行业 × 全日期）
        if df is None:
            df = self.load_history()
        if df.empty:
            return None, None

        # 2) 加载证监会行业映射 (ts_code -> industry)
        #    优先用本地缓存（stock_industry_cache.json）
        stock_industry_path = os.path.join(self.data_dir, 'stock_industry_cache.json')
        ts_to_ind = {}
        if os.path.exists(stock_industry_path):
            try:
                with open(stock_industry_path, 'r', encoding='utf-8') as f:
                    si = json.load(f)
                for code, info in si.items():
                    if isinstance(info, dict):
                        ind = info.get('industry')
                        if ind:
                            # 缓存里是 "000001" 这种，加后缀
                            cstr = str(code).strip()
                            if cstr.startswith(('6', '9', '5', '8', '4')):
                                ts = f'{cstr}.SH'
                            else:
                                ts = f'{cstr}.SZ'
                            ts_to_ind[ts] = ind
            except Exception:
                pass

        # 3) 拿到成分股对应的证监会行业（保留唯一）
        comp_industries = {}
        for ts in codes:
            ind = ts_to_ind.get(ts)
            if ind:
                comp_industries[ind] = comp_industries.get(ind, 0) + 1
        if not comp_industries:
            return None, None

        # 4) 按行业聚合历史数据
        #    index_crowding = sum(industry_crowding × industry_weight) / sum(weight)
        #    weight 简单用每个行业成分股数（更准确应按市值加权，但这里取等权/股票数加权）
        ind_list = list(comp_industries.keys())
        weights = comp_industries
        total_w = sum(weights.values())

        sub = df[df['industry'].isin(ind_list)].copy()
        if sub.empty:
            return None, None
        sub['weight'] = sub['industry'].map(weights).fillna(0)

        # ============ 关键性能点 ============
        # 旧实现用 5 个 lambda 在 groupby.agg 里做
        #   lambda x: (x * sub.loc[x.index, 'weight']).sum()
        # 一次面板渲染要算 10 个指数，每个 lambda 在每个 group 里都要做
        # .loc 重索引 + Series 乘法 + sum。对 ~750 日期 × 10 指数 = ~37000 次 lambda，
        # 实测要 4 秒。改成一次性把 weight 乘到原列里，groupby.agg 用内置 sum()，
        # pandas 走全 C 路径。
        sub['w_total_mv'] = sub['total_mv'] * sub['weight']
        sub['w_rzrqye'] = sub['rzrqye'] * sub['weight']
        sub['w_rzye'] = sub['rzye'] * sub['weight']
        sub['w_rqye'] = sub['rqye'] * sub['weight']

        grouped = sub.groupby('trade_date', as_index=False).agg(
            w_total_mv=('w_total_mv', 'sum'),
            w_rzrqye=('w_rzrqye', 'sum'),
            w_rzye=('w_rzye', 'sum'),
            w_rqye=('w_rqye', 'sum'),
            weight_sum=('weight', 'sum'),
        )
        grouped['crowding_pct'] = grouped['w_rzrqye'] / grouped['w_total_mv'] * 100
        grouped['financing_pct'] = grouped['w_rzye'] / grouped['w_total_mv'] * 100
        grouped['short_pct'] = grouped['w_rqye'] / grouped['w_total_mv'] * 100
        # 行业覆盖比例（已覆盖行业 / 总指数成分股数）
        grouped['coverage'] = grouped['weight_sum'] / total_w * 100

        out = grouped[['trade_date', 'crowding_pct', 'financing_pct', 'short_pct',
                       'coverage']].sort_values('trade_date').reset_index(drop=True)
        return index_name, out

    # ============ 批量预计算：所有指数一次算完 ============
    def precompute_all_indices(self, use_cache=True):
        """一次性算好 INDEX_LIST 里所有指数的时间序列（dict）。

        旧流程里 render_index_cards 对每个指数都调一次
        get_index_crowding_series → 每次都做 isin 切片 + 5 个 weight×sum lambda。
        这里在面板挂载时一次算完并存盘：rows 总数 ~80 行业 × 750 日 = 6 万行，
        算 10 个指数其实可以共用一次 groupby，但 weights 不同所以分开；
        关键是消除 10 次重复的 lambda 调用。
        """
        if use_cache:
            cached = self._load_derived()
            if cached is not None:
                return cached['pre_idx']
        out = {}
        df = self.load_history()
        if df.empty:
            return out
        # 1) ts -> industry 映射（指数 -> 行业 -> 行业）
        ts_to_ind = {}
        stock_industry_path = os.path.join(self.data_dir, 'stock_industry_cache.json')
        if os.path.exists(stock_industry_path):
            try:
                with open(stock_industry_path, 'r', encoding='utf-8') as f:
                    si = json.load(f)
                for code, info in si.items():
                    if isinstance(info, dict):
                        ind = info.get('industry')
                        if not ind:
                            continue
                        cstr = str(code).strip()
                        if cstr.startswith(('6', '9', '5', '8', '4')):
                            ts_to_ind[f'{cstr}.SH'] = ind
                        else:
                            ts_to_ind[f'{cstr}.SZ'] = ind
            except Exception:
                pass

        # 2) 预算 weight 列（一次），每个指数复用
        df = df.copy()
        # 注意：每个指数 weight 不同（按指数覆盖到的行业 -> 成分股数），
        # 所以必须每个指数单独算。但 weight 列本身只需赋值一次即可。
        for code, name, scope in self.INDEX_LIST:
            # 决定成分股列表（与 get_index_crowding_series 同口径）
            if scope is None and code in self.INDEX_LIST_SCOPE_MAP:
                scope = self.INDEX_LIST_SCOPE_MAP[code]
            cache_path = os.path.join(
                self.data_dir, 'index_constituents_cache', f'index_cons_{code}.json'
            )
            if scope and not os.path.exists(cache_path):
                index_name = self._SCOPE_NAMES.get(scope, code)
                codes = self._load_all_a_share_codes(scope)
            elif os.path.exists(cache_path):
                index_name, codes = self._load_index_constituents(code)
            else:
                if scope:
                    index_name = self._SCOPE_NAMES.get(scope, code)
                    codes = self._load_all_a_share_codes(scope)
                else:
                    index_name, codes = self._load_index_constituents(code)
            if not codes:
                continue
            comp_industries = {}
            for ts in codes:
                ind = ts_to_ind.get(ts)
                if ind:
                    comp_industries[ind] = comp_industries.get(ind, 0) + 1
            if not comp_industries:
                continue
            ind_list = list(comp_industries.keys())
            total_w = sum(comp_industries.values())

            sub = df[df['industry'].isin(ind_list)]
            if sub.empty:
                continue
            # 在 sub 上一次性算 weight×col，比 get_index_crowding_series 里的版本少一次 .copy()
            w = sub['industry'].map(comp_industries).fillna(0)
            w_total_mv = sub['total_mv'].values * w.values
            w_rzrqye = sub['rzrqye'].values * w.values
            w_rzye = sub['rzye'].values * w.values
            w_rqye = sub['rqye'].values * w.values

            # 一次性 groupby + sum（纯 C 路径，无 lambda）
            tmp = pd.DataFrame({
                'trade_date': sub['trade_date'].values,
                'w_total_mv': w_total_mv,
                'w_rzrqye': w_rzrqye,
                'w_rzye': w_rzye,
                'w_rqye': w_rqye,
                'weight': w.values,
            })
            grouped = tmp.groupby('trade_date', as_index=False, sort=False).sum()
            grouped['crowding_pct'] = grouped['w_rzrqye'] / grouped['w_total_mv'] * 100
            grouped['financing_pct'] = grouped['w_rzye'] / grouped['w_total_mv'] * 100
            grouped['short_pct'] = grouped['w_rqye'] / grouped['w_total_mv'] * 100
            grouped['coverage'] = grouped['weight'] / total_w * 100

            series = grouped[['trade_date', 'crowding_pct', 'financing_pct',
                              'short_pct', 'coverage']].sort_values('trade_date')
            out[code] = (index_name or name, series.reset_index(drop=True))
        return out

    # ============ 证监会行业层级（一级 industry_name / 二级 industry） ============

    _hierarchy_cache_file = None  # lazy
    _hierarchy_cache = None

    @staticmethod
    def _normalize(s):
        """去掉 * 前缀、空格、做 trim。"""
        if s is None:
            return ''
        return str(s).strip().lstrip('*').strip()

    def _hierarchy_cache_path(self):
        if self._hierarchy_cache_file is None:
            self._hierarchy_cache_file = os.path.join(
                self.data_dir, 'csrc_industry_hierarchy.json'
            )
        return self._hierarchy_cache_file

    def _load_csrc_hierarchy(self, force_refresh=False):
        """读取行业层级。
        优先使用 data/sector_sentiment_cache_erji.json 中已有的同花顺一级分组（group 字段），
        用 data/csrc_to_ths_l1.json 将证监会二级行业映射到同花顺一级。
        兜底：data/csrc_static.py（证监会 GB/T 静态表）。
        """
        cache_path = self._hierarchy_cache_path()
        if self._hierarchy_cache is not None and not force_refresh:
            return self._hierarchy_cache

        # 1) 读本地缓存
        if not force_refresh and os.path.exists(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cached = json.load(f)
                l2_map = cached.get('l2_to_l1', {})
                if l2_map:
                    self._hierarchy_cache = cached
                    return cached
            except Exception:
                pass

        # 2) 优先用同花顺分组（同花顺一级 / 同花顺二级）
        l1_to_l2 = {}
        l2_to_l1 = {}
        ths_l1_list_ordered = []  # 同花顺一级顺序
        try:
            ths_path = os.path.join(self.data_dir, 'sector_sentiment_cache_erji.json')
            with open(ths_path, 'r', encoding='utf-8') as f:
                ths_data = json.load(f)
            for l2_name, info in ths_data.items():
                l1 = self._normalize(info.get('group', ''))
                l2 = self._normalize(l2_name)
                if not l1 or not l2:
                    continue
                if l1 not in l1_to_l2:
                    l1_to_l2[l1] = []
                    ths_l1_list_ordered.append(l1)
                if l2 not in l1_to_l2[l1]:
                    l1_to_l2[l1].append(l2)
                l2_to_l1[l2] = l1
        except Exception as e:
            print(f'SectorCrowding: 读取同花顺分组失败: {e}')

        # 3) 用 csrc_to_ths_l1.json 把证监会行业映射到同花顺一级
        #    （一个证监会行业可能归到多个同花顺二级，但 l1 是确定的）
        csrc_to_l1 = {}
        try:
            csrc_to_l1_path = os.path.join(self.data_dir, 'csrc_to_ths_l1.json')
            if os.path.exists(csrc_to_l1_path):
                with open(csrc_to_l1_path, 'r', encoding='utf-8') as f:
                    csrc_to_ths_l2 = json.load(f)
                # 遍历：拿到 csrc 行业名 -> 它的同花顺二级列表 -> 拿对应的同花顺一级
                for csrc, ths_l2_list in csrc_to_ths_l2.items():
                    csrc_norm = self._normalize(csrc)
                    l1_set = set()
                    for ths_l2 in ths_l2_list:
                        ths_l2_norm = self._normalize(ths_l2)
                        l1 = l2_to_l1.get(ths_l2_norm)
                        if l1:
                            l1_set.add(l1)
                    if l1_set:
                        # 证监会行业归到第一个匹配的同花顺一级（多数情况是 1 个）
                        csrc_to_l1[csrc_norm] = sorted(l1_set)[0]
        except Exception as e:
            print(f'SectorCrowding: 读取证监会→同花顺映射失败: {e}')

        build_date = 'ths-static'

        # 4) 兜底：证监会静态表（如果同花顺数据为空）
        if not l1_to_l2:
            try:
                from csrc_static import CSRC_L1_L2_MAP, STATIC_CSRC_TO_L1
                l2_to_l1 = dict(STATIC_CSRC_TO_L1)
                l1_to_l2 = {l1: list(l2s) for l1, l2s in CSRC_L1_L2_MAP.items()}
                ths_l1_list_ordered = list(l1_to_l2.keys())
                build_date = 'static'
            except Exception as e:
                print(f'SectorCrowding: 静态映射加载失败: {e}')

        cached = {
            'l1_to_l2': l1_to_l2,
            'l2_to_l1': l2_to_l1,
            'csrc_to_l1': csrc_to_l1,  # 证监会行业 -> 同花顺一级（专用）
            'l1_list_ordered': ths_l1_list_ordered,
            'build_date': build_date,
        }
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(cached, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        self._hierarchy_cache = cached
        return cached

    def get_industry_hierarchy(self):
        """返回行业层级（基于同花顺一级分组）。
        输入是证监会行业（历史数据中的 industry 字段），
        输出是同花顺一级 / 同花顺二级 -> 证监会行业的映射。

        返回：
            {
                'all_industries': [...],          # 证监会行业列表
                'l1_list': [...],                 # 同花顺一级列表（按同花顺顺序）
                'l1_to_l2_to_csrc': {            # {同花顺一级: {同花顺二级: [证监会行业]}}
                    '煤炭': {'煤炭开采': ['煤炭开采加工'], '焦炭加工': ['焦炭加工']},
                    '银行': {'全国性银行': ['银行'], ...},
                    ...
                },
                'unmapped': [...],                # 证监会数据缺失映射的行业
                'l1_type': 'ths' | 'csrc-gbt',   # 分组来源
            }
        """
        all_ind = self.get_all_industries()
        hier = self._load_csrc_hierarchy()
        l1_to_l2 = hier.get('l1_to_l2', {})  # 同花顺一级 -> [同花顺二级]
        l2_to_l1 = hier.get('l2_to_l1', {})  # 同花顺二级 -> 同花顺一级
        csrc_to_l1 = hier.get('csrc_to_l1', {})  # 证监会行业 -> 同花顺一级
        l1_ordered = hier.get('l1_list_ordered', list(l1_to_l2.keys()))

        # 关键映射：每个证监会行业 -> (同花顺一级, [同花顺二级])
        csrc_to_ths_l2 = {}
        try:
            csrc_to_ths_l2_path = os.path.join(self.data_dir, 'csrc_to_ths_l1.json')
            if os.path.exists(csrc_to_ths_l2_path):
                with open(csrc_to_ths_l2_path, 'r', encoding='utf-8') as f:
                    raw = json.load(f)
                for csrc, ths_l2_list in raw.items():
                    csrc_to_ths_l2[self._normalize(csrc)] = [
                        self._normalize(x) for x in ths_l2_list
                    ]
        except Exception:
            pass

        result_l1 = {}
        unmapped = []

        for csrc in all_ind:
            csrc_norm = self._normalize(csrc)
            ths_l2_list = csrc_to_ths_l2.get(csrc_norm, [])
            placed = False

            if ths_l2_list:
                # 把证监会行业放到对应的同花顺二级下面
                for ths_l2 in ths_l2_list:
                    l1 = l2_to_l1.get(ths_l2)
                    if l1:
                        result_l1.setdefault(l1, {}).setdefault(ths_l2, []).append(csrc)
                        placed = True

            if not placed:
                # 兜底：归到"其他"一级
                unmapped.append(csrc)
                result_l1.setdefault('其他', {}).setdefault(csrc_norm, []).append(csrc)

        # 构造 l1 列表（按同花顺顺序）
        ordered_l1 = list(l1_ordered)
        for l1 in result_l1:
            if l1 not in ordered_l1:
                ordered_l1.append(l1)

        # 整理每个一级下的二级：保留 l1_to_l2 中出现的顺序
        ordered_result = {}
        for l1 in ordered_l1:
            if l1 not in result_l1:
                continue
            l2_dict = result_l1[l1]
            ordered_l2 = [l2 for l2 in l1_to_l2.get(l1, []) if l2 in l2_dict]
            for l2 in l2_dict:
                if l2 not in ordered_l2:
                    ordered_l2.append(l2)
            ordered_result[l1] = {l2: l2_dict[l2] for l2 in ordered_l2}

        return {
            'all_industries': all_ind,
            'l1_list': ordered_l1,
            'l1_to_l2_to_csrc': ordered_result,
            'unmapped': unmapped,
            'l1_type': 'ths',
        }

    def filter_industries_by_hierarchy(self, l1=None, l2=None, industries=None):
        """根据选中的 l1 / l2 过滤行业列表。
        - l1=None 或 '全部' 返回原列表
        - l1 选中后只返回该 l1 下的行业
        - l2 选中后只返回该 l2 下的证监会行业
        """
        if industries is None:
            industries = self.get_all_industries()
        if not l1 or l1 in ('全部', '全部一级', 'All', ''):
            return industries
        hier = self.get_industry_hierarchy()
        l1_map = hier.get('l1_to_l2_to_csrc', {})
        if l1 not in l1_map:
            return industries
        if l2 and l2 not in ('', '全部', '全部二级', 'All'):
            return [i for i in industries if i in l1_map[l1].get(l2, [])]
        # 只按 l1 过滤
        all_l2 = l1_map[l1]
        csrc_set = []
        for v in all_l2.values():
            csrc_set.extend(v)
        return [i for i in industries if i in csrc_set]


if __name__ == '__main__':
    sc = SectorCrowding()
    print('行业数:', len(sc.get_all_industries()))
