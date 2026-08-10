#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
刷新某一天的拥挤度数据（覆盖式）。

用法：
    python scripts/refresh_crowding_one_day.py --date 20260807

逻辑：
    1) 删除两份 CSV（sector_crowding + trading_crowding 三张表）中该日期的所有行；
    2) 调用 SectorCrowding.fetch_day / TradingCrowding.fetch_day 重新拉取该日；
    3) 把新行 append 到 CSV；
    4) 失效 + 重建派生缓存 pkl；
    5) 更新 meta.json。
"""

import argparse
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from utils.sector_crowding import SectorCrowding
from utils.trading_crowding import TradingCrowding


def drop_date_from_csv(path: str, date_str: str) -> int:
    """从 CSV 物理删除指定日期的行（保留 header + 列顺序），返回删除条数。"""
    if not os.path.exists(path):
        return 0
    df = pd.read_csv(path, dtype={'trade_date': str})
    n_before = len(df)
    df = df[df['trade_date'] != date_str].reset_index(drop=True)
    n_removed = n_before - len(df)
    if n_removed:
        df.to_csv(path, index=False, encoding='utf-8-sig')
    return n_removed


def main():
    parser = argparse.ArgumentParser(description='刷新某一天的拥挤度数据（覆盖式）')
    parser.add_argument('--date', required=True, help='YYYYMMDD，如 20260807')
    args = parser.parse_args()
    target = args.date.strip()

    # ---------- 1. 删除旧行 ----------
    sec_csv = SectorCrowding.__init__.__qualname__  # placeholder; we use real path below
    sc = SectorCrowding()
    tc = TradingCrowding()

    print(f'[{target}] 删除旧行...')
    sec_removed = drop_date_from_csv(sc.history_file, target)
    idx_removed = drop_date_from_csv(tc.index_history_file, target)
    ind_removed = drop_date_from_csv(tc.history_file, target)
    ext_removed = drop_date_from_csv(tc.extreme_file, target)
    print(f'  sector_crowding_history.csv: - {sec_removed} 行')
    print(f'  trading_crowding_history.csv: - {ind_removed} 行')
    print(f'  trading_crowding_index_history.csv: - {idx_removed} 行')
    print(f'  trading_crowding_extreme_history.csv: - {ext_removed} 行')

    # ---------- 2. 失效缓存 ----------
    sc.invalidate_history_cache()
    tc.invalidate_history_cache()

    # ---------- 3. 重拉 sector_crowding ----------
    print(f'\n[{target}] 重拉 sector_crowding（margin_detail + daily_basic）...')
    t0 = datetime.datetime.now()
    sec_df = sc.fetch_day(target)
    if sec_df.empty:
        print('  ❌ sector_crowding 拉取为空（margin_detail 仍无数据？）')
    else:
        sec_df['trade_date'] = target
        rows = sec_df.to_dict('records')
        sc._append_rows(rows)
        dt = (datetime.datetime.now() - t0).total_seconds()
        margin_total = sec_df['rzrqye'].sum() / 1e12
        mv_total = sec_df['total_mv'].sum() / 1e12
        margin_stocks = int(sec_df['margin_stock_count'].sum())
        print(f'  ✅ 写入 {len(rows)} 行，耗时 {dt:.1f}s')
        print(f'     两融余额总和={margin_total:.3f}万亿，'
              f'市值总和={mv_total:.3f}万亿，'
              f'两融标的数={margin_stocks}')

    # ---------- 4. 重拉 trading_crowding ----------
    print(f'\n[{target}] 重拉 trading_crowding（daily + 指数成分 + 涨跌幅榜）...')
    t0 = datetime.datetime.now()
    ind_df, idx_df, ext_df = tc.fetch_day(target)
    if not ind_df.empty:
        ind_df['trade_date'] = target
        tc._append_rows(ind_df.to_dict('records'), tc.history_file,
                        tc.CSV_COLUMNS)
    if not idx_df.empty:
        idx_df['trade_date'] = target
        tc._append_rows(idx_df.to_dict('records'), tc.index_history_file,
                        tc.INDEX_CSV_COLUMNS)
    if not ext_df.empty:
        ext_df['trade_date'] = target
        tc._append_rows(ext_df.to_dict('records'), tc.extreme_file,
                        tc.EXTREME_CSV_COLUMNS)
    dt = (datetime.datetime.now() - t0).total_seconds()
    print(f'  ✅ 行业 {len(ind_df)} 行，指数 {len(idx_df)} 行，'
          f'极端榜 {len(ext_df)} 行，耗时 {dt:.1f}s')

    # ---------- 5. 重建派生缓存 + meta ----------
    print(f'\n[{target}] 重建 sector_crowding 派生缓存（precompute）...')
    t0 = datetime.datetime.now()
    sc.invalidate_history_cache()
    pre = sc.precompute()
    pre_idx = sc.precompute_all_indices()
    print(f'  ✅ 派生缓存就绪：{len(pre.get("by_industry", {}))} 行业，'
          f'{len(pre_idx)} 指数，'
          f'耗时 {(datetime.datetime.now()-t0).total_seconds():.2f}s')

    print(f'\n[{target}] 重建 trading_crowding 派生缓存...')
    t0 = datetime.datetime.now()
    tc.invalidate_history_cache()
    tc.precompute()
    print(f'  ✅ 派生缓存完成，耗时 {(datetime.datetime.now()-t0).total_seconds():.2f}s')

    # ---------- 6. 更新 meta.json ----------
    latest_in_csv = pd.read_csv(sc.history_file, dtype={'trade_date': str})
    latest_date = latest_in_csv['trade_date'].max()
    sc._save_meta(
        start_date=latest_in_csv['trade_date'].min(),
        end_date=latest_in_csv['trade_date'].max(),
        latest_date=latest_date,
        total_days=latest_in_csv['trade_date'].nunique(),
    )
    print(f'\n  meta.latest_date = {latest_date}')

    print(f'\n[{target}] ✅ 刷新完成')


if __name__ == '__main__':
    main()