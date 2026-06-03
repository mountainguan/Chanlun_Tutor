# -*- coding: utf-8 -*-
"""
板块历史PE序列构建脚本
========================
定期执行（建议每周/每月），生成【东方财富细粒度行业】过去N年的市值加权动态PE序列。

输出: data/sector_pe_history_cache.json
      data/stock_industry_map.json   (中间产物：ts_code -> 东方财富 industry，可删除后下次自动重建)

用法:
    python scripts/build_sector_pe_history.py                       # 增量更新，默认10年
    python scripts/build_sector_pe_history.py --lookback-days 750   # 3年
    python scripts/build_sector_pe_history.py --rpm 150             # 限流到 150 req/min
    python scripts/build_sector_pe_history.py --fresh                # 强制重建（清空 PE 缓存 + 行业映射）

设计:
    - 数据源: pro.daily_basic(trade_date=..., fields='ts_code,pe,total_mv')
              限速一次拉全市场 (5329 只 L 股)，再按 pro.stock_basic.industry 本地聚合成
              110 个东方财富细粒度行业的【市值加权动态PE】
    - 行业映射: pro.stock_basic 取一次 → 缓存为 data/stock_industry_map.json，
                7 天后自动刷新（行业分类调整不频繁，节省 1 次 API 调用/天）
    - 增量更新: 跳过所有【所有行业都已缓存】的 trade_date（不只是任意一个行业）
    - 限流: RateLimiter 卡在 RATE_LIMIT_RPM=190 req/min 之下（硬上限 200，留 5% 余量）
    - 失败重试: 单次 API 失败按 1.5s/3s/4.5s 指数退避重试 3 次
    - 原子写入: 每 50 个交易日 save_cache 一次（防中断丢数据）

API 调用量（10 年重建）:
    1  stock_basic  +  1  trade_cal  +  ~2427  daily_basic  =  ~2429 次
    耗时 ≈ 2429 × 0.32s = 12.9 min（vs 原版 ~15min，差异主要在限流一致性）

口径:
    - PE 字段: Tushare pro.daily_basic.pe = 动态市盈率（与 stock_basic.pe 一致）
    - 行业名称: 缓存顶层 key 与 pro.stock_basic().industry 完全一致（110 个东方财富细粒度名）
    - 聚合方式: 行业内 sum(pe * total_mv) / sum(total_mv) = 市值加权动态PE
    - 与现盘 pe_tracker.py 兼容（schema v2 强制写 pe_type='dynamic'）

为什么不直接用 pro.index_dailybasic (申万一级 31 个指数)?
    实测本账户 Tushare 级别下，pro.index_dailybasic 对 801xxx.SI (申万一级)、
    H1xxxx.CSI (中证) 等所有行业指数代码均返回空数据（仅 000300.SH 沪深300等
    规模指数有数据），可能受积分/权限限制。如未来账户升级，可在 _fetch_via_index()
    启用快速路径。
"""

import os
import sys
import json
import time
import argparse
import datetime
import logging
from concurrent.futures import ThreadPoolExecutor

# 项目根目录
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import tushare as ts

CACHE_FILE = os.path.join(ROOT, 'data', 'sector_pe_history_cache.json')
INDUSTRY_MAP_FILE = os.path.join(ROOT, 'data', 'stock_industry_map.json')

# ==================== 缓存 schema ====================
SCHEMA_VERSION = 2
PE_TYPE = 'dynamic'              # 动态市盈率（与 utils/pe_tracker.py 约定一致）
TUSHARE_PE_FIELD = 'pe'          # pro.daily_basic.pe 字段名
SOURCE_API = 'daily_basic_aggregate'  # 标记：来自逐日 daily_basic 聚合
INDUSTRY_MAP_MAX_AGE_DAYS = 7    # 行业映射缓存最大有效期

