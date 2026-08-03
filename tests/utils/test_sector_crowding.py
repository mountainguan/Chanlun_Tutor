"""板块拥挤度聚合逻辑单元测试（纯函数，不联网）。"""

import os

import pandas as pd
import numpy as np

from utils.sector_crowding import SectorCrowding


def test_aggregate_basic():
    # 行业A：3 只股票，其中 2 只有两融；行业B：1 只股票无两融
    margin_df = pd.DataFrame({
        'ts_code': ['000001.SZ', '000002.SZ'],
        'rzye': [1.0e9, 2.0e9],
        'rqye': [1.0e8, 2.0e8],
        'rzrqye': [1.1e9, 2.2e9],
    })
    daily_basic_df = pd.DataFrame({
        'ts_code': ['000001.SZ', '000002.SZ', '000003.SZ', '600001.SH'],
        'close': [10.0, 20.0, 30.0, 40.0],
        # 总市值单位：万元（Tushare 口径）
        'total_mv': [100.0, 200.0, 300.0, 400.0],
    })
    industry_map = {
        '000001.SZ': '行业A',
        '000002.SZ': '行业A',
        '000003.SZ': '行业A',
        '600001.SH': '行业B',
    }

    df = SectorCrowding.aggregate_day(margin_df, daily_basic_df, industry_map)

    assert len(df) == 2
    row_a = df[df['industry'] == '行业A'].iloc[0]
    row_b = df[df['industry'] == '行业B'].iloc[0]

    # 行业A：总市值 = (100+200+300) 万元 = 6e6 元；两融 = 3.3e9 元
    assert row_a['total_mv'] == 6.0e6
    assert row_a['rzrqye'] == 3.3e9
    assert row_a['stock_count'] == 3
    assert row_a['margin_stock_count'] == 2
    assert abs(row_a['crowding_pct'] - 3.3e9 / 6.0e6 * 100) < 1e-9

    # 行业B：无两融数据，拥挤度为 0
    assert row_b['rzrqye'] == 0.0
    assert row_b['crowding_pct'] == 0.0
    assert row_b['stock_count'] == 1
    assert row_b['margin_stock_count'] == 0


def test_aggregate_unknown_industry_dropped():
    margin_df = pd.DataFrame({
        'ts_code': ['999999.SZ'],
        'rzye': [1.0e9],
        'rqye': [0.0],
        'rzrqye': [1.0e9],
    })
    daily_basic_df = pd.DataFrame({
        'ts_code': ['000001.SZ'],
        'close': [10.0],
        'total_mv': [100.0],
    })
    df = SectorCrowding.aggregate_day(margin_df, daily_basic_df, {'000001.SZ': '行业A'})
    assert len(df) == 1
    assert df.iloc[0]['rzrqye'] == 0.0


def test_aggregate_empty_inputs():
    empty = pd.DataFrame()
    df = SectorCrowding.aggregate_day(empty, empty, {})
    assert df.empty

    df2 = SectorCrowding.aggregate_day(None, None, {})
    assert df2.empty


def test_percentile_rank():
    values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    assert SectorCrowding.percentile_rank(values, 5.0) == 50.0
    assert SectorCrowding.percentile_rank(values, 10.0) == 100.0
    assert SectorCrowding.percentile_rank(values, 1.0) == 10.0
    # 样本太少返回 None
    assert SectorCrowding.percentile_rank([1.0, 2.0], 1.5) is None
    assert SectorCrowding.percentile_rank(values, None) is None


def _speed_history_df():
    """25 个交易日的两行业序列：
    行业A：两融按日 1% 复利增长、市值不变 -> 升温；
    行业B：两融不变、市值按日 0.5% 复利增长 -> 降温。
    """
    n = 25
    dates = pd.bdate_range('2023-08-01', periods=n)
    rows = []
    for t, d in enumerate(dates):
        rows.append({
            'trade_date': d, 'industry': '行业A',
            'stock_count': 100, 'margin_stock_count': 80,
            'total_mv': 1e12,
            'rzye': 0.98e10 * (1.01 ** t),
            'rqye': 0.02e10 * (1.01 ** t),
            'rzrqye': 1e10 * (1.01 ** t),
            'crowding_pct': 1e10 * (1.01 ** t) / 1e12 * 100,
            'financing_pct': 0.98e10 * (1.01 ** t) / 1e12 * 100,
            'short_pct': 0.02e10 * (1.01 ** t) / 1e12 * 100,
        })
        rows.append({
            'trade_date': d, 'industry': '行业B',
            'stock_count': 100, 'margin_stock_count': 80,
            'total_mv': 1e12 * (1.005 ** t),
            'rzye': 0.98e10,
            'rqye': 0.02e10,
            'rzrqye': 1e10,
            'crowding_pct': 1e10 / (1e12 * (1.005 ** t)) * 100,
            'financing_pct': 0.98e10 / (1e12 * (1.005 ** t)) * 100,
            'short_pct': 0.02e10 / (1e12 * (1.005 ** t)) * 100,
        })
    return pd.DataFrame(rows), dates


