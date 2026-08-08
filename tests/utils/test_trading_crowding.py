"""成交集中度拥挤度聚合逻辑单元测试（纯函数，不联网）。"""

import os

import pandas as pd
from unittest.mock import MagicMock

from utils.trading_crowding import TradingCrowding


def _daily_df():
    """8 只股票：行业A 6 只，行业B 2 只。"""
    return pd.DataFrame({
        'ts_code': ['000001.SZ', '000002.SZ', '000003.SZ', '000004.SZ',
                    '000005.SZ', '000006.SZ', '600001.SH', '600002.SH'],
        'vol': [100, 80, 60, 40, 20, 10, 50, 5],
        'amount': [1000, 900, 800, 700, 600, 500, 300, 50],
    })


def _industry_map():
    return {
        '000001.SZ': '行业A', '000002.SZ': '行业A', '000003.SZ': '行业A',
        '000004.SZ': '行业A', '000005.SZ': '行业A', '000006.SZ': '行业A',
        '600001.SH': '行业B', '600002.SH': '行业B',
    }


def test_aggregate_industries_top5():
    ind = TradingCrowding.aggregate_industries(_daily_df(), _industry_map())
    assert len(ind) == 2
    a = ind[ind['industry'] == '行业A'].iloc[0]
    b = ind[ind['industry'] == '行业B'].iloc[0]

    # 行业A：6 只，前5% = ceil(0.3) = 1 只 -> 最大 vol 100 / 总 310
    assert a['stock_count'] == 6
    assert a['top5_vol'] == 100
    assert a['total_vol'] == 310
    assert abs(a['vol_concentration_pct'] - 100 / 310 * 100) < 1e-9
    # 成交额维度独立排序：最大 amount 1000 / 总 4500
    assert a['top5_amount'] == 1000
    assert a['total_amount'] == 4500
    assert abs(a['amount_concentration_pct'] - 1000 / 4500 * 100) < 1e-9

    # 行业B：2 只，前5% = max(1, ceil(0.1)) = 1 只
    assert b['stock_count'] == 2
    assert b['top5_vol'] == 50
    assert b['total_vol'] == 55
    assert abs(b['vol_concentration_pct'] - 50 / 55 * 100) < 1e-9
    assert b['top5_amount'] == 300
    assert abs(b['amount_concentration_pct'] - 300 / 350 * 100) < 1e-9


def test_aggregate_indices():
    groups = [('IDX', '测试指数',
               ['000001.SZ', '000002.SZ', '000003.SZ',
                '000004.SZ', '000005.SZ', '000006.SZ'])]
    idx = TradingCrowding.aggregate_indices(_daily_df(), groups)
    assert len(idx) == 1
    r = idx.iloc[0]
    assert r['index_code'] == 'IDX'
    assert r['index_name'] == '测试指数'
    assert r['stock_count'] == 6
    assert r['coverage'] == 100.0
    assert abs(r['vol_concentration_pct'] - 100 / 310 * 100) < 1e-9
    assert abs(r['amount_concentration_pct'] - 1000 / 4500 * 100) < 1e-9


def test_aggregate_market():
    """全A市场维度：全部股票作为一个整体，取前 5% 个股的成交量/成交额占比。"""
    df = _daily_df()
    market = TradingCrowding.aggregate_market(df, _industry_map())
    assert len(market) == 1
    r = market.iloc[0]
    assert r['index_code'] == 'ALL'
    assert r['index_name'] == '全A'
    # 8 只股票：前5% = max(1, ceil(0.4)) = 1 只
    assert r['stock_count'] == 8
    assert r['coverage'] == 100.0
    assert r['top5_vol'] == 100
    assert r['total_vol'] == 365
    assert abs(r['vol_concentration_pct'] - 100 / 365 * 100) < 1e-9
    assert r['top5_amount'] == 1000
    assert r['total_amount'] == 4850
    assert abs(r['amount_concentration_pct'] - 1000 / 4850 * 100) < 1e-9

    # 空输入
    assert TradingCrowding.aggregate_market(pd.DataFrame(), {}).empty
    assert TradingCrowding.aggregate_market(None, {}).empty