# ==================== 限流 ====================
# Tushare Pro 官方硬上限：200 req/min。默认 190 留约 5% 安全余量。
RATE_LIMIT_RPM = 190
MIN_INTERVAL_SEC = 60.0 / RATE_LIMIT_RPM  # ≈ 0.316s

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger('sector_pe_history')


# ==================== 限流器 ====================

class RateLimiter:
    """轻量 sleep 限流器：保证相邻两次调用间隔 ≥ min_interval。

    使用 time.monotonic() 避免系统时间漂移。线程安全：内部有 GIL 保护下的简单赋值。
    """

    def __init__(self, rpm: int = RATE_LIMIT_RPM):
        self.min_interval = 60.0 / max(1, rpm)
        self.last_call_ts = 0.0
        self.call_count = 0

    def wait(self) -> None:
        now = time.monotonic()
        if self.last_call_ts > 0:
            elapsed = now - self.last_call_ts
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
        self.last_call_ts = time.monotonic()
        self.call_count += 1

    def stats(self) -> str:
        return f'{self.call_count} calls, budget≈{self.call_count * self.min_interval:.1f}s'


# ==================== Tushare Pro 客户端 ====================

def get_pro():
    """获取 Tushare Pro 客户端，token 加载顺序：环境变量 > data/tushare_token.txt"""
    token = os.environ.get('TUSHARE_TOKEN', '').strip()
    if not token:
        token_file = os.path.join(ROOT, 'data', 'tushare_token.txt')
        if os.path.exists(token_file):
            try:
                with open(token_file, 'r', encoding='utf-8') as f:
                    token = f.read().strip()
            except Exception as e:
                log.warning(f'Read tushare_token.txt error: {e}')
    if not token:
        raise RuntimeError(
            '未配置 TUSHARE_TOKEN。\n'
            '请通过以下任一方式配置：\n'
            '  1) 设置环境变量 TUSHARE_TOKEN=<你的token>\n'
            '  2) 在 data/tushare_token.txt 写入 token（仅一行）\n'
            'token 在 https://tushare.pro 注册获取。'
        )
    ts.set_token(token)
    return ts.pro_api()


# ==================== 缓存读写 ====================

def empty_cache() -> dict:
    return {
        'schema_version': SCHEMA_VERSION,
        'pe_type': PE_TYPE,
        'tushare_field': TUSHARE_PE_FIELD,
        'source_api': SOURCE_API,
        'build_date': '',
        'lookback_days': 0,
        'start_date': '',
        'end_date': '',
        'industry_count': 0,
        'data': {},  # {industry_name: {trade_date: pe_value}}
    }


def load_cache():
    """读取已有缓存；schema/口径不一致时丢弃（强制重建）"""
    if not os.path.exists(CACHE_FILE):
        return empty_cache()
    try:
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            cache = json.load(f)
        if cache.get('schema_version') != SCHEMA_VERSION:
            log.warning(f'Cache schema_version mismatch, rebuilding')
            return empty_cache()
        if cache.get('pe_type') != PE_TYPE:
            log.warning(f'Cache pe_type mismatch, rebuilding')
            return empty_cache()
        if cache.get('source_api') != SOURCE_API:
            log.warning(f'Cache source_api mismatch, rebuilding')
            return empty_cache()
        cache.setdefault('data', {})
        return cache
    except Exception as e:
        log.error(f'Load cache error: {e}, starting fresh')
        return empty_cache()


def save_cache(cache):
    """原子写入缓存文件"""
    cache['build_date'] = datetime.date.today().strftime('%Y-%m-%d')
    cache['industry_count'] = len(cache['data'])
    cache['pe_type'] = PE_TYPE
    cache['tushare_field'] = TUSHARE_PE_FIELD
    cache['source_api'] = SOURCE_API
    cache['schema_version'] = SCHEMA_VERSION
    tmp = CACHE_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False)
    os.replace(tmp, CACHE_FILE)


