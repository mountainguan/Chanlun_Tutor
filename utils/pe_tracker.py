import os
import json
import time
import datetime
import pandas as pd

import tushare as ts


class PETracker:
    """
    指数成分股PE估值跟踪器
    数据源：Tushare Pro (tushare.pro)

    ⚠️ PE 口径声明：本组件统一使用【动态市盈率】（Tushare pro.daily_basic.pe）
        - 动态PE  -> pro.daily_basic.pe        (动态市盈率 = price / 预测EPS)
        - 静态PE  -> pro.daily_basic.pe_ttm    (滚动12个月市盈率，仅作辅助参考)
        - PB      -> pro.daily_basic.pb        (市净率)
        - 总市值  -> pro.daily_basic.total_mv  (单位：万元，转换为元后输出)
    行业分类：pro.stock_basic.industry (申万一级)
    板块PE：基于全市场 daily_basic × stock_basic.industry 的市值加权平均（同样为动态PE）

    估值判断口径（自 v2 起）：
        - 不再使用「PE溢价率 = 个股PE / 板块PE - 1」判断高估
        - 改用「PE分位 = 当前个股动态PE 在其所属申万一级行业过去 10 年日频 动态PE 序列中的位置」
        - 分位档位：<20% 低估 / 20-50% 偏低 / 50-80% 偏高 / >=80% 高估
        - 历史PE序列由独立脚本 scripts/build_sector_pe_history.py 定期生成：
              python scripts/build_sector_pe_history.py
          缓存文件：data/sector_pe_history_cache.json（schema v2 起强制写 pe_type='dynamic'）
        - 缓存缺失时（首次部署、脚本未跑）PE分位为 None，前端以 '—' 兜底
        - pe_type != 'dynamic' 时启动会打印警告，避免与现盘判断口径不一致
    """

    DATA_SOURCE = 'Tushare Pro'
    # 缓存 schema 版本：1 = 东方财富时代，2 = Tushare Pro 时代
    # 切换数据源时 bump 此值，使旧缓存自动失效
    SCHEMA_VERSION = 2

    # ==================== PE分位档位（基于申万一级行业历史PE分布） ====================
    # 行业PE分位 = 当前个股PE在其所属申万一级行业过去10年日频PE序列中的位置（百分比）
    # 分位档位（保守版）：
    #   <20%  低估     — 个股PE处于行业历史后20%，价格相对便宜
    #   20-50% 偏低    — 处于历史中下沿
    #   50-80% 偏高    — 处于历史中上沿
    #   >=80%  高估    — 个股PE已经接近/超过历史80%分位
    PERCENTILE_LEVELS = [
        # (max_pct, name, bg_color, text_color, ring_color)
        (20,  '低估',  '#dcfce7', '#15803d', '#10b981'),
        (50,  '偏低',  '#dbeafe', '#1d4ed8', '#3b82f6'),
        (80,  '偏高',  '#fef3c7', '#b45309', '#f59e0b'),
        (100, '高估',  '#fee2e2', '#b91c1c', '#ef4444'),
    ]
    # 行业历史PE序列至少需要多少样本才计算分位
    MIN_HISTORY_SAMPLES = 30

    def __init__(self):
        self.data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
        self.cache_file = os.path.join(self.data_dir, 'pe_tracker_cache.json')
        self.sector_cache_file = os.path.join(self.data_dir, 'pe_sector_cache.json')
        self.sector_pe_history_file = os.path.join(self.data_dir, 'sector_pe_history_cache.json')
        self.excel_file = os.path.join(self.data_dir, '指数样本调整名单.xlsx')
        self.cache = self._load_cache()
        self.sector_cache = self._load_sector_cache()
        self._all_sectors = None
        self._daily_basic_df = None
        self._stock_basic_df = None
        self._sector_pe_history = None
        self._pro = None

    # ==================== Tushare Pro 客户端 ====================

    def _get_pro(self):
        """获取 Tushare Pro 客户端
        token 加载顺序：环境变量 TUSHARE_TOKEN > data/tushare_token.txt
        """
        if self._pro is not None:
            return self._pro
        token = os.environ.get('TUSHARE_TOKEN', '').strip()
        if not token:
            token_file = os.path.join(self.data_dir, 'tushare_token.txt')
            if os.path.exists(token_file):
                try:
                    with open(token_file, 'r', encoding='utf-8') as f:
                        token = f.read().strip()
                except Exception as e:
                    print(f"[PETracker] Read tushare_token.txt error: {e}")
        if not token:
            raise RuntimeError(
                '未配置 TUSHARE_TOKEN。\n'
                '请通过以下任一方式配置后重启服务：\n'
                '  1) 设置环境变量  TUSHARE_TOKEN=<你的token>\n'
                '  2) 在 data/tushare_token.txt 写入 token（仅一行）\n'
                'token 在 https://tushare.pro 注册获取。'
            )
        ts.set_token(token)
        self._pro = ts.pro_api()
        return self._pro

    # ==================== 缓存 ====================

    def _load_cache(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    cache = json.load(f)
                if (cache.get('date', '') == datetime.date.today().strftime('%Y-%m-%d')
                        and cache.get('schema_version') == self.SCHEMA_VERSION):
                    return cache
                else:
                    print(f"[PETracker] cache schema/date mismatch, ignore old cache")
            except Exception as e:
                print(f"[PETracker] Cache load error: {e}")
        return {'date': '', 'stocks': {}, 'schema_version': self.SCHEMA_VERSION}

    def _load_sector_cache(self):
        if os.path.exists(self.sector_cache_file):
            try:
                with open(self.sector_cache_file, 'r', encoding='utf-8') as f:
                    cache = json.load(f)
                if (cache.get('date', '') == datetime.date.today().strftime('%Y-%m-%d')
                        and cache.get('schema_version') == self.SCHEMA_VERSION):
                    return cache
                else:
                    print(f"[PETracker] sector cache schema/date mismatch, ignore old cache")
            except Exception as e:
                print(f"[PETracker] Sector cache load error: {e}")
        return {'date': '', 'sectors': {}, 'stock_sector_map': {}, 'schema_version': self.SCHEMA_VERSION}

    def _save_cache(self):
        try:
            self.cache['date'] = datetime.date.today().strftime('%Y-%m-%d')
            self.cache['schema_version'] = self.SCHEMA_VERSION
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[PETracker] Cache save error: {e}")

    def _save_sector_cache(self):
        try:
            self.sector_cache['date'] = datetime.date.today().strftime('%Y-%m-%d')
            self.sector_cache['schema_version'] = self.SCHEMA_VERSION
            with open(self.sector_cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.sector_cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[PETracker] Sector cache save error: {e}")

    # ==================== 指数样本名单 ====================

    def load_index_constituents(self):
        try:
            df = pd.read_excel(self.excel_file)
            df.columns = ['股票编码', '股票名称', '所属指数', '调入调出']
            df['股票编码'] = df['股票编码'].astype(str).str.zfill(6)
            return df
        except Exception as e:
            print(f"[PETracker] Load Excel error: {e}")
            return pd.DataFrame()

    # ==================== 代码转换 ====================

    def _to_ts_code(self, stock_code):
        """6位股票代码 -> tushare ts_code (考虑上证/深证/北交所)"""
        code = str(stock_code).zfill(6)
        if code.startswith(('60', '68', '90', '11', '13')):
            return f'{code}.SH'
        if code.startswith(('8', '43', '92', '83')):
            return f'{code}.BJ'
        return f'{code}.SZ'

    @staticmethod
    def _from_ts_code(ts_code):
        return str(ts_code).split('.')[0]

    # ==================== Tushare 拉取 ====================

    def _fetch_daily_basic(self, force=False, max_retries=2):
        """拉全市场 daily_basic（pe, pe_ttm, pb, total_mv, close），一次拉全 A 缓存到实例"""
        if self._daily_basic_df is not None and not force:
            return self._daily_basic_df
        pro = self._get_pro()
        fields = 'ts_code,trade_date,close,pe,pe_ttm,pb,total_mv'
        last_err = None
        for attempt in range(max_retries):
            try:
                df = pro.daily_basic(fields=fields)
                if df is None:
                    df = pd.DataFrame()
                self._daily_basic_df = df
                return df
            except Exception as e:
                last_err = e
                if attempt < max_retries - 1:
                    time.sleep(1.5)
        print(f"[PETracker] daily_basic fetch failed: {last_err}")
        self._daily_basic_df = pd.DataFrame()
        return self._daily_basic_df

    def _fetch_stock_basic(self, force=False, max_retries=2):
        """拉全市场 stock_basic（name, industry）"""
        if self._stock_basic_df is not None and not force:
            return self._stock_basic_df
        pro = self._get_pro()
        last_err = None
        for attempt in range(max_retries):
            try:
                df = pro.stock_basic(list_status='L', fields='ts_code,name,industry')
                if df is None:
                    df = pd.DataFrame()
                self._stock_basic_df = df
                return df
            except Exception as e:
                last_err = e
                if attempt < max_retries - 1:
                    time.sleep(1.5)
        print(f"[PETracker] stock_basic fetch failed: {last_err}")
        self._stock_basic_df = pd.DataFrame()
        return self._stock_basic_df

    def _compute_industry_pe(self, db_df, sb_df):
        """基于全市场 daily_basic + stock_basic.industry 计算申万一级行业市值加权 PE"""
        if db_df is None or db_df.empty or sb_df is None or sb_df.empty:
            return {}
        try:
            merged = db_df.merge(sb_df[['ts_code', 'industry']], on='ts_code', how='left')
        except Exception as e:
            print(f"[PETracker] industry merge failed: {e}")
            return {}
        merged = merged[(merged['pe'] > 0) & (merged['total_mv'] > 0) & merged['industry'].notna()]
        if merged.empty:
            return {}
        merged = merged.copy()
        merged['pe_x_mv'] = merged['pe'] * merged['total_mv']
        grouped = merged.groupby('industry').agg(
            mv_sum=('total_mv', 'sum'),
            pe_x_mv_sum=('pe_x_mv', 'sum')
        )
        grouped['weighted_pe'] = grouped['pe_x_mv_sum'] / grouped['mv_sum']
        return grouped['weighted_pe'].round(2).to_dict()

    # ==================== 单只股票 PE ====================

    def get_stock_pe(self, stock_code, max_retries=3):
        """获取个股 PE 数据（从批量 daily_basic 取单只）"""
        if stock_code in self.cache.get('stocks', {}):
            cached = self.cache['stocks'][stock_code]
            if 'pe_dynamic' in cached:
                return cached

        db_df = self._fetch_daily_basic()
        if db_df is None or db_df.empty:
            return None
        ts_code = self._to_ts_code(stock_code)
        row = db_df[db_df['ts_code'] == ts_code]
        if row.empty:
            return None
        r = row.iloc[0]
        # 名字
        name = ''
        sb = self._fetch_stock_basic()
        if sb is not None and not sb.empty:
            name_row = sb[sb['ts_code'] == ts_code]
            if not name_row.empty:
                name = str(name_row.iloc[0].get('name') or '')
        result = {
            'code': stock_code,
            'name': name,
            'price': float(r.get('close') or 0),
            'pe_dynamic': float(r.get('pe') or 0),
            'pe_static': float(r.get('pe_ttm') or 0),
            'pb': float(r.get('pb') or 0),
            'market_cap': float(r.get('total_mv') or 0) * 1e4,  # 万元 -> 元
        }
        if 'stocks' not in self.cache:
            self.cache['stocks'] = {}
        self.cache['stocks'][stock_code] = result
        return result

    # ==================== 板块历史PE分位 ====================

    def _load_sector_pe_history(self):
        """加载申万一级行业历史PE序列缓存（由 scripts/build_sector_pe_history.py 生成）
        返回: {pe_type, build_date, start_date, end_date, lookback_days, data: {industry: {date: pe}}}
        缓存缺失时返回空 dict，不抛异常（降级使 PE分位 全部为 None）。
        口径校验：pe_type 必须为 'dynamic'，否则打印警告（说明缓存是用 TTM/其他口径构建的）。
        """
        if self._sector_pe_history is not None:
            return self._sector_pe_history
        if not os.path.exists(self.sector_pe_history_file):
            self._sector_pe_history = {
                'data': {}, 'build_date': '', 'start_date': '', 'end_date': '',
                'pe_type': '',
            }
            return self._sector_pe_history
        try:
            with open(self.sector_pe_history_file, 'r', encoding='utf-8') as f:
                self._sector_pe_history = json.load(f)
            data = self._sector_pe_history.get('data', {})
            sample_industry = next((k for k, v in data.items() if v), None)
            sample_size = len(data[sample_industry]) if sample_industry else 0
            pe_type = self._sector_pe_history.get('pe_type', '')
            tushare_field = self._sector_pe_history.get('tushare_field', '')
            type_warn = ''
            if pe_type and pe_type != 'dynamic':
                type_warn = (f' [WARN] 缓存pe_type={pe_type}与dynamic不一致!'
                             f'请用 scripts/build_sector_pe_history.py --fresh 重建。')
            elif not pe_type:
                type_warn = ' (旧版缓存无pe_type元信息，建议 --fresh 重建)'
            print(f"[PETracker] sector PE history loaded: "
                  f"pe_type={pe_type or 'unknown'} (tushare.{tushare_field or '?'}), "
                  f"{len(data)} industries, sample '{sample_industry}' has {sample_size} dates, "
                  f"build_date={self._sector_pe_history.get('build_date', '')}{type_warn}")
        except Exception as e:
            print(f"[PETracker] sector PE history load error: {e}")
            self._sector_pe_history = {
                'data': {}, 'build_date': '', 'start_date': '', 'end_date': '',
                'pe_type': '',
            }
        return self._sector_pe_history

    def _compute_sector_percentile(self, industry, current_pe):
        """计算 current_pe 在 industry 历史PE序列中的分位（百分比，0-100）
        返回 None 表示样本不足 / 行业未在缓存中。
        """
        if not industry or current_pe is None or current_pe <= 0:
            return None
        history = self._load_sector_pe_history()
        industry_data = history.get('data', {}).get(industry, {})
        if not industry_data:
            return None
        # 取有效PE（去None/0）
        pes = [v for v in industry_data.values() if v and v > 0]
        if len(pes) < self.MIN_HISTORY_SAMPLES:
            return None
        below = sum(1 for p in pes if p <= current_pe)
        return round(below / len(pes) * 100, 1)

    @classmethod
    def get_percentile_level(cls, percentile):
        """根据分位数返回 (档位名称, 背景色, 文字色)"""
        if percentile is None:
            return '—', '#f1f5f9', '#64748b'
        for max_pct, name, bg, text, _ring in cls.PERCENTILE_LEVELS:
            if percentile < max_pct:
                return name, bg, text
        return cls.PERCENTILE_LEVELS[-1][1], cls.PERCENTILE_LEVELS[-1][2], cls.PERCENTILE_LEVELS[-1][3]

    # ==================== 板块 ====================

    def get_all_sectors_pe(self):
        """获取所有申万一级行业板块 PE（基于市值加权）"""
        if self._all_sectors:
            return self._all_sectors
        if self.sector_cache.get('sectors'):
            self._all_sectors = self.sector_cache['sectors']
            return self._all_sectors
        try:
            db_df = self._fetch_daily_basic()
            sb_df = self._fetch_stock_basic()
            industry_pe = self._compute_industry_pe(db_df, sb_df)
            sectors = {
                f'IND_{name}': {'code': f'IND_{name}', 'name': name, 'pe': pe}
                for name, pe in industry_pe.items()
            }
            self._all_sectors = sectors
            self.sector_cache['sectors'] = sectors
            self._save_sector_cache()
            return sectors
        except Exception as e:
            print(f"[PETracker] Get all sectors PE error: {e}")
            return {}

    def get_stock_sector_info(self, stock_code):
        """获取股票所属行业板块信息（申万一级）"""
        if stock_code in self.sector_cache.get('stock_sector_map', {}):
            return self.sector_cache['stock_sector_map'][stock_code]
        try:
            sb = self._fetch_stock_basic()
            if sb is None or sb.empty:
                return None
            ts_code = self._to_ts_code(stock_code)
            row = sb[sb['ts_code'] == ts_code]
            if row.empty:
                return None
            industry = str(row.iloc[0].get('industry') or '').strip()
            if not industry:
                return None
            sectors = self.get_all_sectors_pe()
            sector_pe = sectors.get(f'IND_{industry}', {}).get('pe', 0)
            result = {
                'sector_code': f'IND_{industry}',
                'sector_name': industry,
                'sector_pe': sector_pe,
            }
            if 'stock_sector_map' not in self.sector_cache:
                self.sector_cache['stock_sector_map'] = {}
            self.sector_cache['stock_sector_map'][stock_code] = result
            return result
        except Exception as e:
            print(f"[PETracker] Get stock sector error for {stock_code}: {e}")
            return None

    # ==================== 批量 ====================

    def get_batch_pe(self, stock_codes, max_workers=3):
        """批量获取股票 PE 数据（Tushare 一次全市场拉取，再按 stock_codes 切片）"""
        results = {}
        try:
            db_df = self._fetch_daily_basic()
            sb_df = self._fetch_stock_basic()
            if db_df is None or db_df.empty:
                return {}
            name_map = {}
            if sb_df is not None and not sb_df.empty:
                name_map = dict(zip(sb_df['ts_code'], sb_df['name']))
            for code in stock_codes:
                ts_code = self._to_ts_code(code)
                row = db_df[db_df['ts_code'] == ts_code]
                if row.empty:
                    continue
                r = row.iloc[0]
                results[code] = {
                    'code': code,
                    'name': str(name_map.get(ts_code) or ''),
                    'price': float(r.get('close') or 0),
                    'pe_dynamic': float(r.get('pe') or 0),
                    'pe_static': float(r.get('pe_ttm') or 0),
                    'pb': float(r.get('pb') or 0),
                    'market_cap': float(r.get('total_mv') or 0) * 1e4,
                }
            # 仅保留本次关注的代码进缓存，避免膨胀
            self.cache['stocks'] = {k: v for k, v in results.items() if k in stock_codes}
        except Exception as e:
            print(f"[PETracker] Batch fetch error: {e}")
        self._save_cache()
        return results

    def get_batch_sector_info(self, stock_codes, max_workers=3):
        """批量获取股票所属行业信息（基于 stock_basic.industry）"""
        results = {}
        try:
            sectors = self.get_all_sectors_pe()
            sb = self._fetch_stock_basic()
            if sb is None or sb.empty:
                return {}
            ind_map = dict(zip(sb['ts_code'].astype(str), sb['industry'].astype(str)))
            for code in stock_codes:
                ts_code = self._to_ts_code(code)
                ind = str(ind_map.get(ts_code) or '').strip()
                if not ind:
                    continue
                results[code] = {
                    'sector_code': f'IND_{ind}',
                    'sector_name': ind,
                    'sector_pe': sectors.get(f'IND_{ind}', {}).get('pe', 0),
                }
            self.sector_cache['stock_sector_map'] = {
                k: v for k, v in results.items() if k in stock_codes
            }
        except Exception as e:
            print(f"[PETracker] Batch sector fetch error: {e}")
        self._save_sector_cache()
        return results

    # ==================== 主流程 ====================

    def get_all_data(self, force_update=False):
        """获取所有指数成分股的 PE 数据"""
        df = self.load_index_constituents()
        if df.empty:
            return pd.DataFrame()

        stock_codes = df['股票编码'].unique().tolist()
        cached_stocks = self.cache.get('stocks', {})

        # 1. 优先用缓存
        if not force_update and len(cached_stocks) >= len(stock_codes) * 0.5:
            print(f"[PETracker] Using cached data: {len(cached_stocks)}/{len(stock_codes)}")
            try:
                sectors = self.get_all_sectors_pe()
                sector_map = self.get_batch_sector_info(stock_codes)
            except Exception as e:
                print(f"[PETracker] Sector fetch failed: {e}")
                sectors = self.sector_cache.get('sectors', {})
                sector_map = self.sector_cache.get('stock_sector_map', {})
            return self._merge_data(df, cached_stocks, sector_map, sectors)

        # 2. 拉新数据
        print(f"[PETracker] Fetching PE data for {len(stock_codes)} stocks...")
        try:
            pe_data = self.get_batch_pe(stock_codes)
            for code in stock_codes:
                if code not in pe_data and code in cached_stocks:
                    pe_data[code] = cached_stocks[code]
            sectors = self.get_all_sectors_pe()
            sector_map = self.get_batch_sector_info(stock_codes)
        except Exception as e:
            print(f"[PETracker] Fetch failed, fallback to cache: {e}")
            sectors = self.sector_cache.get('sectors', {})
            sector_map = self.sector_cache.get('stock_sector_map', {})
            pe_data = cached_stocks

        return self._merge_data(df, pe_data, sector_map, sectors)

    def _merge_data(self, df, pe_data, sector_map, sectors):
        """合并成分股名单、PE 数据和板块信息。
        新增 PE分位 字段（替换旧 PE溢价率），需 sector_pe_history_cache.json：
            - 历史样本 ≥ MIN_HISTORY_SAMPLES 时返回 0-100 的分位数
            - 样本不足或行业未在缓存中时返回 None（前端用 '—' 兜底）
        """
        # 预加载历史PE缓存，避免循环内重复IO
        self._load_sector_pe_history()

        results = []
        for _, row in df.iterrows():
            code = row['股票编码']
            pe_info = pe_data.get(code, {})
            sector_info = sector_map.get(code, {})

            sector_pe = 0
            sector_name = ''
            if sector_info:
                sector_pe = sector_info.get('sector_pe', 0)
                sector_name = sector_info.get('sector_name', '')

            pe_dynamic = pe_info.get('pe_dynamic', 0)

            # 计算PE分位（个股PE在所属申万一级行业历史分布中的位置）
            pe_percentile = None
            if sector_name and pe_dynamic > 0:
                pe_percentile = self._compute_sector_percentile(sector_name, pe_dynamic)

            results.append({
                '股票编码': code,
                '股票名称': row['股票名称'],
                '所属指数': row['所属指数'],
                '调入调出': row['调入调出'],
                '最新价': pe_info.get('price', 0),
                '动态PE': pe_dynamic,
                '静态PE': pe_info.get('pe_static', 0),
                'PB': pe_info.get('pb', 0),
                '总市值': pe_info.get('market_cap', 0),
                '所属板块': sector_name,
                '板块PE': sector_pe,
                'PE分位': pe_percentile,
            })
        return pd.DataFrame(results)


# 测试代码
if __name__ == '__main__':
    tracker = PETracker()

    print("测试获取上汽集团PE:")
    pe = tracker.get_stock_pe('600104')
    print(pe)

    print("\n测试获取板块信息:")
    sector = tracker.get_stock_sector_info('600104')
    print(sector)

    print("\n测试加载成分股名单:")
    df = tracker.load_index_constituents()
    print(f"共 {len(df)} 条记录")
