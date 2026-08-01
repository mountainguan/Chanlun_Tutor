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

import tushare as ts


class SectorCrowding:
    """板块拥挤度数据层：拉取、聚合、缓存、查询。"""

    DATA_SOURCE = 'Tushare Pro'
    SCHEMA_VERSION = 1
    HISTORY_YEARS = 3

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
        self._pro = None
        self._stock_basic = None
        self._history_cache = None

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
        """读取历史缓存 CSV（实例内缓存）。"""
        if self._history_cache is not None and not force:
            return self._history_cache
        if not os.path.exists(self.history_file):
            self._history_cache = pd.DataFrame(columns=self.CSV_COLUMNS)
            return self._history_cache
        df = pd.read_csv(self.history_file, dtype={'trade_date': str})
        for col in self.CSV_COLUMNS:
            if col not in df.columns:
                df[col] = None
        df = df[self.CSV_COLUMNS]
        df['trade_date'] = pd.to_datetime(df['trade_date'], errors='coerce')
        df = df.dropna(subset=['trade_date'])
        self._history_cache = df
        return df

    def load_history(self, force=False):
        """对外读取历史数据（trade_date 为 datetime.date 或 Timestamp）。"""
        df = self._load_history(force=force)
        return df.copy()

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
        self._history_cache = None

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
                      progress_cb=None):
        """按交易日逐日拉取并构建三年板块拥挤度历史。

        参数：
            start_date : 'YYYYMMDD'，默认当前日期往前 HISTORY_YEARS 年
            end_date   : 'YYYYMMDD'，默认今天
            max_days   : 本次最多拉取多少天（调试用）
            resume     : 从历史缓存最后一个日期之后继续（默认 True）
            call_delay : 每次接口调用间隔秒数，防止触发限频
            flush_every: 攒多少天写一次缓存
            progress_cb: 进度回调 f(done, total, current_date)
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

        cal = pro.trade_cal(exchange='SSE', start_date=start_date,
                            end_date=end_date, is_open='1')
        if cal is None or cal.empty:
            print('[SectorCrowding] 交易日历为空，请检查日期范围')
            return 0
        dates = sorted(cal['cal_date'].astype(str).tolist())

        if resume and os.path.exists(self.history_file) and os.path.getsize(self.history_file) > 0:
            existing = self.load_history()
            if not existing.empty:
                last = existing['trade_date'].max().strftime('%Y%m%d')
                dates = [d for d in dates if d > last]

        if max_days is not None:
            dates = dates[:max_days]
        if not dates:
            print('[SectorCrowding] 没有需要更新的交易日（数据已最新）')
            return 0

        print(f'[SectorCrowding] 开始构建历史：{dates[0]} ~ {dates[-1]}，共 {len(dates)} 个交易日')
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

        meta_latest = self.load_history(force=True)['trade_date'].max()
        self._save_meta(
            start_date=dates[0],
            end_date=dates[-1],
            latest_date=meta_latest.strftime('%Y%m%d') if meta_latest is not None else latest,
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

    def get_index_crowding_series(self, index_code, scope=None):
        """计算给定指数（成分股聚合）的拥挤度时间序列。

        index_code: 指数代码 或 scope 标识
        scope: 'SH'/'SZ'/'STAR'/'GEM' 表示全市场范围
              例如 '000001'/'SH' -> 沪市全市场
                    '399001'/'SZ' -> 深市全市场
                    'STAR'      -> 科创板（688 开头）
                    'GEM'       -> 创业板（300 开头）

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

        # 按日期加权
        grouped = sub.groupby('trade_date', as_index=False).agg(
            w_total_mv=('total_mv', lambda x: (x * sub.loc[x.index, 'weight']).sum()),
            w_rzrqye=('rzrqye', lambda x: (x * sub.loc[x.index, 'weight']).sum()),
            w_rzye=('rzye', lambda x: (x * sub.loc[x.index, 'weight']).sum()),
            w_rqye=('rqye', lambda x: (x * sub.loc[x.index, 'weight']).sum()),
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