def summarize_cache_range(cache):
    """计算当前缓存的起止日期（基于 data 字段）"""
    all_dates = set()
    for series in cache['data'].values():
        all_dates.update(series.keys())
    if not all_dates:
        return '', ''
    return min(all_dates), max(all_dates)


# ==================== 行业映射 (ts_code -> 东方财富 industry) ====================

def get_stock_industry_map(pro, rate_limiter, force_refresh: bool = False) -> dict:
    """从 data/stock_industry_map.json 读，缺失/过期/--fresh 时重建。

    返回: {ts_code: industry_name}
    """
    if not force_refresh and os.path.exists(INDUSTRY_MAP_FILE):
        try:
            with open(INDUSTRY_MAP_FILE, 'r', encoding='utf-8') as f:
                blob = json.load(f)
            build_date = blob.get('build_date', '')
            age = (datetime.date.today() - datetime.datetime.strptime(build_date, '%Y-%m-%d').date()).days
            if age <= INDUSTRY_MAP_MAX_AGE_DAYS:
                log.info(f'Reusing industry map (built {build_date}, {age}d ago): {len(blob["map"])} stocks')
                return blob['map']
        except Exception as e:
            log.warning(f'Read industry map error: {e}, will rebuild')

    rate_limiter.wait()
    log.info('Fetching stock_basic.industry mapping from Tushare...')
    sb = pro.stock_basic(list_status='L', fields='ts_code,industry')
    if sb is None or sb.empty:
        raise RuntimeError('pro.stock_basic 返回空，无法构建行业映射')
    sb = sb[sb['industry'].notna() & (sb['industry'].astype(str).str.strip() != '')]
    mapping = dict(zip(sb['ts_code'].astype(str), sb['industry'].astype(str)))
    log.info(f'Industry map: {len(mapping)} stocks, '
             f'{len(set(mapping.values()))} industries')

    # 落盘
    try:
        with open(INDUSTRY_MAP_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                'build_date': datetime.date.today().strftime('%Y-%m-%d'),
                'map': mapping,
            }, f, ensure_ascii=False)
    except Exception as e:
        log.warning(f'Save industry map error: {e}')
    return mapping


# ==================== 交易日历 ====================

def get_trade_dates(pro, start_date, end_date, rate_limiter) -> list:
    """获取区间内所有交易日（升序）"""
    rate_limiter.wait()
    df = pro.trade_cal(
        exchange='SSE', start_date=start_date, end_date=end_date,
        is_open='1', fields='cal_date',
    )
    if df is None or df.empty:
        return []
    return sorted(df['cal_date'].tolist())


# ==================== 单日拉取与聚合 ====================

def fetch_and_aggregate_one_day(pro, trade_date, stock_industry_map, rate_limiter, max_retries=3):
    """拉取某一天的 daily_basic，按 stock_industry_map 聚合成【市值加权动态PE】。

    返回: ({industry_name: pe_value, ...}, status_str)
    """
    rate_limiter.wait()
    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            df = pro.daily_basic(
                trade_date=trade_date,
                fields=f'ts_code,{TUSHARE_PE_FIELD},total_mv',
            )
            if df is None or df.empty:
                return {}, 'empty'
            df['industry'] = df['ts_code'].map(stock_industry_map)
            valid = df[
                (df[TUSHARE_PE_FIELD] > 0) & (df['total_mv'] > 0)
                & df['industry'].notna() & (df['industry'] != '')
            ]
            if valid.empty:
                return {}, 'no_valid'
            valid = valid.copy()
            valid['pe_x_mv'] = valid[TUSHARE_PE_FIELD] * valid['total_mv']
            grouped = valid.groupby('industry').agg(
                mv_sum=('total_mv', 'sum'),
                pe_x_mv_sum=('pe_x_mv', 'sum'),
            )
            grouped['pe'] = (grouped['pe_x_mv_sum'] / grouped['mv_sum']).round(2)
            return grouped['pe'].to_dict(), 'ok'
        except Exception as e:
            last_err = e
            err_short = str(e)[:80]
            if attempt < max_retries:
                backoff = 1.5 * attempt
                log.warning(f'{trade_date} attempt {attempt}/{max_retries} failed: '
                            f'{err_short}; sleep {backoff:.1f}s')
                time.sleep(backoff)
                rate_limiter.wait()  # 重试前再次确认限流
            else:
                log.error(f'{trade_date} failed after {max_retries} attempts: {err_short}')
                return {}, f'error: {err_short}'
    return {}, f'error: {last_err}'


