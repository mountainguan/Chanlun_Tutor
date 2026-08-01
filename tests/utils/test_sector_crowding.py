"""板块拥挤度聚合逻辑单元测试（纯函数，不联网）。"""

import pandas as pd

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