def test_aggregate_empty_inputs():
    empty = pd.DataFrame()
    assert TradingCrowding.aggregate_industries(empty, {}).empty
    assert TradingCrowding.aggregate_industries(None, {}).empty
    assert TradingCrowding.aggregate_indices(empty, []).empty
    assert TradingCrowding.aggregate_indices(None, []).empty


def test_top5_min_one():
    """只有 1 只股票的板块：前5% 至少取 1 只 -> 集中度 100%。"""
    df = pd.DataFrame({'ts_code': ['000001.SZ'], 'vol': [10], 'amount': [100]})
    ind = TradingCrowding.aggregate_industries(df, {'000001.SZ': '行业A'})
    assert ind.iloc[0]['vol_concentration_pct'] == 100.0
    assert ind.iloc[0]['amount_concentration_pct'] == 100.0


def test_threshold_definition():
    """阈值口径：>45% 标记拥挤，前5% 个股。"""
    assert TradingCrowding.THRESHOLD == 45.0
    assert TradingCrowding.TOP_PCT == 0.05


def test_history_roundtrip(tmp_path):
    """写行业 CSV 后 load_history 能读回（复用 SectorCrowding 进程级缓存）。"""
    tmp_path = os.path.join(str(tmp_path), 'roundtrip')
    os.makedirs(tmp_path, exist_ok=True)
    tc = TradingCrowding()
    tc.cache_dir = tmp_path
    tc.history_file = os.path.join(tmp_path, 'trading_crowding_history.csv')
    tc.index_history_file = os.path.join(
        tmp_path, 'trading_crowding_index_history.csv')
    rows = [{
        'trade_date': '20260101', 'industry': '行业A', 'stock_count': 6,
        'total_vol': 310.0, 'top5_vol': 100.0, 'vol_concentration_pct': 32.258064,
        'total_amount': 4500.0, 'top5_amount': 1000.0,
        'amount_concentration_pct': 22.222222,
    }]
    tc._append_rows(rows, tc.history_file, TradingCrowding.CSV_COLUMNS)
    df = tc.load_history(force=True)
    assert len(df) == 1
    assert df.iloc[0]['industry'] == '行业A'
    assert abs(df.iloc[0]['vol_concentration_pct'] - 32.258064) < 1e-5
    assert abs(df.iloc[0]['amount_concentration_pct'] - 22.222222) < 1e-5


def _write_history(tmp_path, ind_rows, idx_rows):
    tc = TradingCrowding()
    tc.cache_dir = str(tmp_path)
    tc.history_file = os.path.join(str(tmp_path), 'trading_crowding_history.csv')
    tc.index_history_file = os.path.join(
        str(tmp_path), 'trading_crowding_index_history.csv')
    tc._append_rows(ind_rows, tc.history_file, TradingCrowding.CSV_COLUMNS)
    tc._append_rows(idx_rows, tc.index_history_file,
                    TradingCrowding.INDEX_CSV_COLUMNS)
    return tc


def test_precompute_shapes(tmp_path):
    tmp_path = os.path.join(str(tmp_path), 'precompute')
    os.makedirs(tmp_path, exist_ok=True)
    ind_rows = []
    idx_rows = []
    for d in ('20260101', '20260102'):
        ind_rows.append({
            'trade_date': d, 'industry': '行业A', 'stock_count': 6,
            'total_vol': 310.0, 'top5_vol': 100.0,
            'vol_concentration_pct': 32.0, 'total_amount': 4500.0,
            'top5_amount': 1000.0, 'amount_concentration_pct': 22.0,
        })
        idx_rows.append({
            'trade_date': d, 'index_code': 'IDX', 'index_name': '测试指数',
            'stock_count': 6, 'coverage': 100.0,
            'total_vol': 310.0, 'top5_vol': 100.0,
            'vol_concentration_pct': 32.0, 'total_amount': 4500.0,
            'top5_amount': 1000.0, 'amount_concentration_pct': 22.0,
        })
    tc = _write_history(tmp_path, ind_rows, idx_rows)

    pre = tc.precompute()
    assert pre['latest_date'] is not None
    assert len(pre['latest_df']) == 1
    assert set(pre['by_industry'].keys()) == {'行业A'}
    assert 'vol_concentration_pct' in pre['by_industry']['行业A'].columns
    assert 'amount_concentration_pct' in pre['by_industry']['行业A'].columns

    pre_idx = tc.precompute_indices()
    assert set(pre_idx.keys()) == {'IDX'}
    name, sdf = pre_idx['IDX']
    assert name == '测试指数'
    assert len(sdf) == 2


