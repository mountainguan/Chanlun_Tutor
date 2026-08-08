"""
为成交集中度历史补拉「全A」市场维度行
======================================
历史构建期间尚未包含全A（ALL）行时，用本脚本对已缓存的每个交易日
补拉一次 pro.daily 并追加全A聚合行到
data/trading_crowding/trading_crowding_index_history.csv。

幂等：已有全A行的日期自动跳过，可安全重复执行。

用法：
    python scripts/backfill_trading_crowding_market.py
"""

import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.trading_crowding import TradingCrowding


def main():
    tc = TradingCrowding()
    idx = tc.load_index_history()
    if idx.empty:
        print('暂无指数历史，请先运行 scripts/build_trading_crowding_history.py')
        return

    date_str = idx['trade_date'].dt.strftime('%Y%m%d')
    all_dates = sorted(date_str.unique().tolist())
    have_all = set(
        date_str[idx['index_code'] == 'ALL'].unique().tolist())
    todo = [d for d in all_dates if d not in have_all]
    if not todo:
        print(f'全A行已齐全（{len(all_dates)} 个交易日），无需补拉')
        return

    print(f'共 {len(all_dates)} 个交易日，需要补拉全A行 {len(todo)} 天：'
          f'{todo[0]} ~ {todo[-1]}')
    t0 = datetime.datetime.now()
    rows = []
    done = 0
    for i, d in enumerate(todo, 1):
        m = tc.fetch_market(d)
        if not m.empty:
            m['trade_date'] = d
            rows.append(m.iloc[0].to_dict())
        done += 1
        if len(rows) >= 20:
            tc._append_rows(rows, tc.index_history_file,
                            TradingCrowding.INDEX_CSV_COLUMNS)
            rows = []
        if done % 20 == 0 or done == len(todo):
            eta_sec = ((datetime.datetime.now() - t0).total_seconds()
                       / done * (len(todo) - done))
            print(f'  进度 {done}/{len(todo)} ({d}) '
                  f'预计剩余 {eta_sec/60:.1f} 分钟')
    if rows:
        tc._append_rows(rows, tc.index_history_file,
                        TradingCrowding.INDEX_CSV_COLUMNS)
    dt = (datetime.datetime.now() - t0).total_seconds()
    print(f'完成：补拉 {done} 天全A行，耗时 {dt/60:.1f} 分钟')


if __name__ == '__main__':
    main()