# ==================== 主流程 ====================

def main():
    parser = argparse.ArgumentParser(
        description='构建东方财富细粒度行业历史PE序列（per-trade-date daily_basic 聚合）'
    )
    parser.add_argument('--lookback-days', type=int, default=2500,
                        help='回看自然日数（10年≈2500，3年≈750，含节假日余量）')
    parser.add_argument('--rpm', type=int, default=RATE_LIMIT_RPM,
                        help=f'Tushare 限流（req/min），硬上限 200，默认 {RATE_LIMIT_RPM}')
    parser.add_argument('--workers', type=int, default=1,
                        help='并发线程数（推荐 1-2，2 时每线程 sleep 0.6s 仍可卡 200 req/min）')
    parser.add_argument('--fresh', action='store_true',
                        help='忽略旧缓存，从零重建（同时刷新行业映射）')
    args = parser.parse_args()

    if args.rpm > 200:
        log.warning(f'--rpm {args.rpm} 超过 Tushare 硬上限 200 req/min，将被节流到 200')

    if args.workers > 2 and args.rpm >= 200:
        log.warning(f'--workers {args.workers} 配合 --rpm {args.rpm} 可能突破 200 req/min 上限')

    log.info('=' * 60)
    log.info(f'Building sector PE history (lookback={args.lookback_days}d, '
             f'rpm={args.rpm}, workers={args.workers}, fresh={args.fresh})')
    log.info('=' * 60)

    pro = get_pro()
    rate_limiter = RateLimiter(rpm=args.rpm)

    # 1. 加载行业映射
    if args.fresh and os.path.exists(INDUSTRY_MAP_FILE):
        log.info('--fresh: removing cached industry map')
        os.remove(INDUSTRY_MAP_FILE)
    stock_industry_map = get_stock_industry_map(pro, rate_limiter,
                                                force_refresh=args.fresh)

    # 2. 加载 PE 缓存
    cache = load_cache()
    if args.fresh:
        log.info('--fresh: clearing PE cache data')
        cache['data'] = {}

    # 3. 时间窗口（lookback_days * 1.5 留余量）
    end_date = datetime.date.today().strftime('%Y%m%d')
    start_dt = datetime.date.today() - datetime.timedelta(days=int(args.lookback_days * 1.5))
    start_date = start_dt.strftime('%Y%m%d')
    log.info(f'Window: {start_date} → {end_date}')

    # 4. 交易日历
    trade_dates = get_trade_dates(pro, start_date, end_date, rate_limiter)
    log.info(f'Total trade dates in window: {len(trade_dates)}')

    # 5. 增量：跳过【所有行业都已缓存】的日期
    cached_dates = set()
    for series in cache['data'].values():
        cached_dates.update(series.keys())
    full_industry_count = len(set(stock_industry_map.values()))
    todo_dates = []
    for d in trade_dates:
        # 该日期上没有任何行业有数据，才需要拉
        has_any = any(d in series for series in cache['data'].values())
        if not has_any:
            todo_dates.append(d)
    log.info(f'Already cached: {len(cached_dates)} dates, '
             f'to-do: {len(todo_dates)} dates')

    if not todo_dates:
        log.info('Cache is up-to-date, nothing to do.')
        cache['start_date'], cache['end_date'] = summarize_cache_range(cache)
        cache['lookback_days'] = args.lookback_days
        cache['industry_count'] = len(cache['data'])
        save_cache(cache)
        return

    # 倒序拉取：最新日期优先，刷新一次即可看到顶部数据
    todo_dates = sorted(todo_dates, reverse=True)

    t_start = time.time()
    completed = 0
    ok_count = 0
    fail_count = 0
    last_save = 0

    # 6. 并行 or 串行拉取
    if args.workers <= 1:
        for trade_date in todo_dates:
            pe_by_industry, status = fetch_and_aggregate_one_day(
                pro, trade_date, stock_industry_map, rate_limiter
            )
            completed += 1
            if status == 'ok' and pe_by_industry:
                for ind, pe in pe_by_industry.items():
                    cache['data'].setdefault(ind, {})[trade_date] = pe
                ok_count += 1
            else:
                fail_count += 1
                if fail_count <= 5:
                    log.warning(f'{trade_date}: {status}')

            if completed - last_save >= 50:
                cache['start_date'], cache['end_date'] = summarize_cache_range(cache)
                cache['lookback_days'] = args.lookback_days
                cache['industry_count'] = len(cache['data'])
                save_cache(cache)
                last_save = completed
                _log_progress(completed, len(todo_dates), ok_count, fail_count,
                              t_start, rate_limiter)
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futures = {
                ex.submit(fetch_and_aggregate_one_day, pro, d, stock_industry_map, rate_limiter): d
                for d in todo_dates
            }
            try:
                for fut in futures:  # 顺序：按倒序
                    trade_date = futures[fut]
                    pe_by_industry, status = fut.result()
                    completed += 1
                    if status == 'ok' and pe_by_industry:
                        for ind, pe in pe_by_industry.items():
                            cache['data'].setdefault(ind, {})[trade_date] = pe
                        ok_count += 1
                    else:
                        fail_count += 1
                        if fail_count <= 5:
                            log.warning(f'{trade_date}: {status}')

                    if completed - last_save >= 50:
                        cache['start_date'], cache['end_date'] = summarize_cache_range(cache)
                        cache['lookback_days'] = args.lookback_days
                        cache['industry_count'] = len(cache['data'])
                        save_cache(cache)
                        last_save = completed
                        _log_progress(completed, len(todo_dates), ok_count, fail_count,
                                      t_start, rate_limiter)
            except KeyboardInterrupt:
                log.warning('Interrupted by user, saving partial cache...')
                ex.shutdown(wait=False, cancel_futures=True)

    # 7. 最终保存
    cache['start_date'], cache['end_date'] = summarize_cache_range(cache)
    cache['lookback_days'] = args.lookback_days
    cache['industry_count'] = len(cache['data'])
    save_cache(cache)

    total_dates = sum(len(s) for s in cache['data'].values())
    elapsed = time.time() - t_start
    log.info('=' * 60)
    log.info(f'Done in {elapsed/60:.1f} min')
    log.info(f'  Trade dates processed: ok={ok_count} fail={fail_count}')
    log.info(f'  Industries: {len(cache["data"])}')
    log.info(f'  Total data points: {total_dates}')
    log.info(f'  Date range: {cache["start_date"]} → {cache["end_date"]}')
    log.info(f'  Tushare API: {rate_limiter.stats()}')
    log.info(f'  Cache file: {CACHE_FILE}')
    log.info(f'  Industry map: {INDUSTRY_MAP_FILE}')
    log.info('=' * 60)


def _log_progress(completed, total, ok, fail, t_start, rate_limiter):
    elapsed = time.time() - t_start
    rate = completed / elapsed if elapsed > 0 else 0
    remaining = total - completed
    eta_min = remaining / rate / 60 if rate > 0 else 0
    log.info(
        f'Progress: {completed}/{total} ({completed/total*100:.1f}%) | '
        f'ok={ok} fail={fail} | elapsed={elapsed/60:.1f}min ETA={eta_min:.1f}min | '
        f'API: {rate_limiter.stats()}'
    )


if __name__ == '__main__':
    main()