def test_margin_speed_windows():
    """两融/市值变化：窗口齐全、增量比与拥挤度变化口径正确、日期对齐。"""
    fake, dates = _speed_history_df()
    out = SectorCrowding().compute_margin_speed(df=fake)

    assert set(out.keys()) == {3, 5, 10, 15, 20}
    n = len(dates)
    a_crowd_last = 1e10 * (1.01 ** (n - 1)) / 1e12 * 100
    b_crowd_last = 1e10 / (1e12 * (1.005 ** (n - 1))) * 100
    for w in (3, 5, 10, 15, 20):
        dfw = out[w]
        assert set(dfw.index) == {'行业A', '行业B'}
        a = dfw.loc['行业A']
        b = dfw.loc['行业B']
        # 日期对齐：最新日 = 序列最后一天，起点 = N 个交易日前
        assert a['trade_date'] == dates[-1]
        assert a['prev_date'] == dates[n - 1 - w]
        # 行业A：两融按日 1% 复利，市值不变
        assert abs(a['rzrqye_pct'] - ((1.01 ** w) - 1) * 100) < 1e-9
        assert abs(a['total_mv_pct']) < 1e-9
        # 市值不变 -> 增量比 = +inf（两融增加）；拥挤度上升
        assert np.isposinf(a['delta_ratio'])
        assert abs(a['crowding_chg'] - (a_crowd_last - 1e10 * (1.01 ** (n - 1 - w)) / 1e12 * 100)) < 1e-9
        # 行业B：两融不变，市值按日 0.5% 复利
        assert abs(b['rzrqye_pct']) < 1e-9
        assert abs(b['total_mv_pct'] - ((1.005 ** w) - 1) * 100) < 1e-9
        # 两融不变 -> 增量比 = 0；市值扩张 -> 拥挤度下降
        assert abs(b['delta_ratio']) < 1e-12
        assert abs(b['crowding_chg'] - (b_crowd_last - 1e10 / (1e12 * (1.005 ** (n - 1 - w))) * 100)) < 1e-9
        assert b['crowding_chg'] < 0
        # 变化额绝对值（元）
        assert abs(a['rzrqye_chg'] - 1e10 * ((1.01 ** (n - 1)) - (1.01 ** (n - 1 - w)))) < 1.0
        assert abs(b['total_mv_chg'] - 1e12 * ((1.005 ** (n - 1)) - (1.005 ** (n - 1 - w)))) < 1.0
        assert abs(a['rzrqye_now'] - 1e10 * (1.01 ** (n - 1))) < 1.0
        assert abs(b['total_mv_now'] - 1e12 * (1.005 ** (n - 1))) < 1.0


def test_margin_speed_empty():
    """空历史：每个窗口都返回空 DataFrame。"""
    empty = pd.DataFrame(columns=SectorCrowding.CSV_COLUMNS)
    out = SectorCrowding().compute_margin_speed(df=empty)
    assert set(out.keys()) == {3, 5, 10, 15, 20}
    for w in (3, 5, 10, 15, 20):
        assert out[w].empty


def _fake_history_df():
    dates = pd.to_datetime(['2023-08-01', '2023-08-02', '2023-08-03'])
    rows = []
    for d in dates:
        for ind, mv, rz in (('行业A', 1e12, 4e10), ('行业B', 1.5e13, 5e10)):
            rows.append({
                'trade_date': d, 'industry': ind,
                'stock_count': 100, 'margin_stock_count': 80,
                'total_mv': mv, 'rzye': rz * 0.98, 'rqye': rz * 0.02,
                'rzrqye': rz,
                'crowding_pct': rz / mv * 100,
                'financing_pct': rz * 0.98 / mv * 100,
                'short_pct': rz * 0.02 / mv * 100,
            })
    return pd.DataFrame(rows)


def _redirect_sc(sc, cache_dir):
    """把 SectorCrowding 的缓存目录指向临时目录（避免碰真实数据）。"""
    os.makedirs(cache_dir, exist_ok=True)
    sc.cache_dir = str(cache_dir)
    sc.history_file = os.path.join(str(cache_dir), 'sector_crowding_history.csv')
    sc.meta_file = os.path.join(str(cache_dir), 'meta.json')
    sc.derived_file = os.path.join(str(cache_dir), 'sector_crowding_derived.pkl')


def test_derived_cache_roundtrip(tmp_path):
    """派生缓存：计算一次落盘后，新实例能直接从磁盘还原出相同结果。"""
    sc = SectorCrowding()
    _redirect_sc(sc, tmp_path)
    _fake_history_df().to_csv(sc.history_file, index=False,
                              encoding='utf-8-sig')
    SectorCrowding._PROCESS_DERIVED_CACHE.clear()

    pre1 = sc.precompute()
    assert os.path.exists(sc.derived_file)

    # 新实例 + 清进程缓存 -> 必须走磁盘缓存路径
    SectorCrowding._PROCESS_DERIVED_CACHE.clear()
    sc2 = SectorCrowding()
    _redirect_sc(sc2, tmp_path)
    pre2 = sc2.precompute()
    pre_idx2 = sc2.precompute_all_indices()

    assert list(pre2['by_industry'].keys()) == list(pre1['by_industry'].keys())
    pd.testing.assert_frame_equal(
        pre1['latest_df'], pre2['latest_df'], check_dtype=False)
    pd.testing.assert_series_equal(
        pre1['prev_df']['crowding_pct'], pre2['prev_df']['crowding_pct'],
        check_dtype=False, check_index=False, check_names=False)
    for ind in pre1['by_industry']:
        pd.testing.assert_frame_equal(
            pre1['by_industry'][ind], pre2['by_industry'][ind],
            check_dtype=False)
    # 两融速度：每个窗口的 DataFrame 应完全一致
    assert set(pre2['margin_speed'].keys()) == set(pre1['margin_speed'].keys())
    for w in pre1['margin_speed']:
        pd.testing.assert_frame_equal(
            pre1['margin_speed'][w], pre2['margin_speed'][w],
            check_dtype=False)
    # 指数依赖真实成分股缓存文件，未配置时为 {}，同样应一致
    assert set(pre_idx2.keys()) == set()