def test_cache_key_uses_file_path(tmp_path):
    """行业/指数两个 CSV 同 mtime 时，缓存键必须区分文件路径，
    否则 load_index_history() 会错返回行业表（缺 index_code 列）。"""
    tmp_path = os.path.join(str(tmp_path), 'cachekey')
    os.makedirs(tmp_path, exist_ok=True)
    ind_rows = [{
        'trade_date': '20260101', 'industry': '行业A', 'stock_count': 6,
        'total_vol': 310.0, 'top5_vol': 100.0,
        'vol_concentration_pct': 32.0, 'total_amount': 4500.0,
        'top5_amount': 1000.0, 'amount_concentration_pct': 22.0,
    }]
    idx_rows = [{
        'trade_date': '20260101', 'index_code': 'IDX',
        'index_name': '测试指数', 'stock_count': 6, 'coverage': 100.0,
        'total_vol': 310.0, 'top5_vol': 100.0,
        'vol_concentration_pct': 32.0, 'total_amount': 4500.0,
        'top5_amount': 1000.0, 'amount_concentration_pct': 22.0,
    }]
    tc = TradingCrowding()
    tc.cache_dir = tmp_path
    tc.history_file = os.path.join(tmp_path, 'trading_crowding_history.csv')
    tc.index_history_file = os.path.join(
        tmp_path, 'trading_crowding_index_history.csv')
    tc._append_rows(ind_rows, tc.history_file, TradingCrowding.CSV_COLUMNS)
    tc._append_rows(idx_rows, tc.index_history_file,
                    TradingCrowding.INDEX_CSV_COLUMNS)
    # 模拟同一批写入：两个文件完全相同 mtime
    same_mtime = 1786182811.1040409
    os.utime(tc.history_file, (same_mtime, same_mtime))
    os.utime(tc.index_history_file, (same_mtime, same_mtime))
    from utils.sector_crowding import SectorCrowding
    SectorCrowding._PROCESS_HISTORY_CACHE.clear()

    ind_df = tc.load_history()
    idx_df = tc.load_index_history()
    assert 'industry' in ind_df.columns
    assert 'index_code' in idx_df.columns
    assert idx_df.iloc[0]['index_code'] == 'IDX'
    # precompute_indices 不应再抛 KeyError
    pre_idx = tc.precompute_indices()
    assert set(pre_idx.keys()) == {'IDX'}


def test_build_history_retries_calendar(tmp_path):
    """trade_cal 前两次抛错（DNS 抖动）时，build_history 应重试并成功。"""
    tmp_path = os.path.join(str(tmp_path), 'retry')
    os.makedirs(tmp_path, exist_ok=True)
    tc = TradingCrowding()
    tc.cache_dir = tmp_path
    tc.history_file = os.path.join(tmp_path, 'trading_crowding_history.csv')
    tc.index_history_file = os.path.join(
        tmp_path, 'trading_crowding_index_history.csv')

    pro = MagicMock()
    calls = {'n': 0}

    def fake_trade_cal(**kwargs):
        calls['n'] += 1
        if calls['n'] <= 2:
            raise ConnectionError('DNS failure')
        return pd.DataFrame({'cal_date': ['20260101', '20260102']})

    pro.trade_cal = fake_trade_cal
    tc._get_pro = lambda: pro
    tc.fetch_day = lambda d: (
        pd.DataFrame(columns=TradingCrowding.CSV_COLUMNS),
        pd.DataFrame(columns=TradingCrowding.INDEX_CSV_COLUMNS),
    )

    added = tc.build_history(max_retries=3, retry_delay=0.01)
    assert calls['n'] == 3
    assert added == 2
